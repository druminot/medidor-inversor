# Testing de Consultas y Operación

> **ESTADO: COMPLETADO** — Los tests de consultas SQL han sido verificados. El sistema está en producción con datos reales del protocolo SISER. Los tests de Modbus RTU son legacy (reemplazados por SISER). siser-reader escribe en `realtime` con columnas SISER. Las tablas `fast_samples`, `cumulatives` y `daily_production` NO se actualizan (legacy del daemon C).

## Objetivo

Verificar que cada componente del sistema funciona correctamente de forma individual e integrada: comunicación SISER, escritura en base de datos, consultas SQL, dashboards Grafana, y flujo de datos extremo a extremo.

---

## Categorías de Tests

| Categoría | Qué verifica | Cuándo ejecutar |
|---|---|---|
| SISER Protocol | Comunicación con el inversor | Post-deploy, después de cambios en siser_reader.py |
| Base de datos | Esquema, inserts, aggregates, retención | Post-deploy, después de cambios en init.sql |
| Consultas SQL | Queries que usa Grafana en dashboards | Post-deploy, después de cambios en dashboards |
| Flujo E2E | Datos desde inversor hasta dashboard | Post-deploy, semanalmente |
| Operación | Health checks, backups, reconexión | Diariamente, después de reinicios |
| Rendimiento | Latencia, throughput, almacenamiento | Mensualmente, después de cambios |

---

## 1. Tests de Comunicación SISER Protocol

### 1.1 Conexión básica

```bash
# Verificar que el adaptador USB-RS232 está detectado
ls -la /dev/inverter-serial
# Esperado: enlace simbólico a /dev/ttyUSB0 (o ttyUSB1)

# Verificar permisos
stat -c "%a %U %G" /dev/inverter-serial
# Esperado: 666 root dialout (o similar con acceso lectura/escritura)

# Verificar que siser-reader está usando el puerto
docker exec solar-monitor-siser-reader-1 ls -la /dev/inverter-serial
# Esperado: enlace simbólico dentro del container
```

### 1.2 Verificar lecturas SISER

```bash
# Verificar que siser-reader está corriendo y leyendo datos
docker logs solar-monitor-siser-reader-1 --tail 10
# Esperado: líneas como "[INFO] T=27.5C MPPT1: V=0.0V I=0.0A P=0.0W | MPPT2: V=235.5V I=0.7A P=164.8W ..."

# Verificar datos en la base de datos
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c \
  "SELECT time, status, pac, ppv_total, temp FROM realtime WHERE is_stale=false ORDER BY time DESC LIMIT 5;"
# Esperado: filas recientes con status=1 (Normal) de día, status=0 (Wait) de noche
```

### 1.3 Reconexión USB

```bash
# Test de reconexión automática del daemon
# 1. Verificar que siser-reader está corriendo
docker ps | grep siser-reader
# Esperado: Up

# 2. Reiniciar siser-reader
docker restart solar-monitor-siser-reader-1
sleep 15

# 3. Verificar que recuperó la conexión
docker logs solar-monitor-siser-reader-1 --tail 10
# Esperado: "[INFO] Conectado a /dev/inverter-serial" y lecturas exitosas

# 4. Verificar datos frescos
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c \
  "SELECT EXTRACT(EPOCH FROM (NOW() - time))::int AS seconds_ago FROM realtime WHERE is_stale=false ORDER BY time DESC LIMIT 1;"
# Esperado: < 10 segundos
```

---

## 2. Tests de Base de Datos

### 2.1 Verificar esquema

```bash
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
"
# Esperado: realtime, fast_samples, cumulatives, daily_production, events
```

### 2.2 Verificar columnas SISER en realtime

```bash
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name='realtime' ORDER BY ordinal_position;
"
# Esperado: time, inverter_id, vpv, ipv, vac, iac, pac, fac, temp, status, grid_status,
#           vpv2, vpv3, ipv2, ipv3, vac2, vac3, iac2, iac3, pac2, pac3,
#           energy_total, hours_total, vpv1, ipv1, ppv1, ppv2, ppv3, ppv_total, is_stale
```

### 2.3 Verificar hypertables

```bash
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables;
"
# Esperado: realtime, fast_samples, cumulatives, daily_production como hypertables
```

### 2.4 Verificar datos en realtime (SISER)

```bash
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT time, status, pac, ppv_total, temp, is_stale
FROM realtime WHERE is_stale=false ORDER BY time DESC LIMIT 5;
"
# Esperado: filas recientes con datos SISER (status=1 de día, ppv_total > 0)
```

### 2.5 Verificar continuous aggregates

```bash
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT view_name, materialization_hypertable_name
FROM timescaledb_information.continuous_aggregates;
"
# Esperado: slow_samples, hourly_energy, daily_energy
# NOTA: Estarán vacías porque dependen de fast_samples que no recibe datos de siser-reader
```

