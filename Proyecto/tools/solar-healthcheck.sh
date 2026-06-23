#!/bin/bash
# solar-healthcheck.sh — Verifica y repara automáticamente los servicios del monitor solar
# Se ejecuta cada 5 minutos via cron (lautaro)
# Ubicado en /usr/local/bin/solar-healthcheck.sh en producción

set -euo pipefail

LOG_TAG="solar-healthcheck"
LOG_FILE="/var/log/solar-healthcheck.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE" 2>/dev/null || true
    logger -t "$LOG_TAG" "$1" 2>/dev/null || true
}

REPAIRED=0

# 1. Verificar nginx (puerto 8080)
if ! ss -tlnp | grep -q ':8080 '; then
    log "ALERTA: nginx no escucha en 8080. Verificando config y reiniciando..."
    if ! nginx -t 2>/dev/null; then
        log "ALERTA: config de nginx rota. Restaurando desde backup..."
        if [ -f /opt/solar-monitor/nginx/solar-monitor ]; then
            cp /opt/solar-monitor/nginx/solar-monitor /etc/nginx/sites-enabled/solar-monitor
            log "Config restaurada desde /opt/solar-monitor/nginx/solar-monitor"
        fi
    fi
    sudo systemctl restart nginx 2>/dev/null && log "nginx reiniciado OK" && REPAIRED=1 || log "ERROR: no se pudo reiniciar nginx"
fi

# 2. Verificar Grafana (puerto 3000)
if ! curl -sf http://localhost:3000/api/health > /dev/null 2>&1; then
    log "ALERTA: Grafana no responde en 3000. Reiniciando container..."
    cd /opt/solar-monitor && docker compose restart grafana 2>/dev/null && log "Grafana reiniciado OK" && REPAIRED=1 || log "ERROR: no se pudo reiniciar Grafana"
fi

# 3. Verificar cmd-server (puerto 8023)
if ! ss -tlnp | grep -q ':8023 '; then
    log "ALERTA: cmd-server no escucha en 8023. Reiniciando..."
    sudo systemctl restart cmd-server 2>/dev/null && log "cmd-server reiniciado OK" && REPAIRED=1 || log "ERROR: no se pudo reiniciar cmd-server"
fi

# 4. Verificar ttyd (puerto 8022)
if ! ss -tlnp | grep -q ':8022 '; then
    log "ALERTA: ttyd no escucha en 8022. Reiniciando..."
    sudo systemctl restart ttyd 2>/dev/null && log "ttyd reiniciado OK" && REPAIRED=1 || log "ERROR: no se pudo reiniciar ttyd"
fi

# 5. Verificar ngrok (proceso corriendo)
if ! pgrep -f 'ngrok http' > /dev/null 2>&1; then
    log "ALERTA: ngrok no está corriendo. Reiniciando..."
    sudo systemctl restart ngrok 2>/dev/null && log "ngrok reiniciado OK" && REPAIRED=1 || log "ERROR: no se pudo reiniciar ngrok"
fi

# 6. Verificar Chromium kiosk (si hay display)
if [ -n "${DISPLAY:-}" ] || xdpyinfo -display :0 > /dev/null 2>&1; then
    if ! pgrep -f 'chromium.*--kiosk' > /dev/null 2>&1; then
        log "ALERTA: Chromium kiosk no está corriendo. Reiniciando kiosk.service..."
        sudo systemctl restart kiosk 2>/dev/null && log "kiosk reiniciado OK" && REPAIRED=1 || log "ERROR: no se pudo reiniciar kiosk"
    fi
fi

# 7. Verificar acceso externo via ngrok (si nginx está ok)
if ss -tlnp | grep -q ':8080 '; then
    NGROK_URL=$(curl -sf http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'])" 2>/dev/null || echo "")
    if [ -n "$NGROK_URL" ]; then
        HTTP_CODE=$(curl -sf -o /dev/null -w '%{http_code}' -H 'ngrok-skip-browser-warning: true' "$NGROK_URL/api/health" --max-time 10 2>/dev/null || echo "000")
        if [ "$HTTP_CODE" != "200" ]; then
            log "ALERTA: ngrok túnel responde con HTTP $HTTP_CODE (esperado 200)"
        fi
    else
        log "ALERTA: no se pudo obtener URL de ngrok"
    fi
fi

if [ "$REPAIRED" -eq 1 ]; then
    log "Se repararon problemas. Verificar servicios."
else
    log "Todos los servicios OK"
fi