# Testing de Consultas y Operación

> **ESTADO: COMPLETADO** — Los tests de consultas SQL han sido verificados. El sistema está en producción con datos reales. Las consultas Modbus RTU en este documento son legacy (reemplazadas por SISER).

## Objetivo

Verificar que cada componente del sistema funciona correctamente de forma individual e integrada: comunicación Modbus, escritura en base de datos, consultas SQL, dashboards Grafana, y flujo de datos extremo a extremo.

---

## Categorías de Tests

| Categoría | Qué verifica | Cuándo ejecutar |
|---|---|---|
| Modbus RTU | Comunicación con el inversor | Post-deploy, después de cambios en register_map |
| Base de datos | Esquema, inserts, aggregates, retención | Post-deploy, después de cambios en init.sql |
| Consultas SQL | Queries que usa Grafana en dashboards | Post-deploy, después de cambios en dashboards |
| Flujo E2E | Datos desde inversor hasta dashboard | Post-deploy, semanalmente |
| Operación | Health checks, backups, reconexión | Diariamente, después de reinicios |
| Rendimiento | Latencia, throughput, almacenamiento | Mensualmente, después de cambios |

---

## 1. Tests de Comunicación Modbus RTU

### 1.1 Conexión básica

```bash
# Verificar que el adaptador USB-RS485 está detectado
ls -la /dev/inverter-serial
# Esperado: enlace simbólico a /dev/inverter-serial

# Verificar permisos
stat -c "%a %U %G" /dev/inverter-serial
# Esperado: 666 root dialout (o similar con acceso lectura/escritura)

# Verificar que no hay otro proceso usando el puerto
fuser /dev/inverter-serial
# Esperado: sin salida (puerto libre)
```

### 1.2 Lectura de registros (con mbpoll)

```bash
# Instalar mbpoll si no está
sudo apt-get install -y mbpoll

# Test de lectura: registro 0x101C (temperatura), 1 registro, slave 16
mbpoll -a 1 -b 9600 -p none -t 3 -r 0x101C -c 1 /dev/inverter-serial
# Esperado: valor numérico (ej: 42 = 42°C) sin error de timeout

# Test de lectura: registro 0x1037 (potencia AC), 2 registros, slave 16
mbpoll -a 1 -b 9600 -p none -t 3 -r 0x1037 -c 2 /dev/inverter-serial
# Esperado: 2 valores (32-bit, little-endian)

# Test de lectura: registro 0x1005 (estado), 1 registro, slave 16
mbpoll -a 1 -b 9600 -p none -t 3 -r 0x1005 -c 1 /dev/inverter-serial
# Esperado: 0 (off), 1 (ok), 2 (fault), 3 (standby)
```

### 1.3 Unlock del protocolo

```bash
# Escribir contraseña 0x000000 en registros 0x003C-0x003D para desbloquear
mbpoll -a 1 -b 9600 -p none -t 6 -r 0x003C /dev/inverter-serial 0
# Esperado: respuesta sin error

# Verificar que ahora se pueden leer registros de datos
mbpoll -a 1 -b 9600 -p none -t 3 -r 0x101C -c 1 /dev/inverter-serial
# Esperado: valor numérico válido (antes del unlock podría dar error o 0)
```

### 1.4 Escaneo sistemático de registros

```bash
# Script Python para escaneo completo
python3 << 'EOF'
from pymodbus.client import ModbusSerialClient

client = ModbusSerialClient('/dev/inverter-serial', baudrate=9600, parity='N',
                            stopbits=1, bytesize=8, timeout=0.5)
client.connect()

# Unlock
client.write_registers(0x003C, [0x0000, 0x0000], slave=1)

# Escanear holding registers 0x0000-0x0200
print("=== Holding Registers FC03 ===")
for block in range(0, 0x0200, 10):
    result = client.read_holding_registers(block, 10, slave=1)
    if not result.isError():
        print(f"  0x{block:04X}-0x{block+9:04X}: {result.registers}")

# Escanear holding registers 0x1000-0x1100 (zona de datos)
print("\n=== Data Zone 0x1000-0x1100 ===")
for block in range(0x1000, 0x1100, 10):
    result = client.read_holding_registers(block, 10, slave=1)
    if not result.isError():
        print(f"  0x{block:04X}-0x{block+9:04X}: {result.registers}")

# Escanear 0xC000-0xC030 (gráfico diario)
print("\n=== Daily Graph 0xC000-0xC030 ===")
result = client.read_holding_registers(0xC000, 48, slave=1)
if not result.isError():
    print(f"  0xC000-0xC02F: {result.registers}")

client.close()
EOF
```

