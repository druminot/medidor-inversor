# Database — TimescaleDB

> **ESTADO: OPERATIVO** — La base de datos está en producción con ~28K filas en `realtime`. siser-reader escribe en `realtime` con columnas SISER (3 MPPT, trifásico). Las tablas `fast_samples` y `cumulatives` contienen datos legacy del daemon C (no se actualizan). `daily_production` está vacía. Las continuous aggregates dependen de `fast_samples` y también están desactualizadas.

## Objetivo

Base de datos de series temporales para almacenar lecturas del inversor con resolución estratificada (5 seg → 1 min → 15 min), retention policies automáticas, y compression.

---

## Justificación de TimescaleDB

| Opción | Pros | Contras |
|---|---|---|
| **TimescaleDB** | SQL familiar, hypertables, compression automática, continuous aggregates, retención por tabla, soporta 40+ usuarios sin problema | Requiere PostgreSQL |
| InfluxDB | Series temporales nativo, fácil de empezar | InfluxQL limitado, sin JOINs, Flux language complejo, más pesado |
| SQLite | Simple, sin servidor | Sin series temporales nativas, sin compression, no soporta 40 usuarios concurrentes bien |
| Prometheus | Pull model, buen para métricas | No es base de datos general, sin acumulados, difícil exportar CSV |

**Decisión**: TimescaleDB — SQL completo, retención por tabla, compression automática, y Grafana tiene soporte nativo.

---

## Estado de las Tablas (Producción, junio 2026)

| Tabla/Vista | Registros | Origen | Estado |
|---|---|---|---|
| `realtime` | ~28K (activos) | siser-reader | **OPERATIVO** — datos frescos cada ~6 seg |
| `fast_samples` | ~2.9K (legacy) | daemon C (obsoleto) | **LEGACY** — no se actualiza desde junio 13 |
| `cumulatives` | ~2.9K (legacy) | daemon C (obsoleto) | **LEGACY** — no se actualiza desde junio 13 |
| `daily_production` | 0 | sin writer | **VACÍA** |
| `events` | 0 | sin writer | **VACÍA** |
| `slow_samples` | (vacío, depende de fast_samples) | continuous aggregate | **VACÍA** |
| `hourly_energy` | (vacío, depende de fast_samples) | continuous aggregate | **VACÍA** |
| `daily_energy` | (vacío, depende de fast_samples) | continuous aggregate | **VACÍA** |

> **GAP CONOCIDO**: siser-reader solo escribe en `realtime`. Los dashboards de Grafana leen exclusivamente de `realtime` y funcionan correctamente. Las tablas `fast_samples`, `cumulatives` y `daily_production` no se actualizan. Para habilitarlas, se debe agregar lógica de escritura en `siser_reader.py`.

---

## Docker Configuration

```yaml
timescaledb:
  image: timescale/timescaledb:latest-pg16
  volumes:
    - ts_data:/var/lib/postgresql/data
    - ./db/init.sql:/docker-entrypoint-initdb.d/01-schema.sql
    - ./db/init-users.sh:/docker-entrypoint-initdb.d/02-users.sh
  restart: always
  environment:
    - POSTGRES_PASSWORD=${DB_PASSWORD}
    - POSTGRES_DB=solar_monitor
    - POSTGRES_USER=solar
    - GRAFANA_READER_PASSWORD=${GRAFANA_READER_PASSWORD}
  ports:
    - "127.0.0.1:5432:5432"
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U solar"]
    interval: 10s
    timeout: 5s
    retries: 5
```

> Puerto 5432 enlazado a 127.0.0.1 solamente — no accesible desde fuera.

---

## Esquema SQL Completo (`init.sql`)

> **NOTA**: El esquema en producción fue evolucionando. siser-reader agrega columnas SISER via `ALTER TABLE IF NOT EXISTS` al arrancar. Este init.sql refleja el esquema final completo. Las tablas `fast_samples`, `cumulatives`, `daily_production` y `events` tienen el esquema original del daemon C (legacy).

