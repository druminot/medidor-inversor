#!/bin/bash
# xsession.sh — Sesión X para el kiosco
# Ejecuta openbox y luego el script de kiosco

exec openbox-session &
sleep 2

# Ejecutar kiosco
/opt/solar-monitor/kiosk/kiosk.sh

# Si chromium se cierra, reabrir
while true; do
    sleep 10
    if ! pgrep -x "chromium-browser" > /dev/null; then
        /opt/solar-monitor/kiosk/kiosk.sh
    fi
done