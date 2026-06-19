#!/usr/bin/env python3
"""
test_simulator.py — Test del simulador Modbus RTU/TCP

Inicia un simulador Modbus TCP en puerto 5502 y corre tests automaticos.
No requiere hardware - usa TCP para comunicacion.

Uso:
  python3 test_simulator.py           # Test basico
  python3 test_simulator.py --tcp     # Dejar servidor corriendo para modbus-reader
"""

import argparse
import math
import random
import sys
import threading
import time
from datetime import datetime

from pymodbus.client import ModbusTcpClient
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.server import StartTcpServer

NUM_REGS = 65536
SLAVE_ID = 1
TCP_PORT = 5502
START_TIME = time.time()
START_ENERGY = 12547.32


def create_datastore():
    hr_dblock = ModbusSequentialDataBlock(0x0000, [0] * NUM_REGS)
    ir_dblock = ModbusSequentialDataBlock(0x0000, [0] * NUM_REGS)
    co_dblock = ModbusSequentialDataBlock(0x0000, [False] * NUM_REGS)
    di_dblock = ModbusSequentialDataBlock(0x0000, [False] * NUM_REGS)

    slave_context = ModbusSlaveContext(hr=hr_dblock, ir=ir_dblock, co=co_dblock, di=di_dblock)
    ctx = ModbusServerContext(slaves={SLAVE_ID: slave_context}, single=False)
    slave = ctx[SLAVE_ID]

    slave.setValues(3, 0x0000, [0x6065])  # Modelo
    slave.setValues(3, 0x0001, [0x0001])  # FW menor
    slave.setValues(3, 0x0002, [0x0100])  # FW mayor
    slave.setValues(3, 0x0003, [0x524C])  # 'RL'
    slave.setValues(3, 0x0004, [0x4950])  # 'IP'
    slave.setValues(3, 0x0005, [0x0001])  # Slave address
    slave.setValues(3, 0x0006, [0x2580])  # Baudrate 9600
    slave.setValues(3, 0x0007, [0x0008])  # Data bits
    slave.setValues(3, 0x0008, [0x0000])  # Paridad None
    slave.setValues(3, 0x0009, [0x1770])  # Potencia nominal 6000W
    slave.setValues(3, 0x003C, [0xFFFF])  # Password high (locked)
    slave.setValues(3, 0x003D, [0xFFFF])  # Password low (locked)
    slave.setValues(3, 0x1005, [0x0002])  # Status: Running
    slave.setValues(3, 0x101C, [42])      # Temperatura

    energy_raw = int(START_ENERGY / 0.01)
    slave.setValues(3, 0x1021, [energy_raw & 0xFFFF, (energy_raw >> 16) & 0xFFFF])

    power_raw = int(3200 / 0.01)
    slave.setValues(3, 0x1037, [power_raw & 0xFFFF, (power_raw >> 16) & 0xFFFF])

    slave.setValues(3, 0x1040, [3100])  # Vpv
    slave.setValues(3, 0x1041, [1030])  # Ipv
    slave.setValues(3, 0x1042, [2300])  # Vac
    slave.setValues(3, 0x1043, [1390])  # Iac
    slave.setValues(3, 0x1044, [5000])  # Fac

    hours_raw = int(87654 / 0.01)
    slave.setValues(3, 0x1050, [hours_raw & 0xFFFF, (hours_raw >> 16) & 0xFFFF])

    co2_raw = int(6274.16 / 0.01)
    slave.setValues(3, 0x1052, [co2_raw & 0xFFFF, (co2_raw >> 16) & 0xFFFF])

    slave.setValues(3, 0x1060, [2850])  # Energia diaria

    pdc_raw = int(3193 / 0.01)
    slave.setValues(3, 0x1070, [pdc_raw & 0xFFFF, (pdc_raw >> 16) & 0xFFFF])

    slave.setValues(3, 0x1080, [99])  # Factor de potencia

    daily_graph = []
    for i in range(48):
        hour = i / 2.0
        if 6 <= hour <= 18:
            sf = math.sin(math.pi * (hour - 6) / 12)
        else:
            sf = 0
        daily_graph.append(int(sf * 3200 / 0.01))
    slave.setValues(3, 0xC000, daily_graph)

    slave.setValues(4, 0x0000, [0x0001])  # Input: Modelo
    slave.setValues(4, 0x1005, [0x0002])  # Input: Status
    slave.setValues(4, 0x101C, [42])      # Input: Temp

    slave.setValues(2, 0x0000, [True])    # Discrete: Online
    slave.setValues(2, 0x0001, [True])    # Discrete: Grid OK
    slave.setValues(2, 0x0002, [False])   # Discrete: Fault

    slave.setValues(1, 0x0000, [True])   # Coil: Inverter enabled

    return ctx


