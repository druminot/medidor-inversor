# Pantalla Kiosk — Modo Kiosco en Ubuntu Server

> **ESTADO: OPERATIVO** — El modo kiosco está configurado y funcionando en lautaro.

## Objetivo

Configurar lautaro (Ubuntu Server) para mostrar el dashboard de Grafana en una pantalla conectada 24/7, arrancando automáticamente al encender y con opción de salir a terminal cuando se necesite.

---

## Arquitectura Real

```
systemd: kiosk.service (Type=forking, User=lautaro)
     │
     │  (lightdm auto-login lautaro → openbox session)
     │
     ├── lightdm (auto-login lautaro, session=openbox)
     │     │
     │     └── Xorg :0 (gestionado por lightdm)
     │           │
     │           └── openbox (window manager mínimo)
     │                 │
     │                 └── chromium-browser (kiosk mode, --incognito)
     │                       │
     │                       └── http://localhost:3000/d/solar-realtime/...?kiosk
     │                             │
     │                             └── Grafana Dashboard (local, anonymous viewer)
     │
     └── /usr/local/bin/kiosk.sh (lanzado por kiosk.service)
```

> El kiosco apunta a localhost:3000 (Grafana local con anonymous viewer).
> Chromium arranca en modo `--kiosk --incognito` con URL `?kiosk&theme=light&refresh=5s`.
> Antes de lanzar Chromium, el script espera a que `http://localhost:3000/api/health` responda.

---

## Diferencias con la versión anterior

| Aspecto | Antes | Ahora |
|---|---|---|
| Usuario | `kiosk` (dedicado) | `lautaro` (mismo usuario del sistema) |
| Xorg | Servicio separado `xorg-kiosk.service` | Gestionado por `lightdm` |
| kiosk.sh | `/opt/solar-monitor/kiosk/kiosk.sh` | `/usr/local/bin/kiosk.sh` |
| Service Type | `simple` | `forking` |
| xsession.sh | Script de reinicio de Chromium | `exec openbox-session` (en `.xsession`) |
| Chromium flags | Sin `--incognito`, sin `--disable-gpu` | Con `--incognito`, `--disable-gpu`, `--disable-session-crashed-bubble`, `--password-store=basic` |
| Espera Grafana | No | Sí (`until curl ... /api/health`) |
| Cloudflare cookies | `persist-cookies.sh` | No necesario (incognito mode) |

---

## Archivos en Producción

| Archivo | Ubicación | Descripción |
|---|---|---|
| `kiosk.sh` | `/usr/local/bin/kiosk.sh` | Script principal del kiosco |
| `kiosk.service` | `/etc/systemd/system/kiosk.service` | Servicio systemd (Type=forking) |
| `.xsession` | `/home/lautaro/.xsession` | `exec openbox-session` |
| `lightdm.conf` | `/etc/lightdm/lightdm.conf` | Auto-login lautaro, session=openbox |
| `10-monitor.conf` | `/etc/X11/xorg.conf.d/10-monitor.conf` | Resolución 1920x1080 |
| Scripts legacy | `/opt/solar-monitor/kiosk/` | Versión anterior (no usada) |

### kiosk.sh (`/usr/local/bin/kiosk.sh`)

```bash
#!/bin/bash
while ! xdpyinfo -display :0 > /dev/null 2>&1; do
    sleep 1
done

unclutter -idle 3 -root &

xset s off
xset -dpms
xset s noblank

until curl -s -o /dev/null http://localhost:3000/api/health; do
    sleep 2
done

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
    'http://localhost:3000/d/solar-realtime/solar-monitor-tiempo-real?orgId=1&kiosk&theme=light&refresh=5s' \
    &
```

### kiosk.service (`/etc/systemd/system/kiosk.service`)