### 1.5 Reconexión USB

```bash
# Test de reconexión automática del daemon
# 1. Verificar que el daemon está corriendo
docker compose logs modbus-reader | tail -5
# Esperado: "Connected to /dev/inverter-serial" o "Reading data..."

# 2. Desconectar el adaptador USB físicamente
# 3. Esperar 10 segundos
# 4. Verificar logs
docker compose logs modbus-reader | tail -20
# Esperado: "USB disconnected, reconnecting..." → backoff → "Connected to /dev/inverter-serial"

# 5. Reconectar el adaptador USB
# 6. Esperar 30 segundos
# 7. Verificar que el daemon recuperó la conexión
docker compose logs modbus-reader | tail -5
# Esperado: "Connected to /dev/inverter-serial" y lecturas exitosas

# 8. Verificar que el health check vuelve a "ok"
cat /tmp/modbus-reader-health.json
# Esperado: "modbus_connected": true
```

---

## 2. Tests de Base de Datos

### 2.1 Verificar esquema

```bash
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
"
# Esperado: realtime, fast_samples, slow_samples, hourly_energy, daily_energy,
#           cumulatives, daily_production, events
```

### 2.2 Verificar hypertables

```bash
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables;
"
# Esperado: realtime, fast_samples, cumulatives, daily_production como hypertables
```

### 2.3 Verificar continuous aggregates

```bash
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT view_name, materialization_hypertable_name
FROM timescaledb_information.continuous_aggregates;
"
# Esperado: slow_samples, hourly_energy, daily_energy
```

### 2.4 Verificar retención y compresión

```bash
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT hypertable_name, policy_name, schedule_interval
FROM timescaledb_information.jobs
WHERE proc_name LIKE '%policy%';
"
# Esperado: retention policies para realtime (7d), fast_samples (90d)
#           compression policies para realtime (3d), fast_samples (30d)
```

### 2.5 Insert de prueba

```bash
# Insertar datos de prueba
docker compose exec timescaledb psql -U solar solar_monitor -c "
INSERT INTO realtime (time, inverter_id, vpv, ipv, vac, iac, pac, fac, temp, status, grid_status)
VALUES (NOW(), 1, 340.5, 8.2, 220.1, 14.5, 2800.0, 50.01, 42.3, 1, 0);
"

# Verificar que se insertó
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT * FROM realtime ORDER BY time DESC LIMIT 1;
"
# Esperado: 1 fila con los valores insertados

# Insertar en fast_samples
docker compose exec timescaledb psql -U solar solar_monitor -c "
INSERT INTO fast_samples (time, inverter_id, vpv, ipv, vac, iac, pac, fac, temp, status, grid_status)
VALUES (NOW(), 1, 340.5, 8.2, 220.1, 14.5, 2800.0, 50.01, 42.3, 1, 0);
"

# Verificar
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT * FROM fast_samples ORDER BY time DESC LIMIT 1;
"
```

### 2.6 Verificar continuous aggregates con datos de prueba

```bash
# Esperar 15 minutos a que el continuous aggregate se actualice, o forzar:
docker compose exec timescaledb psql -U solar solar_monitor -c "
CALL refresh_continuous_aggregate('slow_samples', NOW() - INTERVAL '1 hour', NOW());
"

# Verificar slow_samples
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT * FROM slow_samples ORDER BY time DESC LIMIT 5;
"
# Esperado: filas con promedios calculados
```

