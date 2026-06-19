#!/usr/bin/env python3
"""
inverter_simulator.py — Simulador Modbus RTU del inversor Riello H.P.6065REL-D

Simula un inversor solar que responde consultas Modbus por TCP o serial.
Usa setValues() para inicializar (requerido por pymodbus 3.x).

Modos de uso:
  # Modo TCP (para testing sin hardware):
  python3 inverter_simulator.py --tcp --port 5502

  # Modo Serial (con puertos virtuales socat):
  socat -d -d pty,raw,echo=0,link=/tmp/inverter-master pty,raw,echo=0,link=/tmp/inverter-slave &
  python3 inverter_simulator.py --serial --serial-port /tmp/inverter-slave

  # Para probar con modbus_scan (TCP):
  python3 modbus_scan.py --port tcp://127.0.0.1:5502 --slave 1 --unlock --scan-regs

Registros simulados:
  0x003C-0x003D: Unlock (password 0x000000)
  0x1005: Status (0=off, 1=standby, 2=running)
  0x101C: Temperatura (x1 C)
  0x1021-0x1022: Energia total (x0.01 kWh, 32-bit LE)
  0x1037-0x1038: Potencia AC (x0.01 W, 32-bit LE)
  0x1040-0x1044: Vpv, Ipv, Vac, Iac, Fac
"""

import argparse
import math
import random
import sys
import threading
import time
from datetime import datetime

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.server import StartSerialServer, StartTcpServer

NUM_REGS = 65536
SLAVE_ID = 1
TCP_PORT = 5502
START_TIME = time.time()
START_ENERGY = 12547.32


def create_and_init_datastore():
    hr = ModbusSequentialDataBlock(0x0000, [0] * NUM_REGS)
    ir = ModbusSequentialDataBlock(0x0000, [0] * NUM_REGS)
    co = ModbusSequentialDataBlock(0x0000, [False] * NUM_REGS)
    di = ModbusSequentialDataBlock(0x0000, [False] * NUM_REGS)

    slave = ModbusSlaveContext(hr=hr, ir=ir, co=co, di=di)
    context = ModbusServerContext(slaves={SLAVE_ID: slave}, single=False)
    s = context[SLAVE_ID]

    s.setValues(3, 0x0000, [0x6065])   # Modelo
    s.setValues(3, 0x0001, [0x0001])   # FW menor
    s.setValues(3, 0x0002, [0x0100])   # FW mayor
    s.setValues(3, 0x0003, [0x524C])   # 'RL'
    s.setValues(3, 0x0004, [0x4950])   # 'IP'
    s.setValues(3, 0x0005, [0x0001])   # Slave address
    s.setValues(3, 0x0006, [0x2580])   # Baudrate 9600
    s.setValues(3, 0x0007, [0x0008])   # Data bits
    s.setValues(3, 0x0008, [0x0000])   # Paridad None
    s.setValues(3, 0x0009, [0x1770])   # Potencia nominal 6000W
    s.setValues(3, 0x003C, [0xFFFF])   # Password high (locked)
    s.setValues(3, 0x003D, [0xFFFF])   # Password low (locked)
    s.setValues(3, 0x1005, [0x0002])   # Status: Running
    s.setValues(3, 0x101C, [42])       # Temperatura

    energy_raw = int(START_ENERGY / 0.01)
    s.setValues(3, 0x1021, [energy_raw & 0xFFFF, (energy_raw >> 16) & 0xFFFF])

    power_raw = int(3200 / 0.01)
    s.setValues(3, 0x1037, [power_raw & 0xFFFF, (power_raw >> 16) & 0xFFFF])

    s.setValues(3, 0x1040, [3100])     # Vpv
    s.setValues(3, 0x1041, [1030])     # Ipv
    s.setValues(3, 0x1042, [2300])     # Vac
    s.setValues(3, 0x1043, [1390])     # Iac
    s.setValues(3, 0x1044, [5000])     # Fac

    hours_raw = int(87654 / 0.01)
    s.setValues(3, 0x1050, [hours_raw & 0xFFFF, (hours_raw >> 16) & 0xFFFF])

    co2_raw = int(6274.16 / 0.01)
    s.setValues(3, 0x1052, [co2_raw & 0xFFFF, (co2_raw >> 16) & 0xFFFF])

    s.setValues(3, 0x1060, [2850])     # Energia diaria

    pdc_raw = int(3193 / 0.01)
    s.setValues(3, 0x1070, [pdc_raw & 0xFFFF, (pdc_raw >> 16) & 0xFFFF])

    s.setValues(3, 0x1080, [99])       # Factor de potencia

    daily_graph = []
    for i in range(48):
        hour = i / 2.0
        if 6 <= hour <= 18:
            sf = math.sin(math.pi * (hour - 6) / 12)
        else:
            sf = 0
        daily_graph.append(int(sf * 3200 / 0.01))
    s.setValues(3, 0xC000, daily_graph)

    s.setValues(4, 0x0000, [0x0001])
    s.setValues(4, 0x1005, [0x0002])
    s.setValues(4, 0x101C, [42])

    s.setValues(2, 0x0000, [True])
    s.setValues(2, 0x0001, [True])
    s.setValues(2, 0x0002, [False])

    s.setValues(1, 0x0000, [True])

    return context


