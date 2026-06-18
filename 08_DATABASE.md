# Database — TimescaleDB

> **ESTADO: OPERATIVO** — La base de datos está en producción con ~26K filas en `realtime`. Las tablas `fast_samples`, `cumulatives` y `daily_production` están vacías porque siser-reader aún no escribe en ellas. Las continuous aggregates (`slow_samples`, `hourly_energy`, `daily_energy`) están vacías porque dependen de `fast_samples`.

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

## Docker Configuration

```yaml
timescaledb:
  image: timescale/timescaledb:latest-pg16
  volumes:
    - ts_data:/var/lib/postgresql/data
    - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql
  restart: unless-stopped
  environment:
    - POSTGRES_PASSWORD=${DB_PASSWORD}
    - POSTGRES_DB=solar_monitor
    - POSTGRES_USER=solar
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

```sql
-- ============================================
-- Solar Monitor - TimescaleDB Schema
-- Universidad de Concepción - Laboratorio
-- ============================================

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================
-- Tabla de tiempo real (5 segundos, retención 7 días)
-- ============================================
CREATE TABLE realtime (
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

SELECT create_hypertable('realtime', 'time', chunk_time_interval => INTERVAL '1 day');
SELECT add_retention_policy('realtime', INTERVAL '7 days');
ALTER TABLE realtime SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'inverter_id'
);
SELECT add_compression_policy('realtime', INTERVAL '3 days');

-- ============================================
-- Tabla de muestras rápidas (1 minuto, retención 90 días)
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
-- Registros 0xC000-0xC02F del inversor
-- ============================================
CREATE TABLE daily_production (
    time        TIMESTAMPTZ NOT NULL,
    inverter_id SMALLINT    NOT NULL DEFAULT 1,
    hour_slot   SMALLINT    NOT NULL,  -- 0-47 (cada 30 minutos del día)
    power_w     REAL
);

SELECT create_hypertable('daily_production', 'time', chunk_time_interval => INTERVAL '30 days');
SELECT add_retention_policy('daily_production', INTERVAL '5 years');

-- ============================================
-- Tabla de acumulados (1 minuto, retención permanente)
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
-- event_type: 'status_change', 'alarm', 'connection', 'grid', 'modbus_error'

-- ============================================
-- Continuous Aggregates (generados automáticamente por TimescaleDB)
-- El daemon NO calcula promedios — la DB lo hace desde fast_samples
-- ============================================

-- Muestras lentas (15 minutos, retención 5 años) — reemplaza tabla slow_samples manual
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

-- Energía horaria (promedio y pico de potencia)
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

-- Energía diaria (promedio y pico de potencia)
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
    start_offset => INTERVAL '2 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day');

-- ============================================
-- Usuarios y Permisos
-- ============================================

-- Usuario para el daemon modbus-reader (lectura/escritura)
-- Ya creado por POSTGRES_USER=solar

-- Usuario para Grafana (solo lectura) — creado en db/init-users.sh con password desde env var
-- Ver 06_ARQUITECTURA.md para configuración .env
-- NOTA: NO hardcodear el password aquí. El script init-users.sh lo toma de $GRAFANA_READER_PASSWORD

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

Los passwords de roles secundarios se crean desde variables de entorno, nunca hardcodeados en SQL:

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

## Estimación de Almacenamiento

| Tabla/Vista | Registros/día | Tamaño/día (raw) | Tamaño/día (compressed) | Retención |
|---|---|---|---|---|
| realtime | ~17,280 | ~2 MB | ~0.5 MB | 7 días |
| fast_samples | ~1,440 | ~170 KB | ~50 KB | 90 días |
| slow_samples (aggregate) | ~96 | ~12 KB | automático | 5 años |
| hourly_energy (aggregate) | ~24 | ~3 KB | automático | sin política |
| daily_energy (aggregate) | ~1 | ~200 B | automático | sin política |
| cumulatives | ~1,440 | ~170 KB | ~50 KB | Permanente |
| daily_production | ~48 | ~6 KB | ~2 KB | 5 años |
| events | ~10-50 | ~5 KB | ~2 KB | Permanente |
| **Total** | ~20,330 | **~2.4 MB** | **~0.6 MB** | — |

