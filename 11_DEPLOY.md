# Deploy — Despliegue Paso a Paso

> **ESTADO: OPERATIVO** — El sistema está desplegado y corriendo en lautaro. No need to redeploy. Este documento es referencia para reinstalación si fuera necesario. Los servicios activos son: siser-reader, timescaledb, grafana (3 containers, todos con `restart: always`). Los servicios systemd ttyd, cmd-server y nginx también están habilitados.

## Objetivo

Instrucciones completas para desplegar el sistema de monitoreo solar en el PC lautaro desde cero.

---

## Prerequisitos

- PC lautaro con Ubuntu, acceso SSH, WiFi configurado
- Adaptador USB-RS232 conectado (CH340, actualmente en uso)
- Inversor H.P.6065REL-D conectado via RS232

---

## Paso 1: Instalar Docker

```bash
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

sudo usermod -aG docker lautaro
# Cerrar sesión y volver a entrar

docker --version
docker compose version
```

---

## Paso 2: Crear regla udev para USB-RS232

```bash
sudo tee /etc/udev/rules.d/99-serial.rules << 'EOF'
# Adaptador USB-RS232 CH340 (Riello H.P.6065REL-D)
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="inverter-serial", GROUP="dialout", MODE="0666"

# Adaptador USB-RS232 PL2303 (alternativo)
SUBSYSTEM=="tty", ATTRS{idVendor}=="067b", ATTRS{idProduct}=="2303", SYMLINK+="inverter-serial", GROUP="dialout", MODE="0666"

# Adaptador USB-RS232 FT232 (alternativo)
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", SYMLINK+="inverter-serial", GROUP="dialout", MODE="0666"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger

ls -la /dev/inverter-serial
# Debe mostrar: /dev/inverter-serial -> /dev/ttyUSB0
```

---

## Paso 3: Crear estructura de directorios

```bash
sudo mkdir -p /opt/solar-monitor/{siser-reader,grafana/provisioning/datasources,grafana/provisioning/dashboards,grafana/dashboards,db,backups}

sudo chown -R lautaro:lautaro /opt/solar-monitor
```

---

## Paso 4: Crear archivo .env

```bash
cat > /opt/solar-monitor/.env << 'EOF'
DB_PASSWORD=VTwSBPMcFLu1lQUTmQ41MAH
GRAFANA_PASSWORD=8P2Y7juWdzSc1bnCOP55uaL
GRAFANA_READER_PASSWORD=zA6n18BvrFZJt2Q-UCmOFBcff0ze-_2l
EOF

chmod 600 /opt/solar-monitor/.env
```

---

## Paso 5: Crear esquema SQL e init-users.sh

Copiar el contenido de `Proyecto/db/init.sql` a:

```bash
cp init.sql /opt/solar-monitor/db/01-schema.sql
```

Copiar el script de usuarios de `Proyecto/db/init-users.sh` a:

```bash
cp init-users.sh /opt/solar-monitor/db/02-users.sh
chmod +x /opt/solar-monitor/db/02-users.sh
```

---

## Paso 6: Crear siser-reader (Python daemon)

### siser_reader.py

Copiar `Proyecto/siser-reader/siser_reader.py` a:

```bash
/opt/solar-monitor/siser-reader/siser_reader.py
```

### Dockerfile

Copiar `Proyecto/siser-reader/Dockerfile` a:

```bash
/opt/solar-monitor/siser-reader/Dockerfile
```

### requirements.txt

Copiar `Proyecto/siser-reader/requirements.txt` a:

```bash
/opt/solar-monitor/siser-reader/requirements.txt
```

Build y prueba:

```bash
cd /opt/solar-monitor
docker compose build siser-reader
```

---

## Paso 7: Crear docker-compose.yml

Copiar `Proyecto/docker-compose.yml` a:

```bash
/opt/solar-monitor/docker-compose.yml
```

Verificar que todos los servicios tengan `restart: always`.

---

## Paso 8: Crear configuración de Grafana

### 8a: Datasource y dashboard provider

```bash
# Copiar desde Proyecto/grafana/provisioning/
cp datasource.yml /opt/solar-monitor/grafana/provisioning/datasources/
cp dashboard.yml /opt/solar-monitor/grafana/provisioning/dashboards/
```

### 8b: grafana.ini

Copiar `Proyecto/grafana/grafana.ini` a:

