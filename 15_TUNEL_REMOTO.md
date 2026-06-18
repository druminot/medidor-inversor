# Tunel Remoto — Acceso desde fuera de la red

> **ESTADO: OPERATIVO** — El túnel ngrok + nginx + ttyd + cmd-server está en producción. Los servicios systemd (ttyd, cmd-server) están habilitados. Las rutas `/sunvision/` y `/v1sunvision/` fueron eliminadas del nginx (SunVision ya no corre).

## Objetivo

Acceder a Grafana, terminal web, VM Windows XP y ejecución remota de comandos desde cualquier red (incluyendo "Power Electronics" que bloquea todo excepto HTTP/HTTPS saliente), usando ngrok + nginx + ttyd + cmd-server.

## URLs de acceso

| Servicio | URL local | URL remota (ngrok) | Auth |
|---|---|---|---|
| Grafana | http://localhost:3000 | https://XXXX.ngrok-free.dev/ | Grafana login |
| Terminal web | http://localhost:8022 | https://XXXX.ngrok-free.dev/terminal/ | lautaro/lsistem19 |
| SunVision WinXP VM | http://localhost:8006 | https://XXXX.ngrok-free.dev/sunvision/ | Sin auth |
| SunVision Docker | http://localhost:8007 | https://XXXX.ngrok-free.dev/v1sunvision/ | Sin auth |
| Ejecutar comandos | http://localhost:8023/cmd | https://XXXX.ngrok-free.dev/cmd/?cmd=COMANDO | lautaro/lsistem19 |

> La URL de ngrok cambia cada vez que se reinicia. Ver "Obtener URL pública" más abajo.

---

## Arquitectura

```
[Navegador externo / API call]
        │
        │ HTTPS saliente (puerto 443)
        ▼
[ngrok.com] → URL pública https://XXXX.ngrok-free.dev
        │
        │ túnel HTTPS
        ▼
[lautuaro:8080] → nginx reverse proxy
        │
        ├── /            → Grafana (localhost:3000)
        ├── /terminal/    → ttyd (localhost:8022) con basic auth
        ├── /sunvision/  → Windows XP VM (localhost:8006)
        └── /cmd/         → cmd-server.py (localhost:8023) con basic auth
```

Funciona en redes restrictivas porque **solo usa HTTPS saliente en puerto 443**, igual que Chrome Remote Desktop.

---

## Credenciales

| Servicio | Usuario | Password |
|---|---|---|
| Terminal web (nginx basic auth) | lautaro | lsistem19 |
| Ejecutar comandos (nginx basic auth) | lautaro | lsistem19 |
| Grafana admin | admin | 8P2Y7juWdzSc1bnCOP55uaL |
| ngrok | druminot.dr@gmail.com | (cuenta Google) |

---

## Prerequisitos instalados

| Herramienta | Versión | Instalación |
|---|---|---|
| ngrok | 3.39.7 | `/usr/local/bin/ngrok` |
| ttyd | 1.7.7 | `/usr/local/bin/ttyd` |
| nginx | 1.28.3 | `apt install nginx` |
| apache2-utils | - | `apt install apache2-utils` (para htpasswd) |
| w3m | apt | `apt install w3m` (navegador texto) |
| cmd-server.py | - | `/home/lautaro/cmd-server.py` (servidor HTTP de comandos) |

---

## Paso 1: Configurar ngrok (una sola vez)

```bash
# Instalar ngrok
curl -sL -o /tmp/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64
# (descargar de github y copiar a /usr/local/bin/ttyd)

# Autenticar ngrok (token desde https://dashboard.ngrok.com/get-started/your-authtoken)
ngrok config add-authtoken TU_TOKEN_AQUI
```

---

## Paso 2: Configurar nginx (una sola vez)

### Crear archivo de passwords

```bash
sudo htpasswd -cb /etc/nginx/.htpasswd lautaro lsistem19
```

### Configuración de nginx

Archivo: `/etc/nginx/sites-available/solar-monitor`

```nginx
server {
    listen 8080;
    server_name _;

    # Grafana - sin auth (Grafana tiene su propio login)
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Terminal web - con basic auth
    location /terminal/ {
        auth_basic "Restricted";
        auth_basic_user_file /etc/nginx/.htpasswd;
        rewrite ^/terminal/(.*)$ /$1 break;
        proxy_pass http://127.0.0.1:8022;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # SunVision (Windows XP VM)
    location /sunvision/ {
        proxy_pass http://127.0.0.1:8006/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # Ejecutar comandos - con basic auth
    location /cmd/ {
        auth_basic "Restricted";
        auth_basic_user_file /etc/nginx/.htpasswd;
        proxy_pass http://127.0.0.1:8023/cmd;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Habilitar sitio y reiniciar nginx

```bash
sudo ln -sf /etc/nginx/sites-available/solar-monitor /etc/nginx/sites-enabled/solar-monitor
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx
```

---

## Paso 3: Iniciar servicios (cada vez que se reinicia el PC)

```bash
# 1. Iniciar ttyd (terminal web, sin auth propia - la pone nginx)
nohup ttyd -p 8022 -W bash > /home/lautaro/ttyd.log 2>&1 &

# 2. Iniciar cmd-server.py (ejecución remota de comandos)
nohup python3 /home/lautaro/cmd-server.py > /home/lautaro/cmd-server.log 2>&1 &

# 3. Iniciar ngrok (túnel HTTPS)
nohup ngrok http 8080 --log=stdout > /home/lautaro/ngrok.log 2>&1 &

# 4. Obtener URL pública
sleep 4
curl -s http://127.0.0.1:4040/api/tunnels | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["tunnels"][0]["public_url"])'
```

---

## Paso 4: Acceder desde fuera

1. Abrir la URL que devolvió el paso 3 (ej: `https://zoning-heat-groggy.ngrok-free.dev`)
2. Primera vez: ngrok muestra una página de advertencia — hacer clic en "Visit Site"
3. **Grafana**: ir a la raíz (`/`)
4. **Terminal web**: ir a `/terminal/` — pedirá usuario/clave (`lautaro` / `lsistem19`)
5. **SunVision (WinXP)**: ir a `/sunvision/` — escritorio remoto de Windows XP
6. **Ejecutar comandos**: `https://URL/cmd/?cmd=COMANDO` — devuelve JSON con exitcode, stdout, stderr (auth: lautaro/lsistem19)

---

## Verificación

```bash
# Verificar que todo está corriendo
ps aux | grep -E 'ttyd|ngrok|nginx' | grep -v grep

# Ver URL pública de ngrok
curl -s http://127.0.0.1:4040/api/tunnels | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["tunnels"][0]["public_url"])'

# Verificar nginx localmente
curl -sI http://localhost:8080/ | head -3          # Grafana
curl -sI http://localhost:8080/terminal/ | head -3  # Terminal (debe dar 401)
curl -sI http://localhost:8080/cmd/?cmd=echo+test | head -3  # Cmd (debe dar 401 sin auth)

# Ejecutar comando remotamente
curl -s -u lautaro:lsistem19 "http://localhost:8080/cmd/?cmd=hostname"
# Respuesta: {"exitcode": 0, "stdout": "lautuaro\n", "stderr": ""}
```

---

## Detener servicios

```bash
pkill ttyd
pkill -f cmd-server.py
pkill ngrok
sudo systemctl stop nginx
```

---

## Hacerlo persistente (systemd)

### Servicio ttyd

Archivo: `/etc/systemd/system/ttyd.service`

```ini
[Unit]
Description=Terminal web (ttyd)
After=network.target

[Service]
ExecStart=/usr/local/bin/ttyd -p 8022 -W bash
Restart=always
RestartSec=5
User=lautaro

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable ttyd
sudo systemctl start ttyd
```

### Servicio cmd-server

Archivo: `/etc/systemd/system/cmd-server.service`

```ini
[Unit]
Description=Remote command execution server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/lautaro/cmd-server.py
Restart=always
RestartSec=5
User=lautaro

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable cmd-server
sudo systemctl start cmd-server
```

### Servicio ngrok

Archivo: `/etc/systemd/system/ngrok.service`

```ini
[Unit]
Description=ngrok tunnel
After=network.target

[Service]
ExecStart=/usr/local/bin/ngrok http 8080 --log=stdout
Restart=always
RestartSec=10
User=lautaro

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable ngrok
sudo systemctl start ngrok
```

> **Nota**: nginx ya se habilitó con `systemctl enable nginx` en el paso 2.

---

## Troubleshooting

| Problema | Causa | Solución |
|---|---|---|
| ngrok muestra "ERR_NGROK_8013" | Cuenta sin tarjeta para TCP | Usar HTTP (gratis sin tarjeta) |
| Terminal dice "reconectar" | ttyd no corre o auth conflictivo | Verificar `ps aux \| grep ttyd`; no usar `-c` en ttyd si nginx maneja auth |
| URL no responde | ngrok no conectó | `curl -s http://127.0.0.1:4040/api/tunnels`; reiniciar ngrok |
| 401 en /terminal/ | nginx basic auth funciona | Ingresar lautaro/lsistem19 |
| Grafana no carga | Container no corre | `docker compose ps`; `docker compose restart grafana` |
| Página ngrok "Visit Site" | Plan gratis | Solo aparece una vez por navegador; usar header `ngrok-skip-browser-warning: true` |

---

## Alternativas consideradas

### SSH sobre wstunnel (para acceso programático)

wstunnel permite tunelar SSH sobre WebSocket. Funciona cuando ngrok apunta directo al wstunnel server (sin nginx).

**Modo SSH** (ngrok en puerto 2222 — SIN acceso web):

```bash
# En lautuaro: iniciar wstunnel server + ngrok apuntando a wstunnel
nohup wstunnel server ws://0.0.0.0:2222 > /home/lautaro/wstunnel.log 2>&1 &
pkill ngrok; sleep 1
nohup ngrok http 2222 --log=stdout > /home/lautaro/ngrok.log 2>&1 &
sleep 4
curl -s http://127.0.0.1:4040/api/tunnels | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["tunnels"][0]["public_url"])'

# Desde cualquier PC: conectar SSH vía wstunnel
wstunnel client -H "ngrok-skip-browser-warning: true" -L tcp://2222:127.0.0.1:22 "wss://XXXX.ngrok-free.dev"
ssh -p 2222 lautaro@127.0.0.1
```

**Modo Web** (ngrok en puerto 8080 — SIN SSH túnel):

```bash
# En lautuaro: ngrok apuntando a nginx (web)
pkill ngrok; sleep 1
nohup ngrok http 8080 --log=stdout > /home/lautaro/ngrok.log 2>&1 &
```

> **Importante**: ngrok gratis solo permite 1 túnel. Para tener SSH + Web simultáneos, necesitas ngrok de pago o agregar tarjeta para TCP.

### Limitaciones conocidas

- ngrok gratis: solo 1 túnel HTTP; URL cambia al reiniciar; página de advertencia
- wstunnel + nginx: no funciona (ngrok fuerza H2, nginx convierte a H1 sin Upgrade header)
- wstunnel directo (ngrok → wstunnel sin nginx): sí funciona para SSH
- localhost.run: no soporta WebSocket (503), inestable, se desconecta
- Para tener SSH + Web simultáneos: se necesita ngrok de pago o tarjeta de crédito

---

## Alternativas consideradas

| Solución | Pros | Contras |
|---|---|---|
| **ngrok HTTP** (web) | Gratis, sin tarjeta, simple | URL cambia al reiniciar, página de advertencia, 1 túnel |
| **ngrok HTTP + wstunnel** (SSH) | SSH programático, funciona en redes restrictivas | Requiere cambiar ngrok al puerto 2222 (pierde web) |
| localhost.run | Gratis, sin instalación (solo SSH) | URL aleatoria, inestable, no soporta WebSocket |
| ngrok TCP | IP:puerto fijo, SSH directo | Requiere tarjeta de crédito (no cobra) |
| Cloudflare Tunnel | Dominio fijo, sin advertencia | Puerto 7844 bloqueado en "Power Electronics" |
| Tailscale Funnel | Dominio fijo | No funciona en "Power Electronics" (controlplane bloqueado) |