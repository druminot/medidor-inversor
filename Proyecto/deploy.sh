#!/bin/bash

# deploy.sh — Sube archivos al servidor lautaro via ngrok cmd-server.
#
# Credenciales:
#   Las credenciales se leen desde variables de entorno para evitar
#   dejarlas en el historial de shell:
#     DEPLOY_USER    (default: lautaro)
#     DEPLOY_PASS    (requerido)
#     DEPLOY_HOST    (default: zoning-heat-groggy.ngrok-free.dev)
#
# Alternativa: configurar ~/.netrc con:
#   machine zoning-heat-groggy.ngrok-free.dev
#   login lautaro
#   password <tu_password>
# (en este caso no se exporta DEPLOY_PASS y curl usará .netrc)
#
# Archivos remotos requeridos en /opt/solar-monitor/:
#   inverter-simulator/simulator.py
#   docker-compose.yml
#   sunvision-wine/Dockerfile
#   sunvision-wine/sv_cab/ConfigSunVision.xml
#
# Para usar:
#   DEPLOY_PASS=lsistem19 ./deploy.sh
# o agregar a ~/.zshrc: export DEPLOY_PASS='...'

set -eu

DEPLOY_USER="${DEPLOY_USER:-lautaro}"
DEPLOY_HOST="${DEPLOY_HOST:-zoning-heat-groggy.ngrok-free.dev}"

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

upload_file() {
    local_file=$1
    remote_path=$2

    echo "Uploading $local_file to $remote_path"
    curl -s "${CURL_AUTH_OPTS[@]}" -G --data-urlencode "cmd=rm -f $remote_path" "$BASE_URL" > /dev/null

    b64=$(base64 -i "$local_file" | tr -d '\n')
    chunk_size=4000
    len=${#b64}
    for (( i=0; i<len; i+=chunk_size )); do
        chunk="${b64:$i:$chunk_size}"
        curl -s "${CURL_AUTH_OPTS[@]}" -G --data-urlencode "cmd=echo -n $chunk | base64 -d >> $remote_path" "$BASE_URL" > /dev/null
        echo -n "."
    done
    echo " Done."
}

upload_file "/Users/druminot/Documents/Codigos Varios/Medidor Inversor/Proyecto/inverter-simulator/simulator.py" "/opt/solar-monitor/inverter-simulator/simulator.py"
upload_file "/Users/druminot/Documents/Codigos Varios/Medidor Inversor/Proyecto/docker-compose.yml" "/opt/solar-monitor/docker-compose.yml"
upload_file "/Users/druminot/Documents/Codigos Varios/Medidor Inversor/Proyecto/sunvision-wine/Dockerfile" "/opt/solar-monitor/sunvision-wine/Dockerfile"
upload_file "/Users/druminot/Documents/Codigos Varios/Medidor Inversor/Proyecto/sunvision-wine/sv_cab/ConfigSunVision.xml" "/opt/solar-monitor/sunvision-wine/sv_cab/ConfigSunVision.xml"

echo "Restarting containers..."
curl -s "${CURL_AUTH_OPTS[@]}" -G --data-urlencode "cmd=cd /opt/solar-monitor && docker compose build sunvision-wine inverter-simulator" "$BASE_URL"
curl -s "${CURL_AUTH_OPTS[@]}" -G --data-urlencode "cmd=cd /opt/solar-monitor && docker compose up -d sunvision-wine inverter-simulator" "$BASE_URL"
