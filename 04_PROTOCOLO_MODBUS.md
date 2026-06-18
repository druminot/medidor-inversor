# Protocolo RS232/RS485 / Modbus RTU — Referencia Técnica

> **ESTADO: LEGACY** — El protocolo Modbus RTU fue explorado inicialmente pero NO es el protocolo correcto para este inversor. El protocolo real es **SISER (Phoenixtec)**, descubierto por decompilación de SunVision. Los registros Modbus listados en este documento NO funcionan con el H.P.6065REL-D. Este archivo se conserva como referencia histórica.

## Resumen de la Configuración para H.P.6065REL-D

| Parámetro | Valor |
|---|---|
| Protocolo | Modbus RTU |
| Medio físico | **RS232** (adaptador CH340 USB-RS232) |
| Baud rate | 9600 (confirmado) |
| Data bits | 8 |
| Parity | None |
| Stop bits | 1 |
| Formato | 8N1 (11 bits por carácter) |
| Slave address | 1 (confirmado) |
| Byte order wire | LSByte first (little-endian, asumido) |
| Topología | Punto a punto (RS232) |
| Adaptador | CH340 (USB VID:PID = 1a86:7523) |
| Puerto | /dev/ttyUSB0 |

> **NOTA**: El proyecto original asumía RS485 con el Helios Power 4000. El inversor real (H.P.6065REL-D) usa RS232 con un adaptador CH340. Modbus RTU funciona igual sobre RS232, pero la topología es punto a punto (no bus).

### Referencia: Configuración para Helios Power 4000 (RS485)

| Parámetro | Valor |
|---|---|
| Medio físico | RS485 half-duplex |
| Baud rate | 4800 (Helios Power viejo) |
| Slave address | 16 (0x10) |
| Max dispositivos por bus | 20 |

---

## Modbus RTU — Frame Format

### Estructura ADU (Application Data Unit)

```
| Slave Address | Function Code | Data          | CRC Low | CRC High |
| 1 byte        | 1 byte        | 0-252 bytes   | 1 byte  | 1 byte   |
| (1-247)       | (01-7F)       |               |         |          |
```

- **ADU máx**: 256 bytes
- **PDU** = Function Code + Data (máx 253 bytes)
- **CRC**: low byte primero, high byte después

### Byte-level (11 bits por carácter)

```
| Start Bit | Data Bits (LSB first) | Parity Bit | Stop Bit |
| 1 bit      | 8 bits                | 1 bit       | 1 bit    |
```

Con parity=None → 2 stop bits (siguen 11 bits totales).

### Ejemplo: Leer registro 40020, 1 registro, slave 1

```
Request:  01 03 00 14 00 01 84 0F
          │  │  └──┘  └──┘  └──┘
          │  │   │     │     └── CRC (0x0F84 → low=0x84, high=0x0F)
          │  │   │     └── Cantidad: 1 registro
          │  │   └── Dirección: 0x0014 = 20 (40020 - 40001 base)
          │  └── Function code: 0x03 (Read Holding Registers)
          └── Slave: 0x01

Response: 01 03 02 FF FF B8 80
          │  │  │  └──┘  └──┘
          │  │  │   │     └── CRC
          │  │  │   └── Data: 0xFFFF
          │  │  └── Byte count: 2
          │  └── Function code: 0x03
          └── Slave: 0x01
```

---

## Códigos de Función Relevantes

| Código | Función | Uso |
|---|---|---|
| 0x01 | Read Coils | Leer estados binarios (raro en inversores) |
| 0x02 | Read Discrete Inputs | Leer alarmas/estados (usado en String Box) |
| 0x03 | Read Holding Registers | **Principal**: leer mediciones y config |
| 0x04 | Read Input Registers | Leer mediciones read-only |
| 0x06 | Write Single Register | Escribir configuración |
| 0x10 | Write Multiple Registers | Escribir múltiples registros |

---

## CRC16 (Modbus)

### Algoritmo (bit-by-bit)

```python
def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc  # low byte first en transmisión
```

---

## Timing Modbus RTU

| Parámetro | Valor (9600 baud) |
|---|---|
| Tiempo por carácter | ~1.15 ms (11 bits / 9600) |
| Silent interval (3.5 chars) | ~4.0 ms |
| Timeout de respuesta | 100 ms - 1 s (típico inversores: 50-200 ms) |

---

## USB-RS232 en Linux (CH340)

### Adaptador CH340

