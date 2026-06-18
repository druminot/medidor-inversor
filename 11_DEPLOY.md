# Deploy — Despliegue Paso a Paso

> **ESTADO: OPERATIVO** — El sistema está desplegado y corriendo en lautaro. No need to redeploy. Este documento es referencia para reinstalación si fuera necesario. Los servicios activos son: siser-reader, timescaledb, grafana (3 containers). Los servicios systemd ttyd, cmd-server y nginx también están habilitados.

## Objetivo

Instrucciones completas para desplegar el sistema de monitoreo solar en el PC lautaro desde cero.

---

## Prerequisitos

- PC lautaro con Ubuntu, acceso SSH, WiFi configurado
- Adaptador USB-RS232 conectado (PL2303, CH340 o FT232)
- Inversor H.P.6065REL-D conectado via RS232

---

## Paso 1: Instalar Docker

```bash
# Agregar repositorio oficial de Docker
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Agregar usuario al grupo docker
sudo usermod -aG docker lautaro

# Cerrar sesión y volver a entrar para que el grupo surta efecto
exit
# Volver a entrar por SSH

# Verificar
docker --version
docker compose version
```

---

## Paso 2: Crear regla udev para USB-RS232

```bash
# Crear regla udev
sudo tee /etc/udev/rules.d/99-serial.rules << 'EOF'
# Adaptador USB-RS232 PL2303
SUBSYSTEM=="tty", ATTRS{idVendor}=="067b", ATTRS{idProduct}=="2303", SYMLINK+="inverter-serial", GROUP="dialout", MODE="0666"

# Adaptador USB-RS232 CH340
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="inverter-serial", GROUP="dialout", MODE="0666"

# Adaptador USB-RS232 FT232
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", SYMLINK+="inverter-serial", GROUP="dialout", MODE="0666"
EOF

# Recargar reglas
sudo udevadm control --reload-rules
sudo udevadm trigger

# Conectar el adaptador y verificar
ls -la /dev/inverter-serial
# Debe mostrar: /dev/inverter-serial -> /dev/ttyUSB0
```

---

## Paso 3: Instalar dependencias de compilación

```bash
sudo apt-get install -y libmodbus-dev libpq-dev gcc make cmake
```

---

## Paso 4: Crear estructura de directorios

```bash
sudo mkdir -p /opt/solar-monitor/{modbus-reader/src,grafana/provisioning/datasources,grafana/provisioning/dashboards,grafana/dashboards,db,backups}

# Permisos
sudo chown -R lautaro:lautaro /opt/solar-monitor
```

---

## Paso 5: Crear archivo .env

```bash
cat > /opt/solar-monitor/.env << 'EOF'
# Passwords (CAMBIAR ANTES DE DEPLOY)
DB_PASSWORD=VTwSBPMcFLu1lQUTmQ41MAH
GRAFANA_PASSWORD=8P2Y7juWdzSc1bnCOP55uaL
GRAFANA_READER_PASSWORD=cambiar_esta_password
EOF

# Proteger el archivo
chmod 600 /opt/solar-monitor/.env
```

---

## Paso 6: Crear esquema SQL e init-users.sh

Copiar el contenido de `08_DATABASE.md` (sección "Esquema SQL Completo") a:

```bash
/opt/solar-monitor/db/init.sql
```

Copiar el script de usuarios de `08_DATABASE.md` (sección "Script de usuarios") a:

```bash
/opt/solar-monitor/db/init-users.sh
chmod +x /opt/solar-monitor/db/init-users.sh
```

---

## Paso 7: Crear docker-compose.yml y .env

Copiar el contenido de `06_ARQUITECTURA.md` (sección "docker-compose.yml") a:

```bash
/opt/solar-monitor/docker-compose.yml
```

Copiar el contenido de `06_ARQUITECTURA.md` (sección "Archivo .env") a:

```bash
/opt/solar-monitor/.env
chmod 600 /opt/solar-monitor/.env
```

> **Importante**: Cambiar las passwords en `.env` antes del deploy.

---

## Paso 8: Crear código fuente del modbus-reader

Crear los archivos fuente del daemon C copiando el código de `07_MODBUS_READER.md`:

