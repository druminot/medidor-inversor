# Infraestructura — Notebook Lenovo "lautuaro"

> **ESTADO: OPERATIVO** — Todo está corriendo. No modificar sin necesidad. Los servicios systemd (ttyd, cmd-server) están habilitados. SunVision y cloudflared fueron eliminados.

## Acceso

| Parámetro | Valor |
|---|---|
| Hostname | lautuaro |
| IP Local (Power Electronics) | 192.168.0.137 |
| IP Local (RuminotRoa) | 192.168.1.145 |
| IP Tailscale | 100.66.126.91 |
| Dominio | lautuaro.tail6e64d5.ts.net |
| Usuario | lautaro |
| Password | lsistem19 |
| SSH | Habilitado (password + key) |

### Métodos de acceso remoto

| Método | Red | Funciona en "Power Electronics" | Notas |
|---|---|---|---|
| SSH local | Ambas | No (puerto entrante bloqueado) | `ssh lautaro@192.168.0.137` |
| Tailscale | RuminotRoa | No (controlplane bloqueado) | `ssh lautaro@100.66.126.91` |
| Chrome Remote Desktop | Ambas | **Sí** (sale por 443) | PIN: 121212, cuenta: druminot.dr@gmail.com |
| **ttyd + ngrok** | Ambas | **Sí** (sale por 443) | URL dinámica, credenciales: lautaro/lsistem19 |
| **cmd API + ngrok** | Ambas | **Sí** (sale por 443) | Ejecución remota de comandos via HTTP |

> **Nota**: "Power Electronics" bloquea todo tráfico entrante y Tailscale. Solo puertos 80/443 salientes funcionan. ngrok funciona porque usa conexiones salientes HTTPS.

### ngrok + nginx (acceso remoto unificado)

Un solo túnel ngrok expone todo a través de nginx reverse proxy en puerto 8080:

| Servicio | URL local | URL remota | Auth |
|---|---|---|---|
| Grafana | localhost:3000 | `https://XXXX.ngrok-free.dev/` | Grafana login |
| Terminal web | localhost:8022 | `https://XXXX.ngrok-free.dev/terminal/` | lautaro/lsistem19 |
| SunVision (WinXP VM) | localhost:8006 | `https://XXXX.ngrok-free.dev/sunvision/` | Sin auth |
| Ejecutar comandos | localhost:8023 | `https://XXXX.ngrok-free.dev/cmd/?cmd=COMANDO` | lautaro/lsistem19 |

- **ttyd**: servidor de terminal web en puerto 8022 (sin auth propia)
- **cmd-server.py**: servidor HTTP en puerto 8023 que ejecuta comandos y devuelve JSON (`/cmd?cmd=COMANDO`)
- **nginx**: reverse proxy en puerto 8080, combina todos los servicios, basic auth para `/terminal/` y `/cmd/`
- **ngrok**: túnel HTTP que expone nginx (8080) a internet vía HTTPS saliente
- **ngrok cuenta**: druminot.dr@gmail.com (authtoken configurado)
- **URL**: dinámica (cambia cada reinicio de ngrok), verificar con `curl -s http://127.0.0.1:4040/api/tunnels`

#### Iniciar servicios

```bash
# 1. ttyd (terminal web)
nohup ttyd -p 8022 -W bash > /home/lautaro/ttyd.log 2>&1 &
# 2. cmd-server.py (ejecución remota de comandos)
nohup python3 /home/lautaro/cmd-server.py > /home/lautaro/cmd-server.log 2>&1 &
# 3. ngrok (túnel HTTPS)
nohup ngrok http 8080 --log=stdout > /home/lautaro/ngrok.log 2>&1 &
# 4. Ver URL pública
curl -s http://127.0.0.1:4040/api/tunnels | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["tunnels"][0]["public_url"])'
```

#### Ejecutar comandos remotamente

```bash
# Ejemplo: obtener hostname
curl -s -u lautaro:lsistem19 -H "ngrok-skip-browser-warning: true" \
  "https://XXXX.ngrok-free.dev/cmd/?cmd=hostname"
# Respuesta: {"exitcode": 0, "stdout": "lautuaro\n", "stderr": ""}

# Ejemplo: ver containers Docker
curl -s -u lautaro:lsistem19 -H "ngrok-skip-browser-warning: true" \
  "https://XXXX.ngrok-free.dev/cmd/?cmd=docker+ps"
```

