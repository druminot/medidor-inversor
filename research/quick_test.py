#!/usr/bin/env python3
import serial as pyserial
import time
ser = pyserial.Serial('/dev/ttyUSB0', 9600, timeout=3)
ser.setDTR(True)
ser.setRTS(False)
time.sleep(2)
ser.reset_input_buffer()
ser.setRTS(True)
time.sleep(0.01)
ser.write(bytes([0x02]))
time.sleep(0.01)
cs = sum([0xAA,0xAA,0x01,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00]) & 0xFFFF
frame = bytearray([0xAA,0xAA,0x01,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,(cs>>8)&0xFF,cs&0xFF])
ser.write(bytes(frame))
time.sleep(0.05)
ser.setRTS(False)
time.sleep(3)
r = ser.read(512)
print(f"Response: {r.hex()} ({len(r)} bytes)")
if r:
    if r[0] == 0x02:
        r = r[1:]
    if len(r) >= 2 and r[0] == 0xAA and r[1] == 0xAA:
        print("VALID SISER RESPONSE!")
        if len(r) >= 19:
            dlen = r[8]
            serial = r[9:9+dlen]
            print(f"Serial: {serial.decode('ascii', errors='replace').rstrip(chr(0))}")
ser.close()