**Estimación anual**: ~900 MB raw → ~220 MB compressed. Sin problema para un disco de 82 GB.

---

## Queries Útiles para Grafana

```sql
-- Último valor de cada variable (tiempo real) — usado en dashboard Tiempo Real
SELECT * FROM realtime ORDER BY time DESC LIMIT 1;

-- Potencia AC de las últimas 24 horas (resolución 1 minuto) — usado en gráficos
SELECT time_bucket('1 minute', time) AS bucket,
       AVG(pac) AS avg_power_w
FROM fast_samples
WHERE time > NOW() - INTERVAL '24 hours'
GROUP BY bucket ORDER BY bucket;

-- Tendencia de 30 días (desde continuous aggregate slow_samples, 15 min)
SELECT time, pac_avg, pac_max, temp_avg
FROM slow_samples
WHERE time > NOW() - INTERVAL '30 days'
ORDER BY time;

-- Energía diaria del último mes (desde continuous aggregate daily_energy)
SELECT bucket, avg_power_w, peak_power_w, avg_temp_c
FROM daily_energy
WHERE bucket > NOW() - INTERVAL '30 days'
ORDER BY bucket;

-- Energía total acumulada (último valor)
SELECT energy_total, energy_daily, hours_total, co2_saved
FROM cumulatives ORDER BY time DESC LIMIT 1;

-- Eventos de las últimas 24 horas — usado en dashboard Diagnóstico
SELECT time, event_type, event_value, severity
FROM events
WHERE time > NOW() - INTERVAL '24 hours'
ORDER BY time DESC;

-- Performance Ratio aproximado (potencia / nominal) — dashboard Académico
SELECT bucket,
       avg_power_w,
       avg_power_w / 4000.0 * 100 AS pr_percent
FROM daily_energy
WHERE bucket > NOW() - INTERVAL '30 days'
ORDER BY bucket;

-- Gráfico de producción del día — desde daily_production
SELECT hour_slot, power_w
FROM daily_production
WHERE time::date = CURRENT_DATE AND inverter_id = 1
ORDER BY hour_slot;
```

> **Nota**: No se usa `COPY ... TO STDOUT` para exportar. Grafana tiene export nativo: botón **Inspect > Data > Download CSV** en cualquier panel.

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
# Detener el stack
docker compose down

# Restaurar backup
gunzip -c /opt/solar-monitor/backups/solar_monitor_20240115.sql.gz | \
  docker exec -i solar-monitor-timescaledb-1 psql -U solar solar_monitor

# Reiniciar el stack
docker compose up -d
```

---

## Migraciones Futuras

Para agregar sensores adicionales (piranómetro, estación meteorológica):

```sql
-- Agregar columnas a tablas existentes (TimescaleDB soporta ALTER TABLE)
ALTER TABLE realtime ADD COLUMN irradiance REAL;
ALTER TABLE realtime ADD COLUMN ambient_temp REAL;

ALTER TABLE fast_samples ADD COLUMN irradiance REAL;
ALTER TABLE fast_samples ADD COLUMN ambient_temp REAL;

ALTER TABLE slow_samples ADD COLUMN irradiance_avg REAL;
ALTER TABLE slow_samples ADD COLUMN ambient_temp_avg REAL;
ALTER TABLE slow_samples ADD COLUMN ambient_temp_max REAL;
```

Para agregar un segundo inversor en el bus RS485:

```sql
-- Los datos del inversor 2 usarán inverter_id = 2
-- Las mismas tablas soportan múltiples inversores
-- Solo hay que agregar el segundo slave_address en register_map.h
```