```sql
-- ============================================
-- Solar Monitor - TimescaleDB Schema
-- Universidad de Concepción - Laboratorio
-- ============================================
-- ACTUALIZADO: Esquema SISER (3 MPPT) con columnas extendidas
-- El siser-reader agrega columnas via ALTER TABLE IF NOT EXISTS al arrancar.
-- Este init.sql refleja el esquema final completo.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================
-- Tabla de tiempo real (5 segundos, retención 7 días)
-- Columnas SISER (3 MPPT) + columnas legacy Modbus
-- ============================================
CREATE TABLE realtime (
    time        TIMESTAMPTZ NOT NULL,
    inverter_id SMALLINT    NOT NULL DEFAULT 1,
    -- Columnas legacy (compatibilidad con dashboards)
    vpv         REAL,
    ipv         REAL,
    vac         REAL,
    iac         REAL,
    pac         REAL,
    fac         REAL,
    temp        REAL,
    status      SMALLINT,
    grid_status SMALLINT,
    -- Columnas SISER (3 MPPT DC + AC monofásico redundante L1/L2/L3)
    -- El H.P.6065REL-D es monofásico AC; los offsets L2/L3 del protocolo
    -- SENTR 3/3 trifásico se conservan pero contienen el mismo valor que L1.
    vpv2        REAL,
    vpv3        REAL,
    ipv2        REAL,
    ipv3        REAL,
    vac2        REAL,
    vac3        REAL,
    iac2        REAL,
    iac3        REAL,
    pac2        REAL,
    pac3        REAL,
    energy_total REAL,
    hours_total  REAL,
    vpv1        REAL,
    ipv1        REAL,
    ppv1        REAL,
    ppv2        REAL,
    ppv3        REAL,
    ppv_total   REAL,
    is_stale    BOOLEAN    DEFAULT false
);

SELECT create_hypertable('realtime', 'time', chunk_time_interval => INTERVAL '1 day');
SELECT add_retention_policy('realtime', INTERVAL '30 days');
ALTER TABLE realtime SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'inverter_id'
);
SELECT add_compression_policy('realtime', INTERVAL '3 days');

-- ============================================
-- Tabla de muestras rápidas (1 minuto, retención 90 días)
-- LEGACY: siser-reader no escribe aquí. Contiene datos del daemon C.
-- ============================================
CREATE TABLE fast_samples (
    time        TIMESTAMPTZ NOT NULL,
    inverter_id SMALLINT    NOT NULL DEFAULT 1,
    vpv         REAL,
    ipv         REAL,
    vac         REAL,
    iac         REAL,
    pac         REAL,
    fac         REAL,
    temp        REAL,
    status      SMALLINT,
    grid_status SMALLINT
);

SELECT create_hypertable('fast_samples', 'time', chunk_time_interval => INTERVAL '7 days');
SELECT add_retention_policy('fast_samples', INTERVAL '90 days');
ALTER TABLE fast_samples SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'inverter_id'
);
SELECT add_compression_policy('fast_samples', INTERVAL '30 days');

-- ============================================
-- Tabla de gráfico diario (48 puntos por día, 1x por día)
-- VACÍA: siser-reader no escribe aquí.
-- ============================================
CREATE TABLE daily_production (
    time        TIMESTAMPTZ NOT NULL,
    inverter_id SMALLINT    NOT NULL DEFAULT 1,
    hour_slot   SMALLINT    NOT NULL,
    power_w     REAL
);

SELECT create_hypertable('daily_production', 'time', chunk_time_interval => INTERVAL '30 days');
SELECT add_retention_policy('daily_production', INTERVAL '5 years');

-- ============================================
-- Tabla de acumulados (1 minuto, retención permanente)
-- LEGACY: siser-reader no escribe aquí. Contiene datos del daemon C.
-- ============================================
CREATE TABLE cumulatives (
    time            TIMESTAMPTZ NOT NULL,
    inverter_id     SMALLINT    NOT NULL DEFAULT 1,
    energy_total    REAL,
    energy_daily    REAL,
    hours_total     REAL,
    co2_saved       REAL
);

SELECT create_hypertable('cumulatives', 'time', chunk_time_interval => INTERVAL '30 days');

-- ============================================
-- Tabla de eventos y alarmas (permanente)
-- VACÍA: siser-reader no escribe aquí.
-- ============================================
CREATE TABLE events (
    id            BIGSERIAL,
    time          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    inverter_id   SMALLINT    NOT NULL DEFAULT 1,
    event_type    TEXT NOT NULL,
    event_value   TEXT,
    severity      SMALLINT DEFAULT 0
);

CREATE INDEX idx_events_time ON events (time DESC);
CREATE INDEX idx_events_severity ON events (severity, time DESC);

-- severity: 0=info, 1=warning, 2=critical
-- event_type: 'status_change', 'alarm', 'connection', 'grid', 'siser_error'

-- ============================================
-- Continuous Aggregates (dependen de fast_samples)
-- NOTA: Como fast_samples no recibe datos frescos, estos aggregates están vacíos.
-- Los dashboards leen directamente de realtime con time_bucket().
-- ============================================

CREATE MATERIALIZED VIEW slow_samples
WITH (timescaledb.continuous) AS
SELECT time_bucket('15 minutes', time) AS time,
       inverter_id,
       AVG(vpv)  AS vpv_avg,  AVG(ipv)  AS ipv_avg,
       AVG(vac)  AS vac_avg,  AVG(iac)  AS iac_avg,
       AVG(pac)  AS pac_avg,  MAX(pac)  AS pac_max,  MIN(pac)  AS pac_min,
       AVG(fac)  AS fac_avg,
       AVG(temp) AS temp_avg, MAX(temp) AS temp_max
FROM fast_samples
GROUP BY time_bucket('15 minutes', time), inverter_id;

SELECT add_continuous_aggregate_policy('slow_samples',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '15 minutes');

SELECT add_retention_policy('slow_samples', INTERVAL '5 years');

CREATE MATERIALIZED VIEW hourly_energy
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 hour', time) AS bucket,
       inverter_id,
       AVG(pac)   AS avg_power_w,
       MAX(pac)   AS peak_power_w,
       MIN(pac)   AS min_power_w,
       AVG(temp)  AS avg_temp_c
FROM fast_samples
GROUP BY time_bucket('1 hour', time), inverter_id;

SELECT add_continuous_aggregate_policy('hourly_energy',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

CREATE MATERIALIZED VIEW daily_energy
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 day', time) AS bucket,
       inverter_id,
       AVG(pac)   AS avg_power_w,
       MAX(pac)   AS peak_power_w,
       MIN(pac)   AS min_power_w,
       AVG(temp)  AS avg_temp_c,
       AVG(vpv)   AS avg_vpv_v,
       AVG(ipv)   AS avg_ipv_a
FROM fast_samples
GROUP BY time_bucket('1 day', time), inverter_id;

SELECT add_continuous_aggregate_policy('daily_energy',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day');

-- ============================================
-- Índices adicionales
-- ============================================
CREATE INDEX idx_realtime_time ON realtime (time DESC);
CREATE INDEX idx_fast_samples_time ON fast_samples (time DESC);
CREATE INDEX idx_cumulatives_time ON cumulatives (time DESC);
CREATE INDEX idx_daily_production_time ON daily_production (time DESC);
```

