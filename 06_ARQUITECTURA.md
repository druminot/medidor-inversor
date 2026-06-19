# Arquitectura — Sistema de Monitoreo Solar Lab UdeC

> **ESTADO: OPERATIVO** — El sistema está en producción. Los servicios son: siser-reader (Python), timescaledb, grafana. Todos con `restart: always`. modbus-reader (C) fue reemplazado por siser-reader. sunvision-wine y cloudflared fueron eliminados.

## Principios de Diseño

1. **Robustez industrial**: Daemon Python con SISER protocol (reverse-engineered de SunVision) — reconexión automática, heartbeats (is_stale), RTS/DTR para opto-isolación
2. **Estratificación de datos**: 5 seg (realtime) → continuous aggregates (pendientes de activar con fast_samples)
3. **Acceso universal**: Cualquier navegador, sin VPN, sin clientes — via ngrok (URL dinámica) con nginx reverse proxy
4. **Resiliencia**: Reconexión automática ante caídas de USB, bus RS232, o base de datos. Contenedores con `restart: always`
5. **Extensibilidad**: Fácil agregar piranómetro, estación meteorológica, más inversores
6. **Simplicidad**: 3 servicios Docker, sin API intermedia — Grafana consulta TimescaleDB directamente

---

## Diagrama de Arquitectura

```
[Riello H.P.6065REL-D]
        │ RS232 via CH340 (9600, 8N1, SISER protocol, address 33)
        │ RTS/DTR para opto-isolación
        │
[CH340 USB-RS232 Adapter] ── /dev/inverter-serial
        │
[PC "lautaro" — Ubuntu Linux]
        │
  ┌────┴──────────────────────────────────────────┐
  │  Docker Compose (3 servicios, restart: always) │
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

---

## Servicios

| Servicio | Imagen/Build | Función | Puerto Interno | Puerto Expuesto | Restart |
|---|---|---|---|---|---|
| siser-reader | Build local (Python) | Lectura SISER via RS232 | — | Ninguno (acceso /dev/inverter-serial) | always |
| timescaledb | timescale/timescaledb:latest-pg16 | Base de datos series temporales | 5432 | 127.0.0.1:5432 | always |
| grafana | grafana/grafana:latest | Dashboard web (SQL directo a TimescaleDB) | 3000 | 127.0.0.1:3000 | always |

> Todos los puertos internos están en `127.0.0.1`. El acceso externo es exclusivamente via ngrok + nginx.

---

## Flujo de Datos

```
H.P.6065REL-D
    │ SISER protocol (RS232, 9600, 8N1, address 33)
    │ Handshake: offlineEnquiry → sendAddress → readMichele
    ▼
siser-reader (Python daemon)
    │ Cada ~5s: SISER readMichele → realtime (3 MPPT, grid, temp, status)
    │ Heartbeat: is_stale=true cuando inversor offline
    │ ALTER TABLE IF NOT EXISTS para columnas SISER
    ▼
TimescaleDB (PostgreSQL + timescaledb)
    │ Tabla principal: realtime (28 columnas, ~17K registros/día)
    │ Tablas legacy: fast_samples, cumulatives (no se actualizan)
    │ Continuous aggregates: slow_samples, hourly_energy, daily_energy (vacías)
    │
    └── Grafana lee directamente con SQL
        ├── Dashboard Tiempo Real (refresh 5s, 21 paneles)
        ├── Dashboard Histórico (refresh 5min, 10 paneles)
        ├── Dashboard Diagnóstico (refresh 30s, 13 paneles)
        └── Dashboard Académico (refresh 1min, 10 paneles)
```

---

## Comunicación entre Servicios

```
siser-reader ──(psycopg2, INSERT)──▶ TimescaleDB
Grafana ──(PostgreSQL, SELECT)────────▶ TimescaleDB
nginx ──(reverse proxy)─────────────▶ Grafana, ttyd, cmd-server
ngrok ──(HTTPS tunnel)──────────────▶ nginx
```

No se usa message broker (MQTT/Redis) ni API intermedia. TimescaleDB soporta alta velocidad de inserts y siser-reader escribe directamente via psycopg2. Grafana consulta TimescaleDB directamente con SQL.

---

## Acceso Remoto

| URL | Destino | Auth |
|---|---|---|
| `https://zoning-heat-groggy.ngrok-free.dev/` | Grafana Dashboard | Anonymous viewer |
| `https://zoning-heat-groggy.ngrok-free.dev/terminal/` | Web terminal (ttyd) | lautaro:lsistem19 (basic auth) |
| `https://zoning-heat-groggy.ngrok-free.dev/cmd/` | Comandos remotos (cmd-server) | lautaro:lsistem19 (basic auth) |
| `ssh lautaro@192.168.1.145` | Administración red local (RuminotRoa) | Password: lsistem19 |
| Chrome Remote Desktop | Acceso GUI desde cualquier red | PIN: 121212 |

