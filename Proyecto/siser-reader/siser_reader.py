#!/usr/bin/env python3
"""
SISER Protocol Reader for Riello H.P.6065REL-D inverter (3 MPPT).
Reads data via Phoenixtec SISER binary protocol over RS232 (CH340 adapter)
and writes measurements to TimescaleDB for Grafana visualization.

Protocol details (reverse-engineered from SunVision SISERBus.java):
  - STX byte (0x02) sent before each command frame
  - RTS=True before TX, RTS=False after TX (opto-isolated RS232)
  - DTR=True always (powers opto-coupler RX circuit)
  - 600ms delay before each command
  - Frame: AA AA 01 00 00 [addr] [group] [cmd] [dlen] [data...] [chkH] [chkL]
  - Checksum: additive sum of all bytes except last 2, big-endian

readMichele triphase data offsets (from SISERBus.java):
  resp[9:10]   SYSTEMTEMP       /10  -> C
  resp[11:12]  OUTPUTVOLTAGE    /10  -> PV V MPPT1
  resp[13:14]  OUTPUTVOLTAGE2   /10  -> PV V MPPT2
  resp[15:16]  OUTPUTVOLTAGE3   /10  -> PV V MPPT3
  resp[17:18]  OUTPUTCURRENT    /10  -> PV I MPPT1
  resp[19:20]  OUTPUTCURRENT2   /10  -> PV I MPPT2
  resp[21:22]  OUTPUTCURRENT3   /10  -> PV I MPPT3
  resp[23:24]  CURRENTTOGRID    /10  -> Grid I L1
  resp[25:26]  CURRENTTOGRID2   /10  -> Grid I L2
  resp[27:28]  CURRENTTOGRID3   /10  -> Grid I L3
  resp[29:30]  INPUTVOLTAGE     /10  -> Grid V L1
  resp[31:32]  INPUTVOLTAGE2    /10  -> Grid V L2
  resp[33:34]  INPUTVOLTAGE3    /10  -> Grid V L3
  resp[35:36]  INPUTFREQUENCY   /100 -> Hz
  resp[37:38]  OUTPUTLOAD       /10  -> Power L1
  resp[39:40]  OUTPUTLOAD2       /10  -> Power L2
  resp[41:42]  OUTPUTLOAD3       /10  -> Power L3
  resp[49:52]  BATTERYESTCHARG        -> Total Energy (Wh, 32-bit)
  resp[53:56]  BATTERYESTTIME         -> Total Hours
  resp[58]     STATUSCODE              -> 0=wait, 1=normal, 2=fault, 3=perm fault

  0xFFFF = not connected / invalid value
"""
import serial
import time
import sys
import os
import psycopg2
import logging
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger('siser-reader')

SERIAL_PORT = os.environ.get('SERIAL_PORT', '/dev/inverter-serial')
try:
    BAUD = int(os.environ.get('BAUDRATE', '9600'))
except ValueError:
    BAUD = 9600
    log.warning(f"Invalid BAUDRATE env var, using default {BAUD}")
try:
    INVERTER_ADDR = int(os.environ.get('INVERTER_ADDR', '33'))
except ValueError:
    INVERTER_ADDR = 33
    log.warning(f"Invalid INVERTER_ADDR env var, using default {INVERTER_ADDR}")
try:
    POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', '5'))
    if POLL_INTERVAL < 1:
        log.warning(f"POLL_INTERVAL={POLL_INTERVAL} too low, using 5")
        POLL_INTERVAL = 5
except ValueError:
    POLL_INTERVAL = 5
    log.warning(f"Invalid POLL_INTERVAL env var, using default {POLL_INTERVAL}")
DB_HOST = os.environ.get('DB_HOST', 'timescaledb')
try:
    DB_PORT = int(os.environ.get('DB_PORT', '5432'))
except ValueError:
    DB_PORT = 5432
    log.warning(f"Invalid DB_PORT env var, using default {DB_PORT}")
DB_NAME = os.environ.get('DB_NAME', 'solar_monitor')
DB_USER = os.environ.get('DB_USER', 'solar')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'solar')

INVALID = 0xFFFF

def siser_checksum(frame):
    cs = sum(frame[:-2]) & 0xFFFF
    frame[-2] = (cs >> 8) & 0xFF
    frame[-1] = cs & 0xFF
    return frame

def siser_verify_checksum(resp):
    if len(resp) < 3:
        return False
    cs = sum(resp[:-2]) & 0xFFFF
    return (cs >> 8) & 0xFF == resp[-2] and cs & 0xFF == resp[-1]

def word(resp, h_off):
    if h_off + 1 >= len(resp):
        return INVALID
    return resp[h_off] * 256 + resp[h_off + 1]

