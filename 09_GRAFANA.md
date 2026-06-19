# Grafana — Dashboards

> **ESTADO: OPERATIVO** — Dashboard de tiempo real con filtro dinámico de amanecer usando `sunrise_concepcion()`. El rango de tiempo se actualiza automáticamente cada día via cron. Accesible desde `https://zoning-heat-groggy.ngrok-free.dev` (redirige al dashboard de tiempo real).

## Objetivo

Configurar Grafana con dashboards para visualizar datos del inversor Riello H.P.6065REL-D en tiempo real e histórico. Accesible desde `https://zoning-heat-groggy.ngrok-free.dev`.

---

## Configuración de Datasource

### Provisioning automático (`grafana/provisioning/datasources/datasource.yml`)

```yaml
apiVersion: 1

datasources:
  - name: TimescaleDB
    type: grafana-postgresql-datasource
    uid: timescaledb
    url: timescaledb:5432
    database: solar_monitor
    user: grafana_reader
    secureJsonData:
      password: ${GRAFANA_READER_PASSWORD}
    jsonData:
      sslmode: disable
      maxOpenConns: 10
      maxIdleConns: 5
      connMaxLifetime: 14400
      postgresVersion: 1600
      timescaledb: true
    isDefault: true
    editable: true
```

> **NOTA IMPORTANTE**: El `uid: timescaledb` es fijo y debe coincidir en todos los dashboards JSON. Los dashboards provisionados no se pueden modificar via API de Grafana — solo editando los archivos JSON en disco y reiniciando el container.

---

## Provisioning de Dashboards (`grafana/provisioning/dashboards/dashboard.yml`)

```yaml
apiVersion: 1

providers:
  - name: Solar Monitor
    orgId: 1
    folder: Solar Monitor
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: false
```

---

## Dashboard 1: Tiempo Real (`realtime.json`)

**Nombre**: Solar Monitor - Tiempo Real
**UID**: `solar-realtime`
**Refresh**: 5 segundos
**Rango**: Dinámico — desde `sunrise_concepcion(current_date)` hasta `now`

### Filtro dinámico de amanecer

Las 7 queries de timeseries usan `sunrise_concepcion(current_date)` para mostrar datos solo desde el amanecer en Concepción (-36.82°S, -73.05°W). Ejemplo:

```sql
SELECT $__time(bucket), AVG(COALESCE(pac,0)) as ac, AVG(COALESCE(ppv_total,0)) as dc
FROM (SELECT time_bucket('5m', time) AS bucket, pac, ppv_total FROM realtime
      WHERE $__timeFilter(time) AND inverter_id=1 AND is_stale = false
            AND time >= sunrise_concepcion(current_date)) t
GROUP BY bucket ORDER BY bucket
```

El rango de tiempo del dashboard (`time.from`) se actualiza automáticamente cada día a las 05:00 via cron (`/tmp/update_sunrise_dashboard.sh`), que:
1. Consulta `sunrise_concepcion(current_date)` desde PostgreSQL
2. Actualiza el campo `time.from` del JSON con el timestamp UTC del amanecer
3. Reinicia Grafana para que re-provisione el dashboard

El dashboard es **provisionado** (`editable: false`) para que con cada F5 se resetee al rango del amanecer.

### Paneles (21 paneles)