- **Limitaciones**: URL cambia al reiniciar ngrok (plan gratis); ngrok TCP requiere tarjeta; wstunnel para SSH no funciona a través de nginx (ngrok fuerza H2)

### Chrome Remote Desktop

- **Cuenta Google**: druminot.dr@gmail.com
- **PIN**: 121212
- **Acceso**: https://remotedesktop.google.com/access
- **Estado**: funciona en TODAS las redes incluyendo "Power Electronics"

---

## VPN Tailscale

| Parámetro | Valor |
|---|---|
| Versión | 1.98.4 |
| Cuenta | daniel.ruminot.moscoso@gmail.com |
| Estado | Funciona solo en RuminotRoa |

> **ADVERTENCIA**: Tailscale NO funciona en red "Power Electronics" (controlplane.tailscale.com bloqueado). Si lautuaro estaba en Power Electronics y se cambia a RuminotRoa, ejecutar `tailscale down` antes de cambiar red, luego `tailscale up`. Si se congela, matar proceso con `killall tailscaled`.

---

## WiFi (wlp1s0)

### Redes configuradas (netplan)

| Red | SSID | Password | Restricciones |
|---|---|---|---|
| Prioridad 1 | Power Electronics | 1sistem23 | Bloquea Tailscale, SSH entrante, Cloudflare 7844; solo 80/443 salientes |
| Prioridad 2 | RuminotRoa | Blackfox123 | Sin restricciones |

### Configuración persistente aplicada

- `managed=true` en `/etc/NetworkManager/NetworkManager.conf`
- `wifi.powersave = 2` en `/etc/NetworkManager/conf.d/default-wifi-powersave-on.conf`
- rfkill: sin bloques (soft/hard)

---

## Suspensión (deshabilitada)

| Target | Estado |
|---|---|
| sleep.target | Masked |
| suspend.target | Masked |
| hibernate.target | Masked |
| hybrid-sleep.target | Masked |

### Logind (`/etc/systemd/logind.conf.d/no-suspend.conf`)

```ini
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
IdleAction=ignore
```

> **Nota**: La suspensión está deshabilitada porque el PC debe operar 24/7. Esto es compatible con el modo kiosco (ver [[14_PANTALLA_KIOSK]]).

---

## Docker (pendiente de instalación)

### Instalación

```bash
# Agregar repositorio oficial de Docker
sudo apt-get update
sudo apt-get install ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Agregar usuario al grupo docker
sudo usermod -aG docker lautaro

# Verificar
docker --version
docker compose version
```

### Estructura de directorios

```
/opt/solar-monitor/
  ├── modbus-reader/        # Daemon C (libmodbus)
  │   ├── src/               # Código fuente C
  │   ├── Makefile
  │   └── Dockerfile

  ├── grafana/
  │   ├── provisioning/      # Datasources y dashboards auto
  │   └── dashboards/         # JSON de dashboards
  ├── db/
  │   └── init.sql            # Esquema TimescaleDB
  ├── cloudflared/
  │   └── config.yml
  ├── docker-compose.yml
  ├── .env                    # Passwords y tokens (NO commitear)
  └── backups/                # Backups de DB
```

---

## Regla udev para adaptadores USB-Serial

### Archivo: `/etc/udev/rules.d/99-serial.rules`

```udev
# Adaptador USB-RS232 CH340 (Riello H.P.6065REL-D)
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="inverter-serial", GROUP="dialout", MODE="0666"

# Adaptador USB-RS232 PL2303 (alternativo)
SUBSYSTEM=="tty", ATTRS{idVendor}=="067b", ATTRS{idProduct}=="2303", SYMLINK+="inverter-serial", GROUP="dialout", MODE="0666"

# Adaptador USB-RS485 FT232 (alternativo)
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", SYMLINK+="inverter-serial", GROUP="dialout", MODE="0666"
```

> **Nota**: Todos los adaptadores crean el symlink `/dev/inverter-serial`. Actualmente conectado: PL2303 en `/dev/ttyUSB1` (CH340 fue desconectado).

---

## libmodbus (dependencia del daemon C)

