#!/usr/bin/env python3
"""
inverter_simulator.py — Simulador Modbus RTU + NetMan UDP del inversor Riello H.P.6065REL-D

Modos:
  --mode tcp    Modbus TCP server (para testing con pymodbus client)
  --mode qemu   Raw TCP server con Modbus RTU frames (para QEMU serial)
  --mode client Cliente TCP (conectar a QEMU serial server)
  --mode server Servidor TCP raw Modbus RTU
  --mode netman Servidor UDP NetMan (puerto 33000, protocolo SunVision)

Para SunVision en modo Network NetMan:
  Apuntar a la IP del simulador, puerto UDP 33000.
"""

import argparse
import math
import os
import random
import socket
import struct
import threading
import time
from datetime import datetime

NUM_REGS = 65536
SLAVE_ID = 1
TCP_PORT = 5502
START_TIME = time.time()
START_ENERGY = 12547.32

holding = [0] * NUM_REGS
input_regs = [0] * NUM_REGS
coils = [False] * NUM_REGS
discrete_inputs = [False] * NUM_REGS
data_lock = threading.Lock()


def log(level, msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{ts}] [{level}] {msg}", flush=True)


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


def init_registers():
    global holding, input_regs, coils, discrete_inputs
    h = holding

    h[0x0000] = 0x6065
    h[0x0001] = 0x0001
    h[0x0002] = 0x0100
    h[0x0003] = 0x524C
    h[0x0004] = 0x4950
    h[0x0005] = 0x0001
    h[0x0006] = 0x2580
    h[0x0007] = 0x0008
    h[0x0008] = 0x0000
    h[0x0009] = 0x1770
    h[0x003C] = 0xFFFF
    h[0x003D] = 0xFFFF
    h[0x1005] = 0x0002
    h[0x101C] = 42

    energy_raw = int(START_ENERGY / 0.01)
    h[0x1021] = energy_raw & 0xFFFF
    h[0x1022] = (energy_raw >> 16) & 0xFFFF

    power_raw = int(3200 / 0.01)
    h[0x1037] = power_raw & 0xFFFF
    h[0x1038] = (power_raw >> 16) & 0xFFFF

    h[0x1040] = 3100
    h[0x1041] = 1030
    h[0x1042] = 2300
    h[0x1043] = 1390
    h[0x1044] = 5000

    hours_raw = int(87654 / 0.01)
    h[0x1050] = hours_raw & 0xFFFF
    h[0x1051] = (hours_raw >> 16) & 0xFFFF

    co2_raw = int(6274.16 / 0.01)
    h[0x1052] = co2_raw & 0xFFFF
    h[0x1053] = (co2_raw >> 16) & 0xFFFF

    h[0x1060] = 2850

    pdc_raw = int(3193 / 0.01)
    h[0x1070] = pdc_raw & 0xFFFF
    h[0x1071] = (pdc_raw >> 16) & 0xFFFF

    h[0x1080] = 99

    for i in range(48):
        hour = i / 2.0
        if 6 <= hour <= 18:
            sf = math.sin(math.pi * (hour - 6) / 12)
        else:
            sf = 0
        h[0xC000 + i] = int(sf * 3200 / 0.01)

    input_regs[0x0000] = 0x0001
    input_regs[0x1005] = h[0x1005]
    input_regs[0x101C] = h[0x101C]

    discrete_inputs[0x0000] = True
    discrete_inputs[0x0001] = True
    discrete_inputs[0x0002] = False
    coils[0x0000] = True

    log("INIT", "Datastore inicializado")


def update_values():
    global holding
    elapsed = time.time() - START_TIME

    hour_of_day = (elapsed / 3600) % 24
    if 6 <= hour_of_day <= 18:
        solar_factor = math.sin(math.pi * (hour_of_day - 6) / 12)
    else:
        solar_factor = 0.0
    solar_factor = max(0, solar_factor + random.gauss(0, 0.03))

    base_power = 3200
    power_w = int(base_power * solar_factor)
    power_raw = int(power_w / 0.01)
    holding[0x1037] = power_raw & 0xFFFF
    holding[0x1038] = (power_raw >> 16) & 0xFFFF

    vpv = int((310 + 40 * solar_factor) * 10)
    holding[0x1040] = vpv

    ipv_x100 = int((power_w / max(vpv / 10, 1)) * 100) if solar_factor > 0 else 0
    holding[0x1041] = ipv_x100

    vac = int((230 + random.gauss(0, 2)) * 10)
    holding[0x1042] = vac

    iac_x100 = int((power_w / max(vac / 10, 1)) * 100) if solar_factor > 0 else 0
    holding[0x1043] = iac_x100

    fac_x100 = int((50.0 + random.gauss(0, 0.05)) * 100)
    holding[0x1044] = fac_x100

    temp = int(35 + 20 * solar_factor + random.gauss(0, 1))
    holding[0x101C] = temp

    pdc_w = int(power_w / 0.97)
    pdc_raw = int(pdc_w / 0.01)
    holding[0x1070] = pdc_raw & 0xFFFF
    holding[0x1071] = (pdc_raw >> 16) & 0xFFFF

    energy_increment = (elapsed / 3600) * power_w / 1000
    total_energy = START_ENERGY + energy_increment
    energy_raw = int(total_energy / 0.01)
    holding[0x1021] = energy_raw & 0xFFFF
    holding[0x1022] = (energy_raw >> 16) & 0xFFFF

    daily = (elapsed / 3600) * power_w / 1000 * max(solar_factor, 0.01)
    holding[0x1060] = int(daily / 0.01) if daily > 0 else 0

    status = 0x0002 if solar_factor > 0.01 else 0x0001
    holding[0x1005] = status

    co2 = total_energy * 0.5
    co2_raw = int(co2 / 0.01)
    holding[0x1052] = co2_raw & 0xFFFF
    holding[0x1053] = (co2_raw >> 16) & 0xFFFF

    hours = int((87654 + elapsed / 3600) / 0.01)
    holding[0x1050] = hours & 0xFFFF
    holding[0x1051] = (hours >> 16) & 0xFFFF

    return solar_factor, power_w, temp


