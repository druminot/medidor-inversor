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
    start_offset => INTERVAL '3 days',
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