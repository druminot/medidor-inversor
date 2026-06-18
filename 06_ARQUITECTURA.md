# Arquitectura — Sistema de Monitoreo Solar Lab UdeC

> **ESTADO: OPERATIVO** — El sistema está en producción. Los servicios son: siser-reader (Python), timescaledb, grafana. modbus-reader (C) y sunvision-wine fueron eliminados. cloudflared fue eliminado. No modificar sin necesidad.

## Principios de Diseño

1. **Robustez industrial**: Daemon C con libmodbus — resuelve el problema original de SunVision (pérdida de conexión USB)
2. **Estratificación de datos**: 5 seg (realtime) → 1 min (fast) → 15 min (slow, auto-agregado) → permanente (acumulados)
3. **Acceso universal**: Cualquier navegador, sin VPN, sin clientes — via ngrok (URL dinámica) con nginx reverse proxy (5 rutas)
4. **Resiliencia**: Reconexión automática ante caídas de USB, bus RS232, o base de datos
5. **Extensibilidad**: Fácil agregar piranómetro, estación meteorológica, más inversores
6. **Simplicidad**: 5 servicios Docker, sin API intermedia — Grafana consulta TimescaleDB directamente

---

## Diagrama de Arquitectura

```
[H.P.6065REL-D]
        │ RS232 via PL2303 (9600, 8N1, slave 1)
        │
[PL2303 USB-RS232] ── /dev/inverter-serial
        │
[PC "lautuaro" — Ubuntu Linux]
        │
  ┌────┴──────────────────────────────────────────┐
  │  Docker Compose (5 servicios)                  │
  │                                                │
  │  ┌───────────────┐    ┌──────────────┐        │
  │  │ modbus-reader  │    │  TimescaleDB │        │
  │  │ (C + libmodbus)│───▶│  (PostgreSQL)│        │
  │  │ daemon         │    └──────┬───────┘        │
  │  └───────────────┘           │                 │
  │                         ┌────┴──────┐          │
  │                         │  Grafana  │          │
  │                         │ (SQL directo)        │
  │                         └───────────┘          │
  │                                                │
  │  ┌───────────────┐    ┌──────────────┐        │
  │  │sunvision-wine │    │  inverter-   │        │
  │  │  (Wine+VNC)   │    │  simulator   │        │
  │  └───────────────┘    └──────────────┘        │
  └──────────────────────────────┼─────────────────┘
                                 │
                    nginx reverse proxy (:8080)
                    ├── /          → Grafana (:3000)
                    ├── /terminal/ → ttyd (:8022, basic auth)
                    ├── /sunvision/ → sunvision-wine (:8007)
                    ├── /v1sunvision/ → sunvision-wine (:8007)
                    └── /cmd/      → cmd-server (:8023, basic auth)
                                 │
                    ngrok tunnel (HTTPS, URL dinámica)
                                 │
              ┌────────────────┼───────────────┐
              │                │               │
         [Mac Doctor]   [Notebook Alumno]  [Celular]
         navegador        navegador         navegador
```

---

## Servicios

| Servicio | Imagen/Build | Función | Puerto Interno | Puerto Expuesto |
|---|---|---|---|---|
| modbus-reader | Build local (C) | Lectura RS232/Modbus RTU | — | Ninguno (acceso /dev/inverter-serial) |
| timescaledb | timescale/timescaledb:latest-pg16 | Base de datos series temporales | 5432 | 127.0.0.1:5432 |
| grafana | grafana/grafana:latest | Dashboard web (SQL directo a TimescaleDB) | 3000 | 127.0.0.1:3000 |
| sunvision-wine | Build local (Dockerfile) | SunVision via Wine + VNC | 8006 | 0.0.0.0:8007 |
| inverter-simulator | Build local (Dockerfile) | Simulador para testing | 5502-5503 | 5502, 5503, 33000/udp |

> Todos los puertos internos están en `127.0.0.1` excepto sunvision-wine (necesario para VNC). El acceso externo es exclusivamente via ngrok + nginx.
>
> **Nota**: No se usa API intermedia. Grafana consulta TimescaleDB directamente con SQL y soporta nativamente: dashboards interactivos, alertas, export CSV/JSON, refresh de 5 segundos, y 40+ usuarios concurrentes.

---

## Flujo de Datos

```
H.P.6065REL-D
    │ Modbus RTU (9600, 8N1, slave 1)
    ▼
modbus-reader (C daemon)
    │ Cada 5s: lecturas instantáneas → realtime
    │ Cada 60s: lecturas rápidas → fast_samples
    │ Cada 60s: acumulados → cumulatives
    │ 1x/día: gráfico diario → daily_production
    │ Eventos: cambios de estado → events
    ▼
TimescaleDB (PostgreSQL + timescaledb)
    │ Genera automáticamente:
    │   slow_samples (continuous aggregate, 15 min, desde fast_samples)
    │   hourly_energy (continuous aggregate, 1 hora)
    │   daily_energy (continuous aggregate, 1 día)
    │
    └── Grafana lee directamente con SQL
        ├── Dashboard Tiempo Real (refresh 5s)
        ├── Dashboard Histórico (refresh 5min)
        ├── Dashboard Diagnóstico (refresh 30s)
        └── Dashboard Académico (refresh 1min)
```

---

## Comunicación entre Servicios

