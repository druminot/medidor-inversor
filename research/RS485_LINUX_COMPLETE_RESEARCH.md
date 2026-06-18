# RS485 Communication with Solar Inverters on Linux — Complete Research

---

## Table of Contents
1. USB-RS485 Adapters (Chipsets, Drivers, How They Work)
2. Linux Serial Port Interface (/dev/ttyUSB*, termios, RS485 ioctl)
3. Modbus RTU Protocol Details (see also MODBUS_RTU_RESEARCH.md)
4. Common Serial Settings for Solar Inverters
5. Python/C Libraries for Modbus RTU (pymodbus, minimalmodbus, libmodbus)
6. Docker Container with Serial Port Access
7. Best Practices for Reliable RS485 Communication

---

# 1. USB-RS485 ADAPTERS

## 1.1 How USB-RS485 Adapters Work

A USB-RS485 adapter is a 3-stage device:

```
[USB Host] ←→ [USB-to-UART Bridge Chip] ←→ [RS485 Transceiver] ←→ [RS485 Bus (A/B/GND)]
```

1. **USB-to-UART Bridge**: Converts USB protocol to standard UART (TX/RX signals). The host OS loads a driver that creates a serial device node.
2. **RS485 Transceiver** (e.g., MAX485, SP3485, SN65HVD75): Converts UART TTL signals to differential RS485 signals (A/B lines). Handles direction control (DE/RE pins).
3. **Auto-direction control**: Most cheap adapters use a simple trick — they tie DE (driver enable) to the TX signal itself. When TX is idle (high), DE is low (receive mode). When TX is active (bytes being sent), the signal goes low at the start bit, which enables the driver. This works but has a minor timing hazard — the driver may stay enabled briefly after the last stop bit, potentially truncating the response or causing collisions.

### Auto-Direction Control vs Manual DE/RE

| Feature | Auto-direction (cheap adapters) | Manual DE/RE control (better adapters) |
|---------|--------------------------------|---------------------------------------|
| Mechanism | DE tied to TX line via RC circuit or diode | DE/RE controlled by RTS/DTR GPIO from USB-UART chip |
| Pros | No software configuration needed | Precise timing, no truncation risk |
| Cons | Slight timing delay on RX after TX; may cause first byte of response to be lost | Requires RS485 ioctl or RTS pin control in software |
| Linux support | Works out of box | Needs TIOCSRS485 ioctl or RTS control |
| Recommended for | Simple setups, low baud rates | Production/reliable communication, higher baud rates |

## 1.2 Common Chipsets and Linux Driver Support

### CH340 / CH340G (Nanjing Qinheng Microelectronics / WCH)

| Parameter | Value |
|-----------|-------|
| USB VID:PID | 1A86:7523 (CH340), 1A86:5523 (CH340N) |
| Linux Driver | `ch341` (built-in since kernel 2.6.24) |
| Device Node | `/dev/ttyUSB0` |
| Max Baud Rate | 2 Mbps (CH340G), limited by RS485 transceiver |
| Supports RS485 ioctl | No (ch341 driver does not implement TIOCSRS485) |
| Auto-direction | DE tied to TX via hardware |
| Price Range | $1-3 USD |
| Quality | Budget; cloned heavily; some clones have issues at >115200 baud |

**dmesg on plug:**
```
usb 1-1.3: new full-speed USB device number 5 using xhci_hcd
usb 1-1.3: New USB device found, idVendor=1a86, idProduct=7523
usb 1-1.3: New USB device strings: Mfr=0, Product=2, SerialNumber=0
usb 1-1.3: Product: USB2.0-Serial
ch341 1-1.3:1.0: ch341-uart converter detected
usb 1-1.3: ch341-uart converter now attached to ttyUSB0
```

**Sources:**
- Linux kernel source: drivers/usb/serial/ch341.c
- WCH official: http://www.wch-ic.com/products/CH340.html
- kernel.org docs: https://www.kernel.org/doc/html/latest/usb/usb-serial.html

---

### FT232 / FT232R / FT232H (FTDI Future Technology Devices International)

| Parameter | Value |
|-----------|-------|
| USB VID:PID | 0403:6001 (FT232R), 0403:6014 (FT232H) |
| Linux Driver | `ftdi_sio` (built-in since kernel 2.6) |
| Device Node | `/dev/ttyUSB0` |
| Max Baud Rate | 3 Mbps (FT232R), 12 Mbps (FT232H in FIFO mode) |
| Supports RS485 ioctl | Yes (ftdi_sio implements TIOCSRS485 since kernel 4.13) |
| GPIO Pins | CBUS pins usable for DE/RE control (bitbang mode) |
| Price Range | $15-35 USD (genuine); clones circulate |
| Quality | Industrial-grade, excellent driver support, most reliable |

**dmesg on plug:**
```
usb 1-1: new full-speed USB device number 3 using xhci_hcd
usb 1-1: New USB device found, idVendor=0403, idProduct=6001
usb 1-1: New USB device strings: Mfr=1, Product=2, SerialNumber=3
usb 1-1: Product: FT232R USB UART
usb 1-1: Manufacturer: FTDI
usb 1-1: SerialNumber: A50285BI
ftdi_sio 1-1:1.0: FTDI USB Serial Device converter detected
usb 1-1: FTDI USB Serial Device converter now attached to ttyUSB0
```