```ini
[Unit]
Description=Kiosk Mode (Chromium)
After=network-online.target
Wants=network-online.target

[Service]
Type=forking
User=lautaro
Group=lautaro
Environment=DISPLAY=:0
ExecStart=/usr/local/bin/kiosk.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### .xsession (`/home/lautaro/.xsession`)

```bash
#!/bin/bash
exec openbox-session
```

### lightdm.conf (sección relevante)

```ini
[SeatDefaults]
autologin-user=lautaro
autologin-user-timeout=0
user-session=openbox
```

---

## Requisitos de Hardware

- PC lautaro con salida HDMI o VGA conectada a un monitor
- Monitor que soporte 1920x1080 (recomendado)
- Teclado USB conectado (para salir del modo kiosco)

## Paquetes necesarios

```bash
sudo apt-get install -y xorg openbox chromium-browser unclutter lightdm
```

| Paquete | Función |
|---|---|
| `xorg` | Servidor gráfico X11 |
| `openbox` | Window manager mínimo (sin decoraciones) |
| `chromium-browser` | Navegador en modo kiosco |
| `unclutter` | Ocultar cursor del mouse después de inactividad |
| `lightdm` | Display manager con auto-login |

---

## Configuración de Monitor

### Resolución forzada (`/etc/X11/xorg.conf.d/10-monitor.conf`)

```ini
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
```

---

## Cómo funciona

1. **Arranque**: lightdm auto-login → sesión openbox → Xorg :0
2. **kiosk.service** (Type=forking) lanza `/usr/local/bin/kiosk.sh`
3. kiosk.sh espera a Xorg (`xdpyinfo`) y Grafana (`/api/health`)
4. Chromium arranca en modo kiosco con `--incognito` y flags de optimización
5. Si Chromium crashea, kiosk.service lo reinicia (`Restart=always`)

---

## Cómo salir del modo kiosco

### Atajo de teclado: `Ctrl + Alt + F1`

Cambiar a la terminal virtual tty1. El modo kiosco sigue corriendo en el display :0.

### Para volver al kiosco: `Ctrl + Alt + F7`

Volver a la sesión Xorg con Chromium.

### Para detener el kiosco completamente

```bash
sudo systemctl stop kiosk.service
```

### Para reiniciar el kiosco

```bash
sudo systemctl restart kiosk.service
```

### Para deshabilitar el kiosco permanente

```bash
sudo systemctl disable kiosk.service
```

### Para re-habilitar

```bash
sudo systemctl enable kiosk.service
```

---

## Resolución de Problemas

| Problema | Causa | Solución |
|---|---|---|
| Pantalla negra | Xorg o lightdm no arrancó | `systemctl status lightdm` |
| Chromium no aparece | kiosk.service no arrancó | `systemctl status kiosk.service` |
| Resolución incorrecta | Monitor no detectado | Agregar modelo en `10-monitor.conf` |
| Chromium crashea | Out of memory | Agregar `--disk-cache-dir=/tmp/chromium-cache` al kiosk.sh |
| Pantalla se apaga | DPMS activo | Verificar `xset -dpms` en kiosk.sh |
| No puedo salir del kiosco | No hay teclado | Conectar teclado USB y usar Ctrl+Alt+F1 |

---

## Comandos Útiles

```bash
# Ver estado del kiosco
sudo systemctl status kiosk.service

# Ver logs del kiosco
sudo journalctl -u kiosk.service -f

# Reiniciar kiosco
sudo systemctl restart kiosk.service

# Detener kiosco
sudo systemctl stop kiosk.service

# Verificar que Chromium está corriendo
pgrep -a chromium

# Matar Chromium (se reiniciará solo por kiosk.service)
sudo killall -HUP chromium-browser

# Forzar resolución (debug)
sudo -u lautaro DISPLAY=:0 xrandr --output HDMI-1 --mode 1920x1080 --rate 60

# Ver resoluciones disponibles
sudo -u lautaro DISPLAY=:0 xrandr
```

---

## Archivos locales de referencia

Los archivos de configuración del kiosk están en `Proyecto/kiosk/`:

| Archivo local | Ubicación producción | Nota |
|---|---|---|
| `kiosk.sh` | `/usr/local/bin/kiosk.sh` | Script principal |
| `kiosk.service` | `/etc/systemd/system/kiosk.service` | Servicio systemd |
| `xsession.sh` | `/home/lautaro/.xsession` | Contiene `exec openbox-session` |
| `openbox-rc.xml` | `/home/lautaro/.config/openbox/rc.xml` | Openbox fullscreen config |
| `10-monitor.conf` | `/etc/X11/xorg.conf.d/10-monitor.conf` | Resolución monitor |

> **Nota**: Los archivos en `/opt/solar-monitor/kiosk/` son la versión anterior y NO están en uso. El kiosk.sh activo está en `/usr/local/bin/kiosk.sh`.