### Seguridad

- ngrok: URL dinámica, TLS automático (HTTPS)
- nginx: basic auth en /terminal/ y /cmd/
- Todos los puertos internos en 127.0.0.1
- Grafana: usuario admin + viewer anónimo (solo lectura)
- cmd-server: ejecuta comandos como lautaro (sin sudo)

---

## Estrategia de Datos

| Capa | Intervalo | Tabla | Origen | Estado | Propósito |
|---|---|---|---|---|---|
| Tiempo real | ~5 seg | `realtime` | siser-reader (escribe) | **OPERATIVO** | Dashboard live |
| Muestra rápida | 1 min | `fast_samples` | siser-reader (NO escribe) | **LEGACY** (datos del daemon C) | Gráficos hora/día |
| Muestra lenta | 15 min | `slow_samples` | continuous aggregate | **VACÍA** (depende de fast_samples) | Tendencias |
| Acumulados | 1 min | `cumulatives` | siser-reader (NO escribe) | **LEGACY** (datos del daemon C) | Energía total, horas |
| Producción diaria | 1x/día | `daily_production` | siser-reader (NO escribe) | **VACÍA** | 48 slots horarios |
| Eventos | Evento | `events` | siser-reader (NO escribe) | **VACÍA** | Alarmas, cambios |

> **GAP CONOCIDO**: siser-reader solo escribe en `realtime`. Los dashboards leen exclusivamente de `realtime` con `time_bucket()` y `is_stale = false`. Las tablas `fast_samples`, `cumulatives` y `daily_production` no se actualizan. Para habilitarlas, agregar lógica en `siser_reader.py`.

Estimación de almacenamiento: ~2-3 GB/año con compression de TimescaleDB.

---

## docker-compose.yml

Ver archivo actualizado en `Proyecto/docker-compose.yml`. Servicios: siser-reader, timescaledb, grafana (3 containers, todos con `restart: always`).

> **NOTA sobre producción**: El `docker-compose.yml` en lautaro tiene un servicio `cloudflared` residual (sin configuración útil, `command: tunnel -`). No se ejecuta ni consume recursos pero debería eliminarse en una próxima limpieza. También tiene el password de `grafana_reader` hardcodeado en `datasource.yml` en lugar de usar `${GRAFANA_READER_PASSWORD}`, y el `grafana.ini` tiene `root_url` apuntando a la URL de ngrok actual.

---

## Archivo .env (NO commitear)

```env
DB_PASSWORD=VTwSBPMcFLu1lQUTmQ41MAH
GRAFANA_PASSWORD=8P2Y7juWdzSc1bnCOP55uaL
GRAFANA_READER_PASSWORD=zA6n18BvrFZJt2Q-UCmOFBcff0ze-_2l
```

---

## Decisiones Tomadas

| Decisión | Elección | Justificación |
|---|---|---|
| Lector SISER | Python + psycopg2 + pyserial | Protocolo SISER (Phoenixtec) descubierto por reverse engineering de SunVision |
| Base de datos | TimescaleDB | Series temporales nativas, SQL, compression, continuous aggregates |
| API REST | **Ninguna** | Grafana consulta TimescaleDB directamente |
| Dashboard | Grafana | Listo para producción, 4 dashboards, 54 paneles totales, export CSV nativo |
| Acceso remoto | ngrok + nginx | URL dinámica, TLS automático, reverse proxy con 3 rutas |
| Auth | nginx basic auth + Grafana anonymous viewer | lautaro:lsistem19 para terminal/cmd, sin login para Grafana |
| Restart policy | `always` | Contenedores se reinician automáticamente incluso después de `docker stop` |
| Remote access | ngrok (not Cloudflare) | Cloudflare bloqueado en red "Power Electronics" (port 7844) |
| Dashboards provisionados | Archivos JSON en disco | No editables via API, solo editando JSON y reiniciando Grafana |

---

## Escalabilidad Futura

- **Agregar piranómetro**: nuevas columnas en `realtime` (ALTER TABLE), mismas queries con columnas adicionales
- **Agregar estación meteorológica**: mismo patrón
- **Agregar más inversores**: slave_address 2-20 en el bus RS485, siser-reader ya soporta address configurable
- **Alertas Telegram/Email**: Grafana Alerts → Telegram bot o Email SMTP
- **Habilitar fast_samples/cumulatives**: agregar lógica en siser_reader.py para escribir promedios de 1 min y acumulados