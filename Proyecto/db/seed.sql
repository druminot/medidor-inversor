-- ============================================
-- Seed data for local testing (no hardware)
-- Generates realistic solar data for the last 48 hours
-- ============================================

-- Seed realtime (last 2 hours, every 5 seconds)
INSERT INTO realtime (time, inverter_id, vpv, ipv, vac, iac, pac, fac, temp, status, grid_status)
SELECT
    time_bucket_gapfill('5 seconds', ts, now() - INTERVAL '2 hours', now()),
    1,
    (40 + 10 * sin(extract(epoch from ts) / 3600))::real,
    (3 + 2 * sin(extract(epoch from ts) / 3600))::real,
    220.0 + (5 * sin(extract(epoch from ts) / 7200))::real,
    (2.5 + 1.5 * sin(extract(epoch from ts) / 3600))::real,
    (2500 + 1500 * sin(extract(epoch from ts) / 3600))::real,
    50.0 + (0.1 * sin(extract(epoch from ts) / 1800))::real,
    (35 + 15 * sin(extract(epoch from ts) / 7200))::real,
    1,
    1
FROM generate_series(now() - INTERVAL '2 hours', now(), INTERVAL '5 seconds') AS ts;

-- Seed fast_samples (last 48 hours, every 60 seconds)
INSERT INTO fast_samples (time, inverter_id, vpv, ipv, vac, iac, pac, fac, temp, status, grid_status)
SELECT
    ts,
    1,
    (40 + 10 * sin(extract(epoch from ts) / 3600) + 5 * random())::real,
    (3 + 2 * sin(extract(epoch from ts) / 3600) + 0.5 * random())::real,
    (220 + 5 * sin(extract(epoch from ts) / 7200))::real,
    (2.5 + 1.5 * sin(extract(epoch from ts) / 3600) + 0.3 * random())::real,
    (2500 + 1500 * sin(extract(epoch from ts) / 3600) + 200 * random())::real,
    (50 + 0.1 * sin(extract(epoch from ts) / 1800))::real,
    (35 + 15 * sin(extract(epoch from ts) / 7200) + 2 * random())::real,
    1,
    1
FROM generate_series(now() - INTERVAL '48 hours', now(), INTERVAL '60 seconds') AS ts;

-- Seed cumulatives (last 48 hours, every 60 seconds)
INSERT INTO cumulatives (time, inverter_id, energy_total, energy_daily, hours_total, co2_saved)
SELECT
    ts,
    1,
    (12500 + extract(epoch from ts - (now() - INTERVAL '48 hours')) / 3600 * 1.5)::real,
    (5 + extract(epoch from (ts - (now() - INTERVAL '48 hours'))) / 3600 * 0.8 + 10 * random())::real,
    (4500 + extract(epoch from ts - (now() - INTERVAL '48 hours')) / 3600)::real,
    (3200 + extract(epoch from ts - (now() - INTERVAL '48 hours')) / 3600 * 0.4)::real
FROM generate_series(now() - INTERVAL '48 hours', now(), INTERVAL '60 seconds') AS ts;

-- Seed events (a few test events)
INSERT INTO events (time, inverter_id, event_type, event_value, severity) VALUES
    (now() - INTERVAL '2 hours', 1, 'connection', 'modbus_connected', 0),
    (now() - INTERVAL '1 hour', 1, 'status', 'running', 0),
    (now() - INTERVAL '30 minutes', 1, 'grid', 'normal', 0);