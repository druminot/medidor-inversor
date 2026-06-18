# Tools — Herramientas de Diagnóstico y Desarrollo

> **NOTA: El protocolo SISER (Phoenixtec) es el correcto. Modbus RTU NO funciona con este inversor.** Los scripts de modbus_scan son legacy.

## Scripts activos

| Script | Propósito | Estado |
|---|---|---|
| `modbus_scan.py` | Escaneo sistemático de registros Modbus RTU | **LEGACY** — Modbus RTU no funciona con H.P.6065REL-D |
| `diagnose_inverter.py` | Diagnóstico de conexión serial + prueba de lectura básica | **LEGACY** — usar siser_reader.py en producción |
| `inverter_simulator.py` | Simulador de inversor para testing sin hardware | **ACTIVO** — soporta Modbus RTU, SISER y NetMan UDP |

## Protocolo correcto

El inversor H.P.6065REL-D usa **protocolo SISER (Phoenixtec)**, no Modbus RTU. Esto fue descubierto por decompilación de SunVision (clase SISERBus.java). El daemon de producción es `siser-reader/siser_reader.py`.