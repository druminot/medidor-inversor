#!/usr/bin/env python3
"""
diagnose_inverter.py — Diagnostico de comunicacion con inversor Riello H.P.6065REL-D

Prueba multiples protocolos y baudrates para detectar como habla el inversor:
  1. SISER (protocolo Phoenixtec/Riello propietario) - handshake AA AA
  2. Modbus RTU (FC03, FC11)
  3. Megatec ASCII (protocolo UPS comun en inversores)
  4. Escucha pasiva (detectar si el inversor transmite algo por su cuenta)

Uso:
  python3 diagnose_inverter.py [--port /dev/ttyUSB0] [--timeout 2] [--verbose]
"""

import argparse
import os
import struct
import sys
import time

import serial

BAUDRATES = [9600, 19200, 4800, 2400, 115200, 57600, 38400, 1200]
PORT_DEFAULT = '/dev/ttyUSB0'
TIMEOUT_DEFAULT = 1.5

SISER_SYNC = 0xAA


def crc16_modbus(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def siser_checksum(data, length):
    return sum(data[:length - 2]) & 0xFFFF


def build_siser_offline_enquiry(addr=0):
    frame = bytearray(11)
    frame[0] = SISER_SYNC
    frame[1] = SISER_SYNC
    frame[2] = 0x01
    frame[3] = 0x00
    frame[4] = 0x00
    frame[5] = addr & 0xFF
    frame[6] = 0x00
    frame[7] = 0x00
    frame[8] = 0x00
    cs = siser_checksum(frame, len(frame))
    frame[9] = (cs >> 8) & 0xFF
    frame[10] = cs & 0xFF
    return bytes(frame)


def build_siser_send_address(addr=1):
    frame = bytearray(11)
    frame[0] = SISER_SYNC
    frame[1] = SISER_SYNC
    frame[2] = 0x01
    frame[3] = 0x00
    frame[4] = 0x00
    frame[5] = addr & 0xFF
    frame[6] = 0x00
    frame[7] = 0x01
    frame[8] = 0x00
    cs = siser_checksum(frame, len(frame))
    frame[9] = (cs >> 8) & 0xFF
    frame[10] = cs & 0xFF
    return bytes(frame)


def build_siser_registration(addr=1):
    data_len = 2
    frame = bytearray(9 + data_len + 2)
    frame[0] = SISER_SYNC
    frame[1] = SISER_SYNC
    frame[2] = 0x01
    frame[3] = 0x00
    frame[4] = 0x00
    frame[5] = addr & 0xFF
    frame[6] = 0x00
    frame[7] = 0x04
    frame[8] = data_len & 0xFF
    frame[9] = addr & 0xFF
    frame[10] = 0x00
    cs = siser_checksum(frame, len(frame))
    frame[11] = (cs >> 8) & 0xFF
    frame[12] = cs & 0xFF
    return bytes(frame)


def build_modbus_fc03(slave, addr, count):
    data = bytes([slave, 0x03]) + struct.pack('>HH', addr, count)
    crc = crc16_modbus(data)
    return data + struct.pack('<H', crc)


def build_modbus_fc11(slave):
    data = bytes([slave, 0x11])
    crc = crc16_modbus(data)
    return data + struct.pack('<H', crc)


def build_modbus_fc04(slave, addr, count):
    data = bytes([slave, 0x04]) + struct.pack('>HH', addr, count)
    crc = crc16_modbus(data)
    return data + struct.pack('<H', crc)


def build_modbus_unlock(slave):
    unlock_data = struct.pack('>HH', 0x0000, 0x0000)
    data = bytes([slave, 0x10]) + struct.pack('>HH', 0x003C, 2) + bytes([4]) + unlock_data
    crc = crc16_modbus(data)
    return data + struct.pack('<H', crc)


def build_megatec_q1():
    return b"Q1\r"


def build_megatec_qs():
    return b"QS\r"


def build_megatec_d():
    return b"D\r"


def build_megatec_i():
    return b"I\r"


def drain_port(ser, timeout=0.2):
    old_timeout = ser.timeout
    ser.timeout = timeout
    data = b''
    while True:
        chunk = ser.read(256)
        if not chunk:
            break
        data += chunk
    ser.timeout = old_timeout
    return data


def send_and_recv(ser, data, timeout=2.0, label=""):
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    drain_port(ser, 0.1)

    ser.write(data)
    if label:
        sys.stdout.write(f"    TX: {data.hex()} ({len(data)} bytes)")
        if all(32 <= b < 127 for b in data if b != 0x0d and b != 0x0a):
            sys.stdout.write(f"  ASCII: {data.decode('ascii', errors='replace').strip()}")
        sys.stdout.write("\n")
        sys.stdout.flush()

    old_timeout = ser.timeout
    ser.timeout = timeout
    resp = ser.read(512)
    ser.timeout = old_timeout

    if resp:
        sys.stdout.write(f"    RX: {resp.hex()} ({len(resp)} bytes)")
        try:
            ascii_str = resp.decode('ascii', errors='replace').strip()
            if ascii_str and all(c.isprintable() or c in '\r\n\t' for c in ascii_str):
                sys.stdout.write(f"  ASCII: {ascii_str}")
        except Exception:
            pass
        sys.stdout.write("\n")

        if len(resp) >= 2 and resp[0] == SISER_SYNC and resp[1] == SISER_SYNC:
            sys.stdout.write("    >>> SISER RESPONSE DETECTED! <<<\n")
            dlen = resp[8] if len(resp) > 8 else 0
            group = resp[6] if len(resp) > 6 else 0
            cmd = resp[7] if len(resp) > 7 else 0
            sys.stdout.write(f"    SISER: addr={resp[5]:02X} group={group} cmd={cmd:02X} dlen={dlen}\n")

        if len(resp) >= 4 and resp[1] in (0x03, 0x04, 0x06, 0x10, 0x11):
            sys.stdout.write("    >>> MODBUS RESPONSE DETECTED! <<<\n")
            sys.stdout.write(f"    MODBUS: slave={resp[0]:02X} FC={resp[1]:02X}\n")

        sys.stdout.flush()
    else:
        sys.stdout.write(f"    No response (timeout {timeout}s)\n")
        sys.stdout.flush()

    return resp


def test_siser(ser, baudrate, verbose=False):
    sys.stdout.write("  [SISER] offlineEnquiry (addr=0) ...\n")
    sys.stdout.flush()
    resp = send_and_recv(ser, build_siser_offline_enquiry(0), timeout=2.0, label="SISER offlineEnquiry")
    if resp and len(resp) >= 2 and resp[0] == SISER_SYNC and resp[1] == SISER_SYNC:
        sys.stdout.write(f"  *** SISER RESPONSE at {baudrate} baud! ***\n\n")
        sys.stdout.flush()
        return True, resp

    sys.stdout.write("  [SISER] offlineEnquiry (addr=1) ...\n")
    sys.stdout.flush()
    resp = send_and_recv(ser, build_siser_offline_enquiry(1), timeout=2.0, label="SISER offlineEnquiry addr=1")
    if resp and len(resp) >= 2 and resp[0] == SISER_SYNC and resp[1] == SISER_SYNC:
        sys.stdout.write(f"  *** SISER RESPONSE at {baudrate} baud! ***\n\n")
        sys.stdout.flush()
        return True, resp

    sys.stdout.write("  [SISER] sendAddress ...\n")
    sys.stdout.flush()
    resp = send_and_recv(ser, build_siser_send_address(1), timeout=2.0, label="SISER sendAddress")
    if resp and len(resp) >= 2 and resp[0] == SISER_SYNC and resp[1] == SISER_SYNC:
        sys.stdout.write(f"  *** SISER RESPONSE at {baudrate} baud! ***\n\n")
        sys.stdout.flush()
        return True, resp

    sys.stdout.write("  [SISER] reRegistration ...\n")
    sys.stdout.flush()
    resp = send_and_recv(ser, build_siser_registration(1), timeout=2.0, label="SISER reRegistration")
    if resp and len(resp) >= 2 and resp[0] == SISER_SYNC and resp[1] == SISER_SYNC:
        sys.stdout.write(f"  *** SISER RESPONSE at {baudrate} baud! ***\n\n")
        sys.stdout.flush()
        return True, resp

    return False, b''


def test_modbus(ser, baudrate, verbose=False):
    for slave in [1, 2, 16, 247]:
        sys.stdout.write(f"  [MODBUS] slave={slave} FC03 addr=0x0000 count=1 ...\n")
        sys.stdout.flush()
        resp = send_and_recv(ser, build_modbus_fc03(slave, 0x0000, 1), timeout=1.5, label=f"MODBUS FC03 slave={slave}")
        if resp and len(resp) >= 5 and resp[0] == slave and resp[1] == 0x03:
            sys.stdout.write(f"  *** MODBUS FC03 RESPONSE at {baudrate} baud, slave={slave}! ***\n\n")
            sys.stdout.flush()
            return True, resp

        sys.stdout.write(f"  [MODBUS] slave={slave} FC03 addr=0x003C count=2 (unlock area) ...\n")
        sys.stdout.flush()
        resp = send_and_recv(ser, build_modbus_fc03(slave, 0x003C, 2), timeout=1.5, label=f"MODBUS FC03 0x3C slave={slave}")
        if resp and len(resp) >= 5 and resp[0] == slave and resp[1] == 0x03:
            sys.stdout.write(f"  *** MODBUS FC03 RESPONSE at {baudrate} baud, slave={slave}! ***\n\n")
            sys.stdout.flush()
            return True, resp

        sys.stdout.write(f"  [MODBUS] slave={slave} FC11 ReportSlaveID ...\n")
        sys.stdout.flush()
        resp = send_and_recv(ser, build_modbus_fc11(slave), timeout=1.5, label=f"MODBUS FC11 slave={slave}")
        if resp and len(resp) >= 5 and resp[0] == slave:
            sys.stdout.write(f"  *** MODBUS FC11 RESPONSE at {baudrate} baud, slave={slave}! ***\n\n")
            sys.stdout.flush()
            return True, resp

        sys.stdout.write(f"  [MODBUS] slave={slave} FC10 unlock ...\n")
        sys.stdout.flush()
        resp = send_and_recv(ser, build_modbus_unlock(slave), timeout=1.5, label=f"MODBUS FC10 unlock slave={slave}")
        if resp and len(resp) >= 5 and resp[0] == slave and resp[1] == 0x10:
            sys.stdout.write(f"  *** MODBUS FC10 UNLOCK ACK at {baudrate} baud, slave={slave}! ***\n\n")
            sys.stdout.flush()
            return True, resp

    return False, b''


def test_megatec(ser, baudrate, verbose=False):
    for cmd_name, cmd in [("Q1", b"Q1\r"), ("QS", b"QS\r"), ("D", b"D\r"), ("I", b"I\r")]:
        sys.stdout.write(f"  [MEGATEC] {cmd_name} ...\n")
        sys.stdout.flush()
        resp = send_and_recv(ser, cmd, timeout=2.0, label=f"MEGATEC {cmd_name}")
        if resp and len(resp) > 3:
            try:
                ascii_str = resp.decode('ascii', errors='strict')
                if any(c.isalnum() for c in ascii_str):
                    sys.stdout.write(f"  *** MEGATEC RESPONSE at {baudrate} baud! ***\n")
                    sys.stdout.write(f"  ASCII: {ascii_str}\n\n")
                    sys.stdout.flush()
                    return True, resp
            except Exception:
                pass

    return False, b''


def test_passive_listen(ser, baudrate, duration=5, verbose=False):
    sys.stdout.write(f"  [LISTEN] Escuchando {duration}s en {baudrate} baud ...\n")
    sys.stdout.flush()
    drain_port(ser, 0.1)
    start = time.time()
    total_data = bytearray()
    old_timeout = ser.timeout
    ser.timeout = duration
    while time.time() - start < duration:
        chunk = ser.read(4096)
        if chunk:
            total_data.extend(chunk)
            if verbose:
                sys.stdout.write(f"    Received {len(chunk)} bytes: {chunk.hex()}\n")
    ser.timeout = old_timeout

    if total_data:
        sys.stdout.write(f"  *** INVERTER TRANSMITS at {baudrate} baud! {len(total_data)} bytes ***\n")
        sys.stdout.write(f"  Data: {total_data[:200].hex()}\n")
        try:
            ascii_str = total_data.decode('ascii', errors='replace')
            if any(c.isalnum() for c in ascii_str):
                sys.stdout.write(f"  ASCII: {ascii_str[:200]}\n")
        except Exception:
            pass
        sys.stdout.write("\n")
        sys.stdout.flush()
        return True, bytes(total_data)
    else:
        sys.stdout.write(f"  Silencio total ({duration}s)\n\n")
        sys.stdout.flush()
    return False, b''


def test_baudrate(baudrate, port, timeout, verbose):
    sys.stdout.write(f"\n{'='*60}\n")
    sys.stdout.write(f"Probando baudrate {baudrate}\n")
    sys.stdout.write(f"{'='*60}\n")
    sys.stdout.flush()

    try:
        ser = serial.Serial(port, baudrate, bytesize=8, parity='N',
                          stopbits=1, timeout=timeout)
    except Exception as e:
        sys.stdout.write(f"  ERROR abriendo {port} a {baudrate}: {e}\n")
        sys.stdout.flush()
        return None

    try:
        ser.setDTR(True)
        ser.setRTS(True)
        time.sleep(0.5)
        ser.setDTR(False)
        time.sleep(0.5)

        sys.stdout.write("  RTS=1, DTR=0 (RS485 TX enable)\n")
        sys.stdout.flush()

        found, resp = test_siser(ser, baudrate, verbose)
        if found:
            ser.close()
            return ('SISER', baudrate, resp)

        found, resp = test_modbus(ser, baudrate, verbose)
        if found:
            ser.close()
            return ('MODBUS', baudrate, resp)

        found, resp = test_megatec(ser, baudrate, verbose)
        if found:
            ser.close()
            return ('MEGATEC', baudrate, resp)

        found, resp = test_passive_listen(ser, baudrate, duration=3, verbose=verbose)
        if found:
            ser.close()
            return ('PASSIVE', baudrate, resp)

        ser.setDTR(True)
        time.sleep(0.5)
        sys.stdout.write("\n  --- Reintentando con DTR=1 ---\n")
        sys.stdout.flush()

        found, resp = test_siser(ser, baudrate, verbose)
        if found:
            ser.close()
            return ('SISER_DTR', baudrate, resp)

        found, resp = test_modbus(ser, baudrate, verbose)
        if found:
            ser.close()
            return ('MODBUS_DTR', baudrate, resp)

        found, resp = test_megatec(ser, baudrate, verbose)
        if found:
            ser.close()
            return ('MEGATEC_DTR', baudrate, resp)

    finally:
        ser.close()

    return None


def main():
    parser = argparse.ArgumentParser(description='Diagnostico de comunicacion con inversor Riello')
    parser.add_argument('--port', default=PORT_DEFAULT, help='Puerto serial')
    parser.add_argument('--timeout', type=float, default=TIMEOUT_DEFAULT, help='Timeout en segundos')
    parser.add_argument('--verbose', '-v', action='store_true', help='Mas detalle')
    parser.add_argument('--baudrate', type=int, default=None, help='Solo probar este baudrate')
    parser.add_argument('--protocol', choices=['siser', 'modbus', 'megatec', 'all'], default='all',
                       help='Solo probar este protocolo')
    args = parser.parse_args()

    sys.stdout.write(f"\n{'#'*60}\n")
    sys.stdout.write("# Diagnostico de Inversor Riello H.P.6065REL-D\n")
    sys.stdout.write(f"# Puerto: {args.port}\n")
    sys.stdout.write(f"# Timeout: {args.timeout}s\n")
    sys.stdout.write(f"# Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    sys.stdout.write(f"{'#'*60}\n\n")
    sys.stdout.flush()

    if not os.path.exists(args.port):
        sys.stdout.write(f"ERROR: Puerto {args.port} no existe!\n")
        sys.stdout.flush()
        sys.exit(1)

    bauds = [args.baudrate] if args.baudrate else BAUDRATES

    results = []
    for baud in bauds:
        result = test_baudrate(baud, args.port, args.timeout, args.verbose)
        if result:
            results.append(result)

    sys.stdout.write(f"\n\n{'#'*60}\n")
    sys.stdout.write("# RESULTADOS\n")
    sys.stdout.write(f"{'#'*60}\n\n")
    sys.stdout.flush()

    if results:
        for protocol, baud, resp in results:
            sys.stdout.write(f"  *** ENCONTRADO: {protocol} @ {baud} baud ***\n")
            sys.stdout.write(f"  Respuesta: {resp[:100].hex()}\n\n")
        sys.stdout.flush()
        return 0
    else:
        sys.stdout.write("  No se detecto respuesta del inversor en ningun protocolo/baudrate.\n\n")
        sys.stdout.write("Posibles causas:\n")
        sys.stdout.write("  1. Cable USB-RS232 incompatible (necesita USB-TTL si la placa usa niveles TTL)\n")
        sys.stdout.write("  2. Pinout TX/RX invertido (probar cruzar pines 2 y 3 del DB9)\n")
        sys.stdout.write("  3. GND no conectado entre inversor y adaptador\n")
        sys.stdout.write("  4. El inversor no esta generando (sin luz solar o en modo standby)\n")
        sys.stdout.write("  5. Baudrate o protocolo no soportado por este modelo\n")
        sys.stdout.flush()
        return 1


if __name__ == '__main__':
    sys.exit(main())
