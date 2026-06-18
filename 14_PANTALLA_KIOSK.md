# Pantalla Kiosk — Modo Kiosco en Ubuntu Server

> **ESTADO: OPERATIVO** — El modo kiosco está configurado y funcionando en lautaro.

## Objetivo

Configurar lautaro (Ubuntu Server, sin entorno gráfico) para mostrar el dashboard de Grafana en una pantalla conectada 24/7, arrancando automáticamente al encender y con opción de salir a terminal cuando se necesite.

---

## Por qué Ubuntu Server necesita configuración extra

Ubuntu Server no tiene X11 ni Wayland. Para mostrar Grafana en una pantalla conectada físicamente al PC, necesitamos:

1. Un servidor gráfico mínimo (X11 con Openbox)
2. Un navegador en modo kiosco (Chromium)
3. Un servicio systemd que arranque todo automáticamente
4. Un atajo de teclado para salir a terminal

---

## Arquitectura

```
systemd: kiosk.service
    │
    ├── Xorg (servidor gráfico, :0)
    │
    └── openbox (window manager mínimo)
          │
          └── chromium-browser (kiosk mode)
                │
                └── http://localhost:3000
                      │
                      └── Grafana Dashboard (local, sin auth)
```

> El kiosco apunta a localhost:3000 (Grafana local), sin necesidad de autenticación externa.

---

## Requisitos de Hardware

- PC lautaro con salida HDMI o VGA conectada a un monitor
- Monitor que soporte la resolución deseada (1920x1080 recomendado)
- Teclado USB conectado (para salir del modo kiosco)

---

## Paso 1: Instalar paquetes

```bash
sudo apt-get update
sudo apt-get install -y \
    xorg \
    openbox \
    chromium-browser \
    unclutter \
    xdotool
```

| Paquete | Función |
|---|---|
| `xorg` | Servidor gráfico X11 |
| `openbox` | Window manager mínimo (sin decoraciones) |
| `chromium-browser` | Navegador en modo kiosco |
| `unclutter` | Ocultar cursor del mouse después de inactividad |
| `xdotool` | Automatización de teclado/ratón (para simular TAB en Cloudflare) |

---

## Paso 2: Crear usuario kiosk

```bash
sudo adduser --disabled-password --gecos "Kiosk" kiosk
sudo usermod -aG video kiosk
sudo usermod -aG dialout kiosk
```

---

## Paso 3: Script de inicio del kiosco

Crear `/opt/solar-monitor/kiosk/kiosk.sh`:

```bash
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
```

```bash
sudo chmod +x /opt/solar-monitor/kiosk/kiosk.sh
```

---

## Paso 4: Script de sesión X

Crear `/opt/solar-monitor/kiosk/xsession.sh`:

```bash
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
```

```bash
sudo chmod +x /opt/solar-monitor/kiosk/xsession.sh
```

---

## Paso 5: Configuración de Openbox

Crear `/home/kiosk/.config/openbox/rc.xml`:

```bash
sudo mkdir -p /home/kiosk/.config/openbox
sudo tee /home/kiosk/.config/openbox/rc.xml << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <applications>
    <application class="Chromium-browser" type="normal">
      <fullscreen>yes</fullscreen>
      <decor>no</decor>
      <maximized>yes</maximized>
    </application>
  </applications>
</openbox_config>
EOF

sudo chown -R kiosk:kiosk /home/kiosk/.config
```

---

## Paso 6: Servicio systemd para Xorg

Crear `/etc/systemd/system/kiosk.service`:

```ini
[Unit]
Description=Kiosk Mode - Grafana Dashboard
After=network-online.target docker.service
Wants=network-online.target
Conflicts=getty@tty7.service

[Service]
Type=simple
User=kiosk
Group=kiosk
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/kiosk/.Xauthority
ExecStartPre=/bin/bash -c '/usr/bin/xhost +local: > /dev/null 2>&1 || true'
ExecStart=/opt/solar-monitor/kiosk/xsession.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## Paso 7: Servicio systemd para Xorg

Crear `/etc/systemd/system/xorg-kiosk.service`:

```ini
[Unit]
Description=Xorg for Kiosk Display
After=docker.service
Conflicts=getty@tty7.service

[Service]
Type=simple
User=kiosk
Group=kiosk
ExecStart=/usr/bin/Xorg :0 -nolisten tcp -noreset vt7
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## Paso 8: Habilitar servicios

```bash
# Recargar systemd
sudo systemctl daemon-reload

# Habilitar Xorg y kiosco al arranque
sudo systemctl enable xorg-kiosk.service
sudo systemctl enable kiosk.service

# Iniciar servicios
sudo systemctl start xorg-kiosk.service
sleep 5
sudo systemctl start kiosk.service

# Verificar estado
sudo systemctl status xorg-kiosk.service
sudo systemctl status kiosk.service
```