```bash
mkdir -p /opt/solar-monitor/modbus-reader/src

# Headers (copiar de 07_MODBUS_READER.md)
# src/logger.h          → sección "logger.h"
# src/register_map.h    → sección "register_map.h"
# src/config.h          → sección "config.h"
# src/modbus_comm.h     → sección "modbus_comm.h"
# src/db_writer.h       → sección "db_writer.h"
# src/watchdog.h        → sección "watchdog.h"

# Implementaciones C (copiar de 07_MODBUS_READER.md)
# src/config.c          → sección "config.c"
# src/register_map.c    → sección "register_map.c"
# src/modbus_comm.c     → sección "modbus_comm.c"
# src/db_writer.c       → sección "db_writer.c"
# src/watchdog.c         → sección "watchdog.c"
# src/main.c            → sección "main.c"

# Build files (copiar de 07_MODBUS_READER.md)
# Makefile              → sección "Makefile"
# Dockerfile            → sección "Dockerfile (multi-stage)"
```

Ejemplo de creación rápida:

```bash
cd /opt/solar-monitor/modbus-reader

# Crear cada archivo desde el contenido de 07_MODBUS_READER.md
# (cada sección tiene el nombre del archivo como encabezado)
nano src/logger.h
nano src/register_map.h
nano src/config.h
nano src/modbus_comm.h
nano src/db_writer.h
nano src/watchdog.h
nano src/config.c
nano src/register_map.c
nano src/modbus_comm.c
nano src/db_writer.c
nano src/watchdog.c
nano src/main.c
nano Makefile
nano Dockerfile
```

Build y prueba de compilación:

```bash
cd /opt/solar-monitor/modbus-reader
make clean && make
# Si compila sin errores, proceder con Docker build:
docker compose -f /opt/solar-monitor/docker-compose.yml build modbus-reader
```

---

## Paso 9: Crear configuración de Grafana

### 9a: Datasource y dashboard provider

```bash
mkdir -p /opt/solar-monitor/grafana/provisioning/datasources
mkdir -p /opt/solar-monitor/grafana/provisioning/dashboards
mkdir -p /opt/solar-monitor/grafana/dashboards
```

Copiar el contenido de `09_GRAFANA.md` (sección "Provisioning automático") a:

```bash
/opt/solar-monitor/grafana/provisioning/datasources/datasource.yml
```

Copiar el contenido de `09_GRAFANA.md` (sección "Provisioning de Dashboards") a:

```bash
/opt/solar-monitor/grafana/provisioning/dashboards/dashboard.yml
```

### 9b: grafana.ini

Copiar el contenido de `09_GRAFANA.md` (sección "grafana/grafana.ini") a:

```bash
/opt/solar-monitor/grafana/grafana.ini
```

### 9c: Dashboard JSONs

Copiar cada dashboard JSON de `09_GRAFANA.md` (secciones "Dashboard JSONs") a:

```bash
/opt/solar-monitor/grafana/dashboards/realtime.json      # sección "realtime.json"
/opt/solar-monitor/grafana/dashboards/historico.json      # sección "historico.json"
/opt/solar-monitor/grafana/dashboards/diagnostico.json   # sección "diagnostico.json"
/opt/solar-monitor/grafana/dashboards/academico.json      # sección "academico.json"
```

---

## Paso 10: Deploy

```bash
cd /opt/solar-monitor

# Levantar todos los servicios
docker compose up -d

# Verificar que todos están corriendo
docker compose ps

# Verificar logs
docker compose logs -f
```

---

## Paso 11: Verificar cada servicio

```bash
# TimescaleDB
docker compose exec timescaledb pg_isready -U solar
# Debe responder: accepting connections

# Grafana
curl -I http://localhost:3000
# Debe responder: HTTP/1.1 302 Found

# Modbus-reader logs
docker compose logs modbus-reader
# Debe mostrar: "Connected to /dev/ttyUSB0"

# Verificar datos en DB
docker compose exec timescaledb psql -U solar solar_monitor -c "SELECT * FROM realtime ORDER BY time DESC LIMIT 3"
```

---

## Paso 12: Verificar Grafana

