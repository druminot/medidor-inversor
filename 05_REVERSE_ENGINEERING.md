# Reverse Engineering — Descubrir Registros del Inversor Riello H.P.6065REL-D

> **ESTADO: COMPLETADO** — El protocolo fue descubierto. No es Modbus RTU sino **SISER (Phoenixtec)**. Se descubrió por decompilación de SunVision (clase SISERBus.java). El daemon `siser-reader` (Python) está en producción leyendo datos reales del inversor. Las estrategias de escaneo Modbus RTU de este documento son **referencia histórica** — el protocolo real es SISER y los registros se documentan en `siser_reader.py` (offsets de readMichele). No intentar leer el inversor con Modbus RTU: no funciona y puede interferir con siser-reader.

## El Problema

Riello **no publica el mapa de registros Modbus** para sus inversores (ni el Helios Power ni la serie RS actual). Solo se publicó el mapa del String Box, que es un dispositivo de monitoreo separado, no el inversor en sí.

---

## Parámetros de Comunicación Confirmados

El Helios Power 4000 es un producto **discontinuado de ~2010-2015** (referencia histórica). El inversor real es **H.P.6065REL-D** con parámetros distintos a los modelos actuales de Riello:

> NOTA: El inversor real es H.P.6065REL-D. Los parámetros de Helios Power 4000 (4800 baud, slave 16) se mantienen como referencia histórica.

| Parámetro | Valor | Notas |
|---|---|---|
| **Baud rate** | **9600 bps** | Configuración confirmada del H.P.6065REL-D |
| **Slave address** | **1** | Configuración confirmada del H.P.6065REL-D |
| **Paridad** | N (none) | Estándar |
| **Stop bits** | 1 | Estándar |
| **Data bits** | 8 | Estándar |

> **Unlock obligatorio**: Antes de leer cualquier registro, escribir contraseña `0x000000` en registros `0x003C`–`0x003D`. Ver [07_MODBUS_READER.md](07_MODBUS_READER.md) para el código C de unlock.