### 2.6 Verificar retención y compresión

```bash
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT hypertable_name, policy_name, schedule_interval
FROM timescaledb_information.jobs
WHERE proc_name LIKE '%policy%';
"
# Esperado: retention policies para realtime (7d), fast_samples (90d)
#           compression policies para realtime (3d), fast_samples (30d)
```

### 2.7 Verificar usuario grafana_reader

```bash
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT usename, usesuper FROM pg_user WHERE usename = 'grafana_reader';
"
# Esperado: grafana_reader | f (no superuser)

docker exec solar-monitor-timescaledb-1 psql -U grafana_reader -d solar_monitor -c "
SELECT COUNT(*) FROM realtime;
"
# Esperado: conteo numérico sin error de permisos
```

---

## 3. Tests de Consultas SQL (Grafana)

### 3.1 Dashboard Tiempo Real (usando realtime con is_stale=false)

```bash
# Última lectura real
docker exec solar-monitor-timescaledb-1 psql -U grafana_reader -d solar_monitor -c "
SELECT pac, temp, status, ppv_total, is_stale
FROM realtime WHERE inverter_id=1 AND is_stale=false ORDER BY time DESC LIMIT 1;
"

# Señal de datos (segundos desde última lectura real)
docker exec solar-monitor-timescaledb-1 psql -U grafana_reader -d solar_monitor -c "
SELECT EXTRACT(EPOCH FROM (NOW() - time))::int AS seconds_ago
FROM realtime WHERE inverter_id=1 AND time > NOW() - INTERVAL '5 minutes' AND is_stale=false
ORDER BY time DESC LIMIT 1;
"

# Potencia AC/DC últimas 6 horas
docker exec solar-monitor-timescaledb-1 psql -U grafana_reader -d solar_monitor -c "
SELECT time_bucket('5m', time) AS bucket,
       AVG(COALESCE(pac,0)) as ac, AVG(COALESCE(ppv_total,0)) as dc
FROM realtime WHERE time > NOW() - INTERVAL '6 hours' AND inverter_id=1 AND is_stale=false
GROUP BY bucket ORDER BY bucket LIMIT 5;
"
```

### 3.2 Dashboard Diagnóstico

```bash
# Intervalo entre lecturas
docker exec solar-monitor-timescaledb-1 psql -U grafana_reader -d solar_monitor -c "
SELECT time, EXTRACT(EPOCH FROM (time - LAG(time) OVER (ORDER BY time))) AS interval_sec
FROM realtime WHERE time > NOW() - INTERVAL '1 hour' AND inverter_id=1 AND is_stale=false
ORDER BY time LIMIT 10;
"
# Esperado: interval_sec cercano a 5-6 segundos

# Lecturas reales vs heartbeats
docker exec solar-monitor-timescaledb-1 psql -U grafana_reader -d solar_monitor -c "
SELECT
  (SELECT COUNT(*) FROM realtime WHERE time > NOW() - INTERVAL '1 hour' AND is_stale=false) AS real_readings,
  (SELECT COUNT(*) FROM realtime WHERE time > NOW() - INTERVAL '1 hour' AND is_stale=true) AS heartbeats;
"
```

### 3.3 Dashboard Histórico

```bash
# Energía diaria (usando realtime con time_bucket ya que fast_samples está vacío)
docker exec solar-monitor-timescaledb-1 psql -U grafana_reader -d solar_monitor -c "
SELECT time_bucket('1 day', time) AS day,
       AVG(COALESCE(pac,0)) AS avg_power,
       MAX(COALESCE(pac,0)) AS peak_power
FROM realtime WHERE time > NOW() - INTERVAL '7 days' AND inverter_id=1 AND is_stale=false
GROUP BY day ORDER BY day;
"
```

---

## 4. Tests de Flujo E2E (Extremo a Extremo)

### 4.1 Datos desde inversor hasta Grafana

```bash
# 1. Verificar que siser-reader está corriendo
docker ps | grep siser-reader
# Esperado: Up

# 2. Verificar datos en realtime
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT time, status, pac, ppv_total, temp FROM realtime WHERE is_stale=false ORDER BY time DESC LIMIT 1;
"
# Esperado: fila reciente (< 10 segundos)

# 3. Verificar desde Grafana
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/api/health
# Esperado: 200
```

### 4.2 Verificar latencia de datos

```bash
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT EXTRACT(EPOCH FROM (NOW() - time)) AS latency_seconds
FROM realtime WHERE inverter_id=1 AND is_stale=false ORDER BY time DESC LIMIT 1;
"
# Esperado: < 10 segundos
```

---

