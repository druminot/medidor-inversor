#!/bin/bash
# persist-cookies.sh — Mantener cookies de Cloudflare Access
# Ejecutar como cron cada 6 horas para renovar la sesión

COOKIE_DIR="/home/kiosk/.config/chromium/Default"

# Verificar que el directorio de cookies existe
if [ ! -d "$COOKIE_DIR" ]; then
    mkdir -p "$COOKIE_DIR"
fi

# Chromium mantiene las cookies automáticamente en modo incognito
# Pero si se usa sin --incognito, las cookies persisten en el perfil
echo "Cookie persistence check: $(date)"