| # | Panel | Tipo | Posición (x,y,w,h) | Descripción |
|---|---|---|---|---|
| 60 | Período | stat | (0,0,5,4) | Noche/Nublado/Produciendo basado en pac y vpv |
| 50 | Señal Datos | stat | (5,0,5,4) | Segundos desde última lectura real |
| 51 | Estado Lector | stat | (10,0,5,4) | OK/Sin Señal basado en is_stale |
| 52 | Estado Inversor | stat | (15,0,5,4) | Wait/Normal/Fault basado en status |
| 53 | Temperatura | stat | (20,0,4,4) | °C con thresholds |
| 1 | Potencia AC | gauge | (0,4,8,6) | 0-5000W |
| 20 | Potencia DC Total | gauge | (8,4,8,6) | 0-5000W |
| 3 | Voltaje Red | gauge | (16,4,8,6) | 0-300V |
| 4 | Frecuencia | stat | (0,10,8,4) | Hz con thresholds 49.5-50.5 |
| 14 | Horas Op. | stat | (8,10,8,4) | Horas de operación total |
| 55 | Lecturas (1h) | stat | (16,10,8,4) | Contador lecturas reales última hora |
| 30 | Voltaje PV (MPPT) | stat | (0,14,8,4) | MPPT1/MPPT2/MPPT3 |
| 31 | Corriente PV (MPPT) | stat | (8,14,8,4) | MPPT1/MPPT2/MPPT3 |
| 21 | Potencia DC (MPPT) | stat | (16,14,8,4) | MPPT1/MPPT2/MPPT3 |
| 9 | Potencia AC / DC | timeseries | (0,18,24,8) | Líneas AC y DC, 5min bucket |
| 22 | Potencia DC por MPPT | timeseries | (0,26,12,8) | MPPT1/2/3 + Total DC |
| 10 | Voltaje PV por MPPT + Red | timeseries | (12,26,12,8) | PV MPPT1/2/3 + Red L1 |
| 11 | Corrientes PV + Red | timeseries | (0,34,12,8) | PV MPPT1/2/3 + Red L1 |
| 13 | Temperatura | timeseries | (12,34,12,8) | Temperatura inversor °C |
| 23 | Voltaje Red | timeseries | (0,50,24,8) | Voltaje AC L1, ancho completo |
| 61 | Frecuencia Red | timeseries | (0,58,24,8) | Frecuencia Hz, ancho completo |

### Queries clave (todas usan `is_stale = false` y `sunrise_concepcion`)

```sql
-- Período (Noche/Nublado/Produciendo)
SELECT CASE
  WHEN NOT EXISTS (SELECT 1 FROM realtime WHERE inverter_id=1 AND time > NOW() - INTERVAL '10 minutes' AND is_stale = false) THEN 0
  WHEN EXISTS (SELECT 1 FROM realtime WHERE inverter_id=1 AND time > NOW() - INTERVAL '10 minutes' AND is_stale = false AND status = 1 AND COALESCE(pac,0) > 0) THEN 3
  WHEN EXISTS (SELECT 1 FROM realtime WHERE inverter_id=1 AND time > NOW() - INTERVAL '10 minutes' AND is_stale = false AND (COALESCE(vpv,0) > 0 OR COALESCE(vpv1,0) > 0 OR COALESCE(vpv2,0) > 0 OR COALESCE(vpv3,0) > 0)) THEN 2
  ELSE 1 END AS periodo

-- Series temporales con filtro de amanecer (ejemplo: Potencia AC/DC)
SELECT $__time(bucket), AVG(COALESCE(pac,0)) as ac, AVG(COALESCE(ppv_total,0)) as dc
FROM (SELECT time_bucket('5m', time) AS bucket, pac, ppv_total FROM realtime
      WHERE $__timeFilter(time) AND inverter_id=1 AND is_stale = false
            AND time >= sunrise_concepcion(current_date)) t
GROUP BY bucket ORDER BY bucket

-- Amanecer y atardecer (verificación)
SELECT sunrise_concepcion(current_date) AT TIME ZONE 'Chile/Continental' as amanecer,
       sunset_concepcion(current_date) AT TIME ZONE 'Chile/Continental' as atardecer;
-- Resultado ejemplo (junio): amanecer ~08:23 CLT, atardecer ~17:22 CLT
-- Resultado ejemplo (diciembre): amanecer ~06:09 CLT, atardecer ~21:30 CLT
```

---

## Dashboard 2: Histórico (`historico.json`)

**Nombre**: Solar Monitor - Histórico
**UID**: `solar-historico`
**Refresh**: 5 minutos
**Rango**: Últimos 7 días

### Paneles (10 paneles)

