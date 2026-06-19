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
    -- Columnas SISER (3 MPPT, triphase)
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

-- ============================================
-- Continuous Aggregates
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