---

## Cómo salir del modo kiosco

### Atajo de teclado: `Ctrl + Alt + F1`

Cambiar a la terminal virtual tty1 (consola de texto). El modo kiosco sigue corriendo en tty7.

### Para volver al kiosco: `Ctrl + Alt + F7`

Volver a la sesión Xorg con Chromium.

### Para detener el kiosco completamente

```bash
sudo systemctl stop kiosk.service
sudo systemctl stop xorg-kiosk.service
```

### Para reiniciar el kiosco

```bash
sudo systemctl restart xorg-kiosk.service
sudo systemctl restart kiosk.service
```

### Para deshabilitar el kiosco permanente (no arranca al reiniciar)

```bash
sudo systemctl disable kiosk.service
sudo systemctl disable xorg-kiosk.service
```

### Para re-habilitar

```bash
sudo systemctl enable kiosk.service
sudo systemctl enable xorg-kiosk.service
```

---

## Autenticación

El kiosco apunta a `http://localhost:3000` (Grafana local con anonymous viewer). No se requiere autenticación externa. Si en el futuro se necesita acceso via ngrok, se puede cambiar la URL en `kiosk.sh`.

---

## Configuración de Monitor

### Resolución forzada

Si el monitor no detecta la resolución correcta, agregar modelo en xorg.conf:

Crear `/etc/X11/xorg.conf.d/10-monitor.conf`:

```bash
sudo mkdir -p /etc/X11/xorg.conf.d
sudo tee /etc/X11/xorg.conf.d/10-monitor.conf << 'EOF'
Section "Monitor"
    Identifier "Monitor0"
    Modeline "1920x1080_60" 172.80 1920 2040 2248 2576 1080 1081 1084 1118 -hsync +vsync
    Option "PreferredMode" "1920x1080_60"
EndSection

Section "Device"
    Identifier "Card0"
    Driver "modesetting"
EndSection

Section "Screen"
    Identifier "Screen0"
    Device "Card0"
    Monitor "Monitor0"
    DefaultDepth 24
    SubSection "Display"
        Depth 24
        Modes "1920x1080_60"
    EndSubSection
EndSection
EOF
```

### Rotación de pantalla (si el monitor está vertical)

Agregar a `xorg.conf.d/10-monitor.conf`:

```
# En la sección Screen, agregar:
Option "Rotate" "left"    # o "right" o "inverted"
```

---

## Resolución de Problemas

| Problema | Causa | Solución |
|---|---|---|
| Pantalla negra al arrancar | Xorg no arrancó | `systemctl status xorg-kiosk.service` |
| Chromium no aparece | kiosk.service no arrancó | `systemctl status kiosk.service` |
| Resolución incorrecta | Monitor no detectado | Agregar modelo en `10-monitor.conf` |
| Sesión expirada | — | No aplica (kiosco apunta a localhost) |
| Chromium crashea | Out of memory | Agregar `--disk-cache-dir=/tmp/chromium-cache` al kiosk.sh |
| Pantalla se apaga | DPMS activo | Verificar `xset -dpms` en kiosk.sh |
| No puedo salir del kiosco | No hay teclado | Conectar teclado USB y usar Ctrl+Alt+F1 |

---

## Comandos Útiles

```bash
# Ver estado del kiosco
sudo systemctl status kiosk.service xorg-kiosk.service

# Ver logs del kiosco
sudo journalctl -u kiosk.service -f

# Ver logs de Xorg
sudo journalctl -u xorg-kiosk.service -f

# Reiniciar kiosco (sin reiniciar Xorg)
sudo systemctl restart kiosk.service

# Reiniciar todo (Xorg + kiosco)
sudo systemctl restart xorg-kiosk.service kiosk.service

# Detener kiosco y volver a terminal
sudo systemctl stop kiosk.service xorg-kiosk.service

# Salir del kiosco a terminal (desde la pantalla)
# Ctrl + Alt + F1

# Volver al kiosco (desde la pantalla)
# Ctrl + Alt + F7

# Verificar que Chromium está corriendo
pgrep -a chromium

# Matar Chromium y dejar que se reinicie solo
sudo -u kiosk DISPLAY=:0 xdotool key ctrl+q
# O más brusco:
sudo killall -HUP chromium-browser

# Forzar resolución (debug)
sudo -u kiosk DISPLAY=:0 xrandr --output HDMI-1 --mode 1920x1080 --rate 60

# Ver resoluciones disponibles
sudo -u kiosk DISPLAY=:0 xrandr
```