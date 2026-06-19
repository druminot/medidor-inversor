#!/usr/bin/env python3
import sys
import time

import serial as pyserial

PORT = '/dev/ttyUSB0'
BAUD = 9600
ADDR = 33

def siser_checksum(frame):
    cs = sum(frame[:-2]) & 0xFFFF
    frame[-2] = (cs >> 8) & 0xFF
    frame[-1] = cs & 0xFF
    return frame

def send_cmd(ser, frame, timeout=5.0):
    time.sleep(0.6)
    ser.setRTS(True)
    time.sleep(0.01)
    ser.reset_input_buffer()
    ser.write(bytes([0x02]))
    time.sleep(0.01)
    ser.write(bytes(frame))
    time.sleep(0.05)
    ser.setRTS(False)

    old_timeout = ser.timeout
    ser.timeout = 0.02
    resp = bytearray()
    start = time.time()
    while time.time() - start < timeout:
        chunk = ser.read(512)
        if chunk:
            resp.extend(chunk)
        elif resp:
            time.sleep(0.05)
            chunk = ser.read(512)
            if chunk:
                resp.extend(chunk)
            break
    ser.timeout = old_timeout

    if resp and resp[0] == 0x02 and len(resp) > 1:
        resp = resp[1:]
    return bytes(resp) if resp else b''

for attempt in range(5):
    print(f'\n=== Attempt {attempt+1}/5 ===')
    ser = pyserial.Serial(PORT, BAUD, bytesize=8, parity='N', stopbits=1, timeout=5)
    ser.setDTR(True)
    ser.setRTS(False)
    time.sleep(2.0)
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    # Try DTR toggle
    ser.setDTR(False)
    time.sleep(1.0)
    ser.setDTR(True)
    time.sleep(1.0)

    # offlineEnquiry
    frame = bytearray([0xAA, 0xAA, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    siser_checksum(frame)
    resp = send_cmd(ser, frame, timeout=3.0)

    if resp and len(resp) >= 19 and resp[0] == 0xAA and resp[1] == 0xAA:
        dlen = resp[8]
        serial_data = resp[9:9+dlen]
        serial_str = serial_data[:10].decode('ascii', errors='replace').rstrip('\x00')
        print(f'  SERIAL: {serial_str}')

        # sendAddress
        serial_number = serial_data[:10]
        frame = bytearray(22)
        frame[0] = 0xAA; frame[1] = 0xAA; frame[2] = 0x01
        frame[3] = 0x00; frame[4] = 0x00
        frame[5] = 0x00; frame[6] = 0x00; frame[7] = 0x01; frame[8] = 11
        for i in range(10):
            frame[9+i] = serial_number[i]
        frame[19] = ADDR
        siser_checksum(frame)
        resp2 = send_cmd(ser, frame, timeout=3.0)

        if resp2 and len(resp2) >= 10:
            print(f'  sendAddress: {resp2.hex()} (code={resp2[9] if len(resp2) > 9 else "N/A"})')

        # readMichele
        frame = bytearray([0xAA, 0xAA, 0x01, 0x00, 0x00, ADDR, 0x01, 0x10, 0x00, 0x00, 0x00])
        siser_checksum(frame)
        resp4 = send_cmd(ser, frame, timeout=3.0)

        if resp4 and len(resp4) > 10 and resp4[0] == 0xAA and resp4[1] == 0xAA:
            print(f'  readMichele: {len(resp4)} bytes')
            print(f'  RAW: {resp4.hex()}')
            # Parse using SISERBus.java offsets
            def w(h_off):
                if h_off + 1 < len(resp4):
                    v = resp4[h_off] * 256 + resp4[h_off+1]
                    return None if v >= 0xFFFF else v
                return None

            temp = w(9)
            pv_v1 = w(11)
            pv_v2 = w(13)
            pv_v3 = w(15)
            pv_i1 = w(17)
            pv_i2 = w(19)
            pv_i3 = w(21)
            grid_i1 = w(23)
            grid_i2 = w(25)
            grid_i3 = w(27)
            grid_v1 = w(29)
            grid_v2 = w(31)
            grid_v3 = w(33)
            grid_freq = w(35)
            power1 = w(37)
            power2 = w(39)
            power3 = w(41)
            status = resp4[58] if len(resp4) > 58 else None

            def fmt(v, div, unit):
                return f'{v/div:.1f}{unit}' if v is not None else 'N/A'

            print(f'  Temp:     {fmt(temp, 10, "C")}')
            print(f'  PV V L1:  {fmt(pv_v1, 10, "V")}')
            print(f'  PV V L2:  {fmt(pv_v2, 10, "V")}')
            print(f'  PV V L3:  {fmt(pv_v3, 10, "V")}')
            print(f'  PV I L1:  {fmt(pv_i1, 10, "A")}')
            print(f'  PV I L2:  {fmt(pv_i2, 10, "A")}')
            print(f'  PV I L3:  {fmt(pv_i3, 10, "A")}')
            print(f'  Grid I L1:{fmt(grid_i1, 10, "A")}')
            print(f'  Grid V L1:{fmt(grid_v1, 10, "V")}')
            print(f'  Grid V L2:{fmt(grid_v2, 10, "V")}')
            print(f'  Grid V L3:{fmt(grid_v3, 10, "V")}')
            print(f'  Freq:     {fmt(grid_freq, 100, "Hz")}')
            print(f'  Power L1: {fmt(power1, 10, "W")}')
            print(f'  Status:    {status}')

            ser.close()
            print('\nSUCCESS!')
            sys.exit(0)
        else:
            print('  readMichele: no response or invalid')
    else:
        print('  No response to offlineEnquiry')

    ser.close()
    time.sleep(2)

print('\nFailed after 5 attempts')
