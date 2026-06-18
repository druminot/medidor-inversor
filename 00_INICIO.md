# Medidor Inversor — Contexto General

> **ESTADO DEL PROYECTO: COMPLETADO Y OPERATIVO** — El sistema está en producción desde junio 2026. El protocolo SISER (Phoenixtec) fue descubierto mediante reverse engineering de SunVision, reemplazando Modbus RTU como protocolo primario. Los datos reales fluyen desde el inversor. No se requieren más cambios. Este documento es referencia histórica.

## Objetivo del Proyecto

Crear un sistema de monitoreo remoto robusto para el inversor fotovoltaico **Riello H.P.6065REL-D** (Helios Power 6065), reemplazando el software original SunVision que perdía la conexión USB en Windows. El sistema funciona en Linux, es accesible vía internet desde cualquier navegador, y está diseñado para uso académico en la Universidad de Concepción.

---

## Alcance

- Monitoreo en tiempo real del inversor Riello H.P.6065REL-D via RS232/Modbus RTU
- Registro histórico de datos con resolución estratificada (5s / 1min / 15min)
- Dashboard web accesible desde cualquier navegador (Grafana)
- Acceso remoto vía Tailscale Funnel (sin VPN, funciona en la UdeC)
- Descarga de datos en CSV/JSON para trabajos de laboratorio
- KPIs académicos: Performance Ratio, energía específica, horas de sol equivalentes
- Soporte para ~40 usuarios simultáneos (alumnos)
- Preparado para agregar piranómetro/estación meteorológica en el futuro

---

## Stack Tecnológico (PRODUCCIÓN — NO MODIFICAR)

| Componente | Tecnología | Justificación |
|---|---|---|
| Comunicación | **Python + SISER (Phoenixtec)** | Protocolo propietario descubierto por reverse engineering de SunVision. Reemplazó Modbus RTU. |
| Base de datos | **TimescaleDB** (PostgreSQL) | Series temporales nativas, SQL familiar, continuous aggregates, compression automática |
| API REST | **Ninguna** | Grafana consulta TimescaleDB directamente. Sin capa intermedia innecesaria. |
| Dashboard | **Grafana** | Listo para producción, SQL directo, export CSV nativo, 4 dashboards operativos |
| Acceso remoto | **ngrok + nginx** | URL dinámica, TLS automático, reverse proxy con 3 rutas |
| Contenedores | **Docker Compose** | Orquestación simple, 3 servicios, reinicio automático |
| Inversor | Riello H.P.6065REL-D | ~6 kW, monofásico, RS232, 3 MPPTs (solo MPPT2 con paneles) |
| Protocolo | SISER (Phoenixtec), address 33, 9600 baud, RTS/DTR | Protocolo propietario descubierto por decompilación de SunVision |
| Adaptador | CH340 USB-RS232 | Puerto /dev/ttyUSB0, udev symlink /dev/inverter-serial |

> **NOTA**: El daemon C modbus-reader (libmodbus) fue reemplazado por siser-reader (Python). El protocolo SISER requiere un handshake especial (readMichele) y manejo de RTS/DTR. Modbus RTU se usó en la fase inicial de exploración pero no era el protocolo correcto para este inversor.

---

## Arquitectura del Sistema (PRODUCCIÓN)

```
[Riello H.P.6065REL-D]
       │ RS232 (conector VGA/DB15 → CH340)
       │ Cable RS232 (TX, RX, GND)
       │
[CH340 USB-RS232 Adapter] ── /dev/inverter-serial
       │
[PC "lautaro" — Ubuntu Linux]
       │
  ┌────┴──────────────────────────────────────────┐
  │  Docker Compose (3 servicios)                  │
  │                                                │
  │  ┌───────────────┐    ┌──────────────┐        │
  │  │ siser-reader   │    │  TimescaleDB │        │
  │  │ (Python)       │───▶│  (PostgreSQL)│        │
  │  │ daemon         │    └──────┬───────┘        │
  │  └───────────────┘           │                 │
  │                         ┌────┴──────┐          │
  │                         │  Grafana  │          │
  │                         │(SQL directo)         │
  │                         └───────────┘          │
  └──────────────────────────────┼─────────────────┘
                                 │
                    nginx reverse proxy (8080)
                                 │
                    ngrok tunnel (HTTPS, URL dinámica)
                                 │
              ┌────────────────┼───────────────┐
              │                │               │
         [Mac Doctor]   [Notebook Alumno]  [Celular]
```

