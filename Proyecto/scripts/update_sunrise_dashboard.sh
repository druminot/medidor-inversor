#!/bin/bash
# update_sunrise_dashboard.sh
# Actualiza el rango de tiempo del dashboard provisionado con la hora de amanecer
# Se ejecuta diariamente via cron (05:00) y reinicia Grafana para que re-provisione
#
# Con dashboard provisionado (editable=false):
# - Grafana lee el JSON del filesystem al iniciar y con cada F5
# - El time.from se resetea al valor del JSON (no al del browser)
# - El script actualiza el JSON y reinicia Grafana

DASHBOARD_FILE="/opt/solar-monitor/grafana/dashboards/realtime.json"

AMANECER=$(docker exec solar-monitor-timescaledb-1 psql -U solar -d solar_monitor -t -c \
    "SELECT to_char(sunrise_concepcion(current_date) AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')" | tr -d ' ')

if [ -z "$AMANECER" ]; then
    echo "ERROR: No se pudo obtener la hora de amanecer"
    exit 1
fi

python3 -c "
import json, sys

amanecer = sys.argv[1]
f = sys.argv[2]

with open(f, 'r') as fh:
    d = json.load(fh)

old_from = d.get('time', {}).get('from', 'unknown')
d['time'] = {'from': amanecer, 'to': 'now'}

with open(f, 'w') as fh:
    json.dump(d, fh, indent=2)

print(f'Dashboard actualizado: {old_from} -> {amanecer}')
" "$AMANECER" "$DASHBOARD_FILE"

docker restart solar-monitor-grafana-1

echo "Amanecer hoy: $AMANECER - Grafana reiniciado"