```bash
/opt/solar-monitor/grafana/grafana.ini
```

### 8c: Dashboard JSONs

Copiar cada dashboard JSON:

```bash
cp realtime.json /opt/solar-monitor/grafana/dashboards/
cp historico.json /opt/solar-monitor/grafana/dashboards/
cp diagnostico.json /opt/solar-monitor/grafana/dashboards/
cp academico.json /opt/solar-monitor/grafana/dashboards/
```

> **NOTA IMPORTANTE**: Los dashboards provisionados NO se pueden editar via la API de Grafana. Para modificarlos, editar el archivo JSON en disco y reiniciar el container (`docker restart solar-monitor-grafana-1`).

---

## Paso 9: Deploy

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

## Paso 10: Verificar cada servicio

```bash
# TimescaleDB
docker compose exec timescaledb pg_isready -U solar
# Debe responder: accepting connections

# siser-reader logs
docker compose logs siser-reader
# Debe mostrar: "[INFO] T=XX.XC MPPT1: V=0.0V ..." cada ~6 segundos

# Grafana
curl -I http://localhost:3000
# Debe responder: HTTP/1.1 302 Found

# Verificar datos en DB
docker compose exec timescaledb psql -U solar solar_monitor -c \
  "SELECT time, status, pac, ppv_total FROM realtime WHERE is_stale=false ORDER BY time DESC LIMIT 5"
```

---

## Paso 11: Configurar acceso remoto (ngrok + nginx)

Ver instrucciones completas en `15_TUNEL_REMOTO.md`.

```bash
# Instalar ngrok
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc > /dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok
ngrok config add-authtoken <TOKEN>

# Instalar nginx
sudo apt-get install -y nginx apache2-utils
sudo htpasswd -cb /etc/nginx/.htpasswd lautaro lsistem19

# Configurar nginx (ver 15_TUNEL_REMOTO.md)
sudo nginx -t && sudo systemctl reload nginx

# Iniciar ngrok
nohup ngrok http 8080 --log=stdout > /home/lautaro/ngrok.log 2>&1 &
```

---

## Comandos Útiles

```bash
# Ver estado de todos los servicios
docker compose ps

# Ver logs de un servicio específico
docker compose logs -f siser-reader
docker compose logs -f timescaledb
docker compose logs -f grafana

# Reiniciar un servicio
docker restart solar-monitor-siser-reader-1
docker restart solar-monitor-grafana-1

# Reiniciar todo
docker compose down && docker compose up -d

# Reconstruir siser-reader (después de cambios en código)
docker compose build siser-reader
docker compose up -d siser-reader

# Backup de la base de datos
docker exec solar-monitor-timescaledb-1 pg_dump -U solar solar_monitor | gzip > \
  /opt/solar-monitor/backups/solar_monitor_$(date +%Y%m%d).sql.gz

# Restaurar backup
gunzip -c /opt/solar-monitor/backups/solar_monitor_YYYYMMDD.sql.gz | \
  docker exec -i solar-monitor-timescaledb-1 psql -U solar solar_monitor

# Verificar espacio en disco
df -h /

# Verificar adaptador USB-RS232
ls -la /dev/inverter-serial

# Ver consumo de recursos
docker stats
```

---

## Cron: Backup diario

```bash
# Agregar al crontab de root
sudo crontab -e

# Backup diario a las 02:00
0 2 * * * docker exec solar-monitor-timescaledb-1 pg_dump -U solar solar_monitor | gzip > /opt/solar-monitor/backups/solar_monitor_$(date +\%Y\%m\%d).sql.gz

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
gunzip -c /opt/solar-monitor/backups/solar_monitor_YYYYMMDD.sql.gz | \
  docker exec -i solar-monitor-timescaledb-1 psql -U solar solar_monitor

# Volver a la versión anterior de imágenes
docker compose up -d
```

---

## Monitoreo Post-Deploy (primeras 24 horas)

Verificar cada hora durante las primeras 24 horas:

- [ ] `docker compose ps` — todos los servicios "Up"
- [ ] `docker compose logs siser-reader | tail -20` — lecturas exitosas (status=1 de día)
- [ ] `docker compose logs timescaledb | tail -10` — sin errores
- [ ] Abrir Grafana → verificar datos en dashboard de tiempo real
- [ ] Verificar que `is_stale=true` aparece de noche (inversor sin sol)
- [ ] Verificar que los backups diarios se están ejecutando