> Los contenedores `sunvision-wine` y `cloudflared` fueron eliminados. El daemon `modbus-reader` (C) fue reemplazado por `siser-reader` (Python). Solo 3 servicios corren en producción: `siser-reader`, `timescaledb`, `grafana`.

---

## Dominio y Acceso (PRODUCCIÓN)

| URL | Destino | Auth |
|---|---|---|
| `https://XXXX.ngrok-free.dev` | Grafana Dashboard (via nginx) | Anonymous viewer |
| `https://XXXX.ngrok-free.dev/terminal/` | Web terminal (ttyd) | lautaro:lsistem19 (basic auth) |
| `https://XXXX.ngrok-free.dev/cmd/` | Comandos remotos (cmd-server) | lautaro:lsistem19 (basic auth) |
| `ssh lautaro@192.168.1.145` | Administración red local | Password: `lsistem19` |
| Chrome Remote Desktop | Acceso GUI desde cualquier red | PIN: 121212 |

> Las rutas `/sunvision/` y `/v1sunvision/` fueron eliminadas del nginx. SunVision fue descontinuado como servicio.

---

## Estructura del Vault

```
00_INICIO.md                  ← Estás aquí (ESTADO: COMPLETADO)
01_INFRAESTRUCTURA.md         Linux, Docker, udev (ESTADO: OPERATIVO)
02_SUNVISION.md               Software original Riello (ESTADO: REFERENCIA HISTÓRICA)
04_PROTOCOLO_MODBUS.md        Protocolo Modbus RTU (ESTADO: LEGACY — reemplazado por SISER)
05_REVERSE_ENGINEERING.md     Descubrimiento de protocolo (ESTADO: COMPLETADO — SISER descubierto)
06_ARQUITECTURA.md            Arquitectura final del sistema (ESTADO: OPERATIVO)
07_MODBUS_READER.md           Daemon C (libmodbus) (ESTADO: LEGACY — reemplazado por siser-reader)
08_DATABASE.md                TimescaleDB, esquema SQL, continuous aggregates (ESTADO: OPERATIVO)
09_GRAFANA.md                 Dashboards, queries SQL directas, datasources (ESTADO: OPERATIVO)
10_CLOUDFLARE_TUNNEL.md       Túnel Cloudflare (ESTADO: NO USADO — reemplazado por ngrok)
11_DEPLOY.md                  Docker Compose, deploy paso a paso (ESTADO: OPERATIVO)
12_TESTING_CONSULTAS.md       Tests de consultas SQL (ESTADO: OPERATIVO)
13_TESTING_USABILIDAD.md      Tests de usabilidad con Playwright (ESTADO: COMPLETADO)
14_PANTALLA_KIOSK.md          Modo kiosco en Ubuntu Server (ESTADO: OPERATIVO)
15_TUNEL_REMOTO.md            Configuración de ngrok + nginx + ttyd + cmd-server (ESTADO: OPERATIVO)
docs/                         PDFs oficiales, binarios
research/                     Investigación previa (SISER, scripts de test)
```

---

## Datos que Lee el Inversor (PRODUCCIÓN — confirmados por SISER)

### Instantáneos (cada ~5 segundos, tabla `realtime`)