def update_loop():
    while True:
        try:
            sf, pw, t = update_values()
            if int(time.time()) % 30 == 0:
                log("UPDATE", f"Pac={pw}W Temp={t}C sf={sf:.2f}")
        except Exception as e:
            log("ERROR", f"Update error: {e}")
        time.sleep(2)


def build_response_fc03(slave_id, start_addr, count):
    with data_lock:
        values = []
        for i in range(count):
            addr = start_addr + i
            if 0 <= addr < NUM_REGS:
                values.append(holding[addr])
            else:
                values.append(0)
    byte_count = count * 2
    data = bytes([slave_id, 0x03, byte_count])
    for v in values:
        data += struct.pack('>H', v)
    crc = crc16_modbus(data)
    data += struct.pack('<H', crc)
    return data


def build_response_fc04(slave_id, start_addr, count):
    with data_lock:
        values = []
        for i in range(count):
            addr = start_addr + i
            if 0 <= addr < NUM_REGS:
                values.append(input_regs[addr])
            else:
                values.append(0)
    byte_count = count * 2
    data = bytes([slave_id, 0x04, byte_count])
    for v in values:
        data += struct.pack('>H', v)
    crc = crc16_modbus(data)
    data += struct.pack('<H', crc)
    return data


def build_response_fc06(slave_id, addr, value):
    with data_lock:
        holding[addr] = value
        if addr == 0x003C:
            log("UNLOCK", f"Write to 0x003C = 0x{value:04X}")
        elif addr == 0x003D:
            if holding[0x003C] == 0x0000 and value == 0x0000:
                log("UNLOCK", "Protocolo desbloqueado!")
            else:
                log("UNLOCK", f"Write to 0x003D = 0x{value:04X}")
        else:
            log("WRITE", f"FC06 Slave={slave_id} addr=0x{addr:04X} value=0x{value:04X}")
    data = bytes([slave_id, 0x06]) + struct.pack('>H', addr) + struct.pack('>H', value)
    crc = crc16_modbus(data)
    data += struct.pack('<H', crc)
    return data


def build_response_fc10(slave_id, start_addr, count):
    with data_lock:
        log("WRITE", f"FC10 Slave={slave_id} addr=0x{start_addr:04X} count={count}")
        if start_addr == 0x003C:
            log("UNLOCK", "Write multiple to 0x003C (unlock area)")
    data = bytes([slave_id, 0x10]) + struct.pack('>H', start_addr) + struct.pack('>H', count)
    crc = crc16_modbus(data)
    data += struct.pack('<H', crc)
    return data


def build_exception_response(slave_id, fc, exception_code):
    data = bytes([slave_id, fc | 0x80, exception_code])
    crc = crc16_modbus(data)
    data += struct.pack('<H', crc)
    return data


def process_modbus_request(data):
    if len(data) < 6:
        log("WARN", f"Frame too short: {data.hex()}")
        return None

    received_crc = struct.unpack('<H', data[-2:])[0]
    calculated_crc = crc16_modbus(data[:-2])
    if received_crc != calculated_crc:
        log("WARN", f"CRC error: received=0x{received_crc:04X} calculated=0x{calculated_crc:04X}")
        return None

    slave_id = data[0]
    if slave_id != SLAVE_ID:
        return None

    fc = data[1]
    log("REQUEST", f"Slave={slave_id} FC={fc:02X} Data={data[2:-2].hex()}")

    if fc == 0x03:
        start_addr = struct.unpack('>H', data[2:4])[0]
        count = struct.unpack('>H', data[4:6])[0]
        if count > 125:
            return build_exception_response(slave_id, fc, 0x03)
        log("RESPONSE", f"FC03 ReadHoldingRegisters addr=0x{start_addr:04X} count={count}")
        return build_response_fc03(slave_id, start_addr, count)

    elif fc == 0x04:
        start_addr = struct.unpack('>H', data[2:4])[0]
        count = struct.unpack('>H', data[4:6])[0]
        if count > 125:
            return build_exception_response(slave_id, fc, 0x03)
        log("RESPONSE", f"FC04 ReadInputRegisters addr=0x{start_addr:04X} count={count}")
        return build_response_fc04(slave_id, start_addr, count)

    elif fc == 0x06:
        addr = struct.unpack('>H', data[2:4])[0]
        value = struct.unpack('>H', data[4:6])[0]
        return build_response_fc06(slave_id, addr, value)

    elif fc == 0x10:
        start_addr = struct.unpack('>H', data[2:4])[0]
        count = struct.unpack('>H', data[4:6])[0]
        byte_count = data[6]
        values = []
        for i in range(count):
            values.append(struct.unpack('>H', data[7 + i * 2:9 + i * 2])[0])
        with data_lock:
            for i, v in enumerate(values):
                holding[start_addr + i] = v
        return build_response_fc10(slave_id, start_addr, count)

    elif fc == 0x02:
        start_addr = struct.unpack('>H', data[2:4])[0]
        count = struct.unpack('>H', data[4:6])[0]
        if count > 2000:
            return build_exception_response(slave_id, fc, 0x03)
        byte_count = (count + 7) // 8
        bits = []
        with data_lock:
            for i in range(count):
                if 0 <= start_addr + i < NUM_REGS:
                    bits.append(discrete_inputs[start_addr + i])
                else:
                    bits.append(False)
        resp_bytes = bytearray([slave_id, 0x02, byte_count])
        byte_val = 0
        bit_pos = 0
        for b in bits:
            if b:
                byte_val |= (1 << bit_pos)
            bit_pos += 1
            if bit_pos == 8:
                resp_bytes.append(byte_val)
                byte_val = 0
                bit_pos = 0
        if bit_pos > 0:
            resp_bytes.append(byte_val)
        crc = crc16_modbus(bytes(resp_bytes))
        resp_bytes += struct.pack('<H', crc)
        return bytes(resp_bytes)

    elif fc == 0x01:
        start_addr = struct.unpack('>H', data[2:4])[0]
        count = struct.unpack('>H', data[4:6])[0]
        byte_count = (count + 7) // 8
        bits = []
        with data_lock:
            for i in range(count):
                if 0 <= start_addr + i < NUM_REGS:
                    bits.append(coils[start_addr + i])
                else:
                    bits.append(False)
        resp_bytes = bytearray([slave_id, 0x01, byte_count])
        byte_val = 0
        bit_pos = 0
        for b in bits:
            if b:
                byte_val |= (1 << bit_pos)
            bit_pos += 1
            if bit_pos == 8:
                resp_bytes.append(byte_val)
                byte_val = 0
                bit_pos = 0
        if bit_pos > 0:
            resp_bytes.append(byte_val)
        crc = crc16_modbus(bytes(resp_bytes))
        resp_bytes += struct.pack('<H', crc)
        return bytes(resp_bytes)

    else:
        log("WARN", f"Unsupported function code: FC={fc:02X}")
        return build_exception_response(slave_id, fc, 0x01)


