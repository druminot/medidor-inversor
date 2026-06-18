# Modbus RTU Protocol — Comprehensive Research for Solar Inverters

## Sources
- Wikipedia Modbus: https://en.wikipedia.org/wiki/Modbus
- Simply Modbus (Protocol Basics): https://www.simplymodbus.ca/learn-basics.html
- Simply Modbus (Exception Responses): https://www.simplymodbus.ca/learn-exceptions.html
- Lammert Bies (CRC Calculation): https://www.lammertbies.nl/comm/info/crc-calculation
- Lammert Bies (Modbus Tutorial): https://www.lammertbies.nl/comm/info/modbus
- Modbus Organization: https://modbus.org
- Solaranzeige Forum: https://solaranzeige.de

---

## 1. MODBUS RTU COMPLETE FRAME FORMAT

### 1.1 RTU Frame Structure (ADU)

```
| Slave Address | Function Code | Data          | CRC Low | CRC High |
| 1 byte        | 1 byte        | 0-252 bytes   | 1 byte  | 1 byte   |
| (1-247)       | (01-7F)       |               |         |          |
```

- **Total ADU max size**: 256 bytes (serial), 253 bytes max for PDU data
- **PDU = Function Code + Data** (max 253 bytes)
- **ADU = Slave Address + PDU + CRC (2 bytes)**
- **CRC transmitted low byte first, then high byte**

### 1.2 Byte-level Frame (each byte = 11 bits)

```
| Start Bit | Data Bits (LSB first) | Parity Bit | Stop Bit |
| 1 bit      | 8 bits                | 1 bit       | 1 bit    |
```

- Default parity: **Even**. Odd or no parity also possible.
- With no parity: 2 stop bits (still 11 bits total).
- Bit order: **LSB sent first** within each byte.

### 1.3 Example RTU Frame

```
01 04 02 FF FF B8 80
│  │  │  └──┘  └─┘
│  │  │   │     └── CRC = 0x80B8 (low byte 0x80, high byte 0xB8)
│  │  │   └── Data: register value 0xFFFF
│  │  └── Byte count: 2 bytes of data follow
│  └── Function code: 0x04 (Read Input Registers)
└── Slave address: 0x01
```

---

## 2. CRC16 CALCULATION (MODBUS CRC)

### 2.1 Specification

- **Polynomial**: x^16 + x^15 + x^2 + 1
- **Normal hex**: 0x8005
- **Reversed (reflected) hex**: **0xA001** (this is the one used in the bit-by-bit algorithm)
- **Initial value**: 0xFFFF (all ones)
- **Final XOR**: 0x0000 (none)
- **Bit order**: Processed LSB first (reflected)
- **Result**: CRC low byte sent first, CRC high byte sent second

### 2.2 Bit-by-Bit CRC Algorithm (C)

```c
uint16_t ModbusCRC16(const uint8_t *data, uint16_t length) {
    uint16_t crc = 0xFFFF;  // Initialize to all 1s

    for (uint16_t i = 0; i < length; i++) {
        crc ^= (uint16_t)data[i];  // XOR byte into CRC low byte

        for (uint8_t j = 0; j < 8; j++) {
            if (crc & 0x0001) {         // If LSB is 1
                crc >>= 1;              // Shift right
                crc ^= 0xA001;         // XOR with reversed polynomial
            } else {
                crc >>= 1;              // Just shift right
            }
        }
    }
    return crc;  // Low byte first when transmitted
}
```

### 2.3 Table-Based CRC Algorithm (C)