| Dato | Columna | Unidad | Offset SISER | Notas |
|---|---|---|---|---|
| Voltaje PV1 | vpv1 | V | 0x1040 | MPPT1 (sin paneles, 0V) |
| Corriente PV1 | ipv1 | A | 0x1042 | MPPT1 (sin paneles, 0A) |
| Potencia PV1 | ppv1 | W | 0x1044 | MPPT1 |
| Voltaje PV2 | vpv2 | V | 0x1046 | MPPT2 (con paneles, ~160V) |
| Corriente PV2 | ipv2 | A | 0x1048 | MPPT2 (con paneles, ~0.5A) |
| Potencia PV2 | ppv2 | W | 0x104A | MPPT2 |
| Voltaje PV3 | vpv3 | V | 0x104C | MPPT3 (sin paneles, 0V) |
| Corriente PV3 | ipv3 | A | 0x104E | MPPT3 (sin paneles, 0A) |
| Potencia PV3 | ppv3 | W | 0x1050 | MPPT3 |
| Voltaje AC | vac | V | 0x1052 | ~220V |
| Corriente AC | iac | A | 0x1052 | |
| Potencia AC | pac | W | 0x1052 | ~22W (MPPT2 solo) |
| Frecuencia AC | fac | Hz | 0x1052 | ~50Hz |
| Temperatura | temp | °C | 0x1052 | ~28°C |
| Estado | status | flag | readMichele | |
| Estado red | grid_status | flag | readMichele | |

### Acumulados (leídos por SISER, tabla `cumulatives`)

| Dato | Columna | Unidad | Notas |
|---|---|---|---|
| Energía total | energy_total | kWh | |
| Horas operación | hours_total | h | |

> **NOTA IMPORTANTE**: Las tablas `fast_samples` y `cumulatives` están vacías actualmente. siser-reader solo escribe en `realtime`. Las continuous aggregates (`slow_samples`, `hourly_energy`, `daily_energy`) se calculan automáticamente desde `fast_samples`, por lo que también están vacías. Solo `realtime` tiene datos (~26K filas, ~22K con datos reales).

### Datos reales del inversor (junio 2026)

- Solo MPPT2 tiene paneles conectados (~230V, 0.5A, ~115W)
- MPPT1 y MPPT3 muestran 0V/0A (sin paneles)
- Último dato real: 21:22 UTC, temp=28.3°C, vpv2=161.7V, ipv2=0.1A, pac=22.2W
- De noche el inversor se apaga y siser-reader inserta `is_stale=true` (heartbeat)

---

## Estrategia de Datos (PRODUCCIÓN)

| Capa | Intervalo | Tabla | Origen | Estado | Propósito |
|---|---|---|---|---|---|
| Tiempo real | ~5 seg | `realtime` | siser-reader (escribe) | **OPERATIVO** | Dashboard live |
| Muestra rápida | 1 min | `fast_samples` | daemon (escribir) | **VACÍA** | Gráficos hora/día |
| Muestra lenta | 15 min | `slow_samples` | continuous aggregate | **VACÍA** (depende de fast_samples) | Tendencias |
| Acumulados | 1 min | `cumulatives` | daemon (escribir) | **VACÍA** | Energía total, horas |
| Producción diaria | 1x/día | `daily_production` | daemon (escribir) | **VACÍA** | 48 slots horarios |
| Eventos | Evento | `events` | daemon (escribir) | **VACÍA** | Alarmas, cambios |

> **GAP CONOCIDO**: siser-reader actualmente solo escribe en `realtime`. Las tablas `fast_samples`, `cumulatives` y `daily_production` necesitan que se agregue la lógica de escritura en `siser_reader.py`. Las continuous aggregates dependen de `fast_samples` así que también están vacías.

Estimación de almacenamiento: ~2-3 GB/año con compression de TimescaleDB.

---

## Riesgos y Mitigaciones (RESUELTOS)

| Riesgo | Estado | Resolución |
|---|---|---|
| Pérdida de conexión USB (problema original) | **RESUELTO** | siser-reader (Python) con reconexión automática y heartbeats |
| Registros del protocolo desconocidos | **RESUELTO** | Protocolo SISER descubierto por decompilación de SunVision |
| Red UdeC bloquea puertos | **RESUELTO** | ngrok (solo HTTPS saliente puerto 443) |
| Adaptador RS232 falla | **MITIGADO** | Regla udev + device_cgroup_rules para hot-plug, CH340 funciona correctamente |

