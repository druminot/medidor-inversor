#!/usr/bin/env python3
"""
SISER handshake matching SunVision's exact protocol sequence.

KEY DISCOVERY: SunVision sends a STX byte (0x02) BEFORE each SISER command!
Also: RTS=True before TX, RTS=False after TX, 600ms delay before each command.

Byte offsets from decompiled SISERBus.java (word = big-endian: h*256+l):
  readMichele triphase data starts at resp[9]:
    SYSTEMTEMP       = word(resp[9],  resp[10])  /10  -> C
    OUTPUTVOLTAGE    = word(resp[11], resp[12])  /10  -> PV V L1
    OUTPUTVOLTAGE2   = word(resp[13], resp[14])  /10  -> PV V L2
    OUTPUTVOLTAGE3   = word(resp[15], resp[16])  /10  -> PV V L3
    OUTPUTCURRENT    = word(resp[17], resp[18])  /10  -> PV I L1
    OUTPUTCURRENT2   = word(resp[19], resp[20])  /10  -> PV I L2
    OUTPUTCURRENT3   = word(resp[21], resp[22])  /10  -> PV I L3
    CURRENTTOGRID    = word(resp[23], resp[24])  /10  -> Grid I L1
    CURRENTTOGRID2   = word(resp[25], resp[26])  /10  -> Grid I L2
    CURRENTTOGRID3   = word(resp[27], resp[28])  /10  -> Grid I L3
    INPUTVOLTAGE     = word(resp[29], resp[30])  /10  -> Grid V L1
    INPUTVOLTAGE2    = word(resp[31], resp[32])  /10  -> Grid V L2
    INPUTVOLTAGE3    = word(resp[33], resp[34])  /10  -> Grid V L3
    INPUTFREQUENCY   = word(resp[35], resp[36])  /100 -> Hz
    OUTPUTLOAD       = word(resp[37], resp[38])  /10  -> Power L1
    OUTPUTLOAD2      = word(resp[39], resp[40])  /10  -> Power L2
    OUTPUTLOAD3      = word(resp[41], resp[42])  /10  -> Power L3
    GRIDIMPEDANCE    = word(resp[43], resp[44])  /10  -> Ohm L1
    GRIDIMPEDANCE2   = word(resp[45], resp[46])  /10  -> Ohm L2
    GRIDIMPEDANCE3   = word(resp[47], resp[48])  /10  -> Ohm L3
    BATTERYESTCHARG  = (word(resp[49],resp[50])<<16)+word(resp[51],resp[52]) -> Total Energy (Wh)
    BATTERYESTTIME   = (word(resp[53],resp[54])<<16)+word(resp[55],resp[56]) -> Total Hours
    STATUSCODE       = resp[58]  (0=wait, 1=normal, 2=fault, 3=permanent fault)

  0xFFFF = not connected / invalid

  readID data starts at resp[9]:
    IOCONFIGURATION  = resp[9]
    NOMINALPOWERVA  = BCD binary resp[10..15]
    UPSSWVERSION    = resp[16..20]
    UPSMODEL        = resp[21..36]
    FULLSERIAL      = resp[53..68]
    NOMINALPOWERW   = BCD binary resp[69..72]
"""
import sys
import time

import serial as pyserial


def siser_checksum(frame):
    cs = sum(frame[:-2]) & 0xFFFF
    frame[-2] = (cs >> 8) & 0xFF
    frame[-1] = cs & 0xFF
    return frame

def send_siser_command(ser, frame, label, timeout=5.0):
    sys.stdout.write(f'  [{label}] TX: {bytes(frame).hex()} ({len(frame)} bytes)\n')
    sys.stdout.flush()

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

    if resp:
        if resp[0] == 0x02 and len(resp) > 1:
            resp = resp[1:]

        sys.stdout.write(f'  [{label}] RX: {bytes(resp).hex()} ({len(resp)} bytes)\n')
        if len(resp) >= 2 and resp[0] == 0xAA and resp[1] == 0xAA and len(resp) > 8:
            cmd = resp[7]
            dlen = resp[8]
            data = resp[9:9+dlen] if len(resp) >= 9+dlen else resp[9:]
            ascii_str = data.decode('ascii', errors='replace').rstrip('\x00') if data else ''
            sys.stdout.write(f'    cmd={cmd:02X} dlen={dlen}\n')
            if ascii_str and dlen < 30:
                sys.stdout.write(f'    ASCII: {ascii_str}\n')
            if cmd == 0x80:
                sys.stdout.write('    >>> offlineEnquiry RESPONSE <<<\n')
            elif cmd == 0x81:
                code = data[0] if dlen >= 1 else -1
                sys.stdout.write(f'    >>> sendAddress RESPONSE (code={code}) <<<\n')
            elif cmd == 0x83:
                sys.stdout.write('    >>> readID RESPONSE <<<\n')
            elif cmd == 0x90:
                sys.stdout.write('    >>> readMichele TRIPHASE <<<\n')
            elif cmd == 0x82:
                sys.stdout.write('    >>> readMichele MONOPHASE <<<\n')
    else:
        sys.stdout.write(f'  [{label}] No response\n')
    sys.stdout.flush()
    return bytes(resp) if resp else b''