```c
static const uint16_t crc16_table[256] = {
    0x0000, 0xC0C1, 0xC181, 0x0140, 0xC301, 0x03C0, 0x0280, 0xC241,
    0xC601, 0x06C0, 0x0780, 0xC741, 0x0500, 0xC5C1, 0xC481, 0x0440,
    0xCC01, 0x0CC0, 0x0D80, 0xCD41, 0x0F00, 0xCFC1, 0xCE81, 0x0E40,
    0x0A00, 0xCAC1, 0xCB81, 0x0B40, 0xC901, 0x09C0, 0x0880, 0xC841,
    0xD801, 0x18C0, 0x1980, 0xD941, 0x1B00, 0xDBC1, 0xDA81, 0x1A40,
    0x1E00, 0xDEC1, 0xDF81, 0x1F40, 0xDD01, 0x1DC0, 0x1C80, 0xDC41,
    0x1400, 0xD4C1, 0xD581, 0x1540, 0xD701, 0x17C0, 0x1680, 0xD641,
    0xD201, 0x12C0, 0x1380, 0xD341, 0x1100, 0xD1C1, 0xD081, 0x1040,
    0xF001, 0x30C0, 0x3180, 0xF141, 0x3300, 0xF3C1, 0xF281, 0x3240,
    0x3600, 0xF6C1, 0xF781, 0x3740, 0xF501, 0x35C0, 0x3480, 0xF441,
    0x3C00, 0xFCC1, 0xFD81, 0x3D40, 0xFF01, 0x3FC0, 0x3E80, 0xFE41,
    0xFA01, 0x3AC0, 0x3B80, 0xFB41, 0x3900, 0xF9C1, 0xF881, 0x3840,
    0x2800, 0xE8C1, 0xE981, 0x2940, 0xEB01, 0x2BC0, 0x2A80, 0xEA41,
    0xEE01, 0x2EC0, 0x2F80, 0xEF41, 0x2D00, 0xEDC1, 0xEC81, 0x2C40,
    0xE401, 0x24C0, 0x2580, 0xE541, 0x2700, 0xE7C1, 0xE681, 0x2640,
    0x2200, 0xE2C1, 0xE381, 0x2340, 0xE101, 0x21C0, 0x2080, 0xE041,
    0xA001, 0x60C0, 0x6180, 0xA141, 0x6300, 0xA3C1, 0xA281, 0x6240,
    0x6600, 0xA6C1, 0xA781, 0x6740, 0xA501, 0x65C0, 0x6480, 0xA441,
    0x6C00, 0xACC1, 0xAD81, 0x6D40, 0xAF01, 0x6FC0, 0x6E80, 0xAE41,
    0xAA01, 0x6AC0, 0x6B80, 0xAB41, 0x6900, 0xA9C1, 0xA881, 0x6840,
    0x7800, 0xB8C1, 0xB981, 0x7940, 0xBB01, 0x7BC0, 0x7A80, 0xBA41,
    0xBE01, 0x7EC0, 0x7F80, 0xBF41, 0x7D00, 0xBDC1, 0xBC81, 0x7C40,
    0xB401, 0x74C0, 0x7580, 0xB541, 0x7700, 0xB7C1, 0xB681, 0x7640,
    0x7200, 0xB2C1, 0xB381, 0x7340, 0xB101, 0x71C0, 0x7080, 0xB041,
    0x5000, 0x90C1, 0x9181, 0x5140, 0x9301, 0x53C0, 0x5280, 0x9241,
    0x9601, 0x56C0, 0x5780, 0x9741, 0x5500, 0x95C1, 0x9481, 0x5440,
    0x9C01, 0x5CC0, 0x5D80, 0x9D41, 0x5F00, 0x9FC1, 0x9E81, 0x5E40,
    0x5A00, 0x9AC1, 0x9B81, 0x5B40, 0x9901, 0x59C0, 0x5880, 0x9841,
    0x8801, 0x48C0, 0x4980, 0x8941, 0x4B00, 0x8BC1, 0x8A81, 0x4A40,
    0x4E00, 0x8EC1, 0x8F81, 0x4F40, 0x8D01, 0x4DC0, 0x4C80, 0x8C41,
    0x4400, 0x84C1, 0x8581, 0x4540, 0x8701, 0x47C0, 0x4680, 0x8641,
    0x8201, 0x42C0, 0x4380, 0x8341, 0x4100, 0x81C1, 0x8081, 0x4040,
};

uint16_t ModbusCRC16_Table(const uint8_t *data, uint16_t length) {
    uint16_t crc = 0xFFFF;

    for (uint16_t i = 0; i < length; i++) {
        crc = (crc >> 8) ^ crc16_table[(crc ^ data[i]) & 0xFF];
    }
    return crc;
}
```

### 2.4 CRC Verification

For the test string "123456789" (bytes: 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39):
- **CRC-16 (Modbus)** = 0x4B37

---

## 3. MODBUS RTU FUNCTION CODES — DETAILED STRUCTURES

### 3.1 FC 0x01 — Read Coils (1-bit read/write)

**Request:**
```
| Slave Addr | FC | Start Addr Hi | Start Addr Lo | Qty Hi | Qty Lo | CRC Lo | CRC Hi |
| 1 byte      | 01 | 1 byte         | 1 byte         | 1 byte | 1 byte | 1 byte | 1 byte |
```
- Start Address: 0x0000 – 0xFFFF (0-based)
- Quantity: 1 – 2000 (0x0001 – 0x07D0)

**Response:**
```
| Slave Addr | FC | Byte Count | Data (N bytes) | CRC Lo | CRC Hi |
| 1 byte      | 01 | 1 byte     | ceil(Qty/8)    | 1 byte | 1 byte |
```
- Byte count = ceil(Quantity / 8)
- Bits packed LSB first within each byte
- Example: Status 0xCD = 1100 1101 → coil 7=1,6=1,5=0,4=0,3=1,2=1,1=0,0=1

### 3.2 FC 0x02 — Read Discrete Inputs (1-bit read-only)

**Request:**
```
| Slave Addr | FC | Start Addr Hi | Start Addr Lo | Qty Hi | Qty Lo | CRC Lo | CRC Hi |
| 1 byte      | 02 | 1 byte         | 1 byte         | 1 byte | 1 byte | 1 byte | 1 byte |
```
- Same structure as FC 01
- Quantity: 1 – 2000

**Response:**
```
| Slave Addr | FC | Byte Count | Data (N bytes) | CRC Lo | CRC Hi |
| 1 byte      | 02 | 1 byte     | ceil(Qty/8)    | 1 byte | 1 byte |
```