---

## Script de usuarios (`db/init-users.sh`)

Los passwords se crean desde variables de entorno, nunca hardcodeados en SQL:

```bash
#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<-EOSQL
    -- Usuario para Grafana (solo lectura)
    CREATE ROLE grafana_reader WITH PASSWORD '$GRAFANA_READER_PASSWORD' LOGIN;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_reader;
    GRANT SELECT ON slow_samples TO grafana_reader;
    GRANT SELECT ON hourly_energy TO grafana_reader;
    GRANT SELECT ON daily_energy TO grafana_reader;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_reader;
EOSQL
```

> `GRAFANA_READER_PASSWORD` se define en `.env` y Docker lo pasa al container de timescaledb via `environment`.

---

## Columnas de la Tabla `realtime` (Esquema Actual en Producción)

| Columna | Tipo | Origen | Descripción |
|---|---|---|---|
| `time` | TIMESTAMPTZ | siser-reader | Timestamp UTC |
| `inverter_id` | SMALLINT | siser-reader | Siempre 1 |
| `vpv` | REAL | SISER readMichele | Voltaje PV MPPT2 (columna legacy, = vpv2) |
| `ipv` | REAL | SISER readMichele | Corriente PV MPPT2 (columna legacy, = ipv2) |
| `vac` | REAL | SISER readMichele | Voltaje AC L1 (grid) |
| `iac` | REAL | SISER readMichele | Corriente AC L1 (grid) |
| `pac` | REAL | SISER readMichele | Potencia AC L1 (grid) |
| `fac` | REAL | SISER readMichele | Frecuencia AC (Hz) |
| `temp` | REAL | SISER readMichele | Temperatura inversor (°C) |
| `status` | SMALLINT | SISER readMichele | 0=Wait, 1=Normal, 2=Fault, 3=Perm Fault |
| `grid_status` | SMALLINT | SISER readMichele | Estado de la red eléctrica |
| `vpv1` | REAL | SISER readMichele | Voltaje PV MPPT1 (0V, sin paneles) |
| `ipv1` | REAL | SISER readMichele | Corriente PV MPPT1 (0A, sin paneles) |
| `ppv1` | REAL | SISER readMichele | Potencia PV MPPT1 (0W) |
| `vpv2` | REAL | SISER readMichele | Voltaje PV MPPT2 (~230V, con paneles) |
| `ipv2` | REAL | SISER readMichele | Corriente PV MPPT2 (~0.6A) |
| `ppv2` | REAL | SISER readMichele | Potencia PV MPPT2 |
| `vpv3` | REAL | SISER readMichele | Voltaje PV MPPT3 (0V, sin paneles) |
| `ipv3` | REAL | SISER readMichele | Corriente PV MPPT3 (0A) |
| `ppv3` | REAL | SISER readMichele | Potencia PV MPPT3 (0W) |
| `ppv_total` | REAL | SISER readMichele | Potencia DC total (suma 3 MPPT) |
| `vac2` | REAL | SISER readMichele | Voltaje AC (L2 copy, redundante del monofásico) |
| `vac3` | REAL | SISER readMichele | Voltaje AC (L3 copy, redundante del monofásico) |
| `iac2` | REAL | SISER readMichele | Corriente AC (L2 copy, redundante) |
| `iac3` | REAL | SISER readMichele | Corriente AC (L3 copy, redundante) |
| `pac2` | REAL | SISER readMichele | Potencia AC (L2 copy, redundante) |
| `pac3` | REAL | SISER readMichele | Potencia AC (L3 copy, redundante) |
| `energy_total` | REAL | SISER readMichele | Energía total acumulada (Wh) |
| `hours_total` | REAL | SISER readMichele | Horas de operación total |
| `is_stale` | BOOLEAN | siser-reader | true si heartbeat sin datos reales |

