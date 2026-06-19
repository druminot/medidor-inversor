# Medidor Inversor — Contexto General

> **ESTADO DEL PROYECTO: COMPLETADO Y OPERATIVO** — El sistema está en producción desde junio 2026. El protocolo SISER (Phoenixtec) fue descubierto mediante reverse engineering de SunVision, reemplazando Modbus RTU como protocolo primario. Los datos reales fluyen desde el inversor. No se requieren más cambios. Este documento es referencia histórica.

## Objetivo del Proyecto

Crear un sistema de monitoreo remoto robusto para el inversor fotovoltaico **Riello H.P.6065REL-D** (Helios Power 6065), reemplazando el software original SunVision que perdía la conexión USB en Windows. El sistema funciona en Linux, es accesible vía internet desde cualquier navegador, y está diseñado para uso académico en la Universidad de Concepción.

---

## Alcance

- Monitoreo en tiempo real del inversor Riello H.P.6065REL-D via RS232/SISER protocol
- Registro histórico de datos con TimescaleDB (resolución ~5 seg)
- Dashboard web accesible desde cualquier navegador (Grafana, 4 dashboards, filtro dinámico de amanecer)
- Acceso remoto vía ngrok (sin VPN, funciona en la UdeC)
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
| Contenedores | **Docker Compose** | Orquestación simple, 3 servicios, `restart: always` |
| Inversor | Riello H.P.6065REL-D | ~6 kW, salida AC monofásica 220V, 3 entradas MPPT DC (solo MPPT2 con paneles), RS232 |
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
  │  Docker Compose (3 servicios, restart: always)   │
  │                                                 │
  │  ┌───────────────┐    ┌──────────────┐         │
  │  │ siser-reader   │    │  TimescaleDB │         │
  │  │ (Python)       │───▶│  (PostgreSQL)│         │
  │  │ daemon         │    └──────┬───────┘         │
  │  └───────────────┘           │                  │
  │                         ┌────┴──────┐           │
  │                         │  Grafana  │           │
  │                         │(SQL directo)          │
  │                         └───────────┘           │
  └──────────────────────────────┼──────────────────┘
                                 │
                    nginx reverse proxy (8080)
                                 │
                    ngrok tunnel (HTTPS, URL dinámica)
                                 │
               ┌────────────────┼───────────────┐
               │                │               │
          [Mac Doctor]   [Notebook Alumno]  [Celular]
```

> Solo 3 servicios corren en producción: `siser-reader`, `timescaledb`, `grafana`. Todos con `restart: always`.

---

## Dominio y Acceso (PRODUCCIÓN)

| URL | Destino | Auth |
|---|---|---|
| `https://zoning-heat-groggy.ngrok-free.dev` | Grafana Dashboard (via nginx) | Anonymous viewer |
| `https://zoning-heat-groggy.ngrok-free.dev/terminal/` | Web terminal (ttyd) | lautaro:lsistem19 (basic auth) |
| `https://zoning-heat-groggy.ngrok-free.dev/cmd/` | Comandos remotos (cmd-server) | lautaro:lsistem19 (basic auth) |
| SSH | `ssh lautaro@192.168.0.137` | Administración red local (RuminotRoa) | Password: lsistem19 |
| Chrome Remote Desktop | Acceso GUI desde cualquier red | PIN: 121212 |

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
08_DATABASE.md                TimescaleDB, esquema SQL, columnas SISER (ESTADO: OPERATIVO)
09_GRAFANA.md                 Dashboards, queries SQL, provisioning (ESTADO: OPERATIVO)
10_CLOUDFLARE_TUNNEL.md       Túnel Cloudflare (ESTADO: NO USADO — reemplazado por ngrok)
11_DEPLOY.md                  Docker Compose, deploy paso a paso (ESTADO: OPERATIVO)
12_TESTING_CONSULTAS.md       Tests de consultas SQL (ESTADO: OPERATIVO)
13_TESTING_USABILIDAD.md      Tests de usabilidad con Playwright (ESTADO: COMPLETADO)
14_PANTALLA_KIOSK.md          Modo kiosco (lightdm + openbox + chromium) (ESTADO: OPERATIVO)
15_TUNEL_REMOTO.md            Configuración de ngrok + nginx + ttyd + cmd-server (ESTADO: OPERATIVO)
16_PROD.md                     Estado de producción verificado (ESTADO: OPERATIVO)
Proyecto/                     Código de producción sincronizado con lautaro
  ├── docker-compose.yml      # 3 servicios, restart: always
  ├── db/init.sql             # Esquema SISER completo
  ├── siser-reader/           # Daemon Python SISER
  ├── grafana/                # Dashboards + provisioning
  ├── kiosk/                  # Scripts y config del kiosco
  └── ...