def update_values(context):
    s = context[SLAVE_ID]
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
    s.setValues(3, 0x1037, [power_raw & 0xFFFF, (power_raw >> 16) & 0xFFFF])

    vpv = int((310 + 40 * solar_factor) * 10)
    s.setValues(3, 0x1040, [vpv])

    ipv_x100 = int((power_w / max(vpv / 10, 1)) * 100) if solar_factor > 0 else 0
    s.setValues(3, 0x1041, [ipv_x100])

    vac = int((230 + random.gauss(0, 2)) * 10)
    s.setValues(3, 0x1042, [vac])

    iac_x100 = int((power_w / max(vac / 10, 1)) * 100) if solar_factor > 0 else 0
    s.setValues(3, 0x1043, [iac_x100])

    fac_x100 = int((50.0 + random.gauss(0, 0.05)) * 100)
    s.setValues(3, 0x1044, [fac_x100])

    temp = int(35 + 20 * solar_factor + random.gauss(0, 1))
    s.setValues(3, 0x101C, [temp])

    pdc_w = int(power_w / 0.97)
    pdc_raw = int(pdc_w / 0.01)
    s.setValues(3, 0x1070, [pdc_raw & 0xFFFF, (pdc_raw >> 16) & 0xFFFF])

    energy_increment = (elapsed / 3600) * power_w / 1000
    total_energy = START_ENERGY + energy_increment
    energy_raw = int(total_energy / 0.01)
    s.setValues(3, 0x1021, [energy_raw & 0xFFFF, (energy_raw >> 16) & 0xFFFF])

    daily = (elapsed / 3600) * power_w / 1000 * max(solar_factor, 0.01)
    s.setValues(3, 0x1060, [int(daily / 0.01) if daily > 0 else 0])

    status = 0x0002 if solar_factor > 0.01 else 0x0001
    s.setValues(3, 0x1005, [status])

    co2 = total_energy * 0.5
    co2_raw = int(co2 / 0.01)
    s.setValues(3, 0x1052, [co2_raw & 0xFFFF, (co2_raw >> 16) & 0xFFFF])

    hours = int((87654 + elapsed / 3600) / 0.01)
    s.setValues(3, 0x1050, [hours & 0xFFFF, (hours >> 16) & 0xFFFF])


def update_loop(context):
    while True:
        try:
            update_values(context)
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Update error: {e}")
        time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description='Simulador Modbus Riello H.P.6065REL-D')
    parser.add_argument('--tcp', action='store_true', default=True, help='Modo TCP (default)')
    parser.add_argument('--serial', action='store_true', help='Modo serial')
    parser.add_argument('--port', default=None, help='Puerto TCP o serial')
    parser.add_argument('--baud', type=int, default=9600, help='Baudrate (solo serial)')
    parser.add_argument('--slave', type=int, default=1, help='Slave address')
    args = parser.parse_args()

    if args.serial and not args.port:
        args.port = '/tmp/inverter-slave'
    elif not args.port:
        args.port = str(TCP_PORT)

    print(f"{'=' * 60}")
    print("Simulador Modbus RTU - Riello H.P.6065REL-D")
    print(f"{'=' * 60}")

    context = create_and_init_datastore()

    identity = ModbusDeviceIdentification()
    identity.VendorName = "Riello Solartech"
    identity.ProductCode = "HP6065"
    identity.VendorUrl = "https://www.riello-solartech.com"
    identity.ProductName = "H.P.6065REL-D"
    identity.ModelName = "Helios Power 6065"
    identity.FirmwareRevision = "1.00"
    identity.MajorMinorRevision = "1.0"

    update_thread = threading.Thread(target=update_loop, args=(context,), daemon=True)
    update_thread.start()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Thread de actualizacion iniciado")

    if args.serial:
        print("Modo: Serial")
        print(f"Puerto: {args.port}")
        print(f"Baudrate: {args.baud}")
        print(f"Slave: {args.slave}")
        print()
        try:
            StartSerialServer(
                context=context,
                identity=identity,
                port=args.port,
                baudrate=args.baud,
                parity='N',
                stopbits=1,
                bytesize=8,
            )
        except Exception as e:
            print(f"\nError: {e}")
            print("Crea puertos virtuales con:")
            print("  socat -d -d pty,raw,echo=0,link=/tmp/inverter-master pty,raw,echo=0,link=/tmp/inverter-slave")
            sys.exit(1)
    else:
        port = int(args.port)
        print("Modo: TCP")
        print(f"Puerto: {port}")
        print(f"Slave: {args.slave}")
        print()
        print("Registros simulados:")
        print("  0x003C-0x003D: Unlock (password 0x000000)")
        print("  0x1005: Status / 0x101C: Temp / 0x1040-0x1044: Vpv,Ipv,Vac,Iac,Fac")
        print("  0x1021-0x1022: Etotal / 0x1037-0x1038: Pac")
        print("  0xC000-0xC02F: Grafico diario (48 valores)")
        print()
        print("Probar con modbus_scan (TCP):")
        print(f"  python3 modbus_scan.py --port tcp://127.0.0.1:{port} --slave 1 --unlock --scan-regs")
        print()
        print("Ctrl+C para detener...")
        StartTcpServer(context=context, identity=identity, address=("0.0.0.0", port))


if __name__ == '__main__':
    main()