### 2.7 Verificar usuario grafana_reader

```bash
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT usename, usesuper FROM pg_user WHERE usename = 'grafana_reader';
"
# Esperado: grafana_reader | f (no superuser)

# Verificar permisos de lectura
docker compose exec timescaledb psql -U grafana_reader -d solar_monitor -c "
SELECT COUNT(*) FROM realtime;
"
# Esperado: conteo numérico sin error de permisos
```

---

## 3. Tests de Consultas SQL (Grafana)

### 3.1 Dashboard Tiempo Real

```bash
# Última lectura
docker compose exec timescaledb psql -U grafana_reader -d solar_monitor -c "
SELECT pac, temp, status, grid_status FROM realtime WHERE inverter_id=1 ORDER BY time DESC LIMIT 1;
"

# Potencia AC últimas 24 horas
docker compose exec timescaledb psql -U grafana_reader -d solar_monitor -c "
SELECT time_bucket('1 minute', time) AS bucket, AVG(pac)
FROM fast_samples
WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=1
GROUP BY bucket ORDER BY bucket LIMIT 5;
"

# Voltaje y corriente DC
docker compose exec timescaledb psql -U grafana_reader -d solar_monitor -c "
SELECT time_bucket('1 minute', time) AS bucket, AVG(vpv), AVG(ipv)
FROM fast_samples
WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=1
GROUP BY bucket ORDER BY bucket LIMIT 5;
"
```

### 3.2 Dashboard Histórico

```bash
# Energía diaria último mes
docker compose exec timescaledb psql -U grafana_reader -d solar_monitor -c "
SELECT bucket, avg_power_w, peak_power_w
FROM daily_energy
WHERE bucket > NOW() - INTERVAL '30 days' AND inverter_id=1
ORDER BY bucket LIMIT 5;
"

# Energía mensual
docker compose exec timescaledb psql -U grafana_reader -d solar_monitor -c "
SELECT date_trunc('month', bucket) AS month, SUM(avg_power_w * 1/60) AS energy_kwh
FROM hourly_energy
WHERE bucket > NOW() - INTERVAL '1 year' AND inverter_id=1
GROUP BY month ORDER BY month LIMIT 5;
"
```

### 3.3 Dashboard Diagnóstico

```bash
# Última lectura exitosa (debe ser < 30 segundos)
docker compose exec timescaledb psql -U grafana_reader -d solar_monitor -c "
SELECT time, EXTRACT(EPOCH FROM (NOW() - time)) AS seconds_ago
FROM realtime WHERE inverter_id=1 ORDER BY time DESC LIMIT 1;
"
# Esperado: seconds_ago < 30

# Errores de comunicación últimas 24 horas
docker compose exec timescaledb psql -U grafana_reader -d solar_monitor -c "
SELECT time_bucket('1 hour', time) AS bucket, COUNT(*)
FROM events
WHERE event_type='modbus_error' AND time > NOW() - INTERVAL '24 hours'
GROUP BY bucket ORDER BY bucket;
"
```

### 3.4 Dashboard Académico

```bash
# Horas de sol equivalentes últimos 30 días
docker compose exec timescaledb psql -U grafana_reader -d solar_monitor -c "
SELECT date_trunc('day', time) AS day, SUM(pac) / 4000.0 AS peak_hours
FROM fast_samples
WHERE time > NOW() - INTERVAL '30 days' AND pac > 0 AND inverter_id=1
GROUP BY day ORDER BY day LIMIT 5;
"

# CO2 evitado acumulado
docker compose exec timescaledb psql -U grafana_reader -d solar_monitor -c "
SELECT time_bucket('1 day', time) AS bucket, MAX(co2_saved)
FROM cumulatives
WHERE time > NOW() - INTERVAL '1 year' AND inverter_id=1
GROUP BY bucket ORDER BY bucket LIMIT 5;
"
```

---

