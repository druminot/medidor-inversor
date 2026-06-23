#!/bin/bash
# kiosk.sh — Inicia el modo kiosco para Grafana
# Ejecutado por systemd como usuario lautaro (Type=forking)
# Ubicado en /usr/local/bin/kiosk.sh en producción

KIOSK_URL='http://localhost:3000/d/solar-realtime/solar-monitor-tiempo-real?orgId=1&kiosk&theme=light&refresh=5s'

# Esperar a que Xorg esté disponible
while ! xdpyinfo -display :0 > /dev/null 2>&1; do
    sleep 1
done

# Ocultar cursor después de 3 segundos de inactividad
unclutter -idle 3 -root &

# Configurar pantalla: sin screensaver, sin suspensión
xset s off
xset -dpms
xset s noblank

# Esperar a que Grafana responda
until curl -sf http://localhost:3000/api/health > /dev/null 2>&1; do
    sleep 2
done

# Limpiar locks de Chromium de sesiones previas
rm -f ~/snap/chromium/common/chromium/SingletonLock \
      ~/snap/chromium/common/chromium/SingletonCookie \
      ~/snap/chromium/common/chromium/SingletonSocket 2>/dev/null || true

# Lanzar Chromium en modo kiosco (background, systemd lo monitorea)
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
        --disable-gpu \
        --window-position=0,0 \
        --window-size=1920,1080 \
        --incognito \
        --disable-session-crashed-bubble \
        --password-store=basic \
        "$KIOSK_URL" \
        >> /tmp/kiosk-chromium.log 2>&1 &