def update_values(context):
    slave_ctx = context[SLAVE_ID]
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
    slave_ctx.setValues(3, 0x1037, [power_raw & 0xFFFF, (power_raw >> 16) & 0xFFFF])

    vpv = int((310 + 40 * solar_factor) * 10)
    slave_ctx.setValues(3, 0x1040, [vpv])

    ipv_x100 = int((power_w / max(vpv / 10, 1)) * 100) if solar_factor > 0 else 0
    slave_ctx.setValues(3, 0x1041, [ipv_x100])

    vac = int((230 + random.gauss(0, 2)) * 10)
    slave_ctx.setValues(3, 0x1042, [vac])

    iac_x100 = int((power_w / max(vac / 10, 1)) * 100) if solar_factor > 0 else 0
    slave_ctx.setValues(3, 0x1043, [iac_x100])

    fac_x100 = int((50.0 + random.gauss(0, 0.05)) * 100)
    slave_ctx.setValues(3, 0x1044, [fac_x100])

    temp = int(35 + 20 * solar_factor + random.gauss(0, 1))
    slave_ctx.setValues(3, 0x101C, [temp])

    status = 0x0002 if solar_factor > 0.01 else 0x0001
    slave_ctx.setValues(3, 0x1005, [status])

    energy_increment = (elapsed / 3600) * power_w / 1000
    total_energy = START_ENERGY + energy_increment
    energy_raw = int(total_energy / 0.01)
    slave_ctx.setValues(3, 0x1021, [energy_raw & 0xFFFF, (energy_raw >> 16) & 0xFFFF])

    daily = (elapsed / 3600) * power_w / 1000 * max(solar_factor, 0.01)
    slave_ctx.setValues(3, 0x1060, [int(daily / 0.01) if daily > 0 else 0])

    pdc_w = int(power_w / 0.97)
    pdc_raw = int(pdc_w / 0.01)
    slave_ctx.setValues(3, 0x1070, [pdc_raw & 0xFFFF, (pdc_raw >> 16) & 0xFFFF])

    co2 = total_energy * 0.5
    co2_raw = int(co2 / 0.01)
    slave_ctx.setValues(3, 0x1052, [co2_raw & 0xFFFF, (co2_raw >> 16) & 0xFFFF])

    hours = int((87654 + elapsed / 3600) / 0.01)
    slave_ctx.setValues(3, 0x1050, [hours & 0xFFFF, (hours >> 16) & 0xFFFF])


def update_loop(context):
    while True:
        try:
            update_values(context)
        except Exception as e:
            print(f"[UPDATE ERROR] {e}")
        time.sleep(2)