```
modbus-reader ──(libpq, INSERT)──▶ TimescaleDB
Grafana ──(PostgreSQL, SELECT)────▶ TimescaleDB
nginx ──(reverse proxy)─────────▶ Grafana, ttyd, sunvision-wine, cmd-server
ngrok ──(HTTPS tunnel)──────────▶ nginx
```

No se usa message broker (MQTT/Redis) ni API intermedia para simplificar. TimescaleDB soporta alta velocidad de inserts (>10K/s) y el modbus-reader escribe directamente via libpq. Grafana consulta TimescaleDB directamente con SQL.

---

## Acceso Remoto

| URL | Destino | Auth |
|---|---|---|
| `https://XXXX.ngrok-free.dev/` | Grafana Dashboard | Anonymous viewer |
| `https://XXXX.ngrok-free.dev/terminal/` | Web terminal (ttyd) | lautaro:lsistem19 (basic auth) |
| `https://XXXX.ngrok-free.dev/cmd/` | Comandos remotos (cmd-server) | lautaro:lsistem19 (basic auth) |
| `https://XXXX.ngrok-free.dev/v1sunvision/` | SunVision via Wine | — |
| `ssh lautaro@192.168.1.145` | Administración local (RuminotRoa) | Password: `lsistem19` |
| Chrome Remote Desktop | Acceso GUI desde cualquier red | PIN: 121212 |

### Flujo de acceso para alumnos y doctor

1. Abrir navegador → `https://XXXX.ngrok-free.dev/`
2. Primera vez: clic "Visit Site" en warning de ngrok
3. Acceden al dashboard de Grafana (viewer, sin login)

### Seguridad

- ngrok: URL dinámica, TLS automático (HTTPS)
- nginx: basic auth en /terminal/ y /cmd/
- Todos los puertos internos en 127.0.0.1 (excepto sunvision-wine:8007)
- Grafana: usuario admin + viewer (solo lectura)
- cmd-server: ejecuta comandos como lautaro (sin sudo)

---

## Estrategia de Datos

| Capa | Intervalo | Tabla | Retención | Propósito |
|---|---|---|---|---|
| Tiempo real | 5 seg | `realtime` | 7 días (raw) → 3 días comprimido | Dashboard live, WebSocket |
| Muestra rápida | 1 min | `fast_samples` | 90 días → 30 días comprimido | Gráficos por hora/día |
| Muestra lenta | 15 min | `slow_samples` | 5 años | Tendencias mensuales/anuales |
| Acumulados | 1 min | `cumulatives` | Permanente | Energía total, horas, CO2 |
| Eventos | Evento | `events` | Permanente | Alarmas, cambios de estado |

Estimación de almacenamiento: ~2-3 GB/año con compression de TimescaleDB.

---

## docker-compose.yml

Ver archivo actualizado en `Proyecto/docker-compose.yml`. Servicios: modbus-reader, timescaledb, grafana, inverter-simulator, sunvision-wine.

---

## Archivo .env (NO commitear)

```env
DB_PASSWORD=VTwSBPMcFLu1lQUTmQ41MAH
GRAFANA_PASSWORD=8P2Y7juWdzSc1bnCOP55uaL
GRAFANA_READER_PASSWORD=cambiar_esta_password
```

---

## Decisiones Tomadas

| Decisión | Elección | Justificación |
|---|---|---|
| Lector Modbus | C + libmodbus | Robustez industrial, reconexión USB confiable |
| Base de datos | TimescaleDB | Series temporales nativas, SQL, compression, continuous aggregates |
| API REST | **Ninguna** | Grafana consulta TimescaleDB directamente. Sin consumidor que la justifique ahora. Agregar si se necesita app mobile o notebooks. |
| Agregación slow_samples | Continuous aggregate (TimescaleDB) | El daemon no tiene datos intermedios para calcular promedios; la DB lo hace automáticamente desde fast_samples |
| Dashboard | Grafana | Listo para producción, 40 usuarios, exportable, queries SQL directas |
| Acceso remoto | ngrok + nginx | URL dinámica, TLS automático, reverse proxy con 5 rutas |
| Auth | nginx basic auth + Grafana anonymous viewer | lautaro:lsistem19 para terminal/cmd, sin login para Grafana |
| Passwords DB | Variables de entorno (init-users.sh) | No hardcodear en init.sql que puede estar en repositorio |
| Message broker | Ninguno (directo) | Simplicidad, TimescaleDB soporta la carga |
| Contenedores | Docker Compose | Orquestación simple, reinicio automático |
| Remote access | ngrok (not Cloudflare) | Cloudflare bloqueado en red "Power Electronics" (port 7844) |
| Web terminal | ttyd + nginx basic auth | Acceso terminal desde navegador |
| Remote commands | cmd-server.py + nginx basic auth | Ejecutar comandos via HTTP, evita necesidad de SSH tunnel |

---

## Escalabilidad Futura

- **Agregar piranómetro**: nuevas tablas en TimescaleDB, mismas tablas `realtime`/`fast_samples` con columnas adicionales (irradiance, ambient_temp)
- **Agregar estación meteorológica**: mismo patrón
- **Agregar más inversores**: slave_address 2-20 en el bus RS485, modbus-reader ya soporta múltiples slaves
- **Alertas Telegram/Email**: Grafana Alerts → Telegram bot o Email SMTP
- **Mobile app**: se puede agregar API REST si se necesita