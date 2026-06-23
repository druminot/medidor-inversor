# Última Conversación opencode — 2026-06-23

## Resumen

Se diagnosticó y reparó un corte del servicio web del monitor solar (ERR_NGROK_8012), se robusteció el sistema con auto-reparación, y se actualizó el kiosk.

---

## Problema inicial

La URL pública `https://zoning-heat-groggy.ngrok-free.dev` devolvía **ERR_NGROK_8012** (connection refused en localhost:8080). El túnel ngrok estaba vivo pero nginx no escuchaba en el puerto 8080.

## Diagnóstico

1. **Tailscale caído**: `inversor-lab` (100.66.126.91) estaba offline (last seen 11d ago)
2. **IP local de lautaro**: Descubierta en `192.168.0.137` (no 192.168.1.145 como decía la doc vieja)
3. **Acceso SSH**: `sshpass -p 'lsistem19' ssh lautaro@192.168.0.137`
4. **Grafana accesible**: Solo desde localhost:3000 (Docker bind), requirió SSH tunnel
5. **Root cause**: La config de nginx `/etc/nginx/sites-enabled/solar-monitor` tenía directivas `proxy_set_header` vacías (sin valor), causando que nginx fallara al iniciar

```nginx
# ANTES (roto):
proxy_set_header Host ;
proxy_set_header X-Real-IP ;

# DESPUÉS (correcto):
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
```

6. **Chromium kiosk**: No estaba corriendo (crasheó hace días, systemd `Type=forking` no lo reiniciaba)

## Acciones realizadas

### 1. Reparación nginx

Se restauró la config correcta en `/etc/nginx/sites-enabled/solar-monitor` y se reinició nginx:

```bash
sudo cp /tmp/solar-monitor-nginx /etc/nginx/sites-enabled/solar-monitor
sudo nginx -t && sudo systemctl restart nginx
```

Resultado: ngrok volvió a responder HTTP 200.

### 2. Archivos nuevos en el repo

| Archivo | Descripción |
|---|---|
| `Proyecto/nginx/solar-monitor` | Config de nginx como fuente de verdad en el repo |
| `Proyecto/tools/solar-healthcheck.sh` | Cron cada 5min que verifica y repara nginx, Grafana, cmd-server, ttyd, ngrok, kiosk |
| `Proyecto/kiosk/kiosk.sh` | Mejorado: limpia Singleton locks, log a `/tmp/kiosk-chromium.log` |
| `Proyecto/kiosk/kiosk.service` | Mejorado: `ExecStartPre` limpia locks, `ExecStop` mata chromium |

### 3. solar-healthcheck.sh (auto-reparación)

Script que corre cada 5 minutos vía cron y:

- Verifica que nginx escuche en 8080, si no, restaura config desde `/opt/solar-monitor/nginx/solar-monitor` y reinicia
- Verifica Grafana en 3000, cmd-server en 8023, ttyd en 8022
- Verifica que ngrok esté corriendo
- Verifica que Chromium kiosk esté activo, si no, reinicia kiosk.service
- Verifica acceso externo vía ngrok URL

Cron instalado en lautaro: `*/5 * * * * /usr/local/bin/solar-healthcheck.sh`

### 4. deploy.sh actualizado

Ahora incluye en la lista de archivos a sincronizar:

- `nginx/solar-monitor` → `/opt/solar-monitor/nginx/solar-monitor`
- `kiosk/kiosk.sh` → `/usr/local/bin/kiosk.sh`
- `kiosk/kiosk.service` → `/etc/systemd/system/kiosk.service`
- `tools/solar-healthcheck.sh` → `/usr/local/bin/solar-healthcheck.sh`

Y al final del deploy: restaura config nginx, reload, daemon-reload kiosk, configura cron.

### 5. Dashboard comparado

Se descargaron los 4 dashboards desde Grafana de producción y se compararon con el repo:

- `solar-realtime` (versión 64): **idéntico** en contenido (solo difiere el timestamp de rango de tiempo)
- `solar-academico`: **idéntico**
- `solar-diagnostico`: **idéntico**
- `solar-historico`: **idéntico**

No se requirieron cambios en los dashboards.

### 6. Kiosk reiniciado

Chromium se relanzó en modo kiosk con la URL correcta:
```
http://localhost:3000/d/solar-realtime/solar-monitor-tiempo-real?orgId=1&kiosk&theme=light&refresh=5s
```

## Credenciales de acceso

| Servicio | URL | Auth |
|---|---|---|
| Grafana (público) | `https://zoning-heat-groggy.ngrok-free.dev/` | Anonymous viewer |
| Grafana admin | `http://192.168.0.137:3000` (via SSH tunnel) | admin / gaJEXcvNct4HvGrGqBkLE5w8-FzYDKqZ |
| cmd-server | `https://zoning-heat-groggy.ngrok-free.dev/cmd/?cmd=...` | lautaro / lsistem19 |
| SSH | `ssh lautaro@192.168.0.137` | lautaro / lsistem19 |
| Tailscale | `100.66.126.91` | (offline 11 días) |

## URL del kiosk remoto

```
https://zoning-heat-groggy.ngrok-free.dev/d/solar-realtime/solar-monitor-tiempo-real?orgId=1&kiosk&theme=light&refresh=5s
```

## Git

Commit: `8ae7ba7` — "fix: robustecer nginx + kiosk + healthcheck auto-reparacion"
Pushed a `origin/main` y a prod `/opt/solar-monitor/`

## Lecciones aprendidas

1. **La config de nginx no estaba en el repo** — si se corrompía, no había forma de restaurarla automáticamente. Ahora está en `Proyecto/nginx/solar-monitor`.
2. **El kiosk service era `Type=forking` sin watchdog** — si Chromium crasheaba, systemd no lo reiniciaba. Ahora tiene `ExecStop` que mata chromium y `Restart=always`.
3. **No había monitoreo automático** — nginx podía estar caído días sin que nadie se diera cuenta. Ahora `solar-healthcheck.sh` lo verifica cada 5 minutos.
4. **La IP local de lautaro cambió** — era `192.168.1.145` en la doc vieja, ahora es `192.168.0.137`.
5. **Chromium snap requiere limpiar Singleton locks** — si no se limpian, "Se está abriendo en una sesión de navegador existente" y no arranca.