## 4. Tests de Flujo E2E (Extremo a Extremo)

### 4.1 Datos desde inversor hasta Grafana

```bash
# 1. Verificar que el daemon está corriendo
docker compose ps modbus-reader
# Esperado: Up

# 2. Verificar datos en realtime
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT time, pac, temp, status FROM realtime ORDER BY time DESC LIMIT 1;
"
# Esperado: fila reciente (< 10 segundos)

# 3. Verificar datos en fast_samples (esperar 1 minuto)
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT COUNT(*) FROM fast_samples WHERE time > NOW() - INTERVAL '2 minutes';
"
# Esperado: 1-2 filas (daemon escribe cada 60 segundos)

# 4. Verificar datos en cumulatives
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT time, energy_total, energy_daily FROM cumulatives ORDER BY time DESC LIMIT 1;
"
# Esperado: fila reciente

# 5. Verificar desde Grafana
curl -s http://localhost:3000/api/datasources/proxy/1/api/v1/query \
  -u admin:$(grep GRAFANA_PASSWORD /opt/solar-monitor/.env | cut -d= -f2) \
  -d 'query=SELECT pac FROM realtime ORDER BY time DESC LIMIT 1'
# Esperado: JSON con datos
```

### 4.2 Verificar latencia de datos

```bash
# Medir latencia entre lectura del inversor y visualización en DB
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT EXTRACT(EPOCH FROM (NOW() - time)) AS latency_seconds
FROM realtime WHERE inverter_id=1 ORDER BY time DESC LIMIT 1;
"
# Esperado: < 10 segundos
```

### 4.3 Verificar continuous aggregates automáticos

```bash
# Verificar que los jobs de continuous aggregate están corriendo
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT job_id, application_name, schedule_interval, max_runtime
FROM timescaledb_information.jobs
WHERE proc_name LIKE '%refresh%';
"
# Esperado: 3 jobs (slow_samples, hourly_energy, daily_energy)

# Verificar última ejecución
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT job_id, last_start, last_finish, last_run_duration
FROM timescaledb_information.job_stats
WHERE job_id IN (
  SELECT job_id FROM timescaledb_information.jobs
  WHERE proc_name LIKE '%refresh%'
);
"
```

---

## 5. Tests de Operación

### 5.1 Health check del daemon

```bash
# Verificar archivo de health check
cat /tmp/modbus-reader-health.json
# Esperado:
# {
#   "status": "ok",
#   "last_reading": "<timestamp reciente>",
#   "modbus_connected": true,
#   "db_connected": true,
#   "readings_total": <número creciente>,
#   "errors_total": <número bajo>,
#   "buffer_size": 0,
#   "uptime_seconds": <número creciente>
# }
```

### 5.2 Health check de TimescaleDB

```bash
# Verificar que la base de datos está accesible
docker compose exec timescaledb pg_isready -U solar
# Esperado: accepting connections

# Verificar espacio usado
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT pg_size_pretty(pg_database_size('solar_monitor')) AS db_size;
"
# Esperado: < 100 MB inicialmente, creciendo ~2-3 MB/día

# Verificar que no hay locks
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT COUNT(*) AS active_locks FROM pg_locks WHERE NOT granted;
"
# Esperado: 0
```

### 5.3 Health check de Grafana

```bash
# Verificar que Grafana responde
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/api/health
# Esperado: 200

# Verificar datasource
curl -s http://localhost:3000/api/datasources/proxy/1/api/v1/query \
  -u admin:$(grep GRAFANA_PASSWORD /opt/solar-monitor/.env | cut -d= -f2) \
  -d 'query=SELECT 1' 2>/dev/null | head -c 100
# Esperado: JSON con datos
```

### 5.4 Health check de acceso remoto (ngrok + nginx)

```bash
# Verificar que ngrok está corriendo
curl -s http://localhost:4040/api/tunnels | head -50
# Esperado: JSON con URL pública del tunnel

# Verificar acceso remoto
curl -s -o /dev/null -w "%{http_code}" https://XXXX.ngrok-free.dev
# Esperado: 200 (o 302 redirect)
```

