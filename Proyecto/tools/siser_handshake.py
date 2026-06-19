#!/usr/bin/env python3
"""
siser_handshake.py — Handshake completo SISER con el inversor Riello H.P.6065REL-D

Secuencia:
1. offlineEnquiry (group=0, cmd=0) → obtener numero de serie
2. sendAddress (group=0, cmd=1) → registrar direccion
3. readID (group=1, cmd=3) → obtener identificacion del inversor
4. readMichele (group=1, cmd=0x10) → obtener datos de mediciones

Uso:
  python3 siser_handshake.py [--port /dev/ttyUSB0] [--baud 9600] [--addr 1]
"""

import argparse
import sys
import time

SISER_SYNC = 0xAA


def siser_checksum(data, length):
    return sum(data[:length - 2]) & 0xFFFF


def siser_checksum_set(frame):
    cs = siser_checksum(frame, len(frame))
    frame[-2] = (cs >> 8) & 0xFF
    frame[-1] = cs & 0xFF
    return frame


def siser_checksum_verify(data, length):
    cs = siser_checksum(data, length)
    return ((cs >> 8) & 0xFF == data[length - 2] & 0xFF) and (cs & 0xFF == data[length - 1] & 0xFF)


def build_frame(addr, group, cmd, data=b''):
    dlen = len(data)
    frame = bytearray(9 + dlen + 2)
    frame[0] = SISER_SYNC
    frame[1] = SISER_SYNC
    frame[2] = 0x01
    frame[3] = 0x00
    frame[4] = 0x00
    frame[5] = addr & 0xFF
    frame[6] = group & 0xFF
    frame[7] = cmd & 0xFF
    frame[8] = dlen & 0xFF
    if data:
        frame[9:9 + dlen] = data
    siser_checksum_set(frame)
    return bytes(frame)


def send_recv(ser, frame, timeout=2.0, label=""):
    if label:
        print(f"\n  TX [{label}]: {frame.hex()} ({len(frame)} bytes)")

    ser.reset_input_buffer()
    ser.reset_output_buffer()
    time.sleep(0.05)

    ser.write(frame)
    time.sleep(0.05)

    old_timeout = ser.timeout
    ser.timeout = timeout

    resp = bytearray()
    start = time.time()
    while time.time() - start < timeout:
        chunk = ser.read(512)
        if chunk:
            resp.extend(chunk)
        elif resp:
            break

    ser.timeout = old_timeout

    if resp:
        print(f"  RX [{label}]: {bytes(resp).hex()} ({len(resp)} bytes)")
        if len(resp) >= 2 and resp[0] == SISER_SYNC and resp[1] == SISER_SYNC:
            if len(resp) > 7:
                dlen = resp[8]
                group = resp[6]
                cmd = resp[7]
                addr = resp[5]
                data = resp[9:9 + dlen] if len(resp) >= 9 + dlen else resp[9:]
                print(f"    SISER: addr={addr:02X} group={group} cmd={cmd:02X} dlen={dlen}")
                if dlen > 0 and data:
                    ascii_str = bytes(data).decode('ascii', errors='replace')
                    if any(c.isalnum() for c in ascii_str):
                        print(f"    Data ASCII: {ascii_str}")
                    print(f"    Data hex: {bytes(data).hex()}")
            if siser_checksum_verify(resp, len(resp)):
                print("    Checksum: OK")
            else:
                print("    Checksum: FAIL")
    else:
        print(f"  RX [{label}]: No response (timeout {timeout}s)")

    return bytes(resp) if resp else b''


