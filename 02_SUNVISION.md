# SunVision — Software de Monitoreo Riello Solar

> **ESTADO: REFERENCIA HISTÓRICA** — SunVision ya no se usa en producción. El container `sunvision-wine` fue eliminado (crasheaba por Xvfb). El protocolo SISER fue descubierto por decompilación de SunVision (clase SISERBus.java). Este documento se conserva como referencia del reverse engineering.

> **NOTA**: El inversor real es Riello H.P.6065REL-D (6 kW, RS232).

## SunVision en Docker (sunvision-wine)

SunVision se ejecuta en un container Docker con Wine, accesible via web en el puerto 8007.

| Parámetro | Valor |
|---|---|
| Container | sunvision-wine |
| Puerto | 8007 |
| URL remota | https://zoning-heat-groggy.ngrok-free.dev/v1sunvision/ |
| Tecnología | Wine sobre Docker Linux |

### Docker Compose

```yaml
sunvision-wine:
  build: ./sunvision-wine
  container_name: sunvision-wine
  restart: unless-stopped
  ports:
    - "8007:8006"
```

---

## Qué es SunVision / SunVision 2

SunVision 2 es el software de monitoreo y control de instalaciones fotovoltaicas de **RPS SPA / AROS Solar Technology** (división del grupo Riello Elettronica, Italia). Es una **aplicación de escritorio Windows** para monitorear inversores Riello (especialmente la serie Sirio) conectados localmente.

### Datos de SunVision 2