**RS485 ioctl support (kernel 4.13+):**
```c
#include <linux/serial.h>
#include <sys/ioctl.h>

struct serial_rs485 rs485conf;
rs485conf.flags = SER_RS485_ENABLED | SER_RS485_RTS_ON_SEND | SER_RS485_RTS_AFTER_SEND;
ioctl(fd, TIOCSRS485, &rs485conf);
```

**Sources:**
- FTDI official: https://ftdichip.com/products/ft232r/
- Linux kernel: drivers/usb/serial/ftdi_sio.c
- Kernel commit adding RS485: https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=9b8e8c5f

---

### CP2102 / CP2102N (Silicon Labs)

| Parameter | Value |
|-----------|-------|
| USB VID:PID | 10C4:EA60 (CP2102), 10C4:EA70 (CP2102N) |
| Linux Driver | `cp210x` (built-in since kernel 2.6.22) |
| Device Node | `/dev/ttyUSB0` |
| Max Baud Rate | 1 Mbps |
| Supports RS485 ioctl | Yes (cp210x implements TIOCSRS485 since kernel 5.12) |
| GPIO Pins | 2-4 GPIO pins for DE/RE control |
| Price Range | $5-15 USD |
| Quality | Good; widely used in industrial USB-RS485 adapters |

**dmesg on plug:**
```
usb 1-1: new full-speed USB device number 4 using xhci_hcd
usb 1-1: New USB device found, idVendor=10c4, idProduct=ea60
usb 1-1: New USB device strings: Mfr=1, Product=2, SerialNumber=3
usb 1-1: Product: CP2102 USB to UART Bridge Controller
cp210x 1-1:1.0: cp210x converter detected
usb 1-1: cp210x converter now attached to ttyUSB0
```

**Sources:**
- Silicon Labs official: https://www.silabs.com/development-tools/interface/cp2102n-bridge-controllers
- Linux kernel: drivers/usb/serial/cp210x.c
- Kernel commit adding RS485: https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=39a5e44e

---

### CH9344 (WCH - newer, multi-port)

| Parameter | Value |
|-----------|-------|
| USB VID:PID | 1A86:EBxx (varies by variant) |
| Linux Driver | `ch9344` (out-of-tree; WCH provides driver on GitHub/their site) |
| Device Node | `/dev/ttyCH9344USB0` (custom naming) |
| Ports | 2 or 4 RS485/RS232 ports on one USB device |
| Max Baud Rate | 6 Mbps |
| Supports RS485 ioctl | Yes (ch9344 driver implements TIOCSRS485) |
| Price Range | $15-30 USD |
| Quality | Good; aimed at industrial multi-port applications |

**Installation (out-of-tree driver):**
```bash
git clone https://github.com/WCHSoftGroup/ch9344linux.git
cd ch9344linux
make
sudo make install
sudo modprobe ch9344
```

**dmesg on plug:**
```
usb 1-1: new high-speed USB device number 7 using xhci_hcd
usb 1-1: New USB device found, idVendor=1a86, idProduct=eb11
ch9344 1-1:1.0: ch9344 converter detected
usb 1-1: ch9344 converter now attached to ttyCH9344USB0
usb 1-1: ch9344 converter now attached to ttyCH9344USB1
```

**Sources:**
- WCH GitHub: https://github.com/WCHSoftGroup/ch9344linux
- WCH official: http://www.wch-ic.com/products/CH9344.html

---

### Chipset Comparison Summary

| Feature | CH340 | FT232R | CP2102 | CH9344 |
|---------|-------|--------|--------|--------|
| Driver | ch341 (built-in) | ftdi_sio (built-in) | cp210x (built-in) | ch9344 (out-of-tree) |
| RS485 ioctl | No | Yes (≥4.13) | Yes (≥5.12) | Yes |
| Auto-direction | Hardware only | Software or hardware | Software or hardware | Software or hardware |
| Unique Serial# | No (clones) | Yes | Yes | Yes |
| Multi-port | No | No | No | 2-4 ports |
| Built-in kernel | Yes | Yes | Yes | No |
| Reliability | Budget | Excellent | Good | Good |
| Typical use | Hobby/DIY | Professional | Industrial/Maker | Industrial multi-port |
| Counterfeit risk | Very high | High (FTDI clones) | Low | Low (niche) |

---

# 2. LINUX SERIAL PORT INTERFACE

## 2.1 Device Nodes

USB-RS485 adapters appear as serial device nodes under `/dev/`:

| Device | Adapter Type | Driver |
|--------|-------------|--------|
| `/dev/ttyUSB0` | Most USB-serial adapters | ch341, ftdi_sio, cp210x |
| `/dev/ttyACM0` | USB CDC-ACM class devices | cdc_acm |
| `/dev/ttyCH9344USB0` | CH9344 multi-port | ch9344 |
| `/dev/ttyS0` | Native hardware UART (COM1) | 8250/16550 |

**Listing available serial ports:**
```bash
ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
ls -la /dev/serial/by-id/    # persistent naming by USB serial number
dmesg | grep tty             # check kernel logs for detected ports
```

## 2.2 Permissions

Serial ports are typically owned by group `dialout` (Debian/Ubuntu) or `uucp` (RHEL/Fedora/Arch):

```bash
# Add user to dialout group
sudo usermod -aG dialout $USER

# Verify
groups $USER

# Or temporarily change permissions (not recommended)
sudo chmod 666 /dev/ttyUSB0
```

