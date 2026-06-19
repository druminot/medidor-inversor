#!/usr/bin/env python3
"""
modbus_scan.py — Escaneo de registros Modbus RTU para reverse engineering
Uso: python3 modbus_scan.py [--port /dev/ttyUSB0] [--baud 9600] [--slave 1]

Escaneta rangos de registros para descubrir cuáles responden en el inversor.
Probado con adaptador CH340 USB-RS232/RS485.
"""

import minimalmodbus
import argparse
import sys
import time
from datetime import datetime

BAUD_RATES = [9600, 4800, 19200, 2400]
SLAVE_RANGE = range(1, 21)
SCAN_RANGES = [
    (0x0000, 0x0040, "Protocol/unlock area"),
    (0x1000, 0x1050, "Status/control area"),
    (0x2000, 0x2050, "AC measurements"),
    (0x3000, 0x3050, "DC measurements"),
    (0x4000, 0x4050, "Energy/cumulative area"),
    (0x5000, 0x5050, "Grid measurements"),
    (0x6000, 0x6050, "Extended area 1"),
    (0x7000, 0x7050, "Extended area 2"),
    (0x8000, 0x8050, "Extended area 3"),
    (0xC000, 0xC050, "Daily production area"),
    (0xF000, 0xF050, "Info/identification area"),
]

def try_connect(port, baud, slave, parity='N', stopbits=1):
    try:
        instrument = minimalmodbus.Instrument(port, slave)
        instrument.serial.baudrate = baud
        instrument.serial.parity = parity
        instrument.serial.stopbits = stopbits
        instrument.serial.timeout = 1.0
        instrument.mode = minimalmodbus.MODE_RTU
        return instrument
    except Exception as e:
        print(f"  Error opening {port}: {e}")
        return None

def scan_baud_and_slave(port):
    print(f"\n{'='*60}")
    print(f"ESCANEANDO PUERTO: {port}")
    print(f"Probando baudrates y slave addresses...")
    print(f"{'='*60}")
    
    found = []
    for baud in BAUD_RATES:
        for slave in SLAVE_RANGE:
            instrument = try_connect(port, baud, slave)
            if instrument is None:
                continue
            try:
                val = instrument.read_registers(0x0000, 1)
                print(f"  ✓ RESPUESTA: baud={baud} slave={slave} reg=0x0000 val={val}")
                found.append((baud, slave))
                instrument.serial.close()
                return found
            except minimalmodbus.NoResponseError:
                pass
            except Exception:
                pass
            finally:
                try:
                    instrument.serial.close()
                except:
                    pass
            time.sleep(0.1)
    
    print("  No se encontró ningún inversor. Verificar:")
    print("  - Adaptador USB conectado")
    print("  - Cable RS232 conectado al inversor")
    print("  - Inversor encendido")
    return []

def scan_registers(instrument, start, end, desc=""):
    print(f"\n  Escaneando {desc} (0x{start:04X}-0x{end:04X})...")
    results = []
    for addr in range(start, end):
        try:
            val = instrument.read_registers(addr, 1)
            print(f"    0x{addr:04X} = {val[0]} (0x{val[0]:04X})")
            results.append((addr, val[0]))
            time.sleep(0.05)
        except minimalmodbus.NoResponseError:
            pass
        except minimalmodbus.InvalidResponseError:
            pass
        except Exception as e:
            pass
    return results

def try_unlock(instrument, slave):
    print(f"\n  Intentando unlock (slave {slave})...")
    try:
        instrument.write_registers(0x003C, [0x0000, 0x0000])
        print("  ✓ Unlock enviado (0x000000 a 0x003C-0x003D)")
        time.sleep(1)
        return True
    except Exception as e:
        print(f"  ✗ Unlock falló: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Escaneo de registros Modbus RTU para Riello H.P.6065REL-D')
    parser.add_argument('--port', default='/dev/ttyUSB0', help='Puerto serial (default: /dev/ttyUSB0)')
    parser.add_argument('--baud', type=int, default=9600, help='Baudrate (default: 9600)')
    parser.add_argument('--slave', type=int, default=1, help='Slave address (default: 1)')
    parser.add_argument('--scan-all', action='store_true', help='Escanear baudrates y slave addresses')
    parser.add_argument('--scan-regs', action='store_true', help='Escanear rangos de registros')
    parser.add_argument('--unlock', action='store_true', help='Intentar unlock del protocolo')
    args = parser.parse_args()

    print(f"\nModbus Scanner para Riello H.P.6065REL-D")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Puerto: {args.port}")

    if args.scan_all:
        found = scan_baud_and_slave(args.port)
        if not found:
            sys.exit(1)
        baud, slave = found[0]
        print(f"\nUsando: baud={baud} slave={slave}")
        args.baud = baud
        args.slave = slave

    instrument = try_connect(args.port, args.baud, args.slave)
    if instrument is None:
        sys.exit(1)

    if args.unlock:
        if try_unlock(instrument, args.slave):
            time.sleep(2)

    if args.scan_regs:
        all_results = {}
        for start, end, desc in SCAN_RANGES:
            results = scan_registers(instrument, start, end, desc)
            if results:
                all_results[desc] = results
                time.sleep(0.5)

        print(f"\n{'='*60}")
        print(f"RESUMEN DE REGISTROS ENCONTRADOS")
        print(f"{'='*60}")
        for desc, results in all_results.items():
            print(f"\n{desc}:")
            for addr, val in results:
                print(f"  0x{addr:04X} = {val} (0x{val:04X})")
    else:
        print("\nUsa --scan-regs para escanear registros")
        print("Usa --scan-all para buscar baudrate y slave address")
        print("Usa --unlock para intentar unlock del protocolo")
        print("Ejemplo completo: python3 modbus_scan.py --port /dev/ttyUSB0 --scan-all --unlock --scan-regs")

    instrument.serial.close()

if __name__ == '__main__':
    main()