## 5. Tests de Operación

### 5.1 Health check de siser-reader

```bash
# Verificar que siser-reader está corriendo y leyendo datos
docker logs solar-monitor-siser-reader-1 --tail 10
# Esperado: líneas con "[INFO]" mostrando lecturas cada ~6 segundos

# Verificar datos frescos
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT EXTRACT(EPOCH FROM (NOW() - time))::int AS seconds_ago, status, pac
FROM realtime WHERE is_stale=false ORDER BY time DESC LIMIT 1;
"
# Esperado: seconds_ago < 10
```

### 5.2 Health check de TimescaleDB

```bash
docker exec solar-monitor-timescaledb-1 pg_isready -U solar
# Esperado: accepting connections

docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT pg_size_pretty(pg_database_size('solar_monitor')) AS db_size;
"
# Esperado: < 100 MB inicialmente, creciendo ~2-3 MB/día

docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT COUNT(*) AS active_locks FROM pg_locks WHERE NOT granted;
"
# Esperado: 0
```

### 5.3 Health check de Grafana

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/api/health
# Esperado: 200
```

### 5.4 Health check de acceso remoto (ngrok + nginx)

```bash
# Verificar que ngrok está corriendo
curl -s http://localhost:4040/api/tunnels | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["tunnels"][0]["public_url"])'
# Esperado: URL pública de ngrok

# Verificar acceso remoto
curl -s -o /dev/null -w "%{http_code}" -H "ngrok-skip-browser-warning: true" https://zoning-heat-groggy.ngrok-free.dev/
# Esperado: 200 (o 302 redirect)
```

### 5.5 Backup y restore

```bash
# Crear backup manual
docker exec solar-monitor-timescaledb-1 pg_dump -U solar solar_monitor | gzip > /tmp/test_backup.sql.gz

# Verificar tamaño del backup
ls -lh /tmp/test_backup.sql.gz
# Esperado: < 50 MB

# Verificar integridad del backup (sin restaurar)
gunzip -c /tmp/test_backup.sql.gz | head -50
# Esperado: encabezado de pg_dump

# Limpiar backup de test
rm /tmp/test_backup.sql.gz
```

### 5.6 Reinicio de servicios

```bash
# Reiniciar siser-reader
docker restart solar-monitor-siser-reader-1
sleep 15
docker logs solar-monitor-siser-reader-1 --tail 5
# Esperado: "[INFO]" con lecturas exitosas

# Reiniciar TimescaleDB
docker restart solar-monitor-timescaledb-1
sleep 15
docker exec solar-monitor-timescaledb-1 pg_isready -U solar
# Esperado: accepting connections

# Reiniciar Grafana
docker restart solar-monitor-grafana-1
sleep 10
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/api/health
# Esperado: 200

# Reiniciar todo el stack
docker compose -f /opt/solar-monitor/docker-compose.yml down && docker compose -f /opt/solar-monitor/docker-compose.yml up -d
sleep 30
docker ps
# Esperado: 3 containers Up (siser-reader, timescaledb, grafana)
```

---

## 6. Tests de Rendimiento

### 6.1 Throughput de inserts

```bash
# Medir velocidad de inserts en TimescaleDB
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
INSERT INTO realtime (time, inverter_id, vpv, ipv, vac, iac, pac, fac, temp, status, grid_status, vpv1, ipv1, ppv1, vpv2, ipv2, ppv2, vpv3, ipv3, ppv3, ppv_total, is_stale)
SELECT NOW() - (generate_series || ' seconds')::interval,
       1, 0, 0, 220.1, 0.7, 150, 50.01, 27.5, 1, 0,
       0, 0, 0, 235.5, 0.7, 164.8, 0, 0, 0, 164.8, false
FROM generate_series(1, 10000);
"
# Esperado: < 2 segundos para 10,000 inserts

# Limpiar datos de test
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
DELETE FROM realtime WHERE inverter_id=1 AND is_stale=false AND time > NOW() - INTERVAL '1 minute' AND pac=150;
"
```

### 6.2 Latencia de consultas

```bash
# Medir latencia de query de tiempo real
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
EXPLAIN ANALYZE
SELECT * FROM realtime WHERE inverter_id=1 AND is_stale=false ORDER BY time DESC LIMIT 1;
"
# Esperado: < 5 ms execution time

# Medir latencia de query con time_bucket
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
EXPLAIN ANALYZE
SELECT time_bucket('5m', time) AS bucket, AVG(COALESCE(pac,0)) as ac
FROM realtime WHERE time > NOW() - INTERVAL '6 hours' AND inverter_id=1 AND is_stale=false
GROUP BY bucket ORDER BY bucket;
"
# Esperado: < 50 ms
```

### 6.3 Uso de recursos

```bash
# Verificar consumo de recursos de los containers
docker stats --no-stream
# Esperado:
#   siser-reader: CPU < 1%, RAM < 50 MB
#   timescaledb: CPU < 5%, RAM < 200 MB
#   grafana: CPU < 2%, RAM < 100 MB