> **Nota**: Solo MPPT2 tiene paneles conectados. MPPT1 y MPPT3 muestran 0V/0A/0W. Las columnas `vpv`/`ipv` son legacy del daemon C y se mapean a MPPT2.

---

## Estimación de Almacenamiento

| Tabla/Vista | Registros/día | Tamaño/día (raw) | Tamaño/día (compressed) | Retención |
|---|---|---|---|---|
| realtime | ~17,280 | ~2 MB | ~0.5 MB | 7 días |
| fast_samples | ~1,440 (legacy) | — | — | 90 días |
| slow_samples (aggregate) | ~96 (vacío) | — | — | 5 años |
| hourly_energy (aggregate) | ~24 (vacío) | — | — | sin política |
| daily_energy (aggregate) | ~1 (vacío) | — | — | sin política |
| cumulatives | ~1,440 (legacy) | — | — | Permanente |
| daily_production | 0 | — | — | 5 años |
| events | 0 | — | — | Permanente |

**Estimación anual**: ~750 MB raw (solo realtime con datos frescos) → ~180 MB compressed.

---

## Queries Útiles para Grafana (usadas en dashboards de producción)

Los dashboards de producción consultan directamente `realtime` con `time_bucket()` y `is_stale = false`:

```sql
-- Último valor de cada variable (tiempo real)
SELECT * FROM realtime WHERE inverter_id=1 AND time > NOW() - INTERVAL '5 minutes' AND is_stale = false ORDER BY time DESC LIMIT 1;

-- Potencia AC/DC (últimas 6 horas, resolución 5 min)
SELECT $__time(bucket), AVG(COALESCE(pac,0)) as ac, AVG(COALESCE(ppv_total,0)) as dc
FROM (SELECT time_bucket('5m', time) AS bucket, pac, ppv_total FROM realtime
      WHERE $__timeFilter(time) AND inverter_id=1 AND is_stale = false) t
GROUP BY bucket ORDER BY bucket;

-- Voltaje PV por MPPT + Red
SELECT $__time(bucket), AVG(COALESCE(vpv1,0)) as MPPT1, AVG(COALESCE(vpv2,0)) as MPPT2,
       AVG(COALESCE(vpv3,0)) as MPPT3, AVG(COALESCE(vac,0)) as "Red"
FROM (SELECT time_bucket('5m', time) AS bucket, vpv1, vpv2, vpv3, vac FROM realtime
      WHERE $__timeFilter(time) AND inverter_id=1 AND is_stale = false) t
GROUP BY bucket ORDER BY bucket;

-- Corrientes PV + AC
SELECT $__time(bucket), AVG(COALESCE(ipv1,0)) as ipv1, AVG(COALESCE(ipv2,0)) as ipv2,
       AVG(COALESCE(ipv3,0)) as ipv3, AVG(COALESCE(iac,0)) as iac
FROM (SELECT time_bucket('5m', time) AS bucket, ipv1, ipv2, ipv3, iac FROM realtime
      WHERE $__timeFilter(time) AND inverter_id=1 AND is_stale = false) t
GROUP BY bucket ORDER BY bucket;

-- Temperatura
SELECT $__time(bucket), AVG(temp) as temperatura
FROM (SELECT time_bucket('5m', time) AS bucket, temp FROM realtime
      WHERE $__timeFilter(time) AND inverter_id=1 AND is_stale = false) t
GROUP BY bucket ORDER BY bucket;

-- Señal de datos (segundos desde última lectura real)
SELECT EXTRACT(EPOCH FROM (NOW() - time))::int AS seconds_ago
FROM realtime WHERE inverter_id=1 AND time > NOW() - INTERVAL '5 minutes' AND is_stale = false ORDER BY time DESC LIMIT 1;

-- Período del día (Noche/Nublado/Produciendo)
SELECT CASE
  WHEN NOT EXISTS (SELECT 1 FROM realtime WHERE inverter_id=1 AND time > NOW() - INTERVAL '10 minutes' AND is_stale = false) THEN 0
  WHEN EXISTS (SELECT 1 FROM realtime WHERE inverter_id=1 AND time > NOW() - INTERVAL '10 minutes' AND is_stale = false AND status = 1 AND COALESCE(pac,0) > 0) THEN 3
  WHEN EXISTS (SELECT 1 FROM realtime WHERE inverter_id=1 AND time > NOW() - INTERVAL '10 minutes' AND is_stale = false AND (COALESCE(vpv,0) > 0 OR COALESCE(vpv1,0) > 0 OR COALESCE(vpv2,0) > 0 OR COALESCE(vpv3,0) > 0)) THEN 2
  ELSE 1 END AS periodo;
```