def word(d, h_off, l_off):
    return (d[h_off] * 256 + d[l_off]) if max(h_off, l_off) < len(d) else 0

def parse_michele_triphase(resp):
    if len(resp) < 60:
        return None
    INVALID = 0xFFFF
    def w(h_off):
        v = word(resp, h_off, h_off+1)
        return None if v >= INVALID else v

    result = {
        'system_temp':      w(9),
        'pv_voltage_l1':    w(11),
        'pv_voltage_l2':    w(13),
        'pv_voltage_l3':    w(15),
        'pv_current_l1':    w(17),
        'pv_current_l2':    w(19),
        'pv_current_l3':    w(21),
        'grid_current_l1':  w(23),
        'grid_current_l2':  w(25),
        'grid_current_l3':  w(27),
        'grid_voltage_l1':  w(29),
        'grid_voltage_l2':  w(31),
        'grid_voltage_l3':  w(33),
        'grid_frequency':   w(35),
        'power_l1':         w(37),
        'power_l2':         w(39),
        'power_l3':         w(41),
        'grid_impedance_l1': w(43),
        'grid_impedance_l2': w(45),
        'grid_impedance_l3': w(47),
        'status_code':      resp[58] if len(resp) > 58 else None,
    }

    total_energy = None
    if len(resp) >= 53:
        te = (word(resp, 49, 50) << 16) + word(resp, 51, 52)
        if te != 0xFFFFFFFF and te != 0:
            total_energy = te
    result['total_energy_wh'] = total_energy

    total_hours = None
    if len(resp) >= 57:
        th = (word(resp, 53, 54) << 16) + word(resp, 55, 56)
        if th != 0xFFFFFFFF and th != 0:
            total_hours = th
    result['total_operating_hours'] = total_hours

    return result

ADDR = 33
PORT = '/dev/ttyUSB0'
BAUD = 9600

print(f'\n{"#"*60}')
print('# SISER Handshake with STX byte (SunVision exact match)')
print('# DTR=True, RTS toggle, STX=0x02 before each command')
print('# 600ms inter-command delay')
print(f'{"#"*60}\n')

ser = pyserial.Serial(PORT, BAUD, bytesize=8, parity='N', stopbits=1, timeout=5)
ser.setDTR(True)
ser.setRTS(False)
time.sleep(2.0)
ser.reset_input_buffer()
ser.reset_output_buffer()

