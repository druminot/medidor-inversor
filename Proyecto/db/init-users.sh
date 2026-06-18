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