**Udev rule for persistent symlink and permissions** (`/etc/udev/rules.d/99-rs485.rules`):
```udev
# CP2102 RS485 adapter with serial number
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", ATTRS{serial}=="0001", SYMLINK+="inverter_rs485", GROUP="dialout", MODE="0664"

# FTDI adapter
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", SYMLINK+="inverter_rs485", GROUP="dialout", MODE="0664"

# CH340 adapter (no serial number - match by physical USB port)
SUBSYSTEM=="tty", KERNELS=="1-1.3:1.0", SYMLINK+="inverter_rs485", GROUP="dialout", MODE="0664"
```

Apply:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## 2.3 Termios Configuration

The Linux `termios` API controls all serial port parameters:

```c
#include <termios.h>
#include <fcntl.h>
#include <unistd.h>

int fd = open("/dev/ttyUSB0", O_RDWR | O_NOCTTY | O_NDELAY);

struct termios options;
tcgetattr(fd, &options);

// Baud rate
cfsetispeed(&options, B9600);
cfsetospeed(&options, B9600);

// 8 data bits, no parity, 1 stop bit (8N1)
options.c_cflag &= ~PARENB;      // No parity
options.c_cflag &= ~CSTOPB;      // 1 stop bit
options.c_cflag &= ~CSIZE;
options.c_cflag |= CS8;          // 8 data bits

// 8E1 (even parity, 1 stop bit)
// options.c_cflag |= PARENB;    // Enable parity
// options.c_cflag &= ~PARODD;  // Even parity
// options.c_cflag &= ~CSTOPB;  // 1 stop bit

// 8N2 (no parity, 2 stop bits)
// options.c_cflag &= ~PARENB;  // No parity
// options.c_cflag |= CSTOPB;  // 2 stop bits

// Disable flow control (required for RS485)
options.c_cflag &= ~CRTSCTS;    // No hardware flow control

// Enable receiver, ignore modem control lines
options.c_cflag |= CREAD | CLOCAL;

// Raw input mode (no canonical, no echo, no signals)
options.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);

// Disable software flow control
options.c_iflag &= ~(IXON | IXOFF | IXANY);
options.c_iflag &= ~(ICRNL | INLCR);  // No CR/LF translation

// Raw output mode
options.c_oflag &= ~OPOST;

// Timeout settings (for Modbus RTU)
options.c_cc[VMIN] = 0;          // Don't block for minimum bytes
options.c_cc[VTIME] = 1;         // 100ms inter-character timeout (1 = 0.1s)

tcsetattr(fd, TCSANOW, &options);

// Flush buffers
tcflush(fd, TCIOFLUSH);
```

### Baud Rate Constants

| Constant | Baud Rate |
|----------|-----------|
| B1200 | 1200 |
| B2400 | 2400 |
| B4800 | 4800 |
| B9600 | 9600 |
| B19200 | 19200 |
| B38400 | 38400 |
| B57600 | 57600 |
| B115200 | 115200 |
| B230400 | 230400 |
| B460800 | 460800 |

## 2.4 RS485-Specific ioctl (TIOCSRS485)

For adapters that support hardware DE/RE control via software (FT232, CP2102, CH9344):

```c
#include <linux/serial.h>

struct serial_rs485 rs485;
rs485.flags = SER_RS485_ENABLED | SER_RS485_RTS_ON_SEND;
// SER_RS485_ENABLED    - Enable RS485 mode
// SER_RS485_RTS_ON_SEND - Set RTS high before sending (enables driver)
// SER_RS485_RTS_AFTER_SEND - Set RTS high after sending (optional)
// SER_RS485_RX_DURING_TX - Enable receiving while transmitting (full-duplex, rarely used)

rs485.delay_rts_before_send = 0;   // Delay in ms before asserting RTS
rs485.delay_rts_after_send = 1;    // Delay in ms after last byte before releasing RTS
                                  // Critical: must be long enough for last byte to fully transmit

ioctl(fd, TIOCSRS485, &rs485);
```

**Important note on delay_rts_after_send**: This value must account for the time it takes for the last byte to shift out of the UART. At 9600 baud, one character (11 bits) takes ~1.15ms. A 1ms delay is generally safe; some drivers add this automatically.

## 2.5 Using `stty` to Configure and Verify

```bash
# Current settings
stty -F /dev/ttyUSB0 -a

# Configure 9600 8N1
stty -F /dev/ttyUSB0 9600 cs8 -parenb -cstopb -echo raw

# Configure 9600 8E1
stty -F /dev/ttyUSB0 9600 cs8 parenb -parodd -cstopb -echo raw

# Configure 19200 8N2
stty -F /dev/ttyUSB0 19200 cs8 -parenb cstopb -echo raw

# Disable flow control
stty -F /dev/ttyUSB0 -crtscts -ixon -ixoff
```

## 2.6 Python pyserial Configuration

```python
import serial

ser = serial.Serial(
    port='/dev/ttyUSB0',
    baudrate=9600,
    parity=serial.PARITY_NONE,    # PARITY_EVEN, PARITY_ODD
    stopbits=serial.STOPBITS_ONE, # STOPBITS_TWO
    bytesize=serial.EIGHTBITS,
    timeout=3,          # Read timeout in seconds
    xonxoff=False,      # No software flow control
    rtscts=False,       # No hardware flow control
    dsrdtr=False,       # No DTR/DSR flow control
)

# For adapters needing RTS-based direction control:
ser.rs485_mode = serial.RS485Settings(rts_level_for_tx=True)

ser.write(b'\x01\x03\x00\x00\x00\x0A\xC5\xCD')
response = ser.read(25)  # Read expected response
ser.close()
```