> **Nota**: No se usa `COPY ... TO STDOUT` para exportar. Grafana tiene export nativo: botón **Inspect > Data > Download CSV** en cualquier panel.

---

## Funciones PostgreSQL: Amanecer/Atardecer

Definidas en `Proyecto/db/sunrise_functions.sql`:

```sql
-- Amanecer en Concepción (retorna timestamptz UTC)
SELECT sunrise_concepcion(current_date);
-- Ejemplo: 2026-06-18 12:23:24+00 (= 08:23 CLT)

-- Atardecer en Concepción (retorna timestamptz UTC)
SELECT sunset_concepcion(current_date);
-- Ejemplo: 2026-06-18 21:22:18+00 (= 17:22 CLT)

-- Convertir a hora local
SELECT sunrise_concepcion(current_date) AT TIME ZONE 'Chile/Continental';
-- Ejemplo: 2026-06-18 08:23:24.379105

-- Usar en queries de Grafana
SELECT ... FROM realtime
WHERE time >= sunrise_concepcion(current_date)
  AND time <= now()
  AND inverter_id=1 AND is_stale = false;
```

**Algoritmo**: NOAA Solar Calculator con coordenadas -36.8201°S, -73.0455°W, zenith 90.833° (incluye refracción atmosférica).

| Fecha | Amanecer (CLT) | Atardecer (CLT) |
|---|---|---|
| 21 jun (solsticio invierno) | ~08:24 | ~17:22 |
| 21 dic (solsticio verano) | ~06:09 | ~21:30 |
| 20 mar/sep (equinoccios) | ~07:00 | ~19:15 |

