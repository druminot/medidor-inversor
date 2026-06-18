# Cloudflare Tunnel — Dominio y Acceso

> **ESTADO: NO USADO** — Cloudflare Tunnel fue descartado porque el puerto 7844 está bloqueado en la red "Power Electronics" de la UdeC. El acceso remoto se hace exclusivamente via ngrok + nginx. Este documento se conserva como referencia en caso de que se necesite en el futuro.

## Objetivo

Exponer el sistema de monitoreo en `https://lautuaro.tail6e64d5.ts.net` sin abrir puertos entrantes en el PC. Funciona en la red de la Universidad de Concepción porque solo necesita HTTPS saliente (puerto 443), igual que Chrome Remote Desktop.

---

## Por qué Cloudflare Tunnel

| Solución | Funciona en UdeC? | Dominio real? | TLS? | Config |
|---|---|---|---|---|
| **Cloudflare Tunnel** | **Sí** (HTTPS saliente) | **Sí** | **Sí** | Moderada |
| Tailscale Funnel | No probado | Subdominio ts.net | Sí | Simple |
| Port Forwarding | No (bloqueado) | Requiere IP pública | Manual | Impossible |
| VPN propia | No (bloqueado) | Requiere IP pública | Manual | Complex |
| ngrok | Sí | Subdominio ngrok.io | Sí | Simple pero limitado |

**Decisión**: Cloudflare Tunnel porque:
1. Solo necesita conexión HTTPS saliente (puerto 443)
2. Chrome Remote Desktop funciona en la UdeC, lo que confirma que HTTPS saliente está permitido
3. Dominio real: `lautaro.elprobedor.com`
4. TLS automático (no hay que configurar certificados)
5. Cloudflare Access para autenticación por email @udec.cl
6. Rate limiting y DDoS protection incluidos
7. Gratuito para uso no-comercial

---

## Arquitectura de Acceso

```
[Navegador del Doctor/Alumno]
        │
        │ https://lautuaro.tail6e64d5.ts.net
        ▼
[Cloudflare Edge Network]
        │ Cloudflare Access: ¿Email @udec.cl?
        │ (primer acceso: envía código por email)
        ▼
[Cloudflare Tunnel] (conexión HTTPS saliente desde lautaro)
        │
        ▼
[PC lautaro → localhost:3000 (Grafana)]
```

---

## Prerequisitos

1. Dominio `elprobedor.com` registrado en Cloudflare
2. Cuenta de Cloudflare (gratuita)
3. `cloudflared` instalado en lautaro

---

## Paso 1: Instalar cloudflared en lautaro

```bash
# Descargar e instalar cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /tmp/cloudflared
sudo mv /tmp/cloudflared /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared

# Verificar
cloudflared --version
```

---

## Paso 2: Crear el Tunnel

```bash
# Login a Cloudflare (abre navegador para autorizar)
cloudflared tunnel login

# Crear el tunnel
cloudflared tunnel create solar-lab

# Anotar el tunnel ID (se muestra en la salida)
# Ejemplo: tunnel ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## Paso 3: Configurar DNS en Cloudflare

```bash
# Crear registro CNAME para lautaro.elprobedor.com
cloudflared tunnel route dns solar-lab lautaro.elprobedor.com
```

Alternativa manual: en el dashboard de Cloudflare → DNS → agregar:
- Tipo: CNAME, Nombre: `lautaro`, Destino: `<tunnel-id>.cfargotunnel.com`

---

## Paso 4: Configurar el Tunnel

Archivo: `/opt/solar-monitor/cloudflared/config.yml`

```yaml
tunnel: solar-lab
credentials-file: /root/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: lautaro.elprobedor.com
    service: http://localhost:3000
  - service: http_status:404
```

---

## Paso 5: Probar el Tunnel

```bash
# Probar manualmente
cloudflared tunnel --config /opt/solar-monitor/cloudflared/config.yml run

# Verificar desde otro dispositivo
curl -I https://lautaro.elprobedor.com
```

---

## Paso 6: Configurar Cloudflare Access

En el dashboard de Cloudflare → Zero Trust → Access → Applications:

### Aplicación: lautaro.elprobedor.com (Grafana)

1. Crear aplicación
2. Nombre: "Solar Monitor Dashboard"
3. Dominios: `lautaro.elprobedor.com`
4. Policy:
   - Name: "Email UdeC"
   - Action: Allow
   - Include: Email domains → `udec.cl`, `ing.udec.cl`, `dci.udec.cl`
   - También agregar: `daniel.ruminot.moscoso@gmail.com` (admin)
5. Authentication: Email one-time PIN (sin password)

### Flujo de acceso para alumnos

1. Abrir `https://lautuaro.tail6e64d5.ts.net`
2. Cloudflare Access pide email
3. Ingresar email @udec.cl
4. Reciben código de verificación por email (solo la primera vez)
5. Ingresan el código
6. Acceden al dashboard de Grafana (modo Viewer, sin login adicional)

---

## Integración con Docker Compose

```yaml
# En docker-compose.yml, agregar:

cloudflared:
  image: cloudflare/cloudflared:latest
  restart: unless-stopped
  command: tunnel --no-autoupdate run
  environment:
    - TUNNEL_TOKEN=${TUNNEL_TOKEN}
```

El `TUNNEL_TOKEN` se obtiene del dashboard de Cloudflare:
1. Zero Trust → Access → Tunnels → solar-lab → Configure
2. Copiar el token
3. Agregar al archivo `.env`:

```env
TUNNEL_TOKEN=eyJhIjoixxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## Renovación Automática

Cloudflare Tunnel renueva los certificados TLS automáticamente. No hay que hacer nada.

El container `cloudflared` se reinicia automáticamente si falla (`restart: unless-stopped`).

---

## Verificación

```bash
# Verificar que el tunnel está corriendo
docker compose logs cloudflared

# Verificar desde fuera
curl -I https://lautaro.elprobedor.com
# Debe responder: HTTP/2 200

# Verificar acceso con email UdeC
# Abrir navegador en otro dispositivo → https://lautaro.elprobedor.com
# Debe pedir email → ingresar @udec.cl → recibir código → acceder al dashboard
```

---

## Troubleshooting

| Problema | Causa | Solución |
|---|---|---|
| `lautaro.elprobedor.com` no resuelve | DNS no propagado | Esperar 5-10 min, verificar CNAME en Cloudflare |
| Error 502 | Grafana no está corriendo | `docker compose ps`, `docker compose logs grafana` |
| Error 403 | Cloudflare Access bloqueando | Verificar que el email sea @udec.cl |
| Error "connection refused" | Tunnel no conectado | `docker compose logs cloudflared`, verificar TUNNEL_TOKEN |
| No recibo código por email | Spam | Revisar carpeta de spam, verificar dominio en Cloudflare Access |
| Certificado TLS error | Cloudflare renueva automáticamente | Esperar o forzar renovación en dashboard |

---

## Comandos Útiles

```bash
# Ver info del tunnel
cloudflared tunnel info solar-lab

# Listar tunnels
cloudflared tunnel list

# Verificar DNS
dig lautaro.elprobedor.com

# Reiniciar tunnel
docker compose restart cloudflared

# Ver logs en tiempo real
docker compose logs -f cloudflared
```