### 5.5 Backup y restore

```bash
# Crear backup manual
docker compose exec -T timescaledb pg_dump -U solar solar_monitor | gzip > /tmp/test_backup.sql.gz

# Verificar tamaño del backup
ls -lh /tmp/test_backup.sql.gz
# Esperado: < 10 MB inicialmente

# Verificar integridad del backup (sin restaurar)
gunzip -c /tmp/test_backup.sql.gz | head -50
# Esperado: encabezado de pg_dump

# Limpiar backup de test
rm /tmp/test_backup.sql.gz
```

### 5.6 Reinicio de servicios

```bash
# Reiniciar cada servicio individualmente y verificar que vuelve a funcionar

# Reiniciar modbus-reader
docker compose restart modbus-reader
sleep 10
docker compose logs modbus-reader | tail -5
# Esperado: "Connected to /dev/inverter-serial" y lecturas exitosas

# Reiniciar TimescaleDB
docker compose restart timescaledb
sleep 15
docker compose exec timescaledb pg_isready -U solar
# Esperado: accepting connections

# Reiniciar Grafana
docker compose restart grafana
sleep 10
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/api/health
# Esperado: 200

# Reiniciar todo el stack
docker compose down && docker compose up -d
sleep 30
docker compose ps
# Esperado: todos los servicios "Up"
```

---

## 6. Tests de Rendimiento

### 6.1 Throughput de inserts

```bash
# Medir velocidad de inserts en TimescaleDB
docker compose exec timescaledb psql -U solar solar_monitor -c "
INSERT INTO fast_samples (time, inverter_id, vpv, ipv, vac, iac, pac, fac, temp, status, grid_status)
SELECT NOW() - (generate_series || ' seconds')::interval,
       1, 340.5, 8.2, 220.1, 14.5, 2800.0, 50.01, 42.3, 1, 0
FROM generate_series(1, 10000);
"
# Esperado: < 2 segundos para 10,000 inserts

# Verificar
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT COUNT(*) FROM fast_samples;
"
# Limpiar datos de test
docker compose exec timescaledb psql -U solar solar_monitor -c "
DELETE FROM fast_samples WHERE inverter_id=1 AND time > NOW() - INTERVAL '1 minute';
"
```

### 6.2 Latencia de consultas

```bash
# Medir latencia de query de tiempo real
docker compose exec timescaledb psql -U solar solar_monitor -c "
EXPLAIN ANALYZE
SELECT * FROM realtime WHERE inverter_id=1 ORDER BY time DESC LIMIT 1;
"
# Esperado: < 1 ms execution time

# Medir latencia de query de histórico
docker compose exec timescaledb psql -U solar solar_monitor -c "
EXPLAIN ANALYZE
SELECT time_bucket('1 minute', time) AS bucket, AVG(pac)
FROM fast_samples
WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=1
GROUP BY bucket ORDER BY bucket;
"
# Esperado: < 50 ms execution time con datos de prueba

# Medir latencia de continuous aggregate
docker compose exec timescaledb psql -U solar solar_monitor -c "
EXPLAIN ANALYZE
SELECT * FROM slow_samples WHERE time > NOW() - INTERVAL '30 days' LIMIT 100;
"
# Esperado: < 100 ms
```

### 6.3 Uso de recursos

```bash
# Verificar consumo de recursos de los containers
docker stats --no-stream
# Esperado:
#   modbus-reader: CPU < 1%, RAM < 50 MB
#   timescaledb: CPU < 5%, RAM < 200 MB
#   grafana: CPU < 2%, RAM < 100 MB
#   cloudflared: CPU < 1%, RAM < 30 MB

# Verificar espacio en disco
df -h /opt/solar-monitor
# Esperado: > 70% libre

# Verificar tamaño de la base de datos
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT pg_size_pretty(pg_database_size('solar_monitor')) AS total_size;
"
# Esperado: < 1 GB después de 1 semana de operación
```