def run_tests():
    print("\n" + "=" * 60)
    print("TEST DEL SIMULADOR MODBUS RTU")
    print("=" * 60)

    client = ModbusTcpClient('127.0.0.1', port=TCP_PORT)
    if not client.connect():
        print("ERROR: No se pudo conectar al simulador")
        return False

    print("\n[1/5] Lectura de registros de identificacion")
    for addr, name in [(0x0000, "Modelo"), (0x0005, "Slave"), (0x0009, "Pnominal")]:
        result = client.read_holding_registers(addr, count=1, slave=SLAVE_ID)
        if not result.isError():
            val = result.registers[0]
            print(f"  0x{addr:04X} {name:12s} = {val} (0x{val:04X})")
        else:
            print(f"  0x{addr:04X} {name:12s} = ERROR")
            client.close()
            return False

    print("\n[2/5] Lectura de registros de medicion")
    for addr, name in [(0x1005, "Status"), (0x101C, "Temp"), (0x1040, "Vpv"), (0x1042, "Vac"), (0x1044, "Fac")]:
        result = client.read_holding_registers(addr, count=1, slave=SLAVE_ID)
        if not result.isError():
            val = result.registers[0]
            if name == "Vpv":
                print(f"  0x{addr:04X} {name:12s} = {val} ({val/10:.1f} V)")
            elif name == "Vac":
                print(f"  0x{addr:04X} {name:12s} = {val} ({val/10:.1f} V)")
            elif name == "Fac":
                print(f"  0x{addr:04X} {name:12s} = {val} ({val/100:.2f} Hz)")
            elif name == "Temp":
                print(f"  0x{addr:04X} {name:12s} = {val} ({val} C)")
            else:
                print(f"  0x{addr:04X} {name:12s} = {val}")
        else:
            print(f"  0x{addr:04X} {name:12s} = ERROR")

    print("\n[3/5] Lectura de registros 32-bit")
    for addr, name, scale, unit in [(0x1021, "Etotal", 0.01, "kWh"), (0x1037, "Pac", 0.01, "W")]:
        result = client.read_holding_registers(addr, count=2, slave=SLAVE_ID)
        if not result.isError():
            vals = result.registers
            combined = vals[0] + (vals[1] << 16)
            print(f"  0x{addr:04X} {name:12s} = {combined * scale:.2f} {unit}")
        else:
            print(f"  0x{addr:04X} {name:12s} = ERROR")

    print("\n[4/5] Unlock del protocolo (password 0x000000)")
    result = client.write_registers(0x003C, [0x0000, 0x0000], slave=SLAVE_ID)
    print(f"  Write result: {result}")

    time.sleep(0.5)

    for addr in [0x003C, 0x003D]:
        result = client.read_holding_registers(addr, count=1, slave=SLAVE_ID)
        if not result.isError():
            val = result.registers[0]
            print(f"  0x{addr:04X} = {val} (0x{val:04X}) {'OK' if val == 0 else 'LOCKED'}")
        else:
            print(f"  0x{addr:04X} = ERROR")

    print("\n[5/5] Valores dinamicos (espera 3 seg para ver cambios)")
    for _i in range(3):
        result = client.read_holding_registers(0x1037, count=2, slave=SLAVE_ID)
        if not result.isError():
            vals = result.registers
            combined = vals[0] + (vals[1] << 16)
            power = combined * 0.01
            print(f"  Pac = {power:.1f} W")
        result = client.read_holding_registers(0x101C, count=1, slave=SLAVE_ID)
        if not result.isError():
            print(f"  Temp = {result.registers[0]} C")
        time.sleep(1)

    client.close()
    print("\n" + "=" * 60)
    print("TODOS LOS TESTS PASARON!")
    print("=" * 60)
    return True


def main():
    parser = argparse.ArgumentParser(description='Simulador y test Modbus RTU')
    parser.add_argument('--tcp', action='store_true', help='Dejar servidor TCP corriendo (para modbus-reader)')
    parser.add_argument('--port', type=int, default=TCP_PORT, help=f'Puerto TCP (default: {TCP_PORT})')
    parser.add_argument('--test-only', action='store_true', help='Solo correr tests (servidor ya debe estar corriendo)')
    args = parser.parse_args()

    if args.test_only:
        run_tests()
        return

    context = create_datastore()

    identity = ModbusDeviceIdentification()
    identity.VendorName = "Riello Solartech"
    identity.ProductCode = "HP6065"
    identity.VendorUrl = "https://www.riello-solartech.com"
    identity.ProductName = "H.P.6065REL-D"
    identity.ModelName = "Helios Power 6065"
    identity.FirmwareRevision = "1.00"

    update_thread = threading.Thread(target=update_loop, args=(context,), daemon=True)
    update_thread.start()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Thread de actualizacion iniciado")

    server_thread = threading.Thread(
        target=StartTcpServer,
        kwargs={
            'context': context,
            'identity': identity,
            'address': ('0.0.0.0', args.port),
        },
        daemon=True
    )
    server_thread.start()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Servidor Modbus TCP en puerto {args.port}")

    time.sleep(2)

    if not args.tcp:
        print("\nCorriendo tests automaticos...")
        success = run_tests()
        if success:
            print("\nSimulador funcionando correctamente!")
            print("Para dejarlo corriendo para modbus-reader, usa: --tcp")
        else:
            print("\nAlgunos tests fallaron.")
        sys.exit(0 if success else 1)
    else:
        print(f"\nServidor Modbus TCP corriendo en puerto {args.port}")
        print(f"Slave ID: {SLAVE_ID}")
        print("Para conectar modbus-reader:")
        print(f"  SERIAL_PORT=tcp://127.0.0.1:{args.port}")
        print("")
        print("Para probar manualmente:")
        print(f"  python3 modbus_scan.py --port tcp://127.0.0.1:{args.port} --baud 9600 --slave 1 --unlock --scan-regs")
        print("")
        print("Ctrl+C para detener...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Simulador detenido")


if __name__ == '__main__':
    main()