```

---

## Datos que Lee el Inversor (PRODUCCIÓN — confirmados por SISER)

### Instantáneos (cada ~5 segundos, tabla `realtime`)

| Dato | Columna | Unidad | Offset SISER | Notas |
|---|---|---|---|---|
| Voltaje PV1 | vpv1 | V | resp[11:12]/10 | MPPT1 (sin paneles, 0V) |
| Corriente PV1 | ipv1 | A | resp[17:18]/10 | MPPT1 (sin paneles, 0A) |
| Potencia PV1 | ppv1 | W | calculado | MPPT1 |
| Voltaje PV2 | vpv2 | V | resp[13:14]/10 | MPPT2 (con paneles, ~230V) |
| Corriente PV2 | ipv2 | A | resp[19:20]/10 | MPPT2 (con paneles, ~0.7A) |
| Potencia PV2 | ppv2 | W | calculado | MPPT2 |
| Voltaje PV3 | vpv3 | V | resp[15:16]/10 | MPPT3 (sin paneles, 0V) |
| Corriente PV3 | ipv3 | A | resp[21:22]/10 | MPPT3 (sin paneles, 0A) |
| Potencia PV3 | ppv3 | W | calculado | MPPT3 |
| Potencia DC Total | ppv_total | W | calculado | Suma 3 MPPT |
| Voltaje AC (L1 copy) | vac | V | resp[29:30]/10 | ~220V, monofásico |
| Voltaje AC (L2 copy) | vac2 | V | resp[31:32]/10 | Redundante del monofásico |
| Voltaje AC (L3 copy) | vac3 | V | resp[33:34]/10 | Redundante del monofásico |
| Corriente AC (L1 copy) | iac | A | resp[23:24]/10 | Monofásico |
| Corriente AC (L2 copy) | iac2 | A | resp[25:26]/10 | Redundante |
| Corriente AC (L3 copy) | iac3 | A | resp[27:28]/10 | Redundante |
| Potencia AC (L1 copy) | pac | W | resp[37:38]/10 | Monofásico (la "L1" ya es la total) |
| Potencia AC (L2 copy) | pac2 | W | resp[39:40]/10 | Redundante |
| Potencia AC (L3 copy) | pac3 | W | resp[41:42]/10 | Redundante |
| Frecuencia AC | fac | Hz | resp[35:36]/100 | ~50Hz |
| Temperatura | temp | °C | resp[9:10]/10 | ~28°C |
| Estado | status | flag | resp[58] | 0=Wait, 1=Normal, 2=Fault, 3=Perm Fault |
| Estado red | grid_status | flag | readMichele | |
| Energía total | energy_total | Wh | resp[49:52] | 32-bit |
| Horas operación | hours_total | h | resp[53:56] | |

### Datos reales del inversor (junio 2026)

- Solo MPPT2 tiene paneles conectados (~230-280V, 0.1-0.8A)
- MPPT1 y MPPT3 muestran 0V/0A (sin paneles)
- El inversor opera en estado 0 (Wait) de noche/amanecer y estado 1 (Normal) de día
- siser-reader inserta `is_stale=true` cuando el handshake falla (inversor offline de noche)
- Status codes: 0=Wait, 1=Normal, 2=Fault, 3=Permanent Fault

---

## Estrategia de Datos (PRODUCCIÓN)

| Capa | Intervalo | Tabla | Origen | Estado | Propósito |
|---|---|---|---|---|---|
| Tiempo real | ~5 seg | `realtime` | siser-reader (escribe) | **OPERATIVO** | Dashboard live |
| Muestra rápida | 1 min | `fast_samples` | daemon C (escribió) | **LEGACY** (no se actualiza) | Gráficos hora/día |
| Muestra lenta | 15 min | `slow_samples` | continuous aggregate | **VACÍA** (depende de fast_samples) | Tendencias |
| Acumulados | 1 min | `cumulatives` | daemon C (escribió) | **LEGACY** (no se actualiza) | Energía total, horas |
| Producción diaria | 1x/día | `daily_production` | sin writer | **VACÍA** | 48 slots horarios |
| Eventos | Evento | `events` | sin writer | **VACÍA** | Alarmas, cambios |

> **GAP CONOCIDO**: siser-reader solo escribe en `realtime`. Los dashboards leen exclusivamente de `realtime` con `time_bucket()` y `is_stale = false`. Las tablas `fast_samples`, `cumulatives` y `daily_production` no se actualizan. Para habilitarlas, agregar lógica en `siser_reader.py`.

Estimación de almacenamiento: ~2-3 GB/año con compression de TimescaleDB.

---

## Riesgos y Mitigaciones (RESUELTOS)

| Riesgo | Estado | Resolución |
|---|---|---|
| Pérdida de conexión USB (problema original) | **RESUELTO** | siser-reader (Python) con reconexión automática y heartbeats |
| Registros del protocolo desconocidos | **RESUELTO** | Protocolo SISER descubierto por decompilación de SunVision |
| Red UdeC bloquea puertos | **RESUELTO** | ngrok (solo HTTPS saliente puerto 443) |
| Adaptador RS232 falla | **MITIGADO** | Regla udev + device_cgroup_rules para hot-plug, CH340 funciona correctamente |
| Contenedor caído no se reinicia | **RESUELTO** | `restart: always` en todos los servicios (verificado junio 2026) |
| init.sql producción desactualizado | **CONOCIDO** | Producción tiene 181 líneas (sin columnas SISER en CREATE TABLE). siser-reader las agrega via ALTER TABLE. Solo importa si se recrea la DB. |
| fast_samples/cumulative legacy data | **CONOCIDO** | 2,881 filas del daemon C antiguo, no se actualizan |

## Timeline (COMPLETADO)

| Fase | Tarea | Estado |
|---|---|---|
| **1** | TimescaleDB (esquema SQL + continuous aggregates + init-users.sh) | **COMPLETADO** |
| **2** | Docker Compose + .env + udev | **COMPLETADO** |
| **3** | modbus-reader C daemon (legacy) → siser-reader Python | **COMPLETADO** (siser-reader en producción) |
| **4** | Grafana dashboards (datasource + 4 dashboards, SQL directo) | **COMPLETADO** |
| **5** | Cloudflare Tunnel | **DESCARTADO** (bloqueado en UdeC) → ngrok + nginx |
| **6** | Pantalla kiosco (lightdm + Openbox + Chromium + systemd) | **COMPLETADO** |
| **7** | Integración final + backup cron + pruebas 24h | **COMPLETADO** |
| **8** | Reverse Engineering SISER protocol | **COMPLETADO** (decompilación SunVision) |
| **9** | Testing con inversor real | **COMPLETADO** (datos reales fluyendo) |
| **10** | Informe técnico + Tutorial LaTeX | **EN PROGRESO** |

---

## Plan de Implementación — CÓDIGO EN PRODUCCIÓN

> **TODO EL CÓDIGO ESTÁ EN PRODUCCIÓN EN `/opt/solar-monitor/`**. Los archivos del vault son documentos de referencia. El sistema está operativo y no requiere más cambios.

| Host | lautaro (192.168.0.137) | WiFi wlp1s0, Ubuntu, kernel 7.0.0-22-generic |
|---|---|---|
| RAM | 30 GB (3.6 GB usados) | |
| Disco | 98 GB total, 46 GB usados (49%) | |

### Servicios Docker (docker-compose.yml)

| Container | Imagen | Estado | Restart | CPU | RAM |
|---|---|---|---|---|---|
| solar-monitor-siser-reader-1 | solar-monitor-siser-reader (477 MB) | Up | always | ~0% | 11 MB |
| solar-monitor-timescaledb-1 | timescale/timescaledb:latest-pg16 (1.94 GB) | Up (healthy) | always | ~0% | 222 MB |
| solar-monitor-grafana-1 | grafana/grafana:latest (v13.0.2, 1.47 GB) | Up | always | ~0.8% | 468 MB |

### Servicios systemd (host)

| Servicio | Puerto | Estado | Descripción |
|---|---|---|---|
| nginx | 8080 | ACTIVO, enabled | Reverse proxy (Grafana + ttyd + cmd-server) |
| ngrok | → 8080 | ACTIVO, enabled | Túnel HTTPS (`/usr/local/bin/ngrok http 8080`) |
| cmd-server | 8023 | ACTIVO, enabled | Ejecuta comandos remotos, devuelve JSON |
| ttyd | 8022 | ACTIVO, enabled | Terminal web |
| kiosk | — | ACTIVO, enabled | Chromium kiosk (Type=forking, User=lautaro) |
| lightdm | — | ACTIVO, enabled | Auto-login lautaro → sesión openbox |
| docker | — | ACTIVO, enabled | Docker Engine |

### Servicios eliminados

| Servicio | Estado |
|---|---|
| modbus-reader | **DETENIDO** (legacy, reemplazado por siser-reader) |
| sunvision-wine | **ELIMINADO** |
| cloudflared | **ELIMINADO** (bloqueado en UdeC) |
| xorg-kiosk.service | **NO EXISTE** (Xorg lo maneja lightdm) |

### Archivos en producción (`/opt/solar-monitor/`)

```
/opt/solar-monitor/
├── docker-compose.yml          # 3 servicios: siser-reader, timescaledb, grafana
├── .env                         # Passwords (DB_PASSWORD, GRAFANA_PASSWORD, GRAFANA_READER_PASSWORD)
├── siser-reader/                # Daemon Python SISER (PRODUCCIÓN)
│   ├── siser_reader.py          # Script principal (434 líneas)
│   └── Dockerfile
├── modbus-reader/                # Daemon C (LEGACY, no se usa)
│   └── src/
├── db/
│   ├── init.sql                 # Esquema TimescaleDB (sin columnas SISER en CREATE TABLE — las agrega siser-reader via ALTER TABLE)
│   ├── init-users.sh            # Usuarios (solar, grafana_reader)
│   └── seed.sql
├── grafana/
│   ├── provisioning/datasources/datasource.yml
│   ├── provisioning/dashboards/dashboard.yml
│   ├── dashboards/{realtime,historico,diagnostico,academico}.json
│   └── grafana.ini
├── inverter-simulator/          # Simulador para testing
├── backups/                     # Backups diarios de DB
└── kiosk/                       # Scripts legacy del kiosco (NO en uso — el activo está en /usr/local/bin/kiosk.sh)
```

> Ver `16_PROD.md` para el estado completo y detallado de producción.