```bash
sudo apt-get install libmodbus-dev libpq-dev gcc make cmake
```

---

## Herramientas instaladas

| Herramienta | Versión | Ruta | Propósito |
|---|---|---|---|
| Docker + Compose | latest | /usr/bin/docker | Stack de contenedores |
| libmodbus | apt | /usr/lib | Comunicación Modbus RTU |
| cloudflared | 2026.6.0 | /usr/local/bin/cloudflared | Túnel Cloudflare (backup) |
| ngrok | 3.39.7 | /usr/local/bin/ngrok | Túnel HTTP para acceso remoto |
| ttyd | 1.7.7 | /usr/local/bin/ttyd | Terminal web |
| wstunnel | 10.5.5 | /usr/local/bin/wstunnel | Túnel WebSocket para SSH (requiere ngrok en puerto 2222) |
| autossh | apt | /usr/bin/autossh | SSH persistente (backup) |
| noVNC + TigerVNC | apt | /usr/share/novnc/ | VNC web (requiere VNC server corriendo) |
| Chrome Remote Desktop | - | /opt/google/chrome-remote-desktop/ | Escritorio remoto Google |
| nginx | 1.28.3 | /usr/sbin/nginx | Reverse proxy (Grafana+terminal+cmd+SunVision) |
| w3m | apt | /usr/bin/w3m | Navegador texto (para debugging desde terminal) |

---

## Cloudflare Tunnel

Ver detalles en [[11_CLOUDFLARE_TUNNEL]].

Resumen:
- Dominio: `lautuaro.tail6e64d5.ts.net` → Grafana (puerto 3000)
- **NO funciona** en red "Power Electronics" (puerto 7844 bloqueado)
- Se ejecuta como container Docker
- Token: `eyJhIjoiZWMyZmVhNjRkMzUxNTliYzcwNGRhMGZlNjkyMmRkZjEiLCJ0IjoiOWQ2OTYxMDctM2RmMi00MDc5LWEwMDktMTk1M2FkZGJhZjYwIiwicyI6IlVIc0cyMXdxWjFUQXJzWU9QbHNWYWkybFl0VjRKY1dzU0c0a294T2dsT0xqajlJSDlENDUzS0srbDNVV25tWXMxeEFJdHU1TGRKMHMxYndDMHRPVCtnPT0ifQ==`

---

## Comandos útiles

```bash
# SSH via red local
ssh lautaro@192.168.0.137    # Power Electronics
ssh lautaro@192.168.1.145    # RuminotRoa

# SSH via Tailscale (solo RuminotRoa)
ssh lautaro@100.66.126.91

# Ejecutar comandos remotamente via HTTP (funciona en TODAS las redes)
curl -s -u lautaro:lsistem19 -H "ngrok-skip-browser-warning: true" \
  "https://XXXX.ngrok-free.dev/cmd/?cmd=hostname"

# Chrome Remote Desktop (funciona en TODAS las redes)
# Acceder desde: https://remotedesktop.google.com/access
# PIN: 121212

# Iniciar servicios remotos
nohup ttyd -p 8022 -W bash > /home/lautaro/ttyd.log 2>&1 &
nohup python3 /home/lautaro/cmd-server.py > /home/lautaro/cmd-server.log 2>&1 &
nohup ngrok http 8080 --log=stdout > /home/lautaro/ngrok.log 2>&1 &
# Ver URL pública
curl -s http://127.0.0.1:4040/api/tunnels | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["tunnels"][0]["public_url"])'

# Estado WiFi
nmcli device status

# Estado Tailscale (solo RuminotRoa)
sudo tailscale status

# Verificar suspensión deshabilitada
systemctl status sleep.target suspend.target hibernate.target

# Verificar adaptador USB-Serial
ls -la /dev/inverter-serial
dmesg | grep ttyUSB

# Docker
docker compose -f /opt/solar-monitor/docker-compose.yml ps
docker compose -f /opt/solar-monitor/docker-compose.yml logs -f modbus-reader

# Reiniciar todo
docker compose -f /opt/solar-monitor/docker-compose.yml restart

# Verificar Tailscale Funnel (solo RuminotRoa)
tailscale status
curl -I https://lautuaro.tail6e64d5.ts.net
```