## Timeline (COMPLETADO)

| Fase | Tarea | Estado |
|---|---|---|
| **1** | TimescaleDB (esquema SQL + continuous aggregates + init-users.sh) | **COMPLETADO** |
| **2** | Docker Compose + .env + udev | **COMPLETADO** |
| **3** | modbus-reader C daemon (legacy) → siser-reader Python | **COMPLETADO** (siser-reader en producción) |
| **4** | Grafana dashboards (datasource + 4 dashboards, SQL directo) | **COMPLETADO** |
| **5** | Cloudflare Tunnel | **DESCARTADO** (bloqueado en UdeC) → ngrok + nginx |
| **6** | Pantalla kiosco (Xorg + Openbox + Chromium + systemd) | **COMPLETADO** |
| **7** | Integración final + backup cron + pruebas 24h | **COMPLETADO** |
| **8** | Reverse Engineering SISER protocol | **COMPLETADO** (decompilación SunVision) |
| **9** | Testing con inversor real | **COMPLETADO** (datos reales fluyendo) |
| **10** | Informe técnico + Tutorial LaTeX | **EN PROGRESO** |

---

## Plan de Implementación — CÓDIGO EN PRODUCCIÓN

> **TODO EL CÓDIGO ESTÁ EN PRODUCCIÓN EN `/opt/solar-monitor/`**. Los archivos del vault son documentos de referencia. El sistema está operativo y no requiere más cambios. El daemon siser-reader (Python) reemplazó completamente a modbus-reader (C).

### Servicios en producción (docker-compose.yml)

| Servicio | Imagen/Build | Estado | Notas |
|---|---|---|---|
| siser-reader | Build local (Python) | **ACTIVO** | Protocolo SISER, escribe en `realtime` |
| timescaledb | timescale/timescaledb:latest-pg16 | **ACTIVO** | ~26K filas, healthy |
| grafana | grafana/grafana:latest | **ACTIVO** | 4 dashboards, anonymous viewer |
| modbus-reader | Build local (C) | **DETENIDO** | Legacy, reemplazado por siser-reader |
| sunvision-wine | Build local (Docker) | **ELIMINADO** | Crasheaba, innecesario |
| cloudflared | cloudflare/cloudflared | **ELIMINADO** | Bloqueado en UdeC, reemplazado por ngrok |

### Servicios systemd (host)

| Servicio | Puerto | Estado |
|---|---|---|
| ttyd | 8022 | **ACTIVO** (terminal web) |
| cmd-server | 8023 | **ACTIVO** (ejecución remota de comandos) |
| nginx | 8080 | **ACTIVO** (reverse proxy) |
| ngrok | 443 (saliente) | **ACTIVO** (túnel HTTPS) |

### Archivos en producción (`/opt/solar-monitor/`)

```
/opt/solar-monitor/
├── docker-compose.yml          # 3 servicios: siser-reader, timescaledb, grafana
├── .env                         # Passwords (DB_PASSWORD, GRAFANA_PASSWORD, GRAFANA_READER_PASSWORD)
├── siser-reader/                # Daemon Python SISER (PRODUCCIÓN)
│   ├── siser_reader.py          # Script principal
│   ├── Dockerfile
│   └── requirements.txt
├── modbus-reader/               # Daemon C (LEGACY, no se usa)
│   └── src/
├── db/
│   ├── init.sql                 # Esquema TimescaleDB
│   └── init-users.sh            # Usuarios (solar, grafana_reader)
├── grafana/
│   ├── provisioning/datasources/datasource.yml
│   ├── provisioning/dashboards/dashboard.yml
│   ├── dashboards/{realtime,historico,diagnostico,academico}.json
│   └── grafana.ini
├── inverter-simulator/          # Simulador para testing (corre en Docker)
└── backups/                     # Backups de DB
```