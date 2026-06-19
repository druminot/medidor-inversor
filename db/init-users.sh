#!/bin/bash
set -eu

if [ -z "${GRAFANA_READER_PASSWORD:-}" ]; then
    echo "ERROR: GRAFANA_READER_PASSWORD is not set"
    exit 1
fi

if [ -z "${POSTGRES_USER:-}" ] || [ -z "${POSTGRES_DB:-}" ]; then
    echo "ERROR: POSTGRES_USER and POSTGRES_DB must be set by the timescaledb image"
    exit 1
fi

# Escapar la password para uso seguro en SQL literal.
# Se pasa como variable de sesión y se lee con current_setting().
# Esto evita SQL injection si la password contiene comillas, $ o backslashes.
escaped_pwd=$(printf '%s' "$GRAFANA_READER_PASSWORD" | sed "s/'/''/g")

psql -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    -v reader_pwd="$escaped_pwd" <<-'EOSQL'
    -- Usuario para Grafana (solo lectura).
    -- La password se inyecta via psql -v, NO por interpolación de shell en SQL.
    -- Se usa SET LOCAL + current_setting() para pasar el valor de forma segura
    -- a format() y %L, que cita correctamente caracteres especiales.
    SELECT set_config('siser.grafana_reader_pwd', :'reader_pwd', false);

    DO $do$
    DECLARE
        pwd text := current_setting('siser.grafana_reader_pwd', true);
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_reader') THEN
            EXECUTE format('CREATE ROLE grafana_reader WITH LOGIN PASSWORD %L', pwd);
        ELSE
            EXECUTE format('ALTER ROLE grafana_reader WITH LOGIN PASSWORD %L', pwd);
        END IF;
    END
    $do$;

    GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_reader;
    GRANT SELECT ON slow_samples TO grafana_reader;
    GRANT SELECT ON hourly_energy TO grafana_reader;
    GRANT SELECT ON daily_energy TO grafana_reader;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_reader;

    RESET siser.grafana_reader_pwd;
EOSQL