---

## Backup y Restore

### Backup diario (cron)

```bash
# /etc/cron.d/solar-monitor-backup
# Backup diario a las 02:00
0 2 * * * root docker exec solar-monitor-timescaledb-1 pg_dump -U solar solar_monitor | gzip > /opt/solar-monitor/backups/solar_monitor_$(date +\%Y\%m\%d).sql.gz
```

### Retención de backups (7 días)

```bash
# /etc/cron.d/solar-monitor-backup-cleanup
0 3 * * * root find /opt/solar-monitor/backups/ -name "*.sql.gz" -mtime +7 -delete
```

### Restore

```bash
# Detener siser-reader (para que no inserte mientras restauramos)
docker stop solar-monitor-siser-reader-1

# Restaurar backup
gunzip -c /opt/solar-monitor/backups/solar_monitor_YYYYMMDD.sql.gz | \
  docker exec -i solar-monitor-timescaledb-1 psql -U solar solar_monitor

# Reiniciar todo
docker compose -f /opt/solar-monitor/docker-compose.yml up -d
```

---

## Migraciones Futuras

Para agregar columnas SISER a tablas existentes (siser-reader ya lo hace automáticamente):

```sql
-- Agregadas por siser_reader.py al arrancar (ALTER TABLE IF NOT EXISTS)
ALTER TABLE realtime ADD COLUMN IF NOT EXISTS vpv1 REAL;
ALTER TABLE realtime ADD COLUMN IF NOT EXISTS ipv1 REAL;
-- ... etc (ver siser_reader.py para lista completa)
```

Para agregar un segundo inversor en el bus RS485:

```sql
-- Los datos del inversor 2 usarán inverter_id = 2
-- Las mismas tablas soportan múltiples inversores
-- Solo hay que agregar el segundo address en siser_reader.py
```

Para agregar sensor adicional (piranómetro, estación meteorológica):

```sql
ALTER TABLE realtime ADD COLUMN irradiance REAL;
ALTER TABLE realtime ADD COLUMN ambient_temp REAL;

ALTER TABLE fast_samples ADD COLUMN irradiance REAL;
ALTER TABLE fast_samples ADD COLUMN ambient_temp REAL;
```