### 3.3 FC 0x03 — Read Holding Registers (16-bit read/write) — **MOST USED FOR INVERTERS**

**Request:**
```
| Slave Addr | FC | Start Addr Hi | Start Addr Lo | Qty Hi | Qty Lo | CRC Lo | CRC Hi |
| 1 byte      | 03 | 1 byte         | 1 byte         | 1 byte | 1 byte | 1 byte | 1 byte |
```
- Start Address: 0x0000 – 0xFFFF (0-based)
- Quantity: 1 – 125 (0x0001 – 0x007D) registers (some devices support up to 127)
- Register values are 16-bit (2 bytes each)
- **8 bytes total** for request

**Response:**
```
| Slave Addr | FC | Byte Count | Reg Hi | Reg Lo | Reg Hi | Reg Lo | ... | CRC Lo | CRC Hi |
| 1 byte      | 03 | 1 byte     | N*2 bytes of register data                | 1 byte | 1 byte |
```
- Byte count = Number of registers × 2
- Each register: high byte first, low byte second (big-endian per Modbus spec)

**Example — Read 3 holding registers starting at 0x006B:**
```
Request:  11 03 00 6B 00 03 76 87
Response: 11 03 06 00 6B 01 20 00 33 98 B4
                 │  └─────┘  └─────┘  └─────┘
                 6 bytes   Reg1     Reg2     Reg3
```

### 3.4 FC 0x04 — Read Input Registers (16-bit read-only) — **ALSO USED FOR INVERTERS**

**Request:**
```
| Slave Addr | FC | Start Addr Hi | Start Addr Lo | Qty Hi | Qty Lo | CRC Lo | CRC Hi |
| 1 byte      | 04 | 1 byte         | 1 byte         | 1 byte | 1 byte | 1 byte | 1 byte |
```
- Quantity: 1 – 125 registers

**Response:**
```
| Slave Addr | FC | Byte Count | Reg Hi | Reg Lo | ... | CRC Lo | CRC Hi |
| 1 byte      | 04 | 1 byte     | N*2 bytes          | 1 byte | 1 byte |
```
- Same structure as FC 03 response

### 3.5 FC 0x05 — Write Single Coil (1-bit write)

**Request:**
```
| Slave Addr | FC | Output Addr Hi | Output Addr Lo | Output Value Hi | Output Value Lo | CRC Lo | CRC Hi |
| 1 byte      | 05 | 1 byte          | 1 byte          | 1 byte           | 1 byte           | 1 byte | 1 byte |
```
- Output Value: 0xFF00 = ON, 0x0000 = OFF

**Response:** Echo of request ( identical frame returned)

### 3.6 FC 0x06 — Write Single Holding Register (16-bit write)

**Request:**
```
| Slave Addr | FC | Register Addr Hi | Register Addr Lo | Value Hi | Value Lo | CRC Lo | CRC Hi |
| 1 byte      | 06 | 1 byte            | 1 byte            | 1 byte   | 1 byte   | 1 byte | 1 byte |
```

**Response:** Echo of request (identical frame returned)

### 3.7 FC 0x0F (15) — Write Multiple Coils

**Request:**
```
| Slave Addr | FC | Start Addr Hi | Start Addr Lo | Qty Hi | Qty Lo | Byte Count | Data | CRC Lo | CRC Hi |
```

**Response:**
```
| Slave Addr | FC | Start Addr Hi | Start Addr Lo | Qty Hi | Qty Lo | CRC Lo | CRC Hi |
```

### 3.8 FC 0x10 (16) — Write Multiple Holding Registers

**Request:**
```
| Slave Addr | FC | Start Addr Hi | Start Addr Lo | Qty Hi | Qty Lo | Byte Count | Values (N*2) | CRC Lo | CRC Hi |
| 1 byte      | 10 | 1 byte          | 1 byte          | 1 byte  | 1 byte | 1 byte      | N*2 bytes     | 1 byte | 1 byte |
```
- Quantity: 1 – 123 registers
- Byte count = Quantity × 2

**Response:**
```
| Slave Addr | FC | Start Addr Hi | Start Addr Lo | Qty Hi | Qty Lo | CRC Lo | CRC Hi |
| 1 byte      | 10 | 1 byte          | 1 byte          | 1 byte | 1 byte | 1 byte | 1 byte |
```

### 3.9 FC 0x17 (23) — Read/Write Multiple Registers

**Request:**
```
| Slave Addr | FC | Read Start Hi | Read Start Lo | Read Qty Hi | Read Qty Lo | Write Start Hi | Write Start Lo | Write Qty Hi | Write Qty Lo | Write Byte Count | Write Values | CRC Lo | CRC Hi |
```
- Read Quantity: 1 – 125
- Write Quantity: 1 – 121

**Response:**
```
| Slave Addr | FC | Byte Count | Read Values | CRC Lo | CRC Hi |
```

### 3.10 FC 0x2B (43) — Read Device Identification

Subfunction 0x0E: Read Device ID
Used to identify manufacturer, device model, firmware version, etc.

---

## 4. DATA TABLES AND ADDRESSING

### 4.1 Modbus Data Model