---

# 3. MODBUS RTU PROTOCOL DETAILS

**Comprehensive details are in `MODBUS_RTU_RESEARCH.md` in this same directory.** Summary of key points:

## 3.1 Frame Format
- RTU ADU = Slave Address (1 byte) + Function Code (1 byte) + Data (0-252 bytes) + CRC16 (2 bytes, low byte first)
- Each byte on wire = 11 bits (1 start + 8 data LSB-first + 1 parity + 1 stop)
- Max frame: 256 bytes

## 3.2 CRC16 Algorithm
- Polynomial: 0xA001 (reversed), init 0xFFFF, no final XOR
- Bit-by-bit: XOR byte into CRC, shift right 8 times, XOR with 0xA001 if LSB was 1
- Table method: `crc = (crc >> 8) ^ table[(crc ^ byte) & 0xFF]`
- Test vector: "123456789" → CRC = 0x4B37

## 3.3 Key Function Codes for Inverters
- **0x03** Read Holding Registers — most used for inverter data
- **0x04** Read Input Registers — also common
- **0x06** Write Single Register — for configuration
- **0x10** Write Multiple Registers — for batch writes
- Max 125 registers per read request

## 3.4 Timing
- 3.5 character silence between frames
- 1.5 character timeout within frame (exceed = discard)
- At 9600 baud: t3.5 ≈ 4ms, t1.5 ≈ 1.7ms
- Above 19200 baud: use fixed 1.75ms / 750µs

## 3.5 Exception Responses
- Exception FC = Original FC + 0x80
- Code 01: Illegal Function, 02: Illegal Address, 03: Illegal Value, 04: Device Failure

---

# 4. COMMON SERIAL SETTINGS FOR SOLAR INVERTERS

## 4.1 Baud Rate Distribution by Manufacturer

| Manufacturer | Default Baud | Supported Ba | Parity | Stop Bits | Config String |
|-------------|-------------|--------------|--------|-----------|---------------|
| SMA | 9600 | 9600-115200 | Even | 1 | 8E1 |
| Fronius | 9600 | 9600-115200 | None | 2 | 8N2 |
| Growatt | 9600 | 9600, 19200 | None | 1 | 8N1 |
| Solis | 9600 | 9600 | Even/None | 1/2 | 8E1 or 8N2 |
| Deye/Solax/Sofar | 9600 | 9600 | None | 1 | 8N1 |
| GoodWe | 9600 | 9600 | None | 1 | 8N1 |
| Sungrow | 9600 | 9600, 19200 | None | 1 | 8N1 |
| SolarEdge | 9600 | 9600 | None | 1 | 8N1 |
| ABB/FIMER | 19200 | 9600, 19200 | None | 1 | 8N1 |
| Huawei | 9600 | 9600, 19200 | None | 1 | 8N1 |
| Victron | 19200 | 19200 | None | 1 | 8N1 |

## 4.2 Most Common Settings

**9600 8N1** is the most universal setting across solar inverters. If you don't know your inverter's settings, try this first.

**9600 8E1** is the second most common (SMA standard). Try this if 8N1 gives errors.

**9600 8N2** is used by some inverters (Fronius, some Solis models). Note: Modbus spec says no parity → must use 2 stop bits to maintain 11-bit character.

## 4.3 Important Notes

- **Parity + Stop Bits relationship**: Modbus RTU requires 11-bit characters. With parity: 1 start + 8 data + 1 parity + 1 stop = 11. Without parity: 1 start + 8 data + 2 stop = 11. Using 8N1 (10-bit character) technically violates the spec but works with most devices.
- **Flow control**: Always NONE for RS485. RTS/CTS and XON/XOFF are not used.
- **Timeout**: Set to 1-5 seconds for read timeout. Most inverters respond within 100ms at 9600 baud.
- **Inter-frame delay**: At 9600 baud, wait at least 4ms between consecutive Modbus requests.

---

# 5. PYTHON/C LIBRARIES FOR MODBUS RTU

## 5.1 pymodbus (Python)

**Status**: Actively maintained, most feature-rich Python Modbus library  
**License**: BSD-3-Clause  
**PyPI**: https://pypi.org/project/pymodbus/  
**GitHub**: https://github.com/pymodbus/pymodbus  
**Current version**: 3.x (3.13+ as of 2026) — major API changes from 2.x

### Installation
```bash
pip install pymodbus[serial]    # pymodbus + pyserial for RTU
```

### Synchronous Client Example (pymodbus 3.x)
```python
from pymodbus.client import ModbusSerialClient

client = ModbusSerialClient(
    port='/dev/ttyUSB0',
    baudrate=9600,
    parity='N',
    stopbits=1,
    bytesize=8,
    timeout=3,
)

client.connect()

# Read 10 holding registers from slave 1, starting at address 0
result = client.read_holding_registers(address=0, count=10, slave=1)

if not result.isError():
    print(f"Registers: {result.registers}")
else:
    print(f"Error: {result}")

# Read input registers
result = client.read_input_registers(address=0, count=10, slave=1)

# Write single register
client.write_register(address=0, value=1, slave=1)

# Write multiple registers
client.write_registers(address=0, values=[1, 2, 3], slave=1)

client.close()
```

### Asynchronous Client (pymodbus 3.x)
```python
import asyncio
from pymodbus.client import ModbusSerialClient

async def read_inverter():
    client = ModbusSerialClient(
        port='/dev/ttyUSB0',
        baudrate=9600,
        parity='N',
        stopbits=1,
        timeout=3,
    )
    await client.connect()

    result = await client.read_holding_registers(address=0, count=10, slave=1)
    if not result.isError():
        print(f"Registers: {result.registers}")

    await client.close()

asyncio.run(read_inverter())
```

