#!/bin/bash
# migrate_db.sh — Aplica las nuevas CAGGs, triggers y vistas al DB de produccion.
# Las sentencias son idempotentes (DROP IF EXISTS + CREATE OR REPLACE).
# Uso: cd /opt/solar-monitor && docker compose exec timescaledb psql -U solar -d solar_monitor < migrate_db.sql

set -eu

cat <<'EOSQL'
-- ============================================
-- Migracion de schema v2 (idempotente)
-- Aplica CAGGs v2, tabla events_v2 con trigger, vista realtime_clean,
-- trigger cumulatives. Todas las sentencias son DROP IF EXISTS + CREATE
-- para que se puedan aplicar multiples veces sin error.
-- ============================================

-- ============================================
-- Continuous Aggregates v2 — basadas en realtime directamente
-- ============================================

DROP MATERIALIZED VIEW IF EXISTS slow_samples_v2 CASCADE;
CREATE MATERIALIZED VIEW slow_samples_v2
WITH (timescaledb.continuous) AS
SELECT time_bucket('15 minutes', time) AS time,
       inverter_id,
       AVG(vpv)  AS vpv_avg,  AVG(ipv)  AS ipv_avg,
       AVG(vac)  AS vac_avg,  AVG(iac)  AS iac_avg,
       AVG(pac)  AS pac_avg,  MAX(pac)  AS pac_max,  MIN(pac)  AS pac_min,
       AVG(fac)  AS fac_avg,
       AVG(temp) AS temp_avg, MAX(temp) AS temp_max,
       SUM(CASE WHEN is_stale THEN 0 ELSE 1 END) AS real_samples,
       SUM(CASE WHEN is_stale THEN 1 ELSE 0 END) AS stale_samples
FROM realtime
WHERE is_stale = false
GROUP BY time_bucket('15 minutes', time), inverter_id;

SELECT remove_continuous_aggregate_policy('slow_samples_v2');
SELECT add_continuous_aggregate_policy('slow_samples_v2',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '15 minutes');

DROP MATERIALIZED VIEW IF EXISTS hourly_energy_v2 CASCADE;
CREATE MATERIALIZED VIEW hourly_energy_v2
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 hour', time) AS bucket,
       inverter_id,
       AVG(pac)   AS avg_power_w,
       MAX(pac)   AS peak_power_w,
       MIN(pac)   AS min_power_w,
       AVG(temp)  AS avg_temp_c
FROM realtime
WHERE is_stale = false
GROUP BY time_bucket('1 hour', time), inverter_id;