def dword(resp, h_off):
    return (word(resp, h_off) << 16) + word(resp, h_off + 2)

class SISERReader:
    def __init__(self):
        self.ser = None
        self.conn = None
        self.serial_number = None
        self.registered = False
        self.consecutive_failures = 0
        self.max_failures = 10

    def connect_db(self):
        for attempt in range(5):
            try:
                self.conn = psycopg2.connect(
                    host=DB_HOST, port=DB_PORT,
                    dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
                    keepalives=1, keepalives_idle=60,
                    keepalives_interval=10, keepalives_count=3
                )
                self.conn.autocommit = True
                self._ensure_schema()
                log.info(f"Connected to TimescaleDB at {DB_HOST}:{DB_PORT}/{DB_NAME}")
                return True
            except Exception as e:
                log.warning(f"DB connection attempt {attempt+1} failed: {e}")
                time.sleep(5)
        log.error("Failed to connect to TimescaleDB after 5 attempts")
        return False

    def _ensure_schema(self):
        alter_sqls = [
            "ALTER TABLE realtime ADD COLUMN IF NOT EXISTS vpv1 real",
            "ALTER TABLE realtime ADD COLUMN IF NOT EXISTS ipv1 real",
            "ALTER TABLE realtime ADD COLUMN IF NOT EXISTS ppv1 real",
            "ALTER TABLE realtime ADD COLUMN IF NOT EXISTS ppv2 real",
            "ALTER TABLE realtime ADD COLUMN IF NOT EXISTS ppv3 real",
            "ALTER TABLE realtime ADD COLUMN IF NOT EXISTS ppv_total real",
            "ALTER TABLE realtime ADD COLUMN IF NOT EXISTS is_stale boolean DEFAULT false",
        ]
        for sql in alter_sqls:
            with self.conn.cursor() as cur:
                cur.execute(sql)

    def db_insert(self, table, columns_values):
        if not self.conn:
            return False
        ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S%z')
        cols = ['time', 'inverter_id'] + list(columns_values.keys())
        vals = [ts, 1] + list(columns_values.values())
        placeholders = ', '.join(['%s'] * len(vals))
        col_names = ', '.join(cols)
        sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, vals)
            return True
        except Exception as e:
            log.error(f"DB insert error: {e}")
            try:
                self.conn.close()
            except:
                pass
            self.conn = None
            return False

    def db_insert_heartbeat(self):
        if not self.conn:
            return False
        ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S%z')
        sql = "INSERT INTO realtime (time, inverter_id, status, is_stale) VALUES (%s, %s, %s, %s)"
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, [ts, 1, 0, True])
            log.info("Heartbeat row inserted (inverter offline)")
            return True
        except Exception as e:
            log.error(f"DB heartbeat insert error: {e}")
            try:
                self.conn.close()
            except:
                pass
            self.conn = None
            return False

    def open_serial(self):
        try:
            self.ser = serial.Serial(SERIAL_PORT, BAUD, bytesize=8, parity='N', stopbits=1, timeout=5)
            self.ser.setDTR(True)
            self.ser.setRTS(False)
            time.sleep(2.0)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            log.info(f"Opened {SERIAL_PORT} at {BAUD} baud, DTR=True")
            return True
        except Exception as e:
            log.error(f"Failed to open serial port: {e}")
            return False

    def send_siser(self, frame, timeout=5.0):
        if not self.ser:
            return None
        time.sleep(0.6)
        self.ser.setRTS(True)
        time.sleep(0.01)
        self.ser.reset_input_buffer()
        self.ser.write(bytes([0x02]))
        time.sleep(0.01)
        self.ser.write(bytes(frame))
        time.sleep(0.05)
        self.ser.setRTS(False)

        old_timeout = self.ser.timeout
        self.ser.timeout = 0.02
        resp = bytearray()
        start = time.time()
        while time.time() - start < timeout:
            chunk = self.ser.read(512)
            if chunk:
                resp.extend(chunk)
            elif resp:
                time.sleep(0.05)
                chunk = self.ser.read(512)
                if chunk:
                    resp.extend(chunk)
                break
        self.ser.timeout = old_timeout

        if resp:
            while len(resp) > 0 and resp[0] == 0x02:
                resp = resp[1:]
        return bytes(resp) if resp else None

    def offline_enquiry(self):
        frame = bytearray([0xAA, 0xAA, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        siser_checksum(frame)
        resp = self.send_siser(frame, timeout=3.0)
        if resp and len(resp) >= 19 and resp[0] == 0xAA and resp[1] == 0xAA:
            if not siser_verify_checksum(resp):
                log.warning("offlineEnquiry: checksum mismatch, discarding")
                return False
            dlen = resp[8]
            if dlen >= 10:
                serial_data = resp[9:9+10]
                serial_str = serial_data.decode('ascii', errors='replace').rstrip('\x00')
                self.serial_number = serial_data
                log.info(f"offlineEnquiry: serial={serial_str}")
                return True
        return False

    def send_address(self):
        if not self.serial_number:
            return False
        frame = bytearray(22)
        frame[0] = 0xAA; frame[1] = 0xAA; frame[2] = 0x01
        frame[3] = 0x00; frame[4] = 0x00
        frame[5] = 0x00; frame[6] = 0x00; frame[7] = 0x01; frame[8] = 11
        for i in range(10):
            frame[9+i] = self.serial_number[i]
        frame[19] = INVERTER_ADDR
        siser_checksum(frame)
        resp = self.send_siser(frame, timeout=3.0)
        if resp and len(resp) >= 10 and resp[7] == 0x81:
            code = resp[9] if len(resp) > 9 else -1
            if code == 6:
                log.info(f"sendAddress: OK (addr={INVERTER_ADDR})")
                self.registered = True
                return True
            else:
                log.warning(f"sendAddress: code={code} (expected 6)")
        return False

    def read_michele(self):
        frame = bytearray([0xAA, 0xAA, 0x01, 0x00, 0x00, INVERTER_ADDR, 0x01, 0x10, 0x00, 0x00, 0x00])
        siser_checksum(frame)
        resp = self.send_siser(frame, timeout=3.0)
        if not resp or len(resp) < 60 or resp[0] != 0xAA or resp[1] != 0xAA:
            return None
        if not siser_verify_checksum(resp):
            log.warning("readMichele: checksum mismatch, discarding")
            return None

        def w(h_off):
            v = word(resp, h_off)
            return None if v >= INVALID else v

        def div(val, divisor):
            return (val / divisor) if val is not None else None

        temp = w(9)
        pv_v1 = w(11); pv_v2 = w(13); pv_v3 = w(15)
        pv_i1 = w(17); pv_i2 = w(19); pv_i3 = w(21)
        grid_i1 = w(23); grid_i2 = w(25); grid_i3 = w(27)
        grid_v1 = w(29); grid_v2 = w(31); grid_v3 = w(33)
        grid_freq = w(35)
        power1 = w(37); power2 = w(39); power3 = w(41)
        status_code = resp[58] if len(resp) > 58 else None

        total_energy = None
        if len(resp) >= 53:
            te = dword(resp, 49)
            if te != 0xFFFFFFFF and te != 0:
                total_energy = te

        total_hours = None
        if len(resp) >= 57:
            th = dword(resp, 53)
            if th != 0xFFFFFFFF and th != 0:
                total_hours = th

        pv1 = div(pv_v1, 10)
        pv2 = div(pv_v2, 10)
        pv3 = div(pv_v3, 10)
        pi1 = div(pv_i1, 10)
        pi2 = div(pv_i2, 10)
        pi3 = div(pv_i3, 10)

        ppv1 = round(pv1 * pi1, 1) if pv1 is not None and pi1 is not None else None
        ppv2 = round(pv2 * pi2, 1) if pv2 is not None and pi2 is not None else None
        ppv3 = round(pv3 * pi3, 1) if pv3 is not None and pi3 is not None else None

        ppv_vals = [ppv1, ppv2, ppv3]
        ppv_total = round(sum(v for v in ppv_vals if v is not None), 1) if any(v is not None for v in ppv_vals) else None

        vac1 = div(grid_v1, 10)
        iac1 = div(grid_i1, 10)
        vac2_val = div(grid_v2, 10)
        iac2_val = div(grid_i2, 10)
        vac3_val = div(grid_v3, 10)
        iac3_val = div(grid_i3, 10)

        pac_calc = round(vac1 * iac1, 1) if vac1 is not None and iac1 is not None else None
        pac2_calc = round(vac2_val * iac2_val, 1) if vac2_val is not None and iac2_val is not None else None
        pac3_calc = round(vac3_val * iac3_val, 1) if vac3_val is not None and iac3_val is not None else None

        data = {
            'temp': div(temp, 10),
            'vpv1': pv1,
            'vpv2': pv2,
            'vpv3': pv3,
            'ipv1': pi1,
            'ipv2': pi2,
            'ipv3': pi3,
            'ppv1': ppv1,
            'ppv2': ppv2,
            'ppv3': ppv3,
            'ppv_total': ppv_total,
            'vpv': next((v for v in [pv1, pv2, pv3] if v is not None), None),
            'ipv': next((v for v in [pi1, pi2, pi3] if v is not None), None),
            'vac': vac1,
            'iac': iac1,
            'pac': pac_calc,
            'vac2': vac2_val,
            'vac3': vac3_val,
            'iac2': iac2_val,
            'iac3': iac3_val,
            'pac2': pac2_calc,
            'pac3': pac3_calc,
            'fac': div(grid_freq, 100),
            'status': status_code,
            'grid_status': 1 if status_code == 1 else 0,
            'energy_total': total_energy,
            'hours_total': total_hours,
        }

        return data

    def do_handshake(self):
        self.ser.setDTR(False)
        time.sleep(1.0)
        self.ser.setDTR(True)
        time.sleep(1.0)
        self.ser.reset_input_buffer()

        # Try reading directly first (inverter may already be registered)
        log.info("Trying direct read (skip handshake)...")
        data = self.read_michele()
        if data:
            log.info("Direct read succeeded, inverter already registered")
            self.registered = True
            return True

        # Full handshake needed
        for attempt in range(3):
            log.info(f"Handshake attempt {attempt+1}/3")
            if self.offline_enquiry():
                time.sleep(0.5)
                if self.send_address():
                    return True
            time.sleep(2.0)

        log.error("Handshake failed after 3 attempts")
        return False

    def run(self):
        if not self.connect_db():
            log.error("Cannot start without DB connection")
            return

        last_heartbeat = 0

        while True:
            if not self.conn:
                log.warning("DB connection lost, reconnecting...")
                if not self.connect_db():
                    log.error("DB reconnection failed, retrying in 30s...")
                    time.sleep(30)
                    continue

            if not self.ser:
                if not self.open_serial():
                    log.error("Cannot open serial port, retrying in 30s...")
                    now = time.time()
                    if now - last_heartbeat >= 60:
                        if self.db_insert_heartbeat():
                            last_heartbeat = now
                    time.sleep(30)
                    continue

            if not self.registered:
                try:
                    if not self.do_handshake():
                        log.warning("Handshake failed, will retry in 30s...")
                        now = time.time()
                        if now - last_heartbeat >= 60:
                            if self.db_insert_heartbeat():
                                last_heartbeat = now
                        try:
                            self.ser.close()
                        except:
                            pass
                        self.ser = None
                        time.sleep(30)
                        continue
                except (serial.SerialException, OSError) as e:
                    log.error(f"Serial error during handshake: {e}")
                    try:
                        if self.ser:
                            self.ser.close()
                    except:
                        pass
                    self.ser = None
                    self.registered = False
                    time.sleep(30)
                    continue

            try:
                data = self.read_michele()
                if data:
                    self.consecutive_failures = 0
                    data['is_stale'] = False
                    filtered = {k: v for k, v in data.items() if v is not None}
                    self.db_insert('realtime', filtered)

                    log.info(
                        f"T={data.get('temp', 'N/A')}C "
                        f"MPPT1: V={data.get('vpv1', 'N/A')}V I={data.get('ipv1', 'N/A')}A P={data.get('ppv1', 'N/A')}W | "
                        f"MPPT2: V={data.get('vpv2', 'N/A')}V I={data.get('ipv2', 'N/A')}A P={data.get('ppv2', 'N/A')}W | "
                        f"MPPT3: V={data.get('vpv3', 'N/A')}V I={data.get('ipv3', 'N/A')}A P={data.get('ppv3', 'N/A')}W | "
                        f"Grid: V={data.get('vac', 'N/A')}V I={data.get('iac', 'N/A')}A P={data.get('pac', 'N/A')}W "
                        f"F={data.get('fac', 'N/A')}Hz Status={data.get('status', 'N/A')}"
                    )
                else:
                    self.consecutive_failures += 1
                    log.warning(f"No response from inverter ({self.consecutive_failures}/{self.max_failures})")

                    now = time.time()
                    if now - last_heartbeat >= 60:
                        if self.db_insert_heartbeat():
                            last_heartbeat = now

                    if self.consecutive_failures >= self.max_failures:
                        log.error("Too many failures, re-doing handshake...")
                        self.registered = False
                        try:
                            self.ser.close()
                        except:
                            pass
                        self.ser = None

            except (serial.SerialException, OSError) as e:
                log.error(f"Serial error: {e}")
                try:
                    self.ser.close()
                except:
                    pass
                self.ser = None
                self.registered = False
            except Exception as e:
                log.error(f"Unexpected error: {e}")
                try:
                    if self.ser:
                        self.ser.close()
                except:
                    pass
                self.ser = None
                self.registered = False

            time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    reader = SISERReader()
    reader.run()