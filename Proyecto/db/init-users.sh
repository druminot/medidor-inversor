#!/bin/bash
set -eu

if [ -z "${GRAFANA_READER_PASSWORD:-}" ]; then
    echo "ERROR: GRAFANA_READER_PASSWORD is not set"
    exit 1
fi

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<-EOSQL
    -- Usuario para Grafana (solo lectura)
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_reader') THEN
            CREATE ROLE grafana_reader WITH PASSWORD '${GRAFANA_READER_PASSWORD}' LOGIN;
        END IF;
    END
    \$\$;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_reader;
    GRANT SELECT ON slow_samples TO grafana_reader;
    GRANT SELECT ON hourly_energy TO grafana_reader;
    GRANT SELECT ON daily_energy TO grafana_reader;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_reader;
EOSQL