1. Abrir navegador local: `http://localhost:3000`
2. Login: admin / (password del .env)
3. Datasource TimescaleDB ya está provisionado automáticamente (ver `10_GRAFANA.md`)
4. Dashboards ya están provisionados (ver `grafana/provisioning/`)
5. Verificar que los paneles muestran datos del inversor

> No es necesario crear usuarios viewer manualmente — `GF_AUTH_ANONYMOUS_ENABLED=true` permite ver dashboards sin login. Cloudflare Access se encarga de la autenticación.

---

## Paso 13: Configurar acceso remoto (ngrok + nginx)

Ver instrucciones completas en [[15_TUNEL_REMOTO]].

```bash
# Instalar ngrok
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc > /dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok
ngrok config add-authtoken <TOKEN>

# Instalar nginx
sudo apt-get install -y nginx apache2-utils
sudo htpasswd -cb /etc/nginx/.htpasswd lautaro lsistem19

# Copiar config de nginx
sudo cp /opt/solar-monitor/nginx/solar-monitor /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/solar-monitor /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Iniciar ngrok
ngrok http 8080
```

---

## Paso 14: Verificar acceso remoto

```bash
# Desde otro dispositivo
curl -I https://XXXX.ngrok-free.dev
# Debe responder: HTTP/2 200

# Abrir en navegador
# https://XXXX.ngrok-free.dev
# Clic "Visit Site" en warning de ngrok
# Ver dashboard de Grafana (sin login)
```

---

## Comandos Útiles

```bash
# Ver estado de todos los servicios
docker compose ps

# Ver logs de un servicio específico
docker compose logs -f modbus-reader
docker compose logs -f timescaledb
docker compose logs -f grafana

# Reiniciar un servicio
docker compose restart modbus-reader

# Reiniciar todo
docker compose down && docker compose up -d

# Backup de la base de datos
docker compose exec timescaledb pg_dump -U solar solar_monitor | gzip > /opt/solar-monitor/backups/solar_monitor_$(date +%Y%m%d).sql.gz

# Restaurar backup
gunzip -c /opt/solar-monitor/backups/solar_monitor_20240115.sql.gz | docker compose exec -i timescaledb psql -U solar solar_monitor

# Verificar espacio en disco
df -h /

# Verificar adaptador USB-RS232
ls -la /dev/inverter-serial
dmesg | grep ttyUSB

# Actualizar un servicio
docker compose build modbus-reader
docker compose up -d modbus-reader

# Ver consumo de recursos
docker stats
```

---

## Cron: Backup diario

```bash
# Agregar al crontab de root
sudo crontab -e

# Backup diario a las 02:00
0 2 * * * docker compose -f /opt/solar-monitor/docker-compose.yml exec -T timescaledb pg_dump -U solar solar_monitor | gzip > /opt/solar-monitor/backups/solar_monitor_$(date +\%Y\%m\%d).sql.gz

# Limpiar backups mayores a 7 días
0 3 * * * find /opt/solar-monitor/backups/ -name "*.sql.gz" -mtime +7 -delete
```

---

## Rollback

Si algo falla después de un update:

```bash
# Detener todo
docker compose down

# Restaurar backup de DB
gunzip -c /opt/solar-monitor/backups/solar_monitor_YYYYMMDD.sql.gz | docker compose exec -i timescaledb psql -U solar solar_monitor

# Volver a la versión anterior de imágenes
docker compose pull  # si usamos imágenes pre-built
docker compose up -d
```

---

## Monitoreo Post-Deploy (primeras 24 horas)

Verificar cada hora durante las primeras 24 horas:

- [ ] `docker compose ps` — todos los servicios "Up"
- [ ] `docker compose logs modbus-reader | tail -20` — lecturas exitosas
- [ ] `docker compose logs timescaledb | tail -10` — sin errores
- [ ] `curl -I https://lautuaro.tail6e64d5.ts.net` — acceso remoto OK
- [ ] Abrir Grafana → verificar datos en dashboard de tiempo real
- [ ] Verificar que no hay errores de comunicación Modbus en tabla `events`
- [ ] Verificar que los backups diarios se están ejecutando
- [ ] Verificar que `slow_samples` tiene datos (continuous aggregate, esperar ~15 min)
