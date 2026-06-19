# Infraestructura — PC "lautaro"

> **ESTADO: OPERATIVO** — Todo está corriendo. Los servicios systemd (ttyd, cmd-server) están habilitados. SunVision y cloudflared fueron eliminados. Docker tiene 3 containers activos con `restart: always`.

## Acceso

| Parámetro | Valor |
|---|---|
| Hostname | lautaro |
| IP Local (Power Electronics) | 192.168.0.137 |
| IP Local (RuminotRoa) | 192.168.1.145 |
| Usuario | lautaro |
| Password | lsistem19 |
| SSH | Habilitado (password + key) |

### Métodos de acceso remoto

| Método | Red | Funciona en "Power Electronics" | Notas |
|---|---|---|---|
| SSH local | Ambas | No (puerto entrante bloqueado) | `ssh lautaro@192.168.0.137` |
| **ttyd + ngrok** | Ambas | **Sí** (sale por 443) | URL dinámica, credenciales: lautaro/lsistem19 |
| **cmd API + ngrok** | Ambas | **Sí** (sale por 443) | Ejecución remota de comandos via HTTP |
| **Grafana + ngrok** | Ambas | **Sí** (sale por 443) | Dashboard accesible sin login |
| Chrome Remote Desktop | Ambas | **Sí** (sale por 443) | PIN: 121212, cuenta: druminot.dr@gmail.com |

> **Nota**: "Power Electronics" bloquea todo tráfico entrante y Tailscale. Solo puertos 80/443 salientes funcionan. ngrok funciona porque usa conexiones salientes HTTPS.

### ngrok + nginx (acceso remoto unificado)

Un solo túnel ngrok expone todo a través de nginx reverse proxy en puerto 8080:

| Servicio | URL local | URL remota | Auth |
|---|---|---|---|
| Grafana | localhost:3000 | `https://zoning-heat-groggy.ngrok-free.dev/` | Anonymous viewer |
| Terminal web | localhost:8022 | `https://zoning-heat-groggy.ngrok-free.dev/terminal/` | lautaro/lsistem19 |
| Ejecutar comandos | localhost:8023 | `https://zoning-heat-groggy.ngrok-free.dev/cmd/?cmd=COMANDO` | lautaro/lsistem19 |

- **ttyd**: servidor de terminal web en puerto 8022 (sin auth propia)
- **cmd-server.py**: servidor HTTP en puerto 8023 que ejecuta comandos y devuelve JSON (`/cmd?cmd=COMANDO`)
- **nginx**: reverse proxy en puerto 8080, combina todos los servicios, basic auth para `/terminal/` y `/cmd/`
- **ngrok**: túnel HTTP que expone nginx (8080) a internet vía HTTPS saliente
- **ngrok cuenta**: druminot.dr@gmail.com (authtoken configurado)
- **URL**: dinámica (cambia cada reinicio de ngrok), verificar con `curl -s http://127.0.0.1:4040/api/tunnels`

#### Iniciar servicios

```bash
# 1. ttyd (terminal web)
nohup ttyd -p 8022 -W bash > /home/lautaro/ttyd.log 2>&1 &
# 2. cmd-server.py (ejecución remota de comandos)
nohup python3 /home/lautaro/cmd-server.py > /home/lautaro/cmd-server.log 2>&1 &
# 3. ngrok (túnel HTTPS)
nohup ngrok http 8080 --log=stdout > /home/lautaro/ngrok.log 2>&1 &
# 4. Ver URL pública
curl -s http://127.0.0.1:4040/api/tunnels | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["tunnels"][0]["public_url"])'
```

#### Ejecutar comandos remotamente

```bash
# Ejemplo: ver containers Docker
curl -s -u lautaro:lsistem19 -H "ngrok-skip-browser-warning: true" \
  "https://zoning-heat-groggy.ngrok-free.dev/cmd/?cmd=docker+ps"

# Ejemplo: ver logs del siser-reader
curl -s -u lautaro:lsistem19 -H "ngrok-skip-browser-warning: true" \
  "https://zoning-heat-groggy.ngrok-free.dev/cmd/?cmd=docker+logs+solar-monitor-siser-reader-1+--tail+20"
```

- **Limitaciones**: URL cambia al reiniciar ngrok (plan gratis); ngrok TCP requiere tarjeta; wstunnel para SSH no funciona a través de nginx (ngrok fuerza H2)

### Chrome Remote Desktop

- **Cuenta Google**: druminot.dr@gmail.com
- **PIN**: 121212
- **Acceso**: https://remotedesktop.google.com/access
- **Estado**: funciona en TODAS las redes incluyendo "Power Electronics"

---

## Docker (PRODUCCIÓN)

### Servicios en producción (`/opt/solar-monitor/docker-compose.yml`)

| Servicio | Imagen/Build | Estado | Notas |
|---|---|---|---|
| siser-reader | Build local (Python) | **ACTIVO** | Protocolo SISER, escribe en `realtime`, `restart: always` |
| timescaledb | timescale/timescaledb:latest-pg16 | **ACTIVO** | ~28K filas, healthy, `restart: always` |
| grafana | grafana/grafana:latest | **ACTIVO** | 4 dashboards, anonymous viewer, `restart: always` |