### Key pymodbus 3.x API Changes from 2.x
- `client.read_holding_registers(0, 10, unit=1)` → `client.read_holding_registers(address=0, count=10, slave=1)`
- `unit` parameter renamed to `slave`
- `result.registers` still works the same
- `result.isError()` replaces checking for exception responses
- Async requires `await client.connect()` and `await client.read_...()`

### Retry Configuration
```python
from pymodbus.client import ModbusSerialClient
from pymodbus.transaction import ModbusRtuFramer

client = ModbusSerialClient(
    port='/dev/ttyUSB0',
    baudrate=9600,
    framer=ModbusRtuFramer,
    retries=3,
    retry_on_empty=True,
    close_comm_on_error=True,
    timeout=3,
)
```

**Pros:**
- Most feature-complete Python Modbus library
- Sync and async support
- Active community and maintenance
- Supports RTU, ASCII, TCP, TLS
- SunSpec support built-in
- Extensive documentation

**Cons:**
- Heavier dependency (install size)
- API changed significantly from 2.x to 3.x
- Async mode adds complexity for simple use cases
- Some reported issues with auto-reconnect on USB disconnect

---

## 5.2 minimalmodbus (Python)

**Status**: Maintained, simple API  
**License**: MIT  
**PyPI**: https://pypi.org/project/minimalmodbus/  
**GitHub**: https://github.com/pyhys/minimalmodbus  

### Installation
```bash
pip install minimalmodbus
```

### Example
```python
import minimalmodbus

instrument = minimalmodbus.Instrument('/dev/ttyUSB0', 1)  # port, slave address
instrument.serial.baudrate = 9600
instrument.serial.parity = minimalmodbus.serial.PARITY_NONE
instrument.serial.stopbits = 1
instrument.serial.timeout = 3

# Read holding register (function code 3)
value = instrument.read_register(0, 0)  # register address, number of decimals

# Read input register (function code 4)
value = instrument.read_register(0, 0, functioncode=4)

# Read long (32-bit, 2 registers)
value = instrument.read_long(0, functioncode=3)

# Read float (32-bit, 2 registers)
value = instrument.read_float(0, functioncode=3)

# Read multiple registers
values = instrument.read_registers(0, 10, functioncode=3)

# Write register
instrument.write_register(0, 100)

# Write multiple registers
instrument.write_registers(0, [100, 200, 300])
```

**Pros:**
- Extremely simple API — one line per read/write
- Built-in scaling (decimal places)
- Built-in 32-bit and float support
- No async complexity
- Lightweight

**Cons:**
- Synchronous only
- No TCP support (serial RTU only)
- No built-in retry logic
- Less flexible for complex setups
- Smaller community

---

## 5.3 libmodbus (C Library)

**Status**: Actively maintained, industry standard C Modbus library  
**License**: LGPL-2.1  
**Repository**: https://github.com/stephane/libmodbus  
**Documentation**: http://libmodbus.org/documentation/

### Installation
```bash
# Debian/Ubuntu
sudo apt install libmodbus-dev

# From source
git clone https://github.com/stephane/libmodbus.git
cd libmodbus
./autogen.sh
./configure
make
sudo make install
```

### C Example
```c
#include <modbus.h>
#include <stdio.h>
#include <unistd.h>

int main() {
    modbus_t *ctx;
    uint16_t tab_reg[64];
    int rc;

    ctx = modbus_new_rtu("/dev/ttyUSB0", 9600, 'N', 8, 1);
    if (ctx == NULL) {
        fprintf(stderr, "Unable to create Modbus context\n");
        return -1;
    }

    modbus_set_slave(ctx, 1);
    modbus_set_response_timeout(ctx, 0, 500000);  // 0.5 sec

    if (modbus_connect(ctx) == -1) {
        fprintf(stderr, "Connection failed: %s\n", modbus_strerror(errno));
        modbus_free(ctx);
        return -1;
    }

    // Read 10 holding registers starting at address 0
    rc = modbus_read_registers(ctx, 0, 10, tab_reg);
    if (rc == -1) {
        fprintf(stderr, "Read failed: %s\n", modbus_strerror(errno));
    } else {
        for (int i = 0; i < rc; i++) {
            printf("reg[%d]=%d (0x%04X)\n", i, tab_reg[i], tab_reg[i]);
        }
    }

    modbus_close(ctx);
    modbus_free(ctx);
    return 0;
}

// Compile: gcc -o modbus_test modbus_test.c -lmodbus
```

### RS485 Configuration with libmodbus
```c
// Enable RS485 direction control on the serial port
modbus_rtu_set_serial_mode(ctx, MODBUS_RTU_RS485);

// Set RTS ON_SEND (driver enable high during TX)
modbus_rtu_set_rts(ctx, MODBUS_RTU_RTS_UP);

// Set custom RTS delay (microseconds)
modbus_rtu_set_rts_delay(ctx, 1000);  // 1ms
```

### Python Bindings for libmodbus
```bash
pip install pylibmodbus
```
```python
from pylibmodbus import Modbus

ctx = Modbus('rtu', '/dev/ttyUSB0', 9600, 'N', 8, 1)
ctx.slave(1)
ctx.connect()
regs = ctx.read_registers(0, 10)
ctx.close()
```

**Pros:**
- C library — fastest, lowest overhead
- Production-proven (used in industrial systems)
- Full RTU and TCP support
- RS485 ioctl support built-in
- Python bindings available

**Cons:**
- C API — more code required
- Must manage memory and error handling manually
- Python bindings may lag behind C library
- LGPL license may be concern for some commercial projects

---

## 5.4 Comparison Table

| Feature | pymodbus | minimalmodbus | libmodbus (C) |
|---------|-----------|---------------|---------------|
| Language | Python | Python | C (Python bindings available) |
| RTU Serial | Yes | Yes | Yes |
| TCP | Yes | No | Yes |
| Async | Yes (3.x) | No | No |
| 32-bit/float | Manual | Built-in | Manual |
| Retry logic | Built-in | No | Partial |
| Auto-reconnect | Partial | No | No |
| RS485 ioctl | Via pyserial | Via pyserial | Built-in |
| Install size | Large | Small | Small |
| Learning curve | Medium | Low | Medium-High |
| Best for | Full-featured monitoring | Quick scripts, simple reads | Embedded/C systems, max performance |
| License | BSD-3 | MIT | LGPL-2.1 |
| Maintenance | Very active | Active | Active |
| Community | Largest Python Modbus | Smaller | Large (C/industrial) |

**Recommendation:**
- For **Python monitoring/monitoring apps**: Use **pymodbus** — most complete, async support, good docs
- For **quick scripts / one-off reads**: Use **minimalmodbus** — simplest API
- For **C/embedded / max performance**: Use **libmodbus** — industry standard
- For **Docker container**: Use **pymodbus** (most Docker examples use it)

---

# 6. DOCKER CONTAINER WITH SERIAL PORT ACCESS

## 6.1 Basic Device Passthrough

```bash
docker run --device=/dev/ttyUSB0 my-modbus-image
```

The `--device` flag maps a host device into the container. Default permissions are `rwm` (read, write, mknod).

## 6.2 Docker Compose

```yaml
services:
  modbus-collector:
    build: .
    devices:
      - "/dev/inverter_rs485:/dev/ttyUSB0:rwm"
    group_add:
      - "dialout"
    environment:
      - MODBUS_PORT=/dev/ttyUSB0
      - MODBUS_BAUD_RATE=9600
      - MODBUS_PARITY=N
      - MODBUS_STOP_BITS=1
      - MODBUS_SLAVE_ID=1
    restart: unless-stopped
```

## 6.3 Permission Solutions

| Method | Security | Command |
|--------|----------|---------|
| Root (default) | Low | `docker run --device=/dev/ttyUSB0 image` |
| `--group-add dialout` | Medium | `docker run --device=/dev/ttyUSB0 --group-add dialout image` |
| `--user UID:GID` | High | `docker run --device=/dev/ttyUSB0 --user 1000:20 image` |
| `--privileged` | **AVOID** | Don't use — exposes all host devices |

## 6.4 Dockerfile Example

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    pymodbus[serial]==3.13.0 \
    paho-mqtt==2.1.0

COPY modbus_collector.py .

USER 1000:20    # UID 1000, GID 20 (dialout)

CMD ["python", "-u", "modbus_collector.py"]
```

## 6.5 Hot-Plug Handling (USB reconnects)

`--device` only maps devices at container creation. For USB hot-plug:

**Option A — device-cgroup-rule (allows future device creation):**
```bash
docker run --device=/dev/ttyUSB0 --device-cgroup-rule='c 188:* rmw' my-image
```
Major 188 = USB serial devices. Check with `ls -la /dev/ttyUSB0`.

**Option B — Udev trigger restart:**
```udev
# /etc/udev/rules.d/99-docker-serial.rules
ACTION=="add", SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", RUN+="/usr/bin/docker restart modbus-app"
ACTION=="remove", SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", RUN+="/usr/bin/docker restart modbus-app"
```

**Option C — Application-level reconnect (recommended):**
```python
import time
from pymodbus.client import ModbusSerialClient

def create_client():
    return ModbusSerialClient(port='/dev/ttyUSB0', baudrate=9600, parity='N', stopbits=1, timeout=3)

client = create_client()

while True:
    try:
        if not client.connected:
            client = create_client()
            client.connect()
        result = client.read_holding_registers(address=0, count=10, slave=1)
        if result.isError():
            client.close()
    except Exception:
        client.close()
        time.sleep(5)
```

## 6.6 Multi-Container Serial Sharing

A serial port can only be opened by **one process at a time**. For multi-container architectures, use a **Modbus TCP Gateway** pattern:

```yaml
services:
  modbus-gateway:
    image: ghcr.io/revenmartin/mbusd:latest
    devices:
      - "/dev/inverter_rs485:/dev/ttyUSB0"
    group_add:
      - "dialout"
    environment:
      - MBUSD_DEVICE=/dev/ttyUSB0
      - MBUSD_BAUDRATE=9600
      - MBUSD_MODE=rtu
      - MBUSD_PORT=502
    ports:
      - "502:502"

  data-collector:
    build: .
    environment:
      - MODBUS_HOST=modbus-gateway
      - MODBUS_PORT=502
    depends_on:
      - modbus-gateway
```

One container owns the serial port and exposes Modbus TCP; other containers connect via TCP (pymodbus `ModbusTcpClient`).

## 6.7 Full Docker Compose Monitoring Stack

```yaml
version: "3.8"

services:
  modbus-collector:
    build: .
    container_name: modbus-collector
    devices:
      - "/dev/inverter_rs485:/dev/ttyUSB0:rwm"
    group_add:
      - "dialout"
    environment:
      - MODBUS_PORT=/dev/ttyUSB0
      - MODBUS_BAUD_RATE=9600
      - MODBUS_PARITY=N
      - MODBUS_STOP_BITS=1
      - MODBUS_SLAVE_ID=1
      - POLL_INTERVAL=5000
      - MQTT_BROKER=mqtt://mosquitto:1883
    restart: unless-stopped
    depends_on:
      mosquitto:
        condition: service_healthy
    networks:
      - iot-network
    healthcheck:
      test: ["CMD", "test", "-c", "/dev/ttyUSB0"]
      interval: 30s
      timeout: 10s
      retries: 3

  mosquitto:
    image: eclipse-mosquitto:2
    container_name: mosquitto
    ports:
      - "1883:1883"
    volumes:
      - mosquitto-data:/mosquitto/data
    networks:
      - iot-network
    restart: unless-stopped

  influxdb:
    image: influxdb:2.7
    container_name: influxdb
    ports:
      - "8086:8086"
    volumes:
      - influxdb-data:/var/lib/influxdb2
    environment:
      - DOCKER_INFLUXDB_INIT_MODE=setup
      - DOCKER_INFLUXDB_INIT_USERNAME=admin
      - DOCKER_INFLUXDB_INIT_PASSWORD=changeme123
      - DOCKER_INFLUXDB_INIT_ORG=home
      - DOCKER_INFLUXDB_INIT_BUCKET=energy
    networks:
      - iot-network
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    volumes:
      - grafana-data:/var/lib/grafana
    networks:
      - iot-network
    restart: unless-stopped

volumes:
  mosquitto-data:
  influxdb-data:
  grafana-data:

networks:
  iot-network:
    driver: bridge
```

**Sources:**
- Docker --device: https://docs.docker.com/reference/cli/docker/container/run/#device
- Docker Compose devices: https://docs.docker.com/compose/compose-file/05-services/#devices
- Docker --privileged warning: https://docs.docker.com/engine/reference/run/#runtime-privilege-and-linux-capabilities
- Linux cgroup devices: https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v1/devices.html

---

# 7. BEST PRACTICES FOR RELIABLE RS485 COMMUNICATION

## 7.1 Wiring

### Topology
- **ALWAYS use daisy-chain (linear bus)** — never star or ring topology
- Keep stubs (drops to devices off the main bus) under 1m
- Long stubs cause signal reflections

### Cable
- **Use shielded twisted pair (STP)** rated at 120Ω impedance
- Typical: 24 AWG for runs up to 200m; 22 AWG for longer runs
- Capacitance < 30 pF/ft (100 pF/m)
- For outdoor solar: UV-resistant jacket (polyethylene PE), waterproof connectors (IP67)

### Termination
- **120Ω resistor at BOTH ends** of the bus, only 2 total
- Do NOT terminate at every node — over-loads the bus
- Use AC (RC) termination for battery-powered systems: 120Ω + 1nF capacitor in series

### Bias Resistors
- **1kΩ pull-up** (Vcc → Data B) + **1kΩ pull-down** (GND → Data A) at one point (master node)
- Prevents bus floating when no device is transmitting
- Many modern transceivers have internal fail-safe bias — check datasheet

### Grounding
- Connect signal ground (GND/SC/Common) between all devices
- Use current-limited ground connection (100Ω resistor + 0.1µF) between nodes in different buildings
- **Ground shield at ONE END ONLY** (typically master/controller end)
- Never use shield as signal ground conductor

## 7.2 Hardware Protection

| Protection | When Needed | Device |
|-----------|-------------|--------|
| Surge protection | Outdoor cables, between buildings | GDT + TVS at each building entry |
| Galvanic isolation | Ground potential differences > 7V | Isolated RS485 transceiver (ADM2587E, ISO3086) |
| ESD protection | All installations | TVS diodes on A/B lines |
| Cable separation | Near AC power lines | ≥30cm from power; cross at 90° |

## 7.3 Common Problems and Fixes

| Problem | Symptom | Fix |
|---------|---------|-----|
| Signal reflection | Data corruption at high baud | Add 120Ω termination at both ends |
| Floating bus | Random noise read as data | Add bias resistors (1kΩ pull-up/down) |
| Ground loop | Intermittent errors, damage | Current-limit ground; use isolation |
| EMI/noise | Garbled data | Use STP cable; route away from power |
| A/B polarity swapped | No communication | Verify with multimeter; swap A/B |
| Bus overload | Signal too low | Ensure ≤ 32 unit loads; only 2 terminations |
| Overheating transceiver | Intermittent failures in sun | Use industrial-grade transceiver (-40-85°C) |

## 7.4 A/B Label Warning

**CRITICAL**: A/B labeling is NOT standardized between manufacturers.

| Convention | A = | B = | Used by |
|-----------|-----|-----|---------|
| EIA-485 standard | Inverting (-) | Non-inverting (+) | Most IC datasheets |
| Many adapter makers | Non-inverting (+) | Inverting (-) | Some Chinese adapters, some inverters |
| D+ / D- naming | D+ = B, D- = A | — | Some documentation |

**How to verify**: With a multimeter, measure idle bus voltage:
- B (D+) should be slightly higher than A (D-) when bias is applied
- If communication fails, try swapping A/B — this is the #1 cause of "doesn't work" with new installations

## 7.5 Software Best Practices

### Retry and Timeout
- **3 retries** before marking a device offline
- Exponential backoff on retries (1s, 2s, 4s)
- Response timeout: 1-5 seconds (depend on inverter model)
- Inter-frame delay: wait at least 3.5 character times between requests

### Polling Strategy
```python
# Priority-based polling
STATIC_REGISTERS = {0: "model", 3: "firmware"}      # Read once at startup
SLOW_REGISTERS = {38: "total_energy", 42: "daily_energy"}  # Every 30-60s
FAST_REGISTERS = {1: "pv_voltage", 2: "pv_current", 9: "frequency"}  # Every 1-5s
ALARM_REGISTERS = {0: "status", 1: "error_code"}    # Every 1-2s
```

### Data Validation
- **Range checking**: Physically impossible values (negative voltage, power > rated max)
- **Rate-of-change limiting**: Reject sudden impossible jumps (e.g., voltage 300V→50V→300V)
- **Median filtering**: Take 3 readings, use median (better than mean for outlier rejection)
- **Debouncing**: For status changes, require N=3 consecutive identical readings

### Error Handling
```python
class InverterConnection:
    def __init__(self, slave_id, client):
        self.slave_id = slave_id
        self.client = client
        self.consecutive_failures = 0
        self.online = True
        self.poll_interval_fast = 5     # seconds when online
        self.poll_interval_slow = 30    # seconds when offline

    def read_registers(self, address, count):
        for attempt in range(3):
            try:
                result = self.client.read_holding_registers(
                    address=address, count=count, slave=self.slave_id
                )
                if not result.isError():
                    self.consecutive_failures = 0
                    self.online = True
                    return result.registers
            except Exception:
                pass

        self.consecutive_failures += 1
        if self.consecutive_failures >= 5:
            self.online = False
        return None

    @property
    def poll_interval(self):
        return self.poll_interval_slow if not self.online else self.poll_interval_fast