SELECT remove_continuous_aggregate_policy('hourly_energy_v2');
SELECT add_continuous_aggregate_policy('hourly_energy_v2',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

DROP MATERIALIZED VIEW IF EXISTS daily_energy_v2 CASCADE;
CREATE MATERIALIZED VIEW daily_energy_v2
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 day', time) AS bucket,
       inverter_id,
       AVG(pac)   AS avg_power_w,
       MAX(pac)   AS peak_power_w,
       MIN(pac)   AS min_power_w,
       AVG(temp)  AS avg_temp_c,
       AVG(vpv)   AS avg_vpv_v,
       AVG(ipv)   AS avg_ipv_a,
       SUM(CASE WHEN pac > 0 THEN 1 ELSE 0 END) * 5.0 / 60.0 AS productive_hours,
       SUM(pac) * 5.0 / 3600.0 / 1000.0 AS energy_kwh_approx
FROM realtime
WHERE is_stale = false
GROUP BY time_bucket('1 day', time), inverter_id;

SELECT remove_continuous_aggregate_policy('daily_energy_v2');
SELECT add_continuous_aggregate_policy('daily_energy_v2',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day');

GRANT SELECT ON slow_samples_v2 TO grafana_reader;
GRANT SELECT ON hourly_energy_v2 TO grafana_reader;
GRANT SELECT ON daily_energy_v2 TO grafana_reader;

-- ============================================
-- Tabla events_v2 con trigger automatico
-- ============================================

CREATE TABLE IF NOT EXISTS events_v2 (
    id            BIGSERIAL,
    time          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    inverter_id   SMALLINT    NOT NULL DEFAULT 1,
    event_type    TEXT NOT NULL,
    event_subtype TEXT,
    prev_value    TEXT,
    new_value     TEXT,
    severity      SMALLINT DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_events_v2_time ON events_v2 (time DESC);
CREATE INDEX IF NOT EXISTS idx_events_v2_severity ON events_v2 (severity, time DESC);
CREATE INDEX IF NOT EXISTS idx_events_v2_type ON events_v2 (event_type, time DESC);

CREATE OR REPLACE FUNCTION fn_realtime_event_logger()
RETURNS TRIGGER AS $$
BEGIN
    IF (OLD.is_stale IS DISTINCT FROM NEW.is_stale) THEN
        INSERT INTO events_v2 (time, inverter_id, event_type, event_subtype,
                               prev_value, new_value, severity)
        VALUES (
            NEW.time,
            NEW.inverter_id,
            'connectivity',
            CASE WHEN NEW.is_stale THEN 'going_offline' ELSE 'back_online' END,
            OLD.is_stale::text,
            NEW.is_stale::text,
            CASE WHEN NEW.is_stale THEN 2 ELSE 1 END
        );
    END IF;

    IF (OLD.status IS DISTINCT FROM NEW.status)
       AND OLD.status IS NOT NULL AND NEW.status IS NOT NULL THEN
        INSERT INTO events_v2 (time, inverter_id, event_type, event_subtype,
                               prev_value, new_value, severity)
        VALUES (
            NEW.time,
            NEW.inverter_id,
            'inverter_status',
            CASE NEW.status
                WHEN 0 THEN 'wait'
                WHEN 1 THEN 'normal'
                WHEN 2 THEN 'fault'
                WHEN 3 THEN 'permanent_fault'
                ELSE 'unknown'
            END,
            OLD.status::text,
            NEW.status::text,
            CASE NEW.status
                WHEN 2 THEN 4
                WHEN 3 THEN 4
                WHEN 0 THEN 1
                ELSE 1
            END
        );
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_realtime_event_logger ON realtime;
CREATE TRIGGER trg_realtime_event_logger
    AFTER INSERT OR UPDATE ON realtime
    FOR EACH ROW
    EXECUTE FUNCTION fn_realtime_event_logger();

GRANT SELECT ON events_v2 TO grafana_reader;

-- ============================================
-- Trigger cumulatives: extrae energy_total/hours_total y calcula
-- energy_daily = energy_total - energy_total al inicio del dia UTC.
-- ============================================

CREATE OR REPLACE FUNCTION fn_realtime_cumulatives()
RETURNS TRIGGER AS $$
DECLARE
    v_prev_energy_total REAL;
    v_prev_inserted_at  TIMESTAMPTZ;
    v_energy_total      REAL;
    v_hours_total       REAL;
    v_energy_daily      REAL;
    v_co2_saved         REAL;
    v_should_write      BOOLEAN := false;
BEGIN
    IF NEW.is_stale = true THEN
        RETURN NEW;
    END IF;

    v_energy_total := NEW.energy_total;
    v_hours_total  := NEW.hours_total;

    IF v_energy_total IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT energy_total, time
      INTO v_prev_energy_total, v_prev_inserted_at
      FROM cumulatives
     WHERE inverter_id = NEW.inverter_id
     ORDER BY time DESC
     LIMIT 1;

    IF v_prev_energy_total IS NULL THEN
        v_should_write := true;
    ELSIF v_energy_total > v_prev_energy_total THEN
        v_should_write := true;
    ELSIF v_prev_inserted_at IS NULL OR (NEW.time - v_prev_inserted_at) >= INTERVAL '1 hour' THEN
        v_should_write := true;
    END IF;

    IF NOT v_should_write THEN
        RETURN NEW;
    END IF;

    SELECT COALESCE(v_energy_total - r.energy_total, 0)
      INTO v_energy_daily
      FROM realtime r
     WHERE r.inverter_id = NEW.inverter_id
       AND r.is_stale = false
       AND r.energy_total IS NOT NULL
       AND r.time >= date_trunc('day', NEW.time)
       AND r.time <  NEW.time
     ORDER BY r.time ASC
     LIMIT 1;

    IF v_energy_daily IS NULL THEN
        v_energy_daily := 0;
    END IF;

    v_co2_saved := (v_energy_total / 1000.0) * 0.5;

    INSERT INTO cumulatives (time, inverter_id, energy_total, energy_daily, hours_total, co2_saved)
    VALUES (NEW.time, NEW.inverter_id, v_energy_total, v_energy_daily, v_hours_total, v_co2_saved);

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_realtime_cumulatives ON realtime;
CREATE TRIGGER trg_realtime_cumulatives
    AFTER INSERT ON realtime
    FOR EACH ROW
    EXECUTE FUNCTION fn_realtime_cumulatives();

-- ============================================
-- Vista realtime_clean
-- ============================================
CREATE OR REPLACE VIEW realtime_clean AS
    SELECT * FROM realtime WHERE is_stale = false;
GRANT SELECT ON realtime_clean TO grafana_reader;

-- ============================================
-- Indice adicional para queries is_stale
-- ============================================
CREATE INDEX IF NOT EXISTS idx_realtime_stale ON realtime (is_stale, time DESC) WHERE is_stale = false;

SELECT 'migracion_v2 aplicada correctamente' AS resultado;
EOSQL