def parse_readmichele(data, offset=9):
    """Parse readMichele response data (triphase inverter)."""
    def get_word(buf, pos):
        if pos + 1 < len(buf):
            return (buf[pos] << 8) | buf[pos + 1]
        return 0

    if len(data) < offset + 50:
        print(f"  Data too short for readMichele: {len(data)} bytes (need {offset + 50})")
        return

    print("\n  === MEDICIONES DEL INVERSOR ===")
    print(f"  Temperatura:      {get_word(data, offset + 0) / 10:.1f} °C")
    print(f"  Voltaje AC L1:    {get_word(data, offset + 2) / 10:.1f} V")
    print(f"  Voltaje AC L2:    {get_word(data, offset + 4) / 10:.1f} V")
    print(f"  Voltaje AC L3:    {get_word(data, offset + 6) / 10:.1f} V")
    print(f"  Corriente AC L1:  {get_word(data, offset + 8) / 10:.1f} A")
    print(f"  Corriente AC L2:  {get_word(data, offset + 10) / 10:.1f} A")
    print(f"  Corriente AC L3:  {get_word(data, offset + 12) / 10:.1f} A")
    print(f"  Corriente Grid L1: {get_word(data, offset + 14) / 10:.1f} A")
    print(f"  Corriente Grid L2: {get_word(data, offset + 16) / 10:.1f} A")
    print(f"  Corriente Grid L3: {get_word(data, offset + 18) / 10:.1f} A")
    print(f"  Voltaje DC (PV):  {get_word(data, offset + 20) / 10:.1f} V")
    print(f"  Voltaje DC2:      {get_word(data, offset + 22) / 10:.1f} V")
    print(f"  Voltaje DC3:      {get_word(data, offset + 24) / 10:.1f} V")
    print(f"  Frecuencia:       {get_word(data, offset + 26) / 100:.2f} Hz")
    print(f"  Carga L1:         {get_word(data, offset + 28) / 10:.1f} %")
    print(f"  Carga L2:         {get_word(data, offset + 30) / 10:.1f} %")
    print(f"  Carga L3:         {get_word(data, offset + 32) / 10:.1f} %")
    status_byte = data[offset + 49] if len(data) > offset + 49 else 0
    status_names = {0: "Wait", 1: "Normal", 2: "Fault", 3: "PermFault"}
    print(f"  Estado:           {status_byte} ({status_names.get(status_byte, 'Unknown')})")
    print("  ==============================\n")


