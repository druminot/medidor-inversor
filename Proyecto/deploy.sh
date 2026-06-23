#!/bin/bash
# deploy.sh — Sube los archivos del proyecto al servidor lautaro via ngrok cmd-server.
# Sincroniza la version del repo con /opt/solar-monitor/ en produccion.
#
# Credenciales:
#   Las credenciales se leen desde variables de entorno para evitar
#   dejarlas en el historial de shell:
#     DEPLOY_USER    (default: lautaro)
#     DEPLOY_PASS    (requerido si no hay ~/.netrc)
#     DEPLOY_HOST    (default: zoning-heat-groggy.ngrok-free.dev)
#
# Alternativa: configurar ~/.netrc con:
#   machine zoning-heat-groggy.ngrok-free.dev
#   login lautaro
#   password <tu_password>
#
# Para usar:
#   DEPLOY_PASS=lsistem19 ./deploy.sh
# o agregar a ~/.zshrc: export DEPLOY_PASS='...'

set -eu

DEPLOY_USER="${DEPLOY_USER:-lautaro}"
DEPLOY_HOST="${DEPLOY_HOST:-zoning-heat-groggy.ngrok-free.dev}"
LOCAL_REPO="${LOCAL_REPO:-/Users/druminot/Documents/Codigos Varios/Medidor Inversor/Proyecto}"
REMOTE_BASE="/opt/solar-monitor"

if [ -z "${DEPLOY_PASS:-}" ]; then
    if [ ! -f "$HOME/.netrc" ]; then
        echo "ERROR: Define DEPLOY_PASS o configura ~/.netrc para $DEPLOY_HOST" >&2
        exit 1
    fi
    CURL_AUTH_OPTS=("--netrc" "--netrc-file" "$HOME/.netrc")
else
    CURL_AUTH_OPTS=("-u" "$DEPLOY_USER:$DEPLOY_PASS")
fi

BASE_URL="https://$DEPLOY_HOST/cmd/"

run_remote() {
    curl -s "${CURL_AUTH_OPTS[@]}" -G --data-urlencode "cmd=$1" "$BASE_URL"
}

upload_file() {
    local_file=$1
    remote_path=$2

    if [ ! -f "$local_file" ]; then
        echo "  SKIP: $local_file (no existe)"
        return
    fi

    echo "Uploading $local_file -> $remote_path"
    run_remote "rm -f $remote_path" > /dev/null

    b64=$(base64 -i "$local_file" | tr -d '\n')
    chunk_size=4000
    len=${#b64}
    for (( i=0; i<len; i+=chunk_size )); do
        chunk="${b64:$i:$chunk_size}"
        run_remote "echo -n $chunk | base64 -d >> $remote_path" > /dev/null
        echo -n "."
    done
    echo " Done."
}

# Lista de archivos a sincronizar (formato: local|remote)
FILES=(
    "docker-compose.yml|$REMOTE_BASE/docker-compose.yml"
    "db/init.sql|$REMOTE_BASE/db/init.sql"
    "db/init-users.sh|$REMOTE_BASE/db/init-users.sh"
    "db/sunrise_functions.sql|$REMOTE_BASE/db/sunrise_functions.sql"
    "siser-reader/siser_reader.py|$REMOTE_BASE/siser-reader/siser_reader.py"
    "siser-reader/Dockerfile|$REMOTE_BASE/siser-reader/Dockerfile"
    "grafana/update_timerange.py|$REMOTE_BASE/grafana/update_timerange.py"
    "grafana/Dockerfile|$REMOTE_BASE/grafana/Dockerfile"
    "grafana/grafana.ini|$REMOTE_BASE/grafana/grafana.ini"
    "grafana/provisioning/datasources/datasource.yml|$REMOTE_BASE/grafana/provisioning/datasources/datasource.yml"
    "grafana/provisioning/dashboards/dashboard.yml|$REMOTE_BASE/grafana/provisioning/dashboards/dashboard.yml"
    "grafana/dashboards/realtime.json|$REMOTE_BASE/grafana/dashboards/realtime.json"
    "grafana/dashboards/diagnostico.json|$REMOTE_BASE/grafana/dashboards/diagnostico.json"
    "grafana/dashboards/historico.json|$REMOTE_BASE/grafana/dashboards/historico.json"
    "grafana/dashboards/academico.json|$REMOTE_BASE/grafana/dashboards/academico.json"
    "nginx/solar-monitor|$REMOTE_BASE/nginx/solar-monitor"
    "kiosk/kiosk.sh|/usr/local/bin/kiosk.sh"
    "kiosk/kiosk.service|/etc/systemd/system/kiosk.service"
    "tools/solar-healthcheck.sh|/usr/local/bin/solar-healthcheck.sh"
)

for entry in "${FILES[@]}"; do
    IFS='|' read -r local_rel remote_abs <<< "$entry"
    upload_file "$LOCAL_REPO/$local_rel" "$remote_abs"
done

echo ""
echo "=== Archivos sincronizados ==="
echo "Reiniciando servicios Docker..."
run_remote "cd $REMOTE_BASE && docker compose restart timescaledb siser-reader timerange-updater grafana" > /dev/null

echo "Restaurando config de nginx desde backup..."
run_remote "echo lsistem19 | sudo -S cp /opt/solar-monitor/nginx/solar-monitor /etc/nginx/sites-enabled/solar-monitor 2>/dev/null && echo lsistem19 | sudo -S nginx -t 2>&1 && echo lsistem19 | sudo -S systemctl reload nginx 2>/dev/null" > /dev/null

echo "Reinstalando kiosk.service..."
run_remote "echo lsistem19 | sudo -S systemctl daemon-reload 2>/dev/null && echo lsistem19 | sudo -S systemctl restart kiosk 2>/dev/null" > /dev/null

echo "Configurando healthcheck cron..."
run_remote "echo lsistem19 | sudo -S chmod +x /usr/local/bin/solar-healthcheck.sh 2>/dev/null && (crontab -l 2>/dev/null | grep -v solar-healthcheck; echo '*/5 * * * * /usr/local/bin/solar-healthcheck.sh') | crontab - 2>/dev/null" > /dev/null

echo "Hecho. Verifica con: docker compose ps y docker compose logs -f"