print('=== Step 1: offlineEnquiry (addr=0) ===')
frame = bytearray([0xAA, 0xAA, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
siser_checksum(frame)
resp1 = send_siser_command(ser, frame, 'offline', timeout=5.0)

serial_number = None
if resp1 and len(resp1) >= 19 and resp1[0] == 0xAA and resp1[1] == 0xAA:
    dlen = resp1[8]
    serial_data = resp1[9:9+dlen]
    serial_number = serial_data[:10]
    serial_str = serial_data.decode('ascii', errors='replace').rstrip('\x00')
    print(f'\n  >>> SERIAL: {serial_str}')
    print(f'  >>> SERIAL BYTES: {serial_number.hex()}')

if not serial_number:
    print('\n  No response to offlineEnquiry.')
    print('  Trying with DTR toggle...')
    ser.setDTR(False)
    time.sleep(2.0)
    ser.setDTR(True)
    time.sleep(2.0)
    ser.reset_input_buffer()
    resp1 = send_siser_command(ser, frame, 'offline_retry', timeout=5.0)
    if resp1 and len(resp1) >= 19 and resp1[0] == 0xAA and resp1[1] == 0xAA:
        dlen = resp1[8]
        serial_data = resp1[9:9+dlen]
        serial_number = serial_data[:10]
        serial_str = serial_data.decode('ascii', errors='replace').rstrip('\x00')
        print(f'\n  >>> SERIAL: {serial_str}')
        print(f'  >>> SERIAL BYTES: {serial_number.hex()}')

if serial_number:
    print(f'\n=== Step 2: sendAddress (assign addr={ADDR}) ===')
    frame = bytearray(22)
    frame[0] = 0xAA; frame[1] = 0xAA; frame[2] = 0x01
    frame[3] = 0x00; frame[4] = 0x00
    frame[5] = 0x00
    frame[6] = 0x00
    frame[7] = 0x01
    frame[8] = 11
    for i in range(10):
        frame[9+i] = serial_number[i]
    frame[19] = ADDR
    siser_checksum(frame)
    resp2 = send_siser_command(ser, frame, f'sendAddress(addr={ADDR})', timeout=5.0)

    if resp2 and len(resp2) >= 10 and resp2[7] == 0x81:
        code = resp2[9] if len(resp2) > 9 else -1
        print(f'\n  >>> sendAddress code={code} (expected 6=OK)')

    print(f'\n=== Step 3: readID (addr={ADDR}) ===')
    frame = bytearray([0xAA, 0xAA, 0x01, 0x00, 0x00, ADDR, 0x01, 0x03, 0x00, 0x00, 0x00])
    siser_checksum(frame)
    resp3 = send_siser_command(ser, frame, f'readID(addr={ADDR})', timeout=5.0)

    if resp3 and len(resp3) > 9 and resp3[0] == 0xAA and resp3[1] == 0xAA:
        dlen = resp3[8]
        data = resp3[9:9+dlen] if len(resp3) >= 9+dlen else resp3[9:]
        if dlen >= 1:
            io_config = data[0]
            print('\n  >>> INVERTER IDENTIFICATION <<<')
            print(f'  IO Config: {io_config} (0x{io_config:02X})')
        if dlen >= 7:
            nominal_va = data[1:7].decode('ascii', errors='replace').rstrip('\x00')
            print(f'  Nominal VA: {nominal_va}')
        if dlen >= 12:
            firmware = data[7:12].decode('ascii', errors='replace').rstrip('\x00')
            print(f'  Firmware: {firmware}')
        if dlen >= 28:
            model = data[12:28].decode('ascii', errors='replace').rstrip('\x00')
            print(f'  Model: {model}')
        if dlen >= 60:
            full_serial = data[44:60].decode('ascii', errors='replace').rstrip('\x00')
            print(f'  Full Serial: {full_serial}')
        if dlen >= 64:
            nominal_w = data[60:64].decode('ascii', errors='replace').rstrip('\x00')
            print(f'  Nominal W: {nominal_w}')

    print(f'\n=== Step 4: readMichele triphase (addr={ADDR}) ===')
    frame = bytearray([0xAA, 0xAA, 0x01, 0x00, 0x00, ADDR, 0x01, 0x10, 0x00, 0x00, 0x00])
    siser_checksum(frame)
    resp4 = send_siser_command(ser, frame, f'readMichele(addr={ADDR})', timeout=5.0)

    if resp4 and len(resp4) > 9 and resp4[0] == 0xAA and resp4[1] == 0xAA:
        m = parse_michele_triphase(resp4)
        if m:
            print('\n  === MEASUREMENTS (SISERBus.java offsets) ===')
            print(f'  System Temp:        {m["system_temp"]/10:.1f} C' if m["system_temp"] is not None else '  System Temp:        N/A')
            print(f'  PV Voltage L1:      {m["pv_voltage_l1"]/10:.1f} V' if m["pv_voltage_l1"] is not None else '  PV Voltage L1:      N/A')
            print(f'  PV Voltage L2:      {m["pv_voltage_l2"]/10:.1f} V' if m["pv_voltage_l2"] is not None else '  PV Voltage L2:      N/A')
            print(f'  PV Voltage L3:      {m["pv_voltage_l3"]/10:.1f} V' if m["pv_voltage_l3"] is not None else '  PV Voltage L3:      N/A')
            print(f'  PV Current L1:      {m["pv_current_l1"]/10:.1f} A' if m["pv_current_l1"] is not None else '  PV Current L1:      N/A')
            print(f'  PV Current L2:      {m["pv_current_l2"]/10:.1f} A' if m["pv_current_l2"] is not None else '  PV Current L2:      N/A')
            print(f'  PV Current L3:      {m["pv_current_l3"]/10:.1f} A' if m["pv_current_l3"] is not None else '  PV Current L3:      N/A')
            print(f'  Grid Current L1:    {m["grid_current_l1"]/10:.1f} A' if m["grid_current_l1"] is not None else '  Grid Current L1:    N/A')
            print(f'  Grid Current L2:    {m["grid_current_l2"]/10:.1f} A' if m["grid_current_l2"] is not None else '  Grid Current L2:    N/A')
            print(f'  Grid Current L3:    {m["grid_current_l3"]/10:.1f} A' if m["grid_current_l3"] is not None else '  Grid Current L3:    N/A')
            print(f'  Grid Voltage L1:    {m["grid_voltage_l1"]/10:.1f} V' if m["grid_voltage_l1"] is not None else '  Grid Voltage L1:    N/A')
            print(f'  Grid Voltage L2:    {m["grid_voltage_l2"]/10:.1f} V' if m["grid_voltage_l2"] is not None else '  Grid Voltage L2:    N/A')
            print(f'  Grid Voltage L3:    {m["grid_voltage_l3"]/10:.1f} V' if m["grid_voltage_l3"] is not None else '  Grid Voltage L3:    N/A')
            print(f'  Grid Frequency:     {m["grid_frequency"]/100:.2f} Hz' if m["grid_frequency"] is not None else '  Grid Frequency:     N/A')
            print(f'  Power L1:           {m["power_l1"]/10:.1f} W' if m["power_l1"] is not None else '  Power L1:           N/A')
            print(f'  Power L2:           {m["power_l2"]/10:.1f} W' if m["power_l2"] is not None else '  Power L2:           N/A')
            print(f'  Power L3:           {m["power_l3"]/10:.1f} W' if m["power_l3"] is not None else '  Power L3:           N/A')
            print(f'  Grid Impedance L1: {m["grid_impedance_l1"]/10:.1f} Ohm' if m["grid_impedance_l1"] is not None else '  Grid Impedance L1: N/A')
            print(f'  Grid Impedance L2: {m["grid_impedance_l2"]/10:.1f} Ohm' if m["grid_impedance_l2"] is not None else '  Grid Impedance L2: N/A')
            print(f'  Grid Impedance L3: {m["grid_impedance_l3"]/10:.1f} Ohm' if m["grid_impedance_l3"] is not None else '  Grid Impedance L3: N/A')
            print(f'  Total Energy:      {m["total_energy_wh"]} Wh' if m["total_energy_wh"] is not None else '  Total Energy:      N/A')
            print(f'  Total Hours:        {m["total_operating_hours"]}' if m["total_operating_hours"] is not None else '  Total Hours:        N/A')
            status_map = {0: 'Wait', 1: 'Normal', 2: 'Fault', 3: 'Permanent Fault'}
            print(f'  Status:              {status_map.get(m["status_code"], "Unknown")} ({m["status_code"]})')

    print('\n=== Step 5: Continuous readMichele (5 iterations) ===')
    for i in range(5):
        frame = bytearray([0xAA, 0xAA, 0x01, 0x00, 0x00, ADDR, 0x01, 0x10, 0x00, 0x00, 0x00])
        siser_checksum(frame)
        resp = send_siser_command(ser, f'readMichele_{i+1}', timeout=5.0)
        if resp and len(resp) > 9 and resp[0] == 0xAA and resp[1] == 0xAA:
            m = parse_michele_triphase(resp)
            if m:
                parts = []
                if m['system_temp'] is not None: parts.append(f'T={m["system_temp"]/10:.1f}C')
                if m['grid_voltage_l1'] is not None: parts.append(f'Vgrid={m["grid_voltage_l1"]/10:.1f}V')
                if m['pv_voltage_l1'] is not None: parts.append(f'Vpv={m["pv_voltage_l1"]/10:.1f}V')
                if m['grid_frequency'] is not None: parts.append(f'F={m["grid_frequency"]/100:.2f}Hz')
                if m['power_l1'] is not None: parts.append(f'P={m["power_l1"]/10:.1f}W')
                if m['status_code'] is not None: parts.append(f'S={m["status_code"]}')
                print(f'    [{i+1}] {" | ".join(parts)}')

ser.close()
print('\n=== DONE ===')