def main():
    parser = argparse.ArgumentParser(description='SISER Handshake con inversor Riello')
    parser.add_argument('--port', default='/dev/ttyUSB0', help='Puerto serial')
    parser.add_argument('--baud', type=int, default=9600, help='Baudrate')
    parser.add_argument('--addr', type=int, default=1, help='Direccion SISER (despues de sendAddress)')
    parser.add_argument('--timeout', type=float, default=2.0, help='Timeout en segundos')
    args = parser.parse_args()

    print(f"\n{'#'*60}")
    print("# SISER Handshake - Riello H.P.6065REL-D")
    print(f"# Puerto: {args.port}, Baud: {args.baud}, Timeout: {args.timeout}s")
    print(f"# Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}\n")

    import serial as pyserial
    try:
        ser = pyserial.Serial(args.port, args.baud, bytesize=8, parity='N',
                          stopbits=1, timeout=args.timeout)
    except Exception as e:
        print(f"ERROR abriendo {args.port}: {e}")
        return 1

    # CRITICAL: DTR must be True for Riello SISER protocol
    # RTS must be False (opto-isolated TX enable)
    ser.setDTR(True)
    ser.setRTS(False)
    time.sleep(0.5)

    ser.setDTR(True)
    ser.setRTS(True)
    time.sleep(0.5)

    # Step 1: offlineEnquiry (addr=0)
    print("=" * 60)
    print("PASO 1: offlineEnquiry (descubrir dispositivo)")
    print("=" * 60)
    frame = build_frame(0, 0, 0x00)
    resp = send_recv(ser, frame, args.timeout, "offlineEnquiry addr=0")

    if not resp:
        print("\n  Sin respuesta. Probando con addr=1...")
        frame = build_frame(1, 0, 0x00)
        resp = send_recv(ser, frame, args.timeout, "offlineEnquiry addr=1")

    if not resp:
        print("\nERROR: El inversor no responde. Verificar:")
        print("  - Cable conectado (TX/RX/GND)")
        print("  - Inversor encendido")
        print("  - Baudrate correcto")
        ser.close()
        return 1

    # Parse serial number from response
    if len(resp) > 9:
        dlen = resp[8]
        serial_data = resp[9:9 + dlen]
        try:
            serial_str = serial_data.decode('ascii', errors='replace').rstrip('\x00')
            print(f"\n  >>> NUMERO DE SERIE: '{serial_str}'")
        except Exception:
            print(f"\n  >>> Serial data: {serial_data.hex()}")

    # Step 2: sendAddress (register the device)
    print("\n" + "=" * 60)
    print(f"PASO 2: sendAddress (asignar direccion {args.addr})")
    print("=" * 60)
    frame = build_frame(args.addr, 0, 0x01)
    resp = send_recv(ser, frame, args.timeout, "sendAddress")

    if resp and len(resp) >= 9:
        dlen = resp[8]
        if dlen >= 1:
            code = resp[9] if len(resp) > 9 else 0
            if code == 6:
                print(f"\n  >>> Direccion {args.addr} REGISTRADA! (code=6 OK)")
            else:
                print(f"\n  >>> Codigo de respuesta: {code} (esperado 6)")
    else:
        print("\n  WARNING: Sin respuesta al sendAddress, continuando...")

    time.sleep(0.2)

    # Step 3: readID
    print("\n" + "=" * 60)
    print("PASO 3: readID (identificacion del inversor)")
    print("=" * 60)
    frame = build_frame(args.addr, 1, 0x03)
    resp = send_recv(ser, frame, args.timeout, "readID")

    if resp and len(resp) >= 9:
        dlen = resp[8]
        data = resp[9:9 + dlen]
        print(f"\n  readID data ({dlen} bytes): {data.hex()}")

        # Parse identification fields
        if dlen >= 73:
            io_config = data[0]
            nom_va = data[1:7].decode('ascii', errors='replace').rstrip('\x00')
            fw_ver = data[7:12].decode('ascii', errors='replace').rstrip('\x00')
            model = data[12:28].decode('ascii', errors='replace').rstrip('\x00')
            serial = data[44:60].decode('ascii', errors='replace').rstrip('\x00')
            nom_w = data[60:64].decode('ascii', errors='replace').rstrip('\x00')
            print(f"\n  IO Configuration: {io_config}")
            print(f"  Potencia nominal: {nom_va} VA / {nom_w} W")
            print(f"  Firmware: {fw_ver}")
            print(f"  Modelo: {model}")
            print(f"  Serial: {serial}")
    else:
        print("\n  WARNING: Sin respuesta al readID, continuando...")

    time.sleep(0.2)

    # Step 4: readMichele (measurement data)
    print("\n" + "=" * 60)
    print("PASO 4: readMichele (datos de mediciones)")
    print("=" * 60)
    frame = build_frame(args.addr, 1, 0x10)
    resp = send_recv(ser, frame, args.timeout, "readMichele")

    if resp and len(resp) >= 9:
        dlen = resp[8]
        data = resp[9:9 + dlen]
        print(f"\n  readMichele data ({dlen} bytes):")
        for i in range(0, len(data), 16):
            chunk = data[i:i+16]
            hex_str = ' '.join(f'{b:02X}' for b in chunk)
            ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            print(f"    {i:04X}: {hex_str:<48s}  {ascii_str}")

        parse_readmichele(bytearray(resp), offset=9)
    else:
        print("\n  WARNING: Sin respuesta al readMichele")

    # Step 5: Try multiple reads to see if values change
    print("\n" + "=" * 60)
    print("PASO 5: Lecturas continuas (3 iteraciones)")
    print("=" * 60)
    for i in range(3):
        print(f"\n  --- Iteracion {i+1}/3 ---")
        frame = build_frame(args.addr, 1, 0x10)
        resp = send_recv(ser, frame, args.timeout, f"readMichele #{i+1}")
        if resp and len(resp) >= 9:
            parse_readmichele(bytearray(resp), offset=9)
        time.sleep(2)

    # Try also group 0 cmd 4 (reRegistration)
    print("\n" + "=" * 60)
    print("PASO EXTRA: reRegistration (group=0, cmd=4)")
    print("=" * 60)
    frame = build_frame(args.addr, 0, 0x04)
    resp = send_recv(ser, frame, args.timeout, "reRegistration")

    print(f"\n{'#'*60}")
    print("# HANDSHAKE COMPLETADO")
    print(f"{'#'*60}\n")

    ser.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