| Table              | Access | Size    | Register# Range | Offset  | Data Address (0-based) | Read FC | Write FC (single) | Write FC (multiple) |
|--------------------|--------|---------|-----------------|---------|----------------------|---------|-------------------|---------------------|
| Coils              | R/W    | 1 bit   | 00001-09999     | 1       | 0x0000-0x270E        | 01      | 05                | 15                  |
| Discrete Inputs    | R      | 1 bit   | 10001-19999     | 10001   | 0x0000-0x270E        | 02      | —                 | —                   |
| Input Registers    | R      | 16 bit  | 30001-39999     | 30001   | 0x0000-0x270E        | 04      | —                 | —                   |
| Holding Registers  | R/W    | 16 bit  | 40001-49999     | 40001   | 0x0000-0x270E        | 03      | 06                | 16                  |

### 4.2 Address Calculation

**Data Address in message = Register Number - Offset**

Examples:
- Holding Register 40001 → Data Address 0x0000 (40001 - 40001 = 0)
- Holding Register 40100 → Data Address 0x0063 (40100 - 40001 = 99)
- Input Register 30001 → Data Address 0x0000 (30001 - 30001 = 0)
- Coil 00018 → Data Address 0x0011 (18 - 1 = 17)

### 4.3 Extended Addressing

- Holding registers beyond 49999 (data addresses 0x270F to 0xFFFF)
- Supports up to 65536 registers total (40001 to 105536)
- Not all devices or masters support this

---

## 5. TIMING REQUIREMENTS

### 5.1 Inter-Frame Silence

- **Between frames**: Minimum 3.5 character times of silence
- **Within a frame**: Maximum 1.5 character times between consecutive bytes
- If 1.5 char timeout is exceeded within a frame → frame is discarded

### 5.2 Character Time Calculation

Each character = 11 bits (1 start + 8 data + 1 parity + 1 stop)

At **19200 baud** (default Modbus baud rate):
- t1.5 = 1.5 × (11 / 19200) = **859.375 µs**
- t3.5 = 3.5 × (11 / 19200) = **2.005 ms**

At **9600 baud**:
- t1.5 = 1.5 × (11 / 9600) = **1.718 ms**
- t3.5 = 3.5 × (11 / 9600) = **4.010 ms**

At **115200 baud** and higher:
- Use fixed values per spec: **t1.5 = 750 µs, t3.5 = 1.750 ms**

### 5.3 Common Baud Rates

| Baud Rate | t1.5 (µs) | t3.5 (ms) |
|-----------|-----------|-----------|
| 1200      | 13750     | 32.08     |
| 2400      | 6875      | 16.04     |
| 4800      | 3437      | 8.02      |
| 9600      | 1719      | 4.01      |
| 19200     | 859       | 2.01      |
| 38400     | 430       | 1.00      |
| 57600     | 286       | 0.67      |
| 115200    | 750*      | 1.75*     |

*Fixed values for baud rates > 19200 per Modbus spec recommendation.

---

## 6. EXCEPTION RESPONSES

### 6.1 Exception Frame Format

```
| Slave Addr | Exception FC | Exception Code | CRC Lo | CRC Hi |
| 1 byte      | FC + 0x80     | 1 byte         | 1 byte | 1 byte |
```

- **Exception Function Code** = Original FC | 0x80 (MSB set)
- Example: FC 0x01 → Exception FC 0x81; FC 0x03 → Exception FC 0x83

### 6.2 Exception Codes

| Code | Name                       | Description |
|------|----------------------------|-------------|
| 01   | Illegal Function           | FC not recognized or not allowed by device |
| 02   | Illegal Data Address       | Data address does not exist in device |
| 03   | Illegal Data Value         | Value not accepted by device |
| 04   | Server Device Failure      | Unrecoverable error during execution |
| 05   | Acknowledge                | Request accepted, long processing time |
| 06   | Server Device Busy         | Device busy, retry later |
| 07   | Negative Acknowledge       | Cannot perform programming function |
| 08   | Memory Parity Error        | Parity error in extended memory |
| 10   | Gateway Path Unavailable   | Gateway misconfigured/overloaded |
| 11   | Gateway Target Failed       | Target device did not respond |

### 6.3 Response Scenarios

1. **Normal response**: FC echoed same as request, data follows
2. **No response**: Communication error (parity/CRC), device unreachable
3. **Exception response**: FC with MSB set + exception code

---

## 7. BYTE ORDERING (ENDIANNESS)

### 7.1 Modbus Standard Byte Order

The Modbus specification defines **big-endian** for transmission:
- 16-bit values: **High byte sent first, low byte sent second**
- 32-bit values (2 registers): Depends on device implementation

### 7.2 32-bit Value Representations (4 possible byte orders)

Given registers R1 (first) and R2 (second), and 32-bit value ABCD (A=MSByte, D=LSByte):

| Order | Name                        | R1    | R2    | Common Usage                           |
|-------|-----------------------------|-------|-------|----------------------------------------|
| ABCD  | Big-endian (Motorola)       | AB    | CD    | Most Modbus devices                    |
| CDAB  | Little-endian (Intel)       | CD    | AB    | Some devices (ARM, Intel-based)        |
| BADC  | Word-swapped big-endian     | BA    | DC    | Some Schneider/Modicon devices         |
| DCBA  | Word-swapped little-endian | DC    | BA    | Rare                                   |