---

## 7. Tests de Datos

### 7.1 Verificar rangos de valores

```bash
# Verificar que los valores están en rangos esperados
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT
  MIN(vpv) AS min_vpv, MAX(vpv) AS max_vpv,
  MIN(ipv) AS min_ipv, MAX(ipv) AS max_ipv,
  MIN(vac) AS min_vac, MAX(vac) AS max_vac,
  MIN(pac) AS min_pac, MAX(pac) AS max_pac,
  MIN(temp) AS min_temp, MAX(temp) AS max_temp
FROM fast_samples
WHERE time > NOW() - INTERVAL '24 hours';
"
# Rangos esperados (H.P.6065REL-D):
#   vpv: 0-600 V
#   ipv: 0-12 A
#   vac: 207-253 V (220V ± 15%)
#   pac: 0-4600 W
#   temp: -10 a 70 °C
#   fac: 49.5-50.5 Hz
```

### 7.2 Verificar consistencia de datos

```bash
# Verificar que pac ≈ vac * iac (factor de potencia cercano a 1)
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT time, pac, vac * iac AS calculated_va, pac / NULLIF(vac * iac, 0) AS power_factor
FROM fast_samples
WHERE time > NOW() - INTERVAL '1 hour' AND pac > 100 AND inverter_id=1
ORDER BY time DESC LIMIT 10;
"
# Esperado: power_factor entre 0.9 y 1.0 (factor de potencia del inversor)

# Verificar que energy_total es creciente
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT time, energy_total,
       LAG(energy_total) OVER (ORDER BY time) AS prev_energy,
       energy_total - LAG(energy_total) OVER (ORDER BY time) AS delta
FROM cumulatives
WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=1
ORDER BY time DESC LIMIT 10;
"
# Esperado: delta >= 0 (energía total siempre creciente)
```

### 7.3 Verificar ausencia de gaps

```bash
# Buscar gaps > 30 segundos en los datos de realtime
docker compose exec timescaledb psql -U solar solar_monitor -c "
SELECT time, LAG(time) OVER (ORDER BY time) AS prev_time,
       EXTRACT(EPOCH FROM (time - LAG(time) OVER (ORDER BY time))) AS gap_seconds
FROM realtime
WHERE time > NOW() - INTERVAL '1 hour' AND inverter_id=1
ORDER BY time;
"
# Esperado: gap_seconds cercano a 5 segundos, sin gaps > 30 segundos
```

---

## Checklist Post-Deploy

Ejecutar después de cada deploy o cambio importante:

- [ ] Adaptador USB-RS485 detectado: `ls -la /dev/inverter-serial`
- [ ] Daemon modbus-reader conectado: `docker compose logs modbus-reader | tail -5`
- [ ] Datos en tabla realtime: `SELECT * FROM realtime ORDER BY time DESC LIMIT 1`
- [ ] Datos en tabla fast_samples: `SELECT COUNT(*) FROM fast_samples WHERE time > NOW() - INTERVAL '5 minutes'`
- [ ] Daemon health check: `cat /tmp/modbus-reader-health.json`
- [ ] TimescaleDB accesible: `pg_isready -U solar`
- [ ] Hypertables creados: `SELECT * FROM timescaledb_information.hypertables`
- [ ] Continuous aggregates funcionando: `SELECT * FROM slow_samples LIMIT 1`
- [ ] Grafana responde: `curl -s http://localhost:3000/api/health`
- [ ] Dashboard muestra datos en tiempo real
- [ ] Dashboard muestra datos históricos
- [ ] ngrok tunnel activo: `curl -s http://localhost:4040/api/tunnels`
- [ ] Acceso remoto funciona: `curl -I https://XXXX.ngrok-free.dev`
- [ ] Backup manual funciona: `pg_dump | gzip > backup.sql.gz`
- [ ] Docker stats normales: `docker stats --no-stream`
- [ ] Reconexión USB funciona (desconectar/reconectar adaptador)