### Comandos Docker útiles

```bash
# Ver estado de containers
docker compose -f /opt/solar-monitor/docker-compose.yml ps

# Ver logs
docker logs solar-monitor-siser-reader-1 --tail 20
docker logs solar-monitor-timescaledb-1 --tail 10
docker logs solar-monitor-grafana-1 --tail 10

# Reiniciar un servicio
docker restart solar-monitor-siser-reader-1
docker restart solar-monitor-grafana-1

# Reiniciar todo
docker compose -f /opt/solar-monitor/docker-compose.yml restart

# Reconstruir siser-reader (después de cambios en código)
docker compose -f /opt/solar-monitor/docker-compose.yml build siser-reader
docker compose -f /opt/solar-monitor/docker-compose.yml up -d siser-reader
```

---

## Estructura de Directorios en Producción (`/opt/solar-monitor/`)

```
/opt/solar-monitor/
├── docker-compose.yml          # 3 servicios: siser-reader, timescaledb, grafana
├── .env                         # Passwords (DB_PASSWORD, GRAFANA_PASSWORD, GRAFANA_READER_PASSWORD)
├── siser-reader/                # Daemon Python SISER (PRODUCCIÓN)
│   ├── siser_reader.py          # Script principal (434 líneas)
│   ├── Dockerfile
│   └── requirements.txt
├── modbus-reader/               # Daemon C (LEGACY, no se usa)
│   └── src/
├── db/
│   ├── init.sql                 # Esquema TimescaleDB (con columnas SISER)
│   └── init-users.sh            # Usuarios (solar, grafana_reader)
├── grafana/
│   ├── provisioning/datasources/datasource.yml
│   ├── provisioning/dashboards/dashboard.yml
│   ├── dashboards/{realtime,historico,diagnostico,academico}.json
│   └── grafana.ini
├── inverter-simulator/          # Simulador para testing
└── backups/                     # Backups de DB
```

> **NOTA**: Existen archivos legacy en el directorio (`cloudflared/`, `sunvision-wine/`, `winxp-sunvision/`, `dlna/`, `airplay_*.py`, `roku-channel/`, etc.) que NO son parte del proyecto solar-monitor y pueden ser eliminados.

---

## Regla udev para adaptadores USB-Serial

### Archivo: `/etc/udev/rules.d/99-serial.rules`

```udev
# Adaptador USB-RS232 CH340 (Riello H.P.6065REL-D)
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="inverter-serial", GROUP="dialout", MODE="0666"

# Adaptador USB-RS232 PL2303 (alternativo)
SUBSYSTEM=="tty", ATTRS{idVendor}=="067b", ATTRS{idProduct}=="2303", SYMLINK+="inverter-serial", GROUP="dialout", MODE="0666"

# Adaptador USB-RS232 FT232 (alternativo)
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", SYMLINK+="inverter-serial", GROUP="dialout", MODE="0666"
```

> **Nota**: Todos los adaptadores crean el symlink `/dev/inverter-serial`. Actualmente conectado: CH340 en `/dev/ttyUSB0`.

---

## Suspensión (deshabilitada)

| Target | Estado |
|---|---|
| sleep.target | Masked |
| suspend.target | Masked |
| hibernate.target | Masked |
| hybrid-sleep.target | Masked |

### Logind (`/etc/systemd/logind.conf.d/no-suspend.conf`)

```ini
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
IdleAction=ignore
```

> **Nota**: La suspensión está deshabilitada porque el PC debe operar 24/7.

---

## Herramientas instaladas

| Herramienta | Versión | Propósito |
|---|---|---|
| Docker + Compose | latest | Stack de contenedores (siser-reader, timescaledb, grafana) |
| ngrok | 3.39.7 | Túnel HTTP para acceso remoto |
| ttyd | 1.7.7 | Terminal web |
| nginx | 1.28.3 | Reverse proxy (Grafana+terminal+cmd) |
| Python 3 | system | siser-reader, cmd-server |

---

## Comandos útiles

```bash
# Ejecutar comandos remotamente via HTTP (funciona en TODAS las redes)
curl -s -u lautaro:lsistem19 -H "ngrok-skip-browser-warning: true" \
  "https://zoning-heat-groggy.ngrok-free.dev/cmd/?cmd=docker+ps"

# Verificar adaptador USB-Serial
ls -la /dev/inverter-serial
dmesg | grep ttyUSB

# Verificar suspensión deshabilitada
systemctl status sleep.target suspend.target hibernate.target

# Docker
docker compose -f /opt/solar-monitor/docker-compose.yml ps
docker compose -f /opt/solar-monitor/docker-compose.yml logs -f siser-reader

# Consultar DB
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c \
  "SELECT time, status, pac, ppv_total, temp FROM realtime WHERE is_stale=false ORDER BY time DESC LIMIT 5"

# Backup de DB
docker exec solar-monitor-timescaledb-1 pg_dump -U solar solar_monitor | gzip > \
  /opt/solar-monitor/backups/solar_monitor_$(date +%Y%m%d).sql.gz
```