| Aspecto | Valor |
|---|---|
| Fabricante | RPS SPA - AROS Solar Technology (Cormano, MI, Italia) |
| Web original | www.aros-solar.com |
| Capacidad | Hasta 255 elementos (inversores/String Box), 64 sistemas máx |
| Conectividad | RS232, RS485 o red (Ethernet) |
| Alarma | Email, fax, SMS |
| Features | Monitoreo gráfico en tiempo real, control centralizado, cálculo CO2, import datos desde SunVision 1 |
| OS soportados | Windows 8, 7, Server 2008, Vista, 2003, XP, 2000, **Linux (Kernel 2.x)**, Solaris 8/9/10 |
| Descarga Wayback | [ups-technet.com/sunvision.htm](https://web.archive.org/web/2020/https://ups-technet.com/sunvision.htm) |
| Manual EN | `docs/sunvision_manual_EN.pdf` |
| Manual ES | `docs/sunvision_manual_ES.pdf` |
| Linux installer | `docs/SunVision-1.9.3-linux.bin` (15.6 MB) |
| Windows installer | Disponible en Wayback (.msi) |
| Datalog export | Disponible en Wayback (.7z) |

### Versiones disponibles (Wayback Machine)

| Plataforma | Archivo | URL Wayback |
|---|---|---|
| **Linux** | `install-1.9.3.bin` | `web.archive.org/web/2020/https://ups-technet.com/AreaFTP/SunVision/Linux/install-1.9.3.bin` |
| Windows | `SunVision-1.9.3.msi` | `web.archive.org/web/2020/https://ups-technet.com/AreaFTP/SunVision/Windows/SunVision-1.9.3.msi` |
| Solaris | `install-1.9.3.bin` | `web.archive.org/web/2020/https://ups-technet.com/AreaFTP/SunVision/Solaris/install-1.9.3.bin` |
| Manual EN | PDF | `web.archive.org/web/2020/https://ups-technet.com/AreaFTP/SunVision/0MNU118NPC-GB%20(Manuale%20software%20SunVision%20GB).pdf` |
| Manual ES | PDF | `web.archive.org/web/2020/https://ups-technet.com/AreaFTP/SunVision/0MNU118NPC-E%20(Manuale%20software%20SunVision%20E).pdf` |
| Manual IT | PDF | `web.archive.org/web/2020/https://ups-technet.com/AreaFTP/SunVision/0MNU118NPC-I%20(Manuale%20software%20SunVision%20I).pdf` |

---

## Estado del Software

| Aspecto | Valor |
|---|---|
| Tipo | Desktop Windows (probablemente .NET/C++ o Delphi) |
| Licencia | Propietario, cerrado |
| Código fuente | **No disponible públicamente** |
| API/SDK | **No documentado** |
| Riello Solar web | **Offline** (www.riello-solar.com inaccesible) |
| División solar actual | Riello Solartech (riello-solartech.com) |
| Distribución actual | **Descontinuado** — reemplazado por Sirio Data Control |

---

## Comunicación con Inversores

| Parámetro | Valor |
|---|---|
| Protocolo | Modbus RTU over RS485 |
| Baud rate | 9600 |
| Formato | 8N1 (8 data bits, no parity, 1 stop bit) |
| Slave Address | 1 (default, configurable 1-20) |
| Conexión física | RS485 via tarjeta expansión / USB-RS485 adapter |
| Puerto TCP (bridge) | 4196 (Riello/Midea heat pumps), 502 (inversores RS WiFi) |
| Byte order | LSByte first, MSByte after (little-endian on wire) |
| Frame Modbus TCP | 6 bytes header (txId + protocolId + length + unitId) + PDU |
| Códigos función | FC01 (coils), FC02 (discrete), FC03 (holding), FC04 (input), FC06, FC0x10 |

---

## Datos que Lee del Inversor

### Registros conocidos del Riello-RSTool (inversores RS 3.0 via WiFi/TCP)

Basado en el código fuente de [Pierluigi2497/Riello-RSTool](https://github.com/Pierluigi2497/Riello-RSTool):

```
# Frames Modbus TCP descubiertos (slave 1, FC03 Read Holding Registers):
# Formato: [TxID(2)] [ProtocolID(2)] [Length(2)] [UnitID(1)] [FC(1)] [Addr(2)] [Count(2)]

Index 0:  01 03 C000 0030  → Leer 48 registros desde 0xC000 (49152) = Gráfico de producción
Index 1:  01 03 101E 0002  → Leer 2 registros desde 0x101E (4126) 
Index 2:  01 03 101D 0001  → Leer 1 registro desde 0x101D (4125)
Index 3:  01 03 103D 0001  → Leer 1 registro desde 0x103D (4157)
Index 4:  01 03 1005 0001  → Leer 1 registro desde 0x1005 (4101)
Index 5:  01 03 1037 0002  → Leer 2 registros desde 0x1037 (4151) = Potencia actual
Index 6:  01 03 1039 0002  → Leer 2 registros desde 0x1039 (4153)
Index 7:  01 03 1010 000C  → Leer 12 registros desde 0x1010 (4112) = Energía de hoy?
Index 8:  01 03 1001 000F  → Leer 15 registros desde 0x1001 (4097) = Potencia pico
Index 9:  01 03 103B 0002  → Leer 2 registros desde 0x103B (4155)
Index 10: 01 03 1025 0002  → Leer 2 registros desde 0x1025 (4133)
Index 11: 01 03 1021 0002  → Leer 2 registros desde 0x1021 (4129) = Energía total
Index 12: 01 03 101C 0001  → Leer 1 registro desde 0x101C (4124)
Index 13: 01 03 1023 0002  → Leer 2 registros desde 0x1023 (4131)
Index 14: 01 03 1020 0001  → Leer 1 registro desde 0x1020 (4128)
Index 15: 01 03 3080 0001  → Leer 1 registro desde 0x3080 (12416)
```

### Interpretación del código Riello-RSTool

| Index | Registro Modbus | Decodificación | Escala |
|---|---|---|---|
| 0 | 0xC000 (49152) | Gráfico de producción diario (48 registros = puntos horarios) | valor/100 |
| 5 | 0x1037 (4151) | **Potencia actual** (2 registros, 32 bits) | valor/10000 |
| 8 | 0x1010 (4112) | Energía de hoy? (12 registros) | — |
| 9 | 0x1001 (4097) | Potencia pico (15 registros) | — |
| 11 | 0x1021 (4129) | **Energía total** (2 registros, 32 bits) | valor/100 |
| 12 | 0x101C (4124) | **Temperatura del inversor** (1 registro, 8 bits) | directo |

### Formato de decodificación (del código fuente)

```python
# Gráfico diario: cada 4 hex chars = [hora, valor_alto, valor_bajo]
# hora = byte[0], valor = int.from_bytes(byte[1]+byte[2]) / 100

# Potencia: int.from_bytes(2 bytes) / 10000 → kW
# Temperatura: int.from_bytes(1 byte) → grados (directo)

# Energía: int.from_bytes(2 bytes) / 100 → kWh
```

### Registros heatpump-modbus-controller (Riello/Midea, referencia)

| Registro | Nombre | Tipo |
|---|---|---|
| 0 | power_on_off (bits: floor_heating, zone_1, dhw, zone_2) | Config |
| 1 | setting_mode (1=Auto, 2=Cool, 3=Heat) | Config |
| 2 | flow_temps_set (split low=zone1, high=zone2) | Config |
| 5 | function_setting (bits: holiday, silent_mode, eco) | Config |
| 128 | status_bit_1 (bits: defrost, remote_on_off) | Status |
| 129 | load_output (bits: heater, pump, ALARM, RUN, DEFROST) | Status |
| 100 | operating_frequency | Mediciones |
| 104-113 | temps (water_in/out, condenser, ambient, compressor) | Mediciones |
| 116-119 | pressures, current, voltage | Mediciones |
| 124 | current_fault | Alarmas |

> **Nota**: Estos registros son para heat pumps, NO para inversores solares. Los rangos pueden ser diferentes en el H.P.6065REL-D, pero la estructura Modbus es similar.

---

## Ecosistema de Monitoreo Riello Solartech (actual)

### Inversores String & Hybrid

| Software | Tipo | Descripción |
|---|---|---|
| RS Connect (APP) | Móvil | Config local via Wi-Fi |
| Riello PV (APP) | Móvil | Monitoreo remoto (RS, Sirio ES, RS Hybrid) |
| RS Monitoring WEB | Web+App | Supervisión string/hybrid |
| Cloud Inverter WEB | Web | Monitoreo avanzado RS Hybrid y Sirio ES |

### Inversores Sirio Centralizados & HBS

| Software | Tipo | Descripción |
|---|---|---|
| **Sirio Data Control** | Desktop | Monitoreo y config hasta 300 inversores via Ethernet/Internet |
| String Box | Hardware | Panel de monitoreo de corriente por string |
| RS485 | Accesorio | BUS para múltiples inversores |
| ModCOM PV | Accesorio | **Convertidor de protocolo MODBUS** |

### Legacy (Helios Power 4000 — referencia histórica)

| Software | Tipo | Descripción |
|---|---|---|
| **SunVision / SunVision 2** | Desktop Windows | Software original (descontinuado) |
| SunGuard | Web Portal | Monitoreo web avanzado |
| Z Series Datalogger | Accesorio | Envía datos a SunGuard |

---

## Sirio Data Control (sucesor de SunVision)

| Aspecto | Valor |
|---|---|
| Capacidad | Hasta 300 inversores |
| Conectividad | Ethernet o Internet |
| OS | **Windows, Mac OS X, Linux** |
| Compatibilidad | Sirio con firmware >= 1.2.5 |
| Descarga | https://www.riello-solartech.com/download (filtrar "Sirio Data Control" → "Software") |
| Funciones | Monitoreo, configuración remota, recuperación datos históricos, comandos de regulación |

> **Punto clave**: Sirio Data Control tiene versión Linux. Si el protocolo es similar al del Helios Power, se podría sniffar su tráfico para descubrir registros.

---

## Gaps Críticos

1. **No hay mapa de registros Modbus publicado** para inversores Riello (solo String Box)
2. **No hay proyectos open source** para inversores solares Riello
3. **No hay integración** con Home Assistant, PVOutput, Solaranzeige
4. **No hay documentación de API** ni protocolo privado del inversor
5. **Web de Riello Solar offline** — no se pueden descargar manuales originales
6. **No hay reverse engineering previo** de inversores solares Riello por la comunidad

---

## Proyectos de Referencia

### Proyectos Riello (directos)

| Proyecto | URL | Producto | Lenguaje | Relevancia |
|---|---|---|---|---|
| **Riello-RSTool** | [github.com/Pierluigi2497/Riello-RSTool](https://github.com/Pierluigi2497/Riello-RSTool) | RS 3.0 (WiFi/TCP) | Python | **ALTA** — único tool open source para inversores Riello |
| heatpump-modbus-controller | [github.com/stuartornum/heatpump-modbus-controller](https://github.com/stuartornum/heatpump-modbus-controller) | Riello/Midea heat pump | Python | **MEDIA** — demuestra Modbus RTU en Riello, puerto 4196 |
| ha-besmart | [github.com/muchasuerte/ha-besmart](https://github.com/muchasuerte/ha-besmart) | Riello BeSmart termostato | Python | Baja — termostatos, no inversores |

### Proyectos otros inversores (patrones de referencia)

| Proyecto | URL | Inversor | Estrellas |
|---|---|---|---|
| huawei_solar | github.com/wlcrs/huawei_solar | Huawei | 895 |
| ha-solarman | github.com/davidrapan/ha-solarman | Solarman | 480 |
| solaredge-modbus | github.com/binsentsu | Solaredge | 402 |
| Sunsynk-Home-Assistant | github.com/slipx06 | Deye/Sunsynk | 218 |
| bms-to-inverter | github.com/ai-republic | Genérico | 256 |
| growatt-esp8266 | github.com/jkairys | Growatt | 70 |

---

## Foros y Comunidades (hallazgos)

| Foro | URL | Estado |
|---|---|---|
| Home Assistant Community | [thread 442313](https://community.home-assistant.io/t/integration-for-a-riello-solar-inverter-i-only-have-a-python-script/442313) | Usuario Cupra1979 intentó integrar RS 3.0 con HA usando Riello-RSTool |
| Home Assistant Community | [thread 394159](https://community.home-assistant.io/t/riello-pv-rs-3-0-solar-inverter-integration/394159) | Discusión sobre integración WiFi del RS 3.0 con HA |
| Solaranzeige (DE) | sin subforo Riello encontrado | Sin resultados |
| PVOutput | sin resultados | Sin resultados |

---

## Estrategia para Reemplazar SunVision

Dado que SunVision es completamente cerrado, la única vía es **reverse engineering** del protocolo Modbus RTU:

1. **Usar Riello-RSTool como base** — tiene registros descubiertos para RS 3.0
2. **Adaptar a Modbus RTU serial** — RSTool usa TCP (WiFi), necesitamos RTU (RS485)
3. **Escaneo de registros** — los registros del RS 3.0 pueden ser un punto de partida, pero el H.P.6065REL-D puede usar direcciones diferentes
4. **Sniffear Sirio Data Control** — tiene versión Linux y podría revelar registros adicionales
5. Ver [[05_REVERSE_ENGINEERING]] para el plan detallado