```

### Communication Watchdog
- Track last successful communication per device
- If no response within 60s, flag as offline
- If entire bus unresponsive for 5 minutes, reinitialize serial port
- Use hardware watchdog (WDT) on embedded systems

## 7.6 Multi-Inverter Bus

- Assign **unique slave addresses** (1-247) to each inverter
- Poll **sequentially** along the bus (nearest first)
- Maximum recommended without repeaters: **10-15 inverters** at 9600 baud, 5-second intervals
- Each poll cycle: read all registers for one inverter, then move to next
- Consider using **Modbus TCP gateway** if you need multiple masters

## 7.7 Quick Reference Table

| Parameter | Value/Practice |
|-----------|----------------|
| Topology | Daisy-chain only |
| Max cable length | 1200m at low speed |
| Cable | STP 120Ω, 24 AWG |
| Termination | 120Ω at both ends |
| Bias | 1kΩ pull-up (Vcc→B) + 1kΩ pull-down (GND→A) |
| Shield ground | One end only (master) |
| Max devices | 32 standard, 256 (1/8 unit load) |
| Surge protection | GDT/TVS at outdoor cable ends |
| Protocol | Master-slave polling (Modbus RTU) |
| Retry count | 3 before marking offline |
| Poll interval | 1-5s live data, 30-60s totals |
| Turnaround time | 1-5 character times |
| A/B polarity | CHECK WITH MULTIMETER — labels are inconsistent |

---

## Sources Summary

| Topic | Source URLs |
|-------|------------|
| USB-RS485 adapters | https://www.kernel.org/doc/html/latest/usb/usb-serial.html |
| CH340 driver | http://www.wch-ic.com/products/CH340.html |
| FTDI driver | https://ftdichip.com/products/ft232r/ |
| CP2102 driver | https://www.silabs.com/development-tools/interface/cp2102n-bridge-controllers |
| CH9344 driver | https://github.com/WCHSoftGroup/ch9344linux |
| Linux termios | https://man7.org/linux/man-pages/man3/termios.3.html |
| TIOCSRS485 ioctl | https://www.kernel.org/doc/html/latest/driver-api/serial/serial-rs485.html |
| pyserial | https://pyserial.readthedocs.io/en/latest/ |
| pymodbus | https://pymodbus.readthedocs.io/ |
| minimalmodbus | https://minimalmodbus.readthedocs.io/ |
| libmodbus | http://libmodbus.org/documentation/ |
| Docker --device | https://docs.docker.com/reference/cli/docker/container/run/#device |
| Docker Compose devices | https://docs.docker.com/compose/compose-file/05-services/#devices |
| Docker --privileged | https://docs.docker.com/engine/reference/run/#runtime-privilege-and-linux-capabilities |
| RS-485 standard (Wikipedia) | https://en.wikipedia.org/wiki/RS-485 |
| TI RS-485 Design Guide | https://www.ti.com/lit/an/slla272c/slla272c.pdf |
| TI RS-422/485 Overview | https://www.ti.com/lit/an/slla070d/slla070d.pdf |
| Renesas Fail-Safe Bias | https://www.renesas.com/en/document/apn/an1986-external-fail-safe-biasing-rs-485-networks |
| RS485 polarity issues | https://www.chipkin.com/rs485-polarity-issues |
| Lammert Bies RS485 | https://www.lammertbies.nl/comm/info/RS-485 |
| Simply Modbus | https://www.simplymodbus.ca/learn-basics.html |
| Modbus Organization | https://modbus.org |
| SunSpec Alliance | https://sunspec.org |
