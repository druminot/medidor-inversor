#!/bin/bash
# kiosk.sh — Inicia el modo kiosco para Grafana
# Ejecutado por systemd como usuario kiosk

# Esperar a que Xorg esté disponible
while ! xdpyinfo -display :0 > /dev/null 2>&1; do
    sleep 1
done

# Ocultar cursor después de 3 segundos de inactividad
unclutter -idle 3 -root &

# Configurar pantalla: sin screensaver, sin suspensión
xset s off         # Desactivar screensaver
xset -dpms         # Desactivar DPMS (suspensión de monitor)
xset s noblank     # No blanking

# Iniciar Chromium en modo kiosco
chromium-browser \
    --noerrdialogs \
    --disable-infobars \
    --kiosk \
    --disable-translate \
    --disable-features=TranslateUI \
    --no-first-run \
    --disable-background-networking \
    --disable-default-apps \
    --disable-extensions \
    --disable-sync \
    --disable-component-update \
    --disable-prompt-on-repost \
    --disable-hang-monitor \
    --disable-client-side-phishing-detection \
    --disable-breakpad \
    --disable-domain-reliability \
    --disable-background-timer-throttling \
    --disable-renderer-backgrounding \
    --disable-backgrounding-occluded-windows \
    --disable-ipc-flooding-protection \
    --window-position=0,0 \
    --window-size=1920,1080 \
    "http://localhost:3000/d/solar-realtime/solar-monitor-tiempo-real" \
    &