> **Registros de referencia**: Los registros documentados en proyectos como [Riello-RSTool](https://github.com/Pierluigi2497/Riello-RSTool) (0x101C temp, 0x1037 PAC, 0x1021 energía) corresponden al RS 3.0 — **no están confirmados para el H.P.6065REL-D**. Usar como punto de partida del escaneo, no como verdad.

---

---

## Estrategia 1: Captura de Tráfico (si SunVision está disponible)

### Requisitos
- Windows PC con SunVision instalado
- Adaptador RS232 (adaptador CH340 USB-RS232) conectado al inversor
- Sniffer serial (software o hardware)

### Pasos

1. **Instalar sniffer serial** en el PC Windows:
   - [Portmon](https://docs.microsoft.com/en-us/sysinternals/downloads/portmon) (kernel-level)
   - [Serial Port Monitor](https://www.serialportmonitor.com/) (comercial, trial)
   - Alternativa: usar un **splitter RS232 (adaptador CH340 USB-RS232)** + segundo adaptador en Linux sniffing

2. **Capturar tráfico** con SunVision ejecutándose:
   - Iniciar captura antes de abrir SunVision
   - Registrar toda la sesión (15-30 minutos mínimo)
   - Navegar por todas las pantallas de SunVision para forzar lectura de todos los registros

3. **Analizar frames Modbus RTU**:
   ```
   Request:  01 03 XX XX XX XX CRC_L CRC_H  → Qué registro lee?
   Response: 01 03 XX XX XX ... CRC_L CRC_H  → Qué valor devuelve?
   ```

4. **Mapear registros** comparando timestamps con lo que muestra el display del inversor

### Ventaja
- Se obtiene el mapa de registros completo que SunVision usa
- Se descubren los registros en el orden en que SunVision los lee

### Desventaja
- Requiere Windows + SunVision (software que puede no estar disponible)
- Solo descubre los registros que SunVision lee (puede haber más)

---

## Estrategia 2: Escaneo Sistemático de Registros (sin SunVision)

### Requisitos
- PC Linux con adaptador RS232 (adaptador CH340 USB-RS232) conectado al inversor
- Inversor H.P.6065REL-D encendido y operando
- Python + pymodbus instalado

### Escaneo de Holding Registers (FC03)

```python
from pymodbus.client import ModbusSerialClient

client = ModbusSerialClient('/dev/ttyUSB0', baudrate=9600, parity='N',
                            stopbits=1, bytesize=8, timeout=0.5)
client.connect()

# PASO 1: Unlock obligatorio antes de escanear
client.write_registers(0x003C, [0x0000, 0x0000], slave=1)

# Escanear bloques de 10 registros
for block in range(0, 500, 10):  # 0-499 (direcciones Modbus base)
    result = client.read_holding_registers(block, 10, slave=1)
    if not result.isError():
        print(f"Holding {block:4d}-{block+9:4d}: {result.registers}")

client.close()
```

### Escaneo de Input Registers (FC04)

```python
for block in range(0, 500, 10):
    result = client.read_input_registers(block, 10, slave=1)
    if not result.isError():
        print(f"Input {block:4d}-{block+9:4d}: {result.registers}")
```

### Escaneo de Discrete Inputs (FC02)

```python
for block in range(0, 200, 16):
    result = client.read_discrete_inputs(block, 16, slave=1)
    if not result.isError():
        print(f"Discrete {block:4d}: {result.bits[:16]}")
```

### Escaneo de Coils (FC01)

```python
for block in range(0, 200, 16):
    result = client.read_coils(block, 16, slave=1)
    if not result.isError():
        print(f"Coil {block:4d}: {result.bits[:16]}")
```

### Rangos sugeridos para inversores solares

| Tipo | Rango base Modbus | Rango extendido |
|---|---|---|
| Holding Registers | 0-100 | 0-65535 (completo) |
| Input Registers | 0-100 | 0-9999 |
| String Box ref | 40020-40049, 40100-40203 | Ver `docs/riello_modbus_mapping.pdf` |

### Procedimiento paso a paso

1. **Escaneo rápido** (rango 0-500) → identificar qué direcciones responden
2. **Escaneo extendido** (0-65535) → buscar registros fuera del rango estándar
3. **Lecturas repetidas** (cada 5 segundos, 10 minutos) → valores que cambian = mediciones
4. **Comparación con display** → cambiar condiciones y ver qué cambia (apagar paneles, desconectar red, etc.)
5. **Provocar alarmas** → desconectar AC o DC y ver qué registros cambian

### Interpretación de valores

| Patrón de valor | Posible significado |
|---|---|
| Valor 0-1000 que fluctúa con sol | Voltaje DC / Corriente DC / Potencia |
| Valor ~22000-24000 estable | Voltaje AC × 100 |
| Valor ~4990-5010 estable | Frecuencia × 100 |
| Valor incrementando lentamente | Energía acumulada (kWh × factor) |
| Valor 0 o 1 | Estado / Flag / Alarma |
| Valor ~3000-7000 | Temperatura × 10 o × 100 |

---

## Estrategia 3: Solicitar a Riello Solartech

### Contacto

- Soporte: https://www.riello-solartech.com/request-support
- Email de soporte (buscado en web)

### Qué solicitar
- Mapa de registros Modbus RTU para H.P.6065REL-D
- Manual de comunicación RS232 (adaptador CH340 USB-RS232) específico para la serie H.P.6065REL-D
- Posible necesidad de NDA (acuerdo de no divulgación)

### Probabilidad de éxito
- Media-baja: Riello suele pedir NDA para protocolos
- Pero el Helios Power está discontinuado (referencia histórica), puede haber más flexibilidad

---

## Estrategia 4: Hardware Sniffer (método definitivo)

### Setup

```
[Inversor] ──RS232 (adaptador CH340 USB-RS232)──┬──── [PC Linux] (/dev/ttyUSB0)  ← sniffer (solo escucha)
                      │
                      └──── [PC Windows + SunVision]   ← maestro Modbus
```

### Con un Y-splitter RS232 (adaptador CH340 USB-RS232)

1. Conectar adaptador RS232 (adaptador CH340 USB-RS232) #1 al PC Linux (modo escucha pasiva)
2. Conectar adaptador RS232 (adaptador CH340 USB-RS232) #2 al PC Windows + SunVision (maestro)
3. Ambos en el mismo bus RS232 (adaptador CH340 USB-RS232) (A→A, B→B, GND→GND)
4. El adaptador Linux lee todo el tráfico sin transmitir

### Script de captura

```python
import serial

ser = serial.Serial('/dev/ttyUSB0', 9600, bytesize=8, parity='N', stopbits=1, timeout=0.1)
buffer = bytearray()

while True:
    data = ser.read(256)
    if data:
        buffer.extend(data)
        # Procesar frames Modbus (silent interval = 4ms sin datos = fin de frame)
```

---

## Plan de Acción Recomendado

### Fase 1: Preparación
- [ ] Verificar adaptador RS232 (adaptador CH340 USB-RS232) funciona en Linux (`dmesg | grep ttyUSB`)
- [ ] Confirmar conexión física al inversor (A/B/GND)
- [ ] Confirmar configuración serial (9600, 8N1, slave 1)
- [ ] Verificar que el unlock funciona (escribir `[0x0000, 0x0000]` en `0x003C`, recibir ACK)

### Fase 2: Si SunVision disponible
- [ ] Configurar hardware sniffer (Y-splitter)
- [ ] Capturar tráfico completo de SunVision
- [ ] Analizar y mapear registros

### Fase 3: Si NO hay SunVision (escaneo directo)
- [ ] Ejecutar escaneo de Holding Registers (FC03, 0-500)
- [ ] Ejecutar escaneo de Input Registers (FC04, 0-500)
- [ ] Identificar registros que responden sin error
- [ ] Lecturas repetidas para identificar qué cambia
- [ ] Comparar con display del inversor
- [ ] Documentar mapa de registros en YAML/JSON

### Fase 4: Verificación
- [ ] Confirmar mapeo con múltiples sesiones de lectura
- [ ] Verificar valores durante diferentes condiciones operativas
- [ ] Documentar factores de escala (voltaje×10, potencia×1, etc.)
- [ ] Crear archivo de configuración de registros definitivo

---

## Formato de Documentación de Registros (propuesta)

```yaml
# hp_6065rel_d_registers.yaml
inverter:
  model: "H.P.6065REL-D"
  manufacturer: "Riello"
  protocol: "Modbus RTU"
  slave_address: 1
  baudrate: 9600
  parity: "N"
  stopbits: 1

registers:
  holding:
    - address: 0x0000
      name: "pv_voltage"
      unit: "V"
      scale: 0.1
      description: "Voltaje del string fotovoltaico"
    - address: 0x0001
      name: "pv_current"
      unit: "A"
      scale: 0.01
      description: "Corriente del string fotovoltaico"
    # ... más registros después del escaneo

  input:
    - address: 0x0000
      name: "grid_voltage"
      unit: "V"
      scale: 0.1
      description: "Voltaje de red AC"
```