def handle_client(conn, addr):
    log("CONNECT", f"Cliente conectado desde {addr[0]}:{addr[1]}")
    buffer = bytearray()

    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break

            buffer.extend(data)

            # Try to process as many complete frames as possible
            processed = True
            while processed and len(buffer) >= 4:
                processed = False
                slave_id = buffer[0]
                if slave_id != SLAVE_ID and slave_id != 0:
                    buffer = bytearray()
                    continue

                fc = buffer[1]
                frame_len = 0

                if fc in (0x01, 0x02, 0x03, 0x04):
                    if len(buffer) >= 8:
                        frame_len = 8
                elif fc == 0x06:
                    if len(buffer) >= 8:
                        frame_len = 8
                elif fc == 0x10:
                    if len(buffer) >= 7:
                        byte_count = buffer[6]
                        frame_len = 9 + byte_count
                else:
                    buffer = bytearray()
                    continue

                if frame_len == 0 or len(buffer) < frame_len:
                    break

                frame = bytes(buffer[:frame_len])
                buffer = buffer[frame_len:]
                processed = True

                response = process_modbus_request(frame)
                if response:
                    conn.sendall(response)
                    log("SENT", f"Response {len(response)} bytes: {response.hex()}")

    except ConnectionResetError:
        log("DISCONNECT", f"Cliente {addr[0]}:{addr[1]} desconectado (reset)")
    except BrokenPipeError:
        log("DISCONNECT", f"Cliente {addr[0]}:{addr[1]} desconectado (broken pipe)")
    except Exception as e:
        log("ERROR", f"Client error: {e}")
    finally:
        conn.close()
        log("DISCONNECT", f"Cliente {addr[0]}:{addr[1]} cerrado")


def run_qemu_server(host, port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    log("START", f"Escuchando en {host}:{port} (raw Modbus RTU over TCP)")
    log("START", f"Para QEMU: -serial tcp:{host}:{port},server=off,wait=off")
    log("START", "En SunVision: COM1, 9600, 8N1, slave=1")

    while True:
        conn, addr = server.accept()
        t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        t.start()


def run_qemu_client(host, port):
    """Conecta como cliente al QEMU serial server (QEMU es server, nosotros somos client)."""
    while True:
        try:
            log("CLIENT", f"Conectando a {host}:{port}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
            log("CLIENT", f"Conectado a {host}:{port}")

            buffer = bytearray()
            while True:
                data = sock.recv(1024)
                if not data:
                    log("CLIENT", "Desconectado por el server")
                    break

                buffer.extend(data)

                while len(buffer) >= 4:
                    slave_id = buffer[0]
                    fc = buffer[1]
                    frame_len = 0

                    if fc in (0x01, 0x02, 0x03, 0x04):
                        if len(buffer) >= 8:
                            frame_len = 8
                    elif fc == 0x06:
                        if len(buffer) >= 8:
                            frame_len = 8
                    elif fc == 0x10:
                        if len(buffer) >= 7:
                            byte_count = buffer[6]
                            frame_len = 9 + byte_count
                    else:
                        buffer = bytearray()
                        continue

                    if frame_len == 0 or len(buffer) < frame_len:
                        break

                    frame = bytes(buffer[:frame_len])
                    buffer = buffer[frame_len:]

                    received_crc = struct.unpack('<H', frame[-2:])[0]
                    calculated_crc = crc16_modbus(frame[:-2])
                    if received_crc != calculated_crc:
                        log("WARN", "CRC error in client mode")
                        continue

                    if slave_id != SLAVE_ID:
                        continue

                    response = process_modbus_request(frame)
                    if response:
                        sock.sendall(response)

        except ConnectionRefusedError:
            log("CLIENT", "Connection refused, reintentando en 5s...")
            time.sleep(5)
        except Exception as e:
            log("ERROR", f"Client error: {e}")
            time.sleep(5)
        finally:
            try:
                sock.close()
            except Exception:
                pass


def run_tcp_server(host, port):
    from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext, ModbusSlaveContext
    from pymodbus.device import ModbusDeviceIdentification
    from pymodbus.server import StartTcpServer

    hr = ModbusSequentialDataBlock(0x0000, [0] * NUM_REGS)
    ir = ModbusSequentialDataBlock(0x0000, [0] * NUM_REGS)
    co = ModbusSequentialDataBlock(0x0000, [False] * NUM_REGS)
    di = ModbusSequentialDataBlock(0x0000, [False] * NUM_REGS)

    slave = ModbusSlaveContext(hr=hr, ir=ir, co=co, di=di)
    context = ModbusServerContext(slaves={SLAVE_ID: slave}, single=False)
    s = context[SLAVE_ID]

    with data_lock:
        for addr, val in enumerate(holding):
            if val != 0:
                try:
                    s.setValues(3, addr, [val])
                except Exception:
                    pass

    identity = ModbusDeviceIdentification()
    identity.VendorName = "Riello Solartech"
    identity.ProductCode = "HP6065"

    log("START", f"Modbus TCP server en {host}:{port}")
    StartTcpServer(context=context, identity=identity, address=(host, port))


NETMAN_UDP_PORT = 33000
NETMAN_VERSION = b"**0200"
NETMAN_PASSWORD = 0


def build_netman_identif_response(req, src_addr, device_no):
    """Type 1: GET_IDENTIF. SunVision fills Remote.Name, IPAddress, DeviceNo, etc."""
    name = b"SIMULATED-UPS\x00"
    ip_addr = b"10.1.10.70\x00"
    tel_number = b"\x00"
    dev_type = 22
    comm_type = 2
    ups_type = 14
    time_to_shutdown = 0
    type_txt = b"SENTR 3/3 6kVA\x00"
    status_txt = b"On Line\x00"

    payload = bytearray()
    payload += req[0:14]
    payload += struct.pack('<H', 1)  # RR=1 (non-zero for response)
    payload += NETMAN_VERSION
    payload += name
    payload += ip_addr
    if len(req) >= 143 and len(req) < 500:
        payload += struct.pack('<H', device_no)
    else:
        payload += bytes([device_no & 0xFF])
    payload += bytes([0])
    payload += bytes([0])
    payload += tel_number
    payload += bytes([dev_type])
    payload += bytes([comm_type])
    payload += struct.pack('<H', ups_type)
    payload += bytes([0] * 14)
    payload += struct.pack('<H', time_to_shutdown)
    payload += bytes([0] * 14)
    payload += type_txt
    payload += status_txt
    return bytes(payload)


def build_netman_status_response(req):
    """Type 3: GET_STATUS. Returns communication OK and UPS status."""
    payload = bytearray()
    payload += req[0:14]
    payload += struct.pack('<H', 1)  # RR=1
    payload += NETMAN_VERSION
    payload += b"OK\x00"
    payload += b"OK\x00"
    payload += b"On Line\x00"
    payload += struct.pack('<H', 0)
    return bytes(payload)


def build_netman_devdata_response(req):
    """Type 4: GET_DEVDATA. SunVision reads SENTR-format data starting at offset 112.

    Format (big-endian words, scale = value * 10 for V/A):
      b[112..113] = SYSTEMTEMP (°C)
      b[114..115] = OUTPUTVOLTAGE (V × 10)
      b[116..117] = OUTPUTVOLTAGE2
      b[118..119] = OUTPUTVOLTAGE3
      b[120..121] = OUTPUTCURRENT (A × 10)
      b[122..123] = OUTPUTCURRENT2
      b[124..125] = OUTPUTCURRENT3
      b[126..127] = CURRENTTOGRID
      b[128..129] = CURRENTTOGRID2
      b[130..131] = CURRENTTOGRID3
      b[132..133] = INPUTVOLTAGE (V × 10)
      b[134..135] = INPUTVOLTAGE2
      b[136..137] = INPUTVOLTAGE3
      b[138..139] = INPUTFREQUENCY
      b[140..141] = OUTPUTLOAD
      ...
    """
    # Values from env vars (or hardcoded defaults)
    VPV  = float(os.environ.get('SIM_VPV',  '300'))   # PV input voltage (V)
    IPV  = float(os.environ.get('SIM_IPV',  '5'))     # PV input current (A)
    VAC  = float(os.environ.get('SIM_VAC',  '300'))   # AC output voltage (V)
    IAC  = float(os.environ.get('SIM_IAC',  '5'))     # AC output current (A)
    FREQ = float(os.environ.get('SIM_FREQ', '57'))    # Hz
    POWER_W = int(VPV * IPV * 0.97)
    LOAD_PCT = int(POWER_W / 6000.0 * 1000)  # 0.1% units

    # Header layout (bytes):
    #   req[0:14]              = 14 bytes
    #   RR struct.pack('<H',1) =  2 bytes  (total 16)
    #   NETMAN_VERSION "**0200"=  6 bytes  (total 22)
    #   b"OK\x00"             =  3 bytes  (total 25)
    #   b"Communication OK\x00"= 17 bytes  (total 42)
    #   data_area              starts at byte 42
    # SunVision reads SENTR from byte 112
    # → padding in data_area = 112 - 42 = 70 bytes
    HEADER_SIZE = 42
    SENTR_START = 112
    P = SENTR_START - HEADER_SIZE  # = 70  (padding before SENTR data)

    data_area = bytearray(P + 200)

    def set_word(buf, offset, value):
        """Big-endian 16-bit word."""
        value = max(0, min(0xFFFF, int(value)))
        buf[offset]     = (value >> 8) & 0xFF
        buf[offset + 1] =  value       & 0xFF

    # data_area[P + N] → payload byte [112 + N]
    set_word(data_area, P +  0, 35 * 10)          # b[112] SYSTEMTEMP  (°C × 10)
    set_word(data_area, P +  2, VAC * 10)         # b[114] OUTPUTVOLTAGE (V × 10)
    set_word(data_area, P +  4, VAC * 10)         # b[116] OUTPUTVOLTAGE2
    set_word(data_area, P +  6, VAC * 10)         # b[118] OUTPUTVOLTAGE3
    set_word(data_area, P +  8, IAC * 10)         # b[120] OUTPUTCURRENT (A × 10)
    set_word(data_area, P + 10, IAC * 10)         # b[122] OUTPUTCURRENT2
    set_word(data_area, P + 12, IAC * 10)         # b[124] OUTPUTCURRENT3
    set_word(data_area, P + 14, IAC * 10)         # b[126] CURRENTTOGRID
    set_word(data_area, P + 16, IAC * 10)         # b[128] CURRENTTOGRID2
    set_word(data_area, P + 18, IAC * 10)         # b[130] CURRENTTOGRID3
    set_word(data_area, P + 20, VPV * 10)         # b[132] INPUTVOLTAGE (V × 10)
    set_word(data_area, P + 22, VPV * 10)         # b[134] INPUTVOLTAGE2
    set_word(data_area, P + 24, VPV * 10)         # b[136] INPUTVOLTAGE3
    set_word(data_area, P + 26, FREQ * 100)       # b[138] INPUTFREQUENCY (Hz × 100, SunVision divides by 100)
    set_word(data_area, P + 28, LOAD_PCT)         # b[140] OUTPUTLOAD (0.1 % units)
    set_word(data_area, P + 30, LOAD_PCT)         # b[142] OUTPUTLOAD2
    set_word(data_area, P + 32, LOAD_PCT)         # b[144] OUTPUTLOAD3

    # Identification label in free area
    label = b"SIMULATED-UPS\x00"
    data_area[P + 40: P + 40 + len(label)] = label[:16]

    padding_size = 500  # SunVision reads up to position 760+
    payload = bytearray()
    payload += req[0:14]
    payload += struct.pack('<H', 1)         # RR=1 (non-zero = response)
    payload += NETMAN_VERSION
    payload += b"OK\x00"
    payload += b"Communication OK\x00"
    payload += data_area
    payload += bytearray(padding_size)
    return bytes(payload)


def build_netman_browsedata_response(req, src_ip, device_no, port):
    """Type 16: GET_BROWSEDATA. SunVision asks who is on the network."""
    version = b"SunVision 1.9.3\x00"
    platform = b"Riello NetMan\x00"
    # Placeholder; SunVision overwrites with source IP/port
    ip_str = b"0.0.0.0\x00"
    name2 = b"SIMULATED-UPS\x00"
    serial = b"AA-BB-CC-12345\x00"
    our_device_no = 1

    # SunVision parses from offset 16 (not 22). The "**0200" version code
    # is included INSIDE the Version field as the first 6 bytes.
    # Bytes 14-15 (RR) must be NON-ZERO in response, else SunVision treats it as a request
    payload = bytearray()
    payload += req[0:14]                # bytes 0-13: type, dev, zeros, pwd
    payload += struct.pack('<H', 1)     # bytes 14-15: RR=1 (must be != 0 for response)
    payload += NETMAN_VERSION           # 6 bytes of "**0200" - will be part of Version
    payload += version[6:].ljust(26, b'\x00')  # 26 bytes = 32-6
    payload += platform.ljust(72, b'\x00')[:72]
    payload += ip_str.ljust(20, b'\x00')[:20]
    # No port field in buffer - SunVision uses src port
    payload += name2.ljust(20, b'\x00')[:20]
    payload += bytes([22])  # DevType
    payload += bytes([2])   # CommType
    payload += serial.ljust(16, b'\x00')[:16]
    payload += struct.pack('<H', our_device_no)
    payload += b"SENTR 3/3 6kVA\x00".ljust(20, b'\x00')[:20]
    payload += b"OK\x00".ljust(30, b'\x00')[:30]
    payload += b"On Line\x00".ljust(30, b'\x00')[:30]
    payload += struct.pack('<H', 0)
    payload += bytes([0])
    return bytes(payload)


def build_netman_error_response(req, error_code):
    """Type 250: RS_ERROR."""
    payload = bytearray()
    payload += req[0:16]
    payload += NETMAN_VERSION
    payload += struct.pack('<H', 250)
    payload += struct.pack('<H', error_code)
    return bytes(payload)


def handle_netman_packet(data, addr, device_state):
    if len(data) < 16:
        return None

    req_type = data[0] + (data[1] << 8) if len(data) >= 2 else 0
    device_no = data[2] + (data[3] << 8) if len(data) >= 4 else 0
    password = data[12] + (data[13] << 8) if len(data) >= 14 else 0
    rr = data[14] + (data[15] << 8) if len(data) >= 16 else 0
    version = data[16:22] if len(data) >= 22 else b""

    log("NETMAN", f"<- from {addr[0]}:{addr[1]} type={req_type} dev={device_no} pwd=0x{password:04X} rr={rr} ver={version}")

    # Skip our own responses (when simulator receives its own broadcast back via Docker)
    if rr != 0:
        log("NETMAN", f"  -> Skipping response packet (RR={rr})")
        return None

    if password != NETMAN_PASSWORD:
        log("NETMAN", f"  -> Bad password 0x{password:04X}, sending error")
        return build_netman_error_response(data, 4)

    if req_type == 1:
        return build_netman_identif_response(data, addr, device_no)
    elif req_type == 3:
        return build_netman_status_response(data)
    elif req_type == 4:
        return build_netman_devdata_response(data)
    elif req_type == 16:
        return build_netman_browsedata_response(data, addr[0], device_no, NETMAN_UDP_PORT)
    elif req_type == 5:
        return build_netman_status_response(data)
    elif req_type == 7:
        return build_netman_status_response(data)
    elif req_type == 14:
        return build_netman_status_response(data)
    elif req_type == 15:
        return build_netman_status_response(data)
    elif req_type == 250:
        return build_netman_error_response(data, 0)
    else:
        log("NETMAN", f"  -> Unknown type {req_type}, sending error")
        return build_netman_error_response(data, 3)


def run_netman_server(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.settimeout(1.0)
    log("START", f"NetMan UDP server en {host}:{port}")
    log("START", f"Para SunVision: Network NetMan -> {host}:{port}")
    log("START", f"Protocol version: {NETMAN_VERSION.decode()}")

    while True:
        try:
            data, addr = sock.recvfrom(2048)
            response = handle_netman_packet(data, addr, {})
            if response:
                sock.sendto(response, addr)
                log("NETMAN", f"-> sent {len(response)} bytes to {addr[0]}:{addr[1]}")
        except TimeoutError:
            continue
        except Exception as e:
            log("ERROR", f"NetMan error: {e}")

# ═══════════════════════════════════════════════════════════════
# SISER Serial Protocol (Propietario Riello — Descubierto por decompilación)
# ═══════════════════════════════════════════════════════════════

SISER_SYNC = 0xAA            # Frame sync byte (×2)
SISER_DEVICE_ADDR = 1        # Default device address on the bus
SISER_SERIAL_NUMBER = b"AA-BB-CC-1234\x00\x00\x00"  # 16 bytes
SISER_MODEL = b"SENTR 3/3 6kVA\x00\x00"             # 16 bytes


def siser_checksum_calc(data, length):
    """Phoenixtec checksum: sum of all bytes except last 2."""
    return sum(data[:length - 2]) & 0xFFFF


def siser_checksum_set(data):
    """Set the last 2 bytes to the Phoenixtec checksum."""
    total = siser_checksum_calc(data, len(data))
    data[-2] = (total >> 8) & 0xFF
    data[-1] = total & 0xFF
    return data


def siser_checksum_verify(data, length):
    """Verify Phoenixtec checksum."""
    total = siser_checksum_calc(data, length)
    expected_h = data[length - 2] & 0xFF
    expected_l = data[length - 1] & 0xFF
    return ((total >> 8) & 0xFF == expected_h) and (total & 0xFF == expected_l)


def siser_build_header(addr, group, cmd, data_len):
    """Build a SISER response frame header (9 bytes + data + 2 checksum)."""
    frame = bytearray(9 + data_len + 2)
    frame[0] = SISER_SYNC
    frame[1] = SISER_SYNC
    frame[2] = 0x01
    frame[3] = 0x00
    frame[4] = 0x00
    frame[5] = addr & 0xFF
    frame[6] = group & 0xFF
    frame[7] = cmd & 0xFF
    frame[8] = data_len & 0xFF
    return frame


def siser_build_offline_response(addr):
    """Respond to offlineEnquiry (group=0, cmd=0). Return serial number."""
    serial = SISER_SERIAL_NUMBER[:10]
    frame = siser_build_header(addr, 0, 0x80, len(serial))
    frame[9:9 + len(serial)] = serial
    siser_checksum_set(frame)
    log("SISER", f"  -> offlineEnquiry response (serial={serial[:10]})")
    return bytes(frame)


def siser_build_address_response(addr):
    """Respond to sendAddress/registration (group=0, cmd=1). Confirm with code=6 (OK)."""
    frame = siser_build_header(addr, 0, 0x81, 1)
    frame[9] = 6  # OK confirmation code
    siser_checksum_set(frame)
    log("SISER", f"  -> sendAddress confirmed addr={addr}")
    return bytes(frame)


def siser_build_reregistration_response(addr):
    """Respond to reRegistration (group=0, cmd=4)."""
    frame = siser_build_header(addr, 0, 0x81, 1)
    frame[9] = 6
    siser_checksum_set(frame)
    log("SISER", f"  -> reRegistration confirmed addr={addr}")
    return bytes(frame)


def siser_build_readid_response(addr):
    """Respond to readID (group=1, cmd=3). Return device identification."""
    # Response: group=1, cmd=0x83 (-125 signed), data = 73 bytes
    data_len = 73
    frame = siser_build_header(addr, 1, 0x83, data_len)

    # [9]     IOCONFIGURATION = 0 (single input)
    frame[9] = 0

    # [10-15] NOMINALPOWERVA in BCD (6 bytes) = "006000" = 6000VA
    bcd_va = b"006000"
    frame[10:16] = bcd_va

    # [16-20] UPSSWVERSION (5 bytes) = "1.9.3"
    frame[16:21] = b"1.9.3"

    # [21-36] UPSMODEL (16 bytes)
    model = b"SENTR 3/3 6kVA\x00\x00"
    frame[21:37] = model[:16]

    # [37-52] padding (16 bytes)
    # Already zeros

    # [53-68] FULLSERIAL (16 bytes)
    frame[53:69] = SISER_SERIAL_NUMBER[:16]

    # [69-72] NOMINALPOWERW in BCD (4 bytes) = "6000" = 6000W
    frame[69:73] = b"6000"

    siser_checksum_set(frame)
    log("SISER", f"  -> readID response (model={model.rstrip(b'\\x00').decode()}, serial={SISER_SERIAL_NUMBER[:14]})")
    return bytes(frame)


def siser_build_readmichele_response(addr):
    """Respond to readMichele (group=1, cmd=0x10). Return measurement data.

    This is the SENTR 3/3 trifásico response (cmd=0x90).
    Data offsets from byte 9 of the response.
    All values are big-endian 16-bit words.
    """
    VPV  = float(os.environ.get('SIM_VPV',  '300'))
    IPV  = float(os.environ.get('SIM_IPV',  '5'))
    VAC  = float(os.environ.get('SIM_VAC',  '300'))
    IAC  = float(os.environ.get('SIM_IAC',  '5'))
    FREQ = float(os.environ.get('SIM_FREQ', '57'))
    POWER_W = int(VPV * IPV * 0.97)
    LOAD_PCT = int(POWER_W / 6000.0 * 1000)  # 0.1% units

    # Data area = 66 bytes (up to byte 74 relative to offset 9)
    data_len = 66
    frame = siser_build_header(addr, 1, 0x90, data_len)  # 0x90 = trifásico

    def set_word(buf, offset, value):
        """Big-endian 16-bit word at given offset."""
        value = max(0, min(0xFFFF, int(value)))
        buf[offset]     = (value >> 8) & 0xFF
        buf[offset + 1] =  value       & 0xFF

    D = 9  # Data starts at byte 9

    set_word(frame, D + 0,  int(35 * 10))       # [9-10]  SYSTEMTEMP (°C × 10)
    set_word(frame, D + 2,  int(VAC * 10))       # [11-12] OUTPUTVOLTAGE (V × 10)
    set_word(frame, D + 4,  int(VAC * 10))       # [13-14] OUTPUTVOLTAGE2
    set_word(frame, D + 6,  int(VAC * 10))       # [15-16] OUTPUTVOLTAGE3
    set_word(frame, D + 8,  int(IAC * 10))       # [17-18] OUTPUTCURRENT (A × 10)
    set_word(frame, D + 10, int(IAC * 10))       # [19-20] OUTPUTCURRENT2
    set_word(frame, D + 12, int(IAC * 10))       # [21-22] OUTPUTCURRENT3
    set_word(frame, D + 14, int(IAC * 10))       # [23-24] CURRENTTOGRID
    set_word(frame, D + 16, int(IAC * 10))       # [25-26] CURRENTTOGRID2
    set_word(frame, D + 18, int(IAC * 10))       # [27-28] CURRENTTOGRID3
    set_word(frame, D + 20, int(VPV * 10))       # [29-30] INPUTVOLTAGE (V × 10)
    set_word(frame, D + 22, int(VPV * 10))       # [31-32] INPUTVOLTAGE2
    set_word(frame, D + 24, int(VPV * 10))       # [33-34] INPUTVOLTAGE3
    set_word(frame, D + 26, int(FREQ * 100))     # [35-36] INPUTFREQUENCY (Hz × 100)
    set_word(frame, D + 28, LOAD_PCT)            # [37-38] OUTPUTLOAD (0.1% units)
    set_word(frame, D + 30, LOAD_PCT)            # [39-40] OUTPUTLOAD2
    set_word(frame, D + 32, LOAD_PCT)            # [41-42] OUTPUTLOAD3
    set_word(frame, D + 34, 0)                   # [43-44] GRIDIMPEDANCE
    set_word(frame, D + 36, 0)                   # [45-46] GRIDIMPEDANCE2
    set_word(frame, D + 38, 0)                   # [47-48] GRIDIMPEDANCE3
    # [49-52] BATTERYESTCHARG (2 words) = energy estimate
    set_word(frame, D + 40, 0)
    set_word(frame, D + 42, 0)
    # [53-56] BATTERYESTTIME (2 words) = time estimate
    set_word(frame, D + 44, 0)
    set_word(frame, D + 46, 0)
    # [58] STATUSCODE: 0=wait, 1=normal, 2=fault, 3=permFault
    frame[D + 49] = 1  # normal

    siser_checksum_set(frame)
    log("SISER", f"  -> readMichele response: Vac={VAC}V Iac={IAC}A Vpv={VPV}V Freq={FREQ}Hz")
    return bytes(frame)


def handle_siser_frame(data, length):
    """Parse and respond to a SISER frame."""
    if length < 11:
        log("SISER", f"  Frame too short: {length} bytes")
        return None

    # Verify header
    if data[0] != SISER_SYNC or data[1] != SISER_SYNC:
        log("SISER", f"  Bad sync: {data[0]:02X} {data[1]:02X}")
        return None

    # Verify checksum
    if not siser_checksum_verify(data, length):
        log("SISER", f"  Checksum FAIL (len={length})")
        return None

    addr = data[5] & 0xFF
    group = data[6] & 0xFF
    cmd = data[7] & 0xFF
    dlen = data[8] & 0xFF

    log("SISER", f"<- addr={addr} group={group} cmd=0x{cmd:02X} dlen={dlen}")

    # offlineEnquiry: group=0, cmd=0
    if group == 0 and cmd == 0:
        return siser_build_offline_response(addr)

    # sendAddress (registration): group=0, cmd=1
    if group == 0 and cmd == 1:
        return siser_build_address_response(addr)

    # reRegistration: group=0, cmd=4
    if group == 0 and cmd == 4:
        return siser_build_reregistration_response(addr)

    # readID: group=1, cmd=3
    if group == 1 and cmd == 3:
        return siser_build_readid_response(addr)

    # readMichele: group=1, cmd=0x10 (16)
    if group == 1 and cmd == 0x10:
        return siser_build_readmichele_response(addr)

    # Unknown command — log but don't respond (real inverter would ignore)
    log("SISER", f"  -> Unknown command group={group} cmd=0x{cmd:02X}, ignoring")
    return None


def run_siser_server(host, port):
    """Run SISER serial protocol server over TCP.

    SunVision connects via socat bridge:
      socat PTY,link=/dev/ttyS0 TCP:inverter-simulator:PORT

    The TCP stream carries raw serial bytes (no framing beyond SISER).
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    log("START", f"SISER serial server en {host}:{port}")
    log("START", "Protocolo: SISER propietario Riello")
    log("START", f"Para SunVision: commtype=0, socat PTY↔TCP:{host}:{port}")

    while True:
        conn, addr = server.accept()
        log("SISER", f"Client connected from {addr[0]}:{addr[1]}")
        t = threading.Thread(target=handle_siser_client, args=(conn, addr), daemon=True)
        t.start()


def handle_siser_client(conn, addr):
    """Handle a single SISER client connection (from socat bridge)."""
    buffer = bytearray()
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break

            buffer.extend(data)

            # Process all complete frames in the buffer
            while len(buffer) >= 11:
                # Look for sync bytes 0xAA 0xAA
                sync_pos = -1
                for i in range(len(buffer) - 1):
                    if buffer[i] == SISER_SYNC and buffer[i + 1] == SISER_SYNC:
                        sync_pos = i
                        break

                if sync_pos < 0:
                    # No sync found, discard buffer
                    buffer.clear()
                    break

                # Discard bytes before sync
                if sync_pos > 0:
                    buffer = buffer[sync_pos:]

                # Need at least 11 bytes for a minimal frame
                if len(buffer) < 11:
                    break

                # Get data length from byte 8
                dlen = buffer[8] & 0xFF
                frame_len = 9 + dlen + 2  # header(9) + data(dlen) + checksum(2)

                if len(buffer) < frame_len:
                    break  # Wait for more data

                frame = bytes(buffer[:frame_len])
                buffer = buffer[frame_len:]

                response = handle_siser_frame(bytearray(frame), frame_len)
                if response:
                    conn.sendall(response)
                    log("SISER", f"-> sent {len(response)} bytes")

    except (ConnectionResetError, BrokenPipeError):
        log("SISER", f"Client {addr[0]}:{addr[1]} disconnected")
    except Exception as e:
        log("ERROR", f"SISER client error: {e}")
    finally:
        conn.close()
        log("SISER", f"Client {addr[0]}:{addr[1]} closed")


def main():
    parser = argparse.ArgumentParser(description='Simulador Modbus + NetMan + SISER Riello H.P.6065REL-D')
    parser.add_argument('--mode', choices=['tcp', 'qemu', 'client', 'server', 'netman', 'siser'], default='qemu',
                        help='Modo: tcp (Modbus TCP), qemu/server (RTU over TCP), client (QEMU serial), netman (UDP NetMan), siser (SISER serial over TCP)')
    parser.add_argument('--host', default='0.0.0.0', help='Host para escuchar')
    parser.add_argument('--port', type=int, default=5502, help='Puerto TCP')
    parser.add_argument('--baud', type=int, default=9600, help='Baudrate (info)')
    parser.add_argument('--slave', type=int, default=1, help='Slave address')
    args = parser.parse_args()

    env_mode = os.environ.get('SIMULATOR_MODE', '')
    env_port = os.environ.get('SIMULATOR_PORT', '')
    env_host = os.environ.get('SIMULATOR_HOST', '')
    if env_mode:
        args.mode = env_mode
    if env_port:
        args.port = int(env_port)
    if env_host:
        args.host = env_host

    log("START", "=" * 60)
    log("START", "Simulador Riello H.P.6065REL-D")
    log("START", "=" * 60)
    log("START", f"Modo:     {args.mode}")
    log("START", f"Host:     {args.host}")
    log("START", f"Puerto:   {args.port}")
    log("START", f"Baudrate: {args.baud}")
    log("START", f"Slave:    {args.slave}")
    log("START", "")

    init_registers()

    update_thread = threading.Thread(target=update_loop, daemon=True)
    update_thread.start()
    log("START", "Thread de actualizacion iniciado")

    if args.mode == 'tcp':
        run_tcp_server(args.host, args.port)
    elif args.mode == 'netman':
        run_netman_server(args.host, NETMAN_UDP_PORT)
    elif args.mode == 'siser':
        siser_port = int(os.environ.get('SISER_PORT', args.port or 5504))
        run_siser_server(args.host, siser_port)
    elif args.mode == 'client':
        run_qemu_client(args.host, args.port)
    else:
        run_qemu_server(args.host, args.port)


if __name__ == '__main__':
    main()