# Verificar espacio en disco
df -h /opt/solar-monitor
# Esperado: > 70% libre

# Verificar tamaño de la base de datos
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT pg_size_pretty(pg_database_size('solar_monitor')) AS total_size;
"
# Esperado: < 1 GB después de 1 semana de operación
```

---

## 7. Tests de Datos

### 7.1 Verificar rangos de valores (SISER)

```bash
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT
  MIN(vpv2) AS min_vpv2, MAX(vpv2) AS max_vpv2,
  MIN(ipv2) AS min_ipv2, MAX(ipv2) AS max_ipv2,
  MIN(vac) AS min_vac, MAX(vac) AS max_vac,
  MIN(pac) AS min_pac, MAX(pac) AS max_pac,
  MIN(temp) AS min_temp, MAX(temp) AS max_temp,
  MIN(fac) AS min_fac, MAX(fac) AS max_fac
FROM realtime WHERE time > NOW() - INTERVAL '24 hours' AND is_stale=false;
"
# Rangos esperados (H.P.6065REL-D, solo MPPT2 con paneles):
#   vpv2: 0-600 V (typical 200-280V de día)
#   ipv2: 0-12 A (typical 0-1A)
#   vac: 207-253 V (220V ± 15%)
#   pac: 0-6000 W (typical 0-300W con 1 string)
#   temp: -10 a 70 °C (typical 25-45°C)
#   fac: 49.5-50.5 Hz
```

### 7.2 Verificar consistencia de datos

```bash
# Verificar que ppv_total ≈ ppv1 + ppv2 + ppv3
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT time, ppv_total, ppv1 + ppv2 + ppv3 AS sum_ppv,
       ppv_total - (ppv1 + ppv2 + ppv3) AS diff
FROM realtime WHERE time > NOW() - INTERVAL '1 hour' AND is_stale=false AND ppv_total > 0
ORDER BY time DESC LIMIT 10;
"
# Esperado: diff cercano a 0 (redondeo de punto flotante)

# Verificar que is_stale=true aparece de noche
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT time_bucket('1 hour', time) AS hour, is_stale, COUNT(*)
FROM realtime WHERE time > NOW() - INTERVAL '24 hours'
GROUP BY hour, is_stale ORDER BY hour, is_stale;
"
# Esperado: is_stale=true en horas nocturnas, is_stale=false de día
```

### 7.3 Verificar ausencia de gaps

```bash
# Buscar gaps > 30 segundos en los datos reales
docker exec solar-monitor-timescaledb-1 psql -U solar solar_monitor -c "
SELECT time, LAG(time) OVER (ORDER BY time) AS prev_time,
       EXTRACT(EPOCH FROM (time - LAG(time) OVER (ORDER BY time))) AS gap_seconds
FROM realtime
WHERE time > NOW() - INTERVAL '1 hour' AND inverter_id=1 AND is_stale=false
ORDER BY time
LIMIT 20;
"
# Esperado: gap_seconds cercano a 5-6 segundos, sin gaps > 30 segundos
```

---

## Checklist Post-Deploy

Ejecutar después de cada deploy o cambio importante:

- [ ] Adaptador USB-RS232 detectado: `ls -la /dev/inverter-serial`
- [ ] siser-reader corriendo: `docker ps | grep siser-reader`
- [ ] Datos en tabla realtime: `SELECT time, status, pac FROM realtime WHERE is_stale=false ORDER BY time DESC LIMIT 1`
- [ ] siser-reader leyendo: `docker logs solar-monitor-siser-reader-1 --tail 10`
- [ ] TimescaleDB accesible: `docker exec solar-monitor-timescaledb-1 pg_isready -U solar`
- [ ] Hypertables creados: `SELECT * FROM timescaledb_information.hypertables`
- [ ] Grafana responde: `curl -s http://localhost:3000/api/health`
- [ ] Dashboard muestra datos en tiempo real (verificar en navegador)
- [ ] ngrok tunnel activo: `curl -s http://localhost:4040/api/tunnels`
- [ ] Acceso remoto funciona: `curl -sI -H "ngrok-skip-browser-warning: true" https://zoning-heat-groggy.ngrok-free.dev/`
- [ ] Backup manual funciona: `docker exec solar-monitor-timescaledb-1 pg_dump -U solar solar_monitor | gzip > backup.sql.gz`
- [ ] Docker stats normales: `docker stats --no-stream`
- [ ] Reconexión USB funciona (desconectar/reconectar adaptador)