### 7.3 Word Swapping (Register Order)

For 32-bit values spanning 2 consecutive registers:
- **Standard (Big-endian)**: High word in first register, Low word in second
- **Swapped**: Low word in first register, High word in second
- **Must check device documentation** — no universal standard for 32-bit values

### 7.4 Practical Examples

Value: 0x12345678

| Byte Order | Register 1 | Register 2 | Bytes on wire                    |
|------------|-----------|-----------|----------------------------------|
| ABCD       | 0x1234    | 0x5678    | 12 34 56 78                     |
| CDAB       | 0x5678    | 0x1234    | 56 78 12 34                     |
| BADC       | 0x3412    | 0x7856    | 34 12 78 56                     |
| DCBA       | 0x7856    | 0x3412    | 78 56 34 12                     |

**IMPORTANT**: Solar inverters frequently use different byte orders. Always consult the specific inverter's Modbus register map documentation.

---

## 8. SOLAR INVERTER — MODBUS RTU IMPLEMENTATIONS

### 8.1 Common Register Types for Solar Inverters

Most solar inverters expose the following data types via Modbus:

| Measurement              | Typical Data Type      | Unit     | Notes                                    |
|--------------------------|------------------------|----------|------------------------------------------|
| DC Voltage (PV)         | uint16 / float32       | V        | Per MPPT/string                          |
| DC Current (PV)         | uint16 / int16         | A        | Per MPPT/string, may be signed           |
| DC Power (PV)           | uint16 / uint32        | W        | Per MPPT/string                          |
| AC Voltage (L1/L2/L3)   | uint16 / float32       | V        | Per phase, scaled (×10 or ×100)         |
| AC Current (L1/L2/L3)   | uint16 / int16         | A        | Per phase, scaled (×10 or ×100)         |
| AC Power (total)         | uint16 / int32         | W        | Total active power, may be signed        |
| AC Reactive Power       | int16 / int32          | VAr     | Signed value                             |
| AC Frequency             | uint16                 | Hz       | Scaled (×100 = 5000 for 50.00Hz)         |
| Total Energy (yield)    | uint32 / float32       | kWh      | Cumulative, 2 registers for uint32       |
| Daily Energy             | uint16 / uint32        | kWh      | Reset at midnight                       |
| Temperature (inverter)   | int16                  | °C       | Can be negative                         |
| Temperature (heatsink)   | int16                  | °C       |                                          |
| Power Factor             | int16                  | —        | Scaled (×100 or ×1000)                  |
| Operating Status         | uint16                 | —        | Bitfield: running/fault/standby          |
| Error Codes              | uint16                 | —        | Bitfield or enumerated                   |
| Firmware Version         | uint16 / string        | —        | Multiple registers for string           |
| Serial Number            | string                 | —        | Multiple registers (8-16)                |

### 8.2 Common Scaling Factors

| Value               | Scale      | Example: Register Value | Real Value  |
|----------------------|-----------|------------------------|-------------|
| Voltage              | ×10        | 2301                   | 230.1 V     |
| Voltage              | ×100       | 23010                  | 230.10 V    |
| Current              | ×10        | 55                     | 5.5 A       |
| Current              | ×100       | 550                    | 5.50 A      |
| Power                | ×1         | 5000                   | 5000 W      |
| Power                | ×10        | 500                    | 5000 W      |
| Energy               | ×1         | 12345                  | 12345 kWh   |
| Energy               | ×0.01      | 1234500                | 12345.00 kWh|
| Frequency            | ×100       | 5000                   | 50.00 Hz    |
| Temperature          | ×10        | 455                    | 45.5 °C     |
| Power Factor         | ×1000      | 950                    | 0.950       |

### 8.3 Inverter-Specific Register Maps

#### 8.3.1 SMA Inverters (Sunny Boy, Sunny Tripower)
- **Slave Address**: 3 (default), configurable 1-247
- **Baud Rate**: 9600 (default), supports up to 115200
- **Function Code**: Primarily FC 03 (Read Holding Registers) and FC 04 (Read Input Registers)
- **Protocol**: SMA uses a Modbus subset known as "SMA Modbus Profile"
- **Typical Register Map (SMA SunSpec models)**:

| Register  | Description                    | Scale  | Type   |
|-----------|-------------------------------|--------|--------|
| 30201     | DC Current String A           | ×100   | uint16 |
| 30203     | DC Voltage String A           | ×100   | uint16 |
| 30207     | DC Power String A             | ×1     | uint16 |
| 30225     | DC Current String B           | ×100   | uint16 |
| 30227     | DC Voltage String B           | ×100   | uint16 |
| 30231     | DC Power String B             | ×1     | uint16 |
| 30283     | Total DC Power                | ×1     | uint32 |
| 30351     | Phase A Current (L1)          | ×1000  | int16  |
| 30353     | Phase B Current (L2)          | ×1000  | int16  |
| 30355     | Phase C Current (L3)          | ×1000  | int16  |
| 30357     | Phase A Voltage (L-N)          | ×100   | uint16 |
| 30359     | Phase B Voltage (L-N)          | ×100   | uint16 |
| 30361     | Phase C Voltage (L-N)          | ×100   | uint16 |
| 30369     | AC Power                      | ×1     | int32  |
| 30373     | AC Reactive Power             | ×1     | int32  |
| 30379     | AC Frequency                  | ×1000  | uint16 |
| 30385     | Operating Status              | —      | uint32 |
| 30387     | Temperature (inverter)        | ×10    | int16  |
| 30389     | Total Yield (cumulative)      | ×1     | uint32 |
| 30529     | Daily Yield                   | ×1     | uint32 |

#### 8.3.2 Growatt Inverters
- **Slave Address**: 1 (default)
- **Baud Rate**: 9600
- **Function Code**: FC 03 (Read Holding Registers), FC 04 (Read Input Registers)
- **Register Map**:

| Register  | Description                    | Scale  | Type   |
|-----------|-------------------------------|--------|--------|
| 0         | Inverter Status               | —      | uint16 |
| 1         | PV1 Voltage                   | ×10    | uint16 |
| 2         | PV1 Current                   | ×10    | uint16 |
| 3         | PV1 Power                     | ×1     | uint16 |
| 4         | PV2 Voltage                   | ×10    | uint16 |
| 5         | PV2 Current                    | ×10    | uint16 |
| 6         | PV2 Power                      | ×1     | uint16 |
| 7-8       | Total DC Power                | ×1     | uint32 |
| 9         | Grid Frequency                | ×100   | uint16 |
| 10        | L1 Voltage                    | ×10    | uint16 |
| 11        | L1 Current                    | ×10    | uint16 |
| 12        | L1 Power                      | ×1     | uint16 |
| 13        | L2 Voltage                    | ×10    | uint16 |
| 14        | L2 Current                    | ×10    | uint16 |
| 15        | L2 Power                      | ×1     | uint16 |
| 16        | L3 Voltage                    | ×10    | uint16 |
| 17        | L3 Current                    | ×10    | uint16 |
| 18        | L3 Power                      | ×1     | uint16 |
| 26-27     | Total Active Power            | ×1     | int32  |
| 28-29     | Total Reactive Power          | ×1     | int32  |
| 34        | Inverter Temperature          | ×1     | uint16 |
| 35        | IPM Temperature               | ×1     | uint16 |
| 36        | Boost Temperature             | ×1     | uint16 |
| 38-39     | Total Energy (cumulative)     | ×0.1   | uint32 |
| 40-41     | Total Energy (this month)     | ×0.1   | uint32 |
| 42-43     | Daily Energy                  | ×0.1   | uint32 |
| 44-45     | Last Month Energy             | ×0.1   | uint32 |

#### 8.3.3 Solis Inverters
- **Slave Address**: 1 (default)
- **Baud Rate**: 9600, 8N2 or 8E1
- **Function Code**: FC 03, FC 04
- **Register Map**:

| Register  | Description                    | Scale  | Type   |
|-----------|-------------------------------|--------|--------|
| 0         | Inverter State                | —      | uint16 |
| 1         | Inverter Error Code           | —      | uint16 |
| 3         | DC Voltage PV1                 | ×10    | uint16 |
| 4         | DC Current PV1                 | ×100   | uint16 |
| 5         | DC Power PV1                   | ×10    | uint16 |
| 7         | DC Voltage PV2                 | ×10    | uint16 |
| 8         | DC Current PV2                 | ×100   | uint16 |
| 9         | DC Power PV2                   | ×10    | uint16 |
| 13        | AC Voltage L1                  | ×10    | uint16 |
| 14        | AC Current L1                  | ×100   | uint16 |
| 23        | AC Frequency                   | ×100   | uint16 |
| 24        | AC Active Power (total)         | ×1     | uint16 |
| 28        | AC Reactive Power              | ×1     | int16  |
| 30        | Inverter Temperature           | ×1     | int16  |
| 35-36     | Total Energy Production        | ×1     | uint32 |
| 37-38     | Monthly Energy Production      | ×1     | uint32 |
| 39-40     | Yearly Energy Production       | ×1     | uint32 |
| 41-42     | Daily Energy Production        | ×0.1   | uint32 |

#### 8.3.4 Deye / Solax / Sofar Inverters
- **Slave Address**: 1 (default)
- **Baud Rate**: 9600, 8N1
- **Function Code**: FC 03 (Reading Holding Registers)
- **Note**: Deye, Solax, Sofar share very similar firmware/register maps
- **Register Map**:

| Register  | Description                    | Scale  | Type   |
|-----------|-------------------------------|--------|--------|
| 0x00      | Inverter Model                | —      | uint16 |
| 0x03      | Rated Power                   | ×1     | uint16 |
| 0x04      | AC Output Type                | —      | uint16 |
| 0x05      | Firmware Version (major)      | —      | uint16 |
| 0x0C-0x0D| Serial Number (partial)       | —      | string |
| 0x12      | PV1 Voltage                   | ×10    | uint16 |
| 0x13      | PV1 Current                   | ×10    | uint16 |
| 0x14      | PV2 Voltage                   | ×10    | uint16 |
| 0x15      | PV2 Current                   | ×10    | uint16 |
| 0x16-0x17| PV1 Power                     | ×1     | uint32 |
| 0x18-0x19| PV2 Power                     | ×1     | uint32 |
| 0x3C      | AC Output Voltage L1           | ×10    | uint16 |
| 0x3E      | AC Output Frequency            | ×100   | uint16 |
| 0x3F-0x40| AC Output Power               | ×1     | uint32 |
| 0x41-0x42| Grid Voltage L1               | ×10    | uint16 |
| 0x44      | Grid Frequency                | ×100   | uint16 |
| 0x4A      | Inverter Temperature          | ×1     | int16  |
| 0x4C-0x4D| Total Energy (lifetime)       | ×1     | uint32 |
| 0x4E-0x4F| Daily Energy                  | ×1     | uint32 |
| 0x50-0x51| Monthly Energy                | ×1     | uint32 |
| 0x52-0x53| Yearly Energy                 | ×1     | uint32 |

#### 8.3.5 Fronius Inverters
- **Slave Address**: 1 (default), configurable 1-247
- **Baud Rate**: 9600
- **Function Code**: FC 03, FC 04
- **Protocol**: Fronius uses a proprietary register map AND supports SunSpec
- **Notable**: Fronius uses both holding and input registers
- **SunSpec Common Block** starts at register 40000 (offset 0)

| Register (Offset) | Description (SunSpec)          |
|-------------------|-------------------------------|
| 0                 | SunSpec Identifier (0x53756E53)|
| 2                 | SunSpec DID (1 = Common)       |
| 3                 | SunSpec Length (65 or 66)      |
| 4-19              | Manufacturer (string)          |
| 20-35             | Model (string)                 |
| 36-41             | Options (string)               |
| 42-57             | Version (string)               |
| 58-73             | Serial Number (string)         |
| 74                | Device Address                 |
| 75                | Next DID                       |

#### 8.3.6 Victron Energy
- **Slave Address**: 100 (default for GX device)
- **Baud Rate**: 19200 (VE.Bus), configurable for RS485
- **Function Code**: FC 03, FC 04
- **Supports**: Both Victron proprietary protocol and Modbus TCP/RTU

---

## 9. SUNSPEC MODBUS STANDARD FOR SOLAR INVERTERS

### 9.1 Overview

SunSpec is an industry-standard Modbus register mapping for solar/PV devices.
Many inverters (SMA, Fronius, SolarEdge, ABB, etc.) support SunSpec.

### 9.2 SunSpec Model Structure

| Model ID | Name                          | Description                        |
|----------|------------------------------|------------------------------------|
| 1        | Common Block                  | Device identification              |
| 101-103  | Single Phase Inverter          | 1-phase inverter data              |
| 111-113  | Three Phase Inverter (wye)     | 3-phase wye inverter data          |
| 120-122  | Three Phase Inverter (delta)   | 3-phase delta inverter data        |
| 160      | Multiple MPPT Inverter         | Extended MPPT data                 |
| 201-203  | Single Phase Meter             | 1-phase meter reading              |
| 211-213  | Three Phase Meter (wye)        | 3-phase meter data                 |
| 64001-64101 | String Inverter Extension   | Additional inverter data           |

### 9.3 SunSpec Inverter Model 113 (3-Phase) Typical Registers

| Offset | Name                  | Type    | Scale | Units |
|--------|----------------------|---------|-------|-------|
| 0      | DID (113)            | uint16  | —     | —     |
| 1      | Length               | uint16  | —     | —     |
| 2      | AC Current           | int16   | ×10   | A     |
| 3      | AC Current Phase A   | int16   | ×10   | A     |
| 4      | AC Current Phase B   | int16   | ×10   | A     |
| 5      | AC Current Phase C   | int16   | ×10   | A     |
| 6      | AC Voltage Phase AB  | int16   | ×10   | V     |
| 7      | AC Voltage Phase BC  | int16   | ×10   | V     |
| 8      | AC Voltage Phase CA  | int16   | ×10   | V     |
| 9      | AC Voltage Phase A   | int16   | ×10   | V     |
| 10     | AC Voltage Phase B   | int16   | ×10   | V     |
| 11     | AC Voltage Phase C   | int16   | ×10   | V     |
| 13     | AC Power             | int32   | ×1   | W     |
| 15     | AC Power Phase A     | int16   | ×1   | W     |
| 16     | AC Power Phase B     | int16   | ×1   | W     |
| 17     | AC Power Phase C     | int16   | ×1   | W     |
| 19     | AC Frequency         | int16   | ×100  | Hz    |
| 20     | AC VA                | int32   | ×1   | VA    |
| 22     | AC VA Phase A        | int16   | ×1   | VA    |
| 23     | AC VA Phase B        | int16   | ×1   | VA    |
| 24     | AC VA Phase C        | int16   | ×1   | VA    |
| 26     | AC VAR               | int32   | ×1   | VAr   |
| 28     | AC PF                | int16   | ×1000| —     |
| 29     | AC PF Phase A        | int16   | ×1000| —     |
| 30     | AC PF Phase B        | int16   | ×1000| —     |
| 31     | AC PF Phase C        | int16   | ×1000| —     |
| 33     | AC Energy            | uint32  | ×1   | kWh   |
| 39     | DC Current           | int16   | ×10   | A     |
| 40     | DC Voltage           | int16   | ×10   | V     |
| 41     | DC Power             | int32   | ×1   | W     |
| 43     | Heatsink Temp        | int16   | ×1   | °C    |
| 44     | Operating State      | uint16  | —     | —     |
| 45     | Vendor Operating State| uint16 | —     | —     |

---

## 10. PRACTICAL IMPLEMENTATION NOTES FOR SOLAR INVERTERS

### 10.1 Typical Connection Setup

```
RS485 Bus:
  Master (ESP32/Arduino/PC) ←→ RS485 Transceiver (MAX485/MAX3485) ←→ Inverter(s)
  
Wiring:
  A (D+) → A (D+) on all devices
  B (D-) → B (D-) on all devices
  GND    → GND on all devices (important for noise immunity)
  120Ω termination resistor at each end of the bus
```

### 10.2 Typical Communication Parameters

| Parameter    | Common Values                          |
|-------------|----------------------------------------|
| Baud Rate   | 9600 (most common), 19200, 115200      |
| Data Bits   | 8                                      |
| Parity      | None (2 stop bits) or Even (1 stop bit)|
| Stop Bits   | 1 (with parity) or 2 (no parity)      |
| Flow Control| None                                   |

### 10.3 32-bit Value Reading Strategy

When reading 32-bit values (uint32, int32, float32) via Modbus:
1. Read 2 consecutive registers
2. Note the byte order (check inverter documentation)
3. Reassemble: high word and low word may need swapping
4. For float32: IEEE 754 representation across 2 registers

### 10.4 Polling Strategy for Solar Inverters

- **Recommended poll interval**: 1-5 seconds for real-time data
- **Batch reading**: Read multiple consecutive registers in one request (FC 03/04) rather than individual reads
- **Max registers per request**: 125 (some devices support less)
- **Error handling**: If CRC fails, retry 2-3 times before reporting error
- **Broadcast (address 0)**: Only for writes, slaves must not respond

### 10.5 RS485 Multi-Inverter Configuration

- Each inverter must have a **unique slave address** (1-247)
- Master polls each inverter sequentially
- Maximum 247 devices on one RS485 bus
- Cable length max: 1200m at 9600 baud (decreases with higher baud)
- Use twisted pair cable, shielded if possible
- Termination resistors (120Ω) at both ends of the bus

---

## 11. COMPLETE EXAMPLE: Read Solar Inverter Power via Modbus RTU

### Scenario: Read 10 holding registers starting at address 0x0000 from inverter at address 1

**Request Frame:**
```
01 03 00 00 00 0A C5 CD
│  │  └──┘  └──┘ └──┘
│  │   │     │     └── CRC: 0xCDC5 (Lo=C5, Hi=CD)
│  │   │     └── Quantity: 10 registers
│  │   └── Starting address: 0x0000
│  └── Function Code: 0x03 (Read Holding Registers)
└── Slave Address: 1
```

**Response Frame:**
```
01 03 14 00 00 00 0B 00 14 00 55 00 00 00 64 13 88 00 19 00 C8 01 F4 00 00 XX XX
│  │  │  └─────────────────────────────────────────────────────────────┘  └──┘
│  │  │  20 bytes of data (10 registers × 2 bytes each)                   CRC
│  │  └─ Byte count: 0x14 = 20 bytes
│  └─ Function Code: 0x03
└─ Slave Address: 1

Register values:
  Reg 0: 0x0000 = 0     (status)
  Reg 1: 0x000B = 11    (PV1 voltage ×10 = 1.1V... or 11V depending on scale)
  Reg 2: 0x0014 = 20    (PV1 current ×10 = 2.0A)
  Reg 3: 0x0055 = 85    (PV1 power)
  ...
```

---

## 12. QUICK REFERENCE SUMMARY

| Item | Value |
|------|-------|
| Max ADU size (RTU) | 256 bytes |
| Max PDU data | 253 bytes |
| Max registers per read (FC 03/04) | 125 |
| Max registers per write (FC 16) | 123 |
| Max coils per read (FC 01/02) | 2000 |
| Max coils per write (FC 15) | 1968 |
| Slave address range | 1-247 (248-255 reserved) |
| Broadcast address | 0 |
| CRC polynomial | 0xA001 (reversed) |
| CRC init value | 0xFFFF |
| CRC byte order | Low byte first |
| Data byte order | Big-endian (MSB first) per spec |
| Inter-frame gap | 3.5 character times |
| Inter-character timeout | 1.5 character times |
| Default baud | 19200 (many inverters use 9600) |
| Default parity | Even |
| Exception FC | Original FC + 0x80 |