| Característica | Valor |
|---|---|
| Chipset | CH340 (VID:PID = 1a86:7523) |
| Driver Linux | ch341 (built-in kernel 2.6+) |
| Puerto | /dev/ttyUSB0 |
| Velocidad máx | 2 Mbps |
| Tipo | USB-RS232/TTL |
| RS485 ioctl | No (no soporta RS485 half-duplex) |

### Adaptadores alternativos

| Chipset | Driver Linux | /dev/ | RS485 ioctl | Recomendado |
|---|---|---|---|---|
| CH340/CH340G | ch341 (built-in) | ttyUSB0 | No | **Usado en este proyecto** |
| FT232RL/FT232H | ftdi_sio (built-in) | ttyUSB0 | Sí (kernel 4.13+) | Mejor para RS485 |
| CP2102 | cp210x (built-in) | ttyUSB0 | Sí (kernel 5.12+) | Bueno |

### Configurar puerto serial (termios)

```python
import serial

ser = serial.Serial(
    port='/dev/ttyUSB0',
    baudrate=9600,
    bytesize=8,
    parity='N',
    stopbits=1,
    timeout=1
)
```

### Regla udev para nombre persistente

```
# /etc/udev/rules.d/99-serial.rules
# CH340 USB-RS232 (H.P.6065REL-D)
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="inverter-serial", GROUP="dialout", MODE="0666"

# FT232 USB-RS485 (alternativo)
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", SYMLINK+="inverter-serial", GROUP="dialout", MODE="0666"
```

Esto crea `/dev/inverter-serial` para ambos adaptadores (CH340 y FT232).

---

## Librerías Python

### pymodbus (recomendado — más completo)

```python
from pymodbus.client import ModbusSerialClient

client = ModbusSerialClient(
    port='/dev/ttyUSB0',
    baudrate=9600,
    parity='N',
    stopbits=1,
    bytesize=8,
    timeout=1
)
client.connect()

result = client.read_holding_registers(address=0, count=10, slave=1)
if not result.isError():
    print(result.registers)

client.close()
```

### minimalmodbus (más simple)

```python
import minimalmodbus

instrument = minimalmodbus.Instrument('/dev/ttyUSB0', slaveaddress=1)
instrument.serial.baudrate = 9600
instrument.serial.parity = 'N'

value = instrument.read_register(0, numberOfDecimals=0, functioncode=3)
```

---

## Docker con Serial Port

### docker-compose.yml

```yaml
services:
  modbus-reader:
    image: python:3.12-slim
    devices:
      - /dev/ttyUSB0:/dev/ttyUSB0
    group_add:
      - dialout
    volumes:
      - ./src:/app
    command: python /app/main.py
```

### Para hot-plug (adaptadores que se desconectan/reconectan)

```yaml
services:
  modbus-reader:
    device_cgroup_rules:
      - 'c 188:* rwm'  # /dev/ttyUSB* major 188
    devices:
      - /dev/ttyUSB0:/dev/ttyUSB0
```

---

## Mejores Prácticas RS232/RS485

### RS232 (H.P.6065REL-D — este proyecto)

| Práctica | Detalle |
|---|---|
| Cable | RS232 directo (TX, RX, GND) |
| Longitud máx | ~15m (RS232 estándar) |
| Cruzamiento | TX inversor → RX adaptador, RX inversor → TX adaptador |
| GND | Conectar GND entre inversor y adaptador |
| Sin terminadores | RS232 es punto a punto, no necesita terminación |

### RS485 (referencia — Helios Power 4000)

| Práctica | Detalle |
|---|---|
| Cable | STP 120Ω (par trenzado blindado) |
| Terminación | 120Ω en ambos extremos del bus |
| Bias | 1kΩ pull-up A, pull-down B |
| Tierra blindaje | Un solo extremo (evitar ground loops) |
| Topología | Daisy-chain únicamente (no estrella/troncal) |
| Longitud máx | 1200m a 9600 baud |
| Polaridad | Verificar A/B — si falla, intercambiar |
| Surges | Protección para instalaciones exteriores |

---

## Referencias Detalladas

- Ver `research/MODBUS_RTU_RESEARCH.md` — Referencia completa del protocolo (802 líneas)
- Ver `research/RS485_LINUX_COMPLETE_RESEARCH.md` — RS485 en Linux detallado (1168 líneas)
- Simply Modbus: https://www.simplymodbus.ca/learn-basics.html
- Modbus Organization: https://modbus.org
- pymodbus docs: https://pymodbus.readthedocs.io