| # | Panel | Tipo | Posición | Descripción |
|---|---|---|---|---|
| - | Energia del Periodo | stat | (0,0,6,4) | kWh calculados desde realtime |
| - | Pico de Potencia | stat | (6,0,6,4) | Máximo pac del período |
| - | Horas Sol Eq. | stat | (12,0,6,4) | Horas sol equivalentes |
| - | Factor de Planta | stat | (18,0,6,4) | Capacity factor % |
| - | Energia Diaria | barchart | (0,4,24,9) | kWh por día |
| - | Potencia AC vs DC | timeseries | (0,13,12,9) | Líneas AC y DC promedio |
| - | Potencia por MPPT | timeseries | (12,13,12,9) | MPPT1/2/3 + Total |
| - | Voltaje PV por MPPT + Red | timeseries | (0,22,12,9) | PV MPPT1/2/3 + Red |
| - | Temperatura | timeseries | (12,22,12,9) | °C promedio |
| - | Resumen Diario | table | (0,31,24,10) | Tabla exportable CSV |

---

## Dashboard 3: Diagnóstico (`diagnostico.json`)

**Nombre**: Solar Monitor - Diagnóstico
**UID**: `solar-diagnostico`
**Refresh**: 30 segundos
**Rango**: Últimas 24 horas

### Paneles (13 paneles)

| # | Panel | Tipo | Posición | Descripción |
|---|---|---|---|---|
| - | Período | stat | (0,0,5,4) | Noche/Nublado/Produciendo |
| - | Ultima Lectura (datos reales) | stat | (5,0,5,4) | Segundos desde última lectura |
| - | Estado Señal | stat | (10,0,5,4) | OK/Sin Señal |
| - | Lecturas Hoy (reales) | stat | (15,0,5,4) | Contador lecturas reales hoy |
| - | Disponibilidad Hoy | stat | (20,0,4,4) | % del día con datos reales |
| - | Estado Actual | stat | (0,4,6,4) | Wait/Normal/Fault |
| - | Heartbeats Hoy (sin datos) | stat | (6,4,6,4) | Registros is_stale=true hoy |
| - | Intervalo entre Lecturas (24h) | timeseries | (0,8,24,8) | Delta entre lecturas consecutivas |
| - | Temperatura con Límite 65°C | timeseries | (0,16,24,8) | Con threshold rojo |
| - | Voltaje de Red con Bandas | timeseries | (0,24,12,8) | 220V ±10% |
| - | Frecuencia con Bandas 49.5-50.5 | timeseries | (12,24,12,8) | 50Hz ±0.5Hz |
| - | Potencia DC por MPPT (24h) | timeseries | (0,32,24,8) | MPPT1/2/3 + Total |
| - | Registro de Eventos (24h) | table | (0,40,24,10) | Tabla de eventos |

---

## Dashboard 4: Académico (`academico.json`)

**Nombre**: Solar Monitor - Académico
**UID**: `solar-academico`
**Refresh**: 1 minuto
**Rango**: Últimos 30 días

### Paneles (10 paneles)

| # | Panel | Tipo | Posición | Descripción |
|---|---|---|---|---|
| - | Performance Ratio | stat | (0,0,6,4) | PR% |
| - | Horas Sol Eq. | stat | (6,0,6,4) | Horas sol equivalentes |
| - | Energia Específica | stat | (12,0,6,4) | kWh/kWp |
| - | Factor de Planta | stat | (18,0,6,4) | Capacity factor |
| - | Horas de Sol Equivalentes (diario) | barchart | (0,4,12,9) | Barras por día |
| - | Energía Específica Diaria (kWh/kWp) | barchart | (12,4,12,9) | Barras por día |
| - | Eficiencia DC-AC diaria | timeseries | (0,13,12,9) | Ratio pac/ppv_total |
| - | Potencia AC vs DC (promedio diario) | timeseries | (12,13,12,9) | Comparación |
| - | Contribución por MPPT (promedio diario) | timeseries | (0,22,24,9) | % cada MPPT |
| - | Tabla Comparativa MPPT | table | (0,31,24,10) | Tabla exportable |

---

## Alertas

| Alerta | Condición | Canal |
|---|---|---|
| Temperatura alta | `temp > 65` por más de 5 min | Email + Dashboard |
| Desconexión SISER | No hay lectura real en > 60 seg (is_stale=true) | Email + Dashboard |
| Frecuencia fuera de rango | `fac < 49.5 OR fac > 50.5` | Email + Dashboard |
| Voltaje fuera de rango | `vac < 207 OR vac > 253` | Dashboard |
| Inversor en fault | `status = 2` | Email + Dashboard |

Configuración de alertas en Grafana: Contact points → Email (SMTP de la UdeC o Gmail con App Password).

---

## Usuarios Grafana

| Usuario | Rol | Descripción |
|---|---|---|
| admin | Admin | Administración completa, dashboards, datasources |
| (anonymous) | Viewer | Solo lectura, ver dashboards, exportar datos |

Grafana en modo anónimo (Viewer) permite ver sin login adicional.

Configuración en `grafana/grafana.ini`:

```ini
[server]
root_url = https://zoning-heat-groggy.ngrok-free.dev

[security]
cookie_secure = false
cookie_samesite = lax

[auth]
disable_login_form = false

[auth.anonymous]
enabled = true
org_name = Main Org.
org_role = Viewer

[users]
allow_sign_up = false

[log]
mode = console
level = info

[theme]
default_theme = light

[paths]
provisioning = /etc/grafana/provisioning
```

---

## Implementación — Archivos de Configuración

Los archivos JSON de los dashboards están en `Proyecto/grafana/dashboards/` en el repo local y en `/opt/solar-monitor/grafana/dashboards/` en producción. Son provisionados automáticamente por Grafana al arrancar.

> **NOTA IMPORTANTE**: Los dashboards provisionados NO se pueden editar via la API de Grafana. Para modificarlos, se debe editar el archivo JSON en disco y reiniciar el container de Grafana (`docker restart solar-monitor-grafana-1`). El dashboard de tiempo real usa `editable: false` para que el rango de tiempo se resetee al amanecer con cada F5.

### Funciones PostgreSQL de amanecer/atarder

Definidas en `Proyecto/db/sunrise_functions.sql`:

| Función | Retorna | Descripción |
|---|---|---|
| `sunrise_concepcion(date)` | `timestamptz` (UTC) | Hora de amanecer en Concepción para la fecha dada |
| `sunset_concepcion(date)` | `timestamptz` (UTC) | Hora de atardecer en Concepción para la fecha dada |

Algoritmo: NOAA Solar Calculator con coordenadas -36.8201°S, -73.0455°W, zenith 90.833°.

### Script cron: actualización diaria del amanecer

`/tmp/update_sunrise_dashboard.sh` se ejecuta a las 05:00 cada día:

1. Consulta `sunrise_concepcion(current_date)` desde PostgreSQL
2. Actualiza `time.from` en `/opt/solar-monitor/grafana/dashboards/realtime.json`
3. Reinicia Grafana para que re-provisione el dashboard

```
# crontab -l
0 5 * * * bash /tmp/update_sunrise_dashboard.sh >> /tmp/sunrise_cron.log 2>>1
```

### Dashboard JSONs

Los archivos completos están en:
- `Proyecto/grafana/dashboards/realtime.json` — Dashboard de tiempo real (21 paneles)
- `Proyecto/grafana/dashboards/historico.json` — Dashboard histórico (10 paneles)
- `Proyecto/grafana/dashboards/diagnostico.json` — Dashboard de diagnóstico (13 paneles)
- `Proyecto/grafana/dashboards/academico.json` — Dashboard académico (10 paneles)

Todos los dashboards usan `editable: false` para evitar modificaciones accidentales desde la UI.

---

## Snapshots Compartibles

Para compartir un dashboard con alguien fuera del sistema:

1. En Grafana → Share → Snapshot → Publish to snapshot.raintank.io
2. Genera una URL pública temporal
3. Ideal para alumnos que necesitan mostrar datos en informes

Para descargar datos como CSV desde Grafana:

1. Panel → Inspect → Data → Download CSV
2. O JSON: Panel → Inspect → Data → Download JSON

> No se usa API externa para exportar — Grafana lo maneja nativamente.