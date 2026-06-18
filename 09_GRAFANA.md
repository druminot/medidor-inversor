# Grafana — Dashboards

> **ESTADO: OPERATIVO** — 4 dashboards provisionados y funcionando. El datasource conecta correctamente a TimescaleDB. Accesible via ngrok (anónimo, rol Viewer).

## Objetivo

Configurar Grafana con dashboards pre-armados para visualizar datos del inversor Riello H.P.6065REL-D en tiempo real e histórico. Accesible desde cualquier navegador via `https://lautuaro.tail6e64d5.ts.net`.

---

## Configuración de Datasource

### Provisioning automático (`grafana/provisioning/datasources/datasource.yml`)

```yaml
apiVersion: 1

datasources:
  - name: TimescaleDB
    type: postgres
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
```

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

## Variables Globales

| Variable | Query | Descripción |
|---|---|---|
| `inverter_id` | `SELECT DISTINCT inverter_id FROM realtime` | Selector de inversor |
| `interval` | Manual: `5s`, `1m`, `5m`, `15m`, `1h`, `6h`, `1d` | Intervalo de tiempo |

---

## Dashboard 1: Tiempo Real

**Nombre**: Solar Monitor - Tiempo Real
**Refresh**: 5 segundos
**Variables**: `$inverter_id`, `$interval=5s`

### Paneles

#### Row 1: Indicadores principales (4 gauge panels)

| Panel | Query | Unidad | Rango | Thresholds |
|---|---|---|---|---|
| Potencia AC | `SELECT pac FROM realtime WHERE inverter_id=$inverter_id ORDER BY time DESC LIMIT 1` | W | 0-5000 | Verde: <3000, Amarillo: 3000-4000, Rojo: >4000 |
| Temperatura | `SELECT temp FROM realtime WHERE inverter_id=$inverter_id ORDER BY time DESC LIMIT 1` | °C | 0-80 | Verde: <50, Amarillo: 50-65, Rojo: >65 |
| Energía Diaria | `SELECT energy_daily FROM cumulatives WHERE inverter_id=$inverter_id ORDER BY time DESC LIMIT 1` | kWh | 0-50 | — |
| Energía Total | `SELECT energy_total FROM cumulatives WHERE inverter_id=$inverter_id ORDER BY time DESC LIMIT 1` | kWh | 0-∞ | — |

#### Row 2: Gráficos de tiempo (3 time-series panels)

| Panel | Query | Tipo |
|---|---|---|
| Potencia AC (24h) | `SELECT time_bucket('$interval', time) AS bucket, AVG(pac) FROM realtime WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=$inverter_id GROUP BY bucket ORDER BY bucket` | Línea, color naranja |
| Voltaje y Corriente DC (24h) | `SELECT time_bucket('$interval', time) AS bucket, AVG(vpv) as vpv, AVG(ipv) as ipv FROM realtime WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=$inverter_id GROUP BY bucket ORDER BY bucket` | Línea dual eje |
| Voltaje y Frecuencia AC (24h) | `SELECT time_bucket('$interval', time) AS bucket, AVG(vac) as vac, AVG(fac) as fac FROM realtime WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=$inverter_id GROUP BY bucket ORDER BY bucket` | Línea dual eje (V y Hz) |

#### Row 3: Estado (2 stat panels)

| Panel | Query | Descripción |
|---|---|---|
| Estado Inversor | `SELECT status FROM realtime WHERE inverter_id=$inverter_id ORDER BY time DESC LIMIT 1` | 0=Off(Gris), 1=OK(Verde), 2=Fault(Rojo), 3=Standby(Amarillo) |
| Estado Red | `SELECT grid_status FROM realtime WHERE inverter_id=$inverter_id ORDER BY time DESC LIMIT 1` | 0=OK(Verde), 1=No disponible(Gris) |

#### Row 4: Contadores (4 stat panels)

| Panel | Query |
|---|---|
| Horas Operación | `SELECT hours_total FROM cumulatives WHERE inverter_id=$inverter_id ORDER BY time DESC LIMIT 1` |
| CO2 Ahorrado | `SELECT co2_saved FROM cumulatives WHERE inverter_id=$inverter_id ORDER BY time DESC LIMIT 1` |
| % Potencia Nominal | `SELECT (pac / 4000.0 * 100) FROM realtime WHERE inverter_id=$inverter_id ORDER BY time DESC LIMIT 1` |
| Última Lectura | `SELECT time FROM realtime WHERE inverter_id=$inverter_id ORDER BY time DESC LIMIT 1` |

---

## Dashboard 2: Histórico y Análisis

**Nombre**: Solar Monitor - Histórico
**Refresh**: 5 minutos
**Variables**: `$inverter_id`, rango de fecha seleccionable

### Paneles

| Panel | Query | Tipo |
|---|---|---|
| Energía Diaria (último mes) | `SELECT bucket, avg_power_w/1000 AS avg_kwh FROM daily_energy WHERE bucket > NOW() - INTERVAL '30 days' AND inverter_id=$inverter_id` | Barras |
| Potencia Máxima Diaria | `SELECT bucket, peak_power_w FROM daily_energy WHERE bucket > NOW() - INTERVAL '30 days'` | Línea |
| Energía Mensual (último año) | `SELECT date_trunc('month', bucket) AS month, SUM(avg_power_w * 1/60) AS energy_kwh FROM hourly_energy WHERE bucket > NOW() - INTERVAL '1 year' GROUP BY month ORDER BY month` | Barras |
| Temperatura vs Potencia | `SELECT temp, pac FROM fast_samples WHERE time > NOW() - INTERVAL '7 days' AND inverter_id=$inverter_id` | Scatter |
| Eficiencia del Inversor | `SELECT time_bucket('5m', time) AS bucket, AVG(pac) / NULLIF(AVG(vpv * ipv), 0) * 100 AS efficiency FROM fast_samples WHERE time > NOW() - INTERVAL '7 days' AND vpv > 0 AND ipv > 0 AND inverter_id=$inverter_id GROUP BY bucket ORDER BY bucket` | Línea, % |
| Horas de Sol Equivalentes | `SELECT date_trunc('day', time) AS day, SUM(pac) / 4000.0 AS peak_hours FROM fast_samples WHERE time > NOW() - INTERVAL '30 days' AND pac > 0 AND inverter_id=$inverter_id GROUP BY day ORDER BY day` | Barras |

---

## Dashboard 3: Diagnóstico y Salud

**Nombre**: Solar Monitor - Diagnóstico
**Refresh**: 30 segundos

### Paneles

| Panel | Query | Tipo |
|---|---|---|
| Última Lectura Exitosa | `SELECT time FROM realtime ORDER BY time DESC LIMIT 1` | Stat, verde si < 30s, amarillo si < 5min, rojo si > 5min |
| Tiempo entre Lecturas | `SELECT time, EXTRACT(EPOCH FROM (time - LAG(time) OVER (ORDER BY time))) AS interval_sec FROM realtime WHERE time > NOW() - INTERVAL '24 hours' ORDER BY time` | Línea |
| Errores de Comunicación | `SELECT time_bucket('1h', time) AS bucket, COUNT(*) FROM events WHERE event_type='modbus_error' AND time > NOW() - INTERVAL '7 days' GROUP BY bucket ORDER BY bucket` | Barras |
| Temperatura del Inversor (24h) | `SELECT time_bucket('1m', time) AS bucket, AVG(temp) FROM fast_samples WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=$inverter_id GROUP BY bucket ORDER BY bucket` | Línea con threshold rojo en 65°C |
| Voltaje de Red (24h) | `SELECT time_bucket('1m', time) AS bucket, AVG(vac) FROM fast_samples WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=$inverter_id GROUP BY bucket ORDER BY bucket` | Línea con bandas 220V±10% |
| Frecuencia de Red (24h) | `SELECT time_bucket('1m', time) AS bucket, AVG(fac) FROM fast_samples WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=$inverter_id GROUP BY bucket ORDER BY bucket` | Línea con bandas 50Hz±0.5Hz |

---

## Dashboard 4: Académico (KPIs)

**Nombre**: Solar Monitor - Académico
**Refresh**: 1 minuto

### Paneles

| Panel | Query / Fórmula | Descripción |
|---|---|---|
| Performance Ratio (PR) | `SELECT date_trunc('day', time) AS day, (SUM(pac) / 4000.0) / (NULLIF((SELECT irradiance FROM fast_samples fs2 WHERE fs2.time = fs1.time LIMIT 1), 0) / 1000.0) * 100 FROM fast_samples fs1 WHERE time > NOW() - INTERVAL '30 days' GROUP BY day ORDER BY day` | Eficiencia real vs teórica (requiere piranómetro, ver nota) |
| Energía Específica | `SELECT date_trunc('day', time) AS day, SUM(pac) / 1000.0 / 4.0 AS specific_energy FROM fast_samples WHERE time > NOW() - INTERVAL '30 days' AND inverter_id=$inverter_id GROUP BY day ORDER BY day` | kWh/kWp por día |
| Horas de Sol Equivalentes | `SELECT date_trunc('day', time) AS day, SUM(pac) / 4000.0 AS equiv_hours FROM fast_samples WHERE time > NOW() - INTERVAL '30 days' AND pac > 0 AND inverter_id=$inverter_id GROUP BY day ORDER BY day` | Horas de sol pico equivalentes |
| CO2 Evitado Acumulado | `SELECT time_bucket('1d', time) AS bucket, MAX(co2_saved) FROM cumulatives WHERE time > NOW() - INTERVAL '1 year' GROUP BY bucket ORDER BY bucket` | Línea acumulativa |
| Resumen Diario (tabla) | `SELECT date(time) AS fecha, ROUND(SUM(pac)/1000.0, 2) AS energia_kwh, ROUND(MAX(temp), 1) AS temp_max, ROUND(AVG(vac), 1) AS vac_avg, ROUND(AVG(fac), 2) AS fac_avg FROM fast_samples WHERE time > NOW() - INTERVAL '30 days' AND inverter_id=$inverter_id GROUP BY date(time) ORDER BY date(time) DESC` | Tabla exportable |

> **Nota sobre PR**: Sin piranómetro, se puede estimar la irradiancia usando datos de la DMC (Dirección Meteorológica de Chile) o APIs como Solcast/PVGIS para la ubicación de Concepción (-36.83, -73.04).

---

## Alertas

| Alerta | Condición | Canal |
|---|---|---|
| Temperatura alta | `temp > 65` por más de 5 min | Email + Dashboard |
| Desconexión Modbus | No hay lectura en > 60 seg | Email + Dashboard |
| Frecuencia fuera de rango | `fac < 49.5 OR fac > 50.5` | Email + Dashboard |
| Voltaje fuera de rango | `vac < 207 OR vac > 253` | Dashboard |
| Inversor en fault | `status = 2` | Email + Dashboard |

Configuración de alertas en Grafana: Contact points → Email (SMTP de la UdeC o Gmail con App Password).

---

## Usuarios Grafana

| Usuario | Rol | Descripción |
|---|---|---|
| admin | Admin | Administración completa, dashboards, datasources |
| viewer | Viewer | Solo lectura, ver dashboards, exportar datos |

Cloudflare Access maneja la autenticación de acceso (email @udec.cl). Dentro de Grafana, el usuario `viewer` tiene permisos de solo lectura.

Configuración en `grafana.ini`:

```ini
[auth]
disable_login_form = false

[auth.anonymous]
enabled = true
org_name = Main Org.
org_role = Viewer

[security]
cookie_secure = true
cookie_samesite = none
```

> Con Cloudflare Access delante, los usuarios ya están autenticados por email. Grafana en modo anónimo (Viewer) permite ver sin login adicional.

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

---

## Implementación — Archivos de Configuración

### `grafana/grafana.ini`

```ini
[server]
root_url = https://lautuaro.tail6e64d5.ts.net

[security]
cookie_secure = true
cookie_samesite = none

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

[paths]
provisioning = /etc/grafana/provisioning
```

---

## Implementación — Dashboard JSONs

> Los dashboards a continuación son archivos JSON completos listos para copiar a `grafana/dashboards/`. Cada dashboard se provisioning automáticamente vía `dashboard.yml` (configurado más arriba). Los UIDs son fijos para que las referencias cruzadas funcionen.

### `grafana/dashboards/realtime.json`

```json
{
  "annotations": { "list": [] },
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 1,
  "id": null,
  "links": [],
  "liveNow": true,
  "panels": [
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": {
          "color": { "mode": "thresholds" },
          "mappings": [],
          "thresholds": {
            "steps": [
              { "color": "green", "value": null },
              { "color": "yellow", "value": 3000 },
              { "color": "red", "value": 4000 }
            ]
          },
          "unit": "watt"
        },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 6, "x": 0, "y": 0 },
      "id": 1,
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "showThresholdLabels": false, "showThresholdMarkers": true },
      "title": "Potencia AC",
      "type": "gauge",
      "targets": [
        { "rawSql": "SELECT pac FROM realtime WHERE inverter_id=1 ORDER BY time DESC LIMIT 1", "format": "table" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": {
          "color": { "mode": "thresholds" },
          "mappings": [],
          "thresholds": {
            "steps": [
              { "color": "green", "value": null },
              { "color": "yellow", "value": 50 },
              { "color": "red", "value": 65 }
            ]
          },
          "unit": "celsius"
        },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 6, "x": 6, "y": 0 },
      "id": 2,
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "showThresholdLabels": false, "showThresholdMarkers": true },
      "title": "Temperatura",
      "type": "gauge",
      "targets": [
        { "rawSql": "SELECT temp FROM realtime WHERE inverter_id=1 ORDER BY time DESC LIMIT 1", "format": "table" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": {
          "color": { "mode": "palette-classic" },
          "mappings": [],
          "thresholds": { "steps": [{ "color": "green", "value": null }] },
          "unit": "kWh"
        },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 6, "x": 12, "y": 0 },
      "id": 3,
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "textMode": "auto", "wideLayout": true },
      "title": "Energía Diaria",
      "type": "stat",
      "targets": [
        { "rawSql": "SELECT energy_daily FROM cumulatives WHERE inverter_id=1 ORDER BY time DESC LIMIT 1", "format": "table" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": {
          "color": { "mode": "palette-classic" },
          "mappings": [],
          "thresholds": { "steps": [{ "color": "green", "value": null }] },
          "unit": "kWh"
        },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 6, "x": 18, "y": 0 },
      "id": 4,
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "textMode": "auto", "wideLayout": true },
      "title": "Energía Total",
      "type": "stat",
      "targets": [
        { "rawSql": "SELECT energy_total FROM cumulatives WHERE inverter_id=1 ORDER BY time DESC LIMIT 1", "format": "table" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": {
          "color": { "mode": "palette-classic" },
          "custom": { "lineWidth": 2, "fillOpacity": 20 },
          "unit": "watt"
        },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 8 },
      "id": 5,
      "title": "Potencia AC (24h)",
      "type": "timeseries",
      "targets": [
        { "rawSql": "SELECT time_bucket('$interval', time) AS bucket, AVG(pac) FROM realtime WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=1 GROUP BY bucket ORDER BY bucket", "format": "time_series" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": {
          "color": { "mode": "palette-classic" },
          "custom": { "lineWidth": 2 }
        },
        "overrides": [
          { "matcher": { "id": "byName", "options": "vpv" }, "properties": [{ "id": "unit", "value": "volt" }, { "id": "displayName", "value": "Voltaje DC (V)" }] },
          { "matcher": { "id": "byName", "options": "ipv" }, "properties": [{ "id": "unit", "value": "amp" }, { "id": "displayName", "value": "Corriente DC (A)" }] }
        ]
      },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 16 },
      "id": 6,
      "title": "Voltaje y Corriente DC (24h)",
      "type": "timeseries",
      "targets": [
        { "rawSql": "SELECT time_bucket('$interval', time) AS bucket, AVG(vpv) as vpv, AVG(ipv) as ipv FROM realtime WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=1 GROUP BY bucket ORDER BY bucket", "format": "time_series" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": {
          "color": { "mode": "palette-classic" },
          "custom": { "lineWidth": 2 }
        },
        "overrides": [
          { "matcher": { "id": "byName", "options": "vac" }, "properties": [{ "id": "unit", "value": "volt" }, { "id": "displayName", "value": "Voltaje AC (V)" }] },
          { "matcher": { "id": "byName", "options": "fac" }, "properties": [{ "id": "unit", "value": "hertz" }, { "id": "displayName", "value": "Frecuencia (Hz)" }] }
        ]
      },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 16 },
      "id": 7,
      "title": "Voltaje y Frecuencia AC (24h)",
      "type": "timeseries",
      "targets": [
        { "rawSql": "SELECT time_bucket('$interval', time) AS bucket, AVG(vac) as vac, AVG(fac) as fac FROM realtime WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=1 GROUP BY bucket ORDER BY bucket", "format": "time_series" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": {
          "color": { "mode": "thresholds" },
          "mappings": [
            { "type": "value", "options": { "0": { "text": "Off", "color": "gray" }, "1": { "text": "OK", "color": "green" }, "2": { "text": "Fault", "color": "red" }, "3": { "text": "Standby", "color": "yellow" } } }
          ],
          "thresholds": { "steps": [{ "color": "gray", "value": null }] }
        },
        "overrides": []
      },
      "gridPos": { "h": 4, "w": 12, "x": 0, "y": 24 },
      "id": 8,
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "textMode": "auto" },
      "title": "Estado Inversor",
      "type": "stat",
      "targets": [
        { "rawSql": "SELECT status FROM realtime WHERE inverter_id=1 ORDER BY time DESC LIMIT 1", "format": "table" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": {
          "color": { "mode": "thresholds" },
          "mappings": [
            { "type": "value", "options": { "0": { "text": "OK", "color": "green" }, "1": { "text": "No disponible", "color": "gray" } } }
          ],
          "thresholds": { "steps": [{ "color": "gray", "value": null }] }
        },
        "overrides": []
      },
      "gridPos": { "h": 4, "w": 12, "x": 12, "y": 24 },
      "id": 9,
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "textMode": "auto" },
      "title": "Estado Red",
      "type": "stat",
      "targets": [
        { "rawSql": "SELECT grid_status FROM realtime WHERE inverter_id=1 ORDER BY time DESC LIMIT 1", "format": "table" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" }, "unit": "h" },
        "overrides": []
      },
      "gridPos": { "h": 4, "w": 6, "x": 0, "y": 28 },
      "id": 10,
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "textMode": "auto" },
      "title": "Horas Operación",
      "type": "stat",
      "targets": [
        { "rawSql": "SELECT hours_total FROM cumulatives WHERE inverter_id=1 ORDER BY time DESC LIMIT 1", "format": "table" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" }, "unit": "kg" },
        "overrides": []
      },
      "gridPos": { "h": 4, "w": 6, "x": 6, "y": 28 },
      "id": 11,
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "textMode": "auto" },
      "title": "CO2 Ahorrado",
      "type": "stat",
      "targets": [
        { "rawSql": "SELECT co2_saved FROM cumulatives WHERE inverter_id=1 ORDER BY time DESC LIMIT 1", "format": "table" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" }, "unit": "percent", "decimals": 1 },
        "overrides": []
      },
      "gridPos": { "h": 4, "w": 6, "x": 12, "y": 28 },
      "id": 12,
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "textMode": "auto" },
      "title": "% Potencia Nominal",
      "type": "stat",
      "targets": [
        { "rawSql": "SELECT (pac / 4000.0 * 100) AS pct FROM realtime WHERE inverter_id=1 ORDER BY time DESC LIMIT 1", "format": "table" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" } },
        "overrides": []
      },
      "gridPos": { "h": 4, "w": 6, "x": 18, "y": 28 },
      "id": 13,
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "textMode": "auto" },
      "title": "Última Lectura",
      "type": "stat",
      "targets": [
        { "rawSql": "SELECT time FROM realtime WHERE inverter_id=1 ORDER BY time DESC LIMIT 1", "format": "table" }
      ]
    }
  ],
  "refresh": "5s",
  "schemaVersion": 39,
  "tags": ["solar", "realtime"],
  "templating": {
    "list": [
      {
        "current": { "selected": true, "text": "1", "value": "1" },
        "datasource": { "type": "postgres", "uid": "timescaledb" },
        "name": "inverter_id",
        "query": "SELECT DISTINCT inverter_id FROM realtime",
        "type": "query"
      },
      {
        "current": { "selected": true, "text": "5s", "value": "5s" },
        "name": "interval",
        "options": [
          { "text": "5s", "value": "5s" },
          { "text": "1m", "value": "1m" },
          { "text": "5m", "value": "5m" },
          { "text": "15m", "value": "15m" },
          { "text": "1h", "value": "1h" }
        ],
        "type": "interval"
      }
    ]
  },
  "time": { "from": "now-24h", "to": "now" },
  "title": "Solar Monitor - Tiempo Real",
  "uid": "solar-realtime",
  "version": 1
}
```

### `grafana/dashboards/historico.json`

```json
{
  "annotations": { "list": [] },
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 1,
  "id": null,
  "links": [],
  "panels": [
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" }, "unit": "kWh" },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 0 },
      "id": 1,
      "title": "Energía Diaria (último mes)",
      "type": "barchart",
      "targets": [
        { "rawSql": "SELECT bucket::timestamp AS time, avg_power_w/1000.0 AS avg_kwh FROM daily_energy WHERE bucket > NOW() - INTERVAL '30 days' AND inverter_id=$inverter_id ORDER BY bucket", "format": "time_series" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" }, "unit": "watt" },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 8 },
      "id": 2,
      "title": "Potencia Máxima Diaria",
      "type": "timeseries",
      "targets": [
        { "rawSql": "SELECT bucket::timestamp AS time, peak_power_w FROM daily_energy WHERE bucket > NOW() - INTERVAL '30 days' ORDER BY bucket", "format": "time_series" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" }, "unit": "kWh" },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 16 },
      "id": 3,
      "title": "Energía Mensual (último año)",
      "type": "barchart",
      "targets": [
        { "rawSql": "SELECT date_trunc('month', bucket) AS time, SUM(avg_power_w * 1.0/60) AS energy_kwh FROM hourly_energy WHERE bucket > NOW() - INTERVAL '1 year' AND inverter_id=$inverter_id GROUP BY 1 ORDER BY 1", "format": "time_series" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" }, "unit": "percent" },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 24 },
      "id": 4,
      "title": "Eficiencia del Inversor",
      "type": "timeseries",
      "targets": [
        { "rawSql": "SELECT time_bucket('5m', time) AS time, AVG(pac) / NULLIF(AVG(vpv * ipv), 0) * 100 AS efficiency FROM fast_samples WHERE time > NOW() - INTERVAL '7 days' AND vpv > 0 AND ipv > 0 AND inverter_id=$inverter_id GROUP BY 1 ORDER BY 1", "format": "time_series" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" }, "unit": "h" },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 32 },
      "id": 5,
      "title": "Horas de Sol Equivalentes",
      "type": "barchart",
      "targets": [
        { "rawSql": "SELECT date_trunc('day', time) AS time, SUM(pac) / 4000.0 AS peak_hours FROM fast_samples WHERE time > NOW() - INTERVAL '30 days' AND pac > 0 AND inverter_id=$inverter_id GROUP BY 1 ORDER BY 1", "format": "time_series" }
      ]
    }
  ],
  "refresh": "5m",
  "schemaVersion": 39,
  "tags": ["solar", "historico"],
  "templating": {
    "list": [
      {
        "current": { "selected": true, "text": "1", "value": "1" },
        "datasource": { "type": "postgres", "uid": "timescaledb" },
        "name": "inverter_id",
        "query": "SELECT DISTINCT inverter_id FROM realtime",
        "type": "query"
      }
    ]
  },
  "time": { "from": "now-30d", "to": "now" },
  "title": "Solar Monitor - Histórico",
  "uid": "solar-historico",
  "version": 1
}
```

### `grafana/dashboards/diagnostico.json`

```json
{
  "annotations": { "list": [] },
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 1,
  "id": null,
  "links": [],
  "panels": [
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": {
          "color": { "mode": "thresholds" },
          "thresholds": {
            "steps": [
              { "color": "green", "value": null },
              { "color": "yellow", "value": 30 },
              { "color": "red", "value": 300 }
            ]
          },
          "unit": "s"
        },
        "overrides": []
      },
      "gridPos": { "h": 4, "w": 6, "x": 0, "y": 0 },
      "id": 1,
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] }, "textMode": "auto" },
      "title": "Última Lectura Exitosa",
      "type": "stat",
      "targets": [
        { "rawSql": "SELECT EXTRACT(EPOCH FROM (NOW() - time))::int AS seconds_ago FROM realtime ORDER BY time DESC LIMIT 1", "format": "table" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" }, "unit": "s" },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 4 },
      "id": 2,
      "title": "Intervalo entre Lecturas (24h)",
      "type": "timeseries",
      "targets": [
        { "rawSql": "SELECT time, EXTRACT(EPOCH FROM (time - LAG(time) OVER (ORDER BY time))) AS interval_sec FROM realtime WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=1 ORDER BY time", "format": "time_series" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" } },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 4 },
      "id": 3,
      "title": "Errores de Comunicación (7d)",
      "type": "barchart",
      "targets": [
        { "rawSql": "SELECT time_bucket('1h', time)::timestamp AS time, COUNT(*) AS errors FROM events WHERE event_type='modbus_error' AND time > NOW() - INTERVAL '7 days' GROUP BY 1 ORDER BY 1", "format": "time_series" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": {
          "color": { "mode": "palette-classic" },
          "unit": "celsius",
          "custom": { "lineWidth": 2, "fillOpacity": 10 }
        },
        "overrides": [
          { "matcher": { "id": "byName", "options": "threshold" }, "properties": [{ "id": "color", "value": { "fixedColor": "red", "mode": "fixed" } }] }
        ]
      },
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 12 },
      "id": 4,
      "title": "Temperatura del Inversor (24h)",
      "type": "timeseries",
      "targets": [
        { "rawSql": "SELECT time_bucket('1m', time) AS time, AVG(temp) AS temperature FROM fast_samples WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=$inverter_id GROUP BY 1 ORDER BY 1", "format": "time_series" },
        { "rawSql": "SELECT time_bucket('1m', time) AS time, 65 AS threshold FROM fast_samples WHERE time > NOW() - INTERVAL '24 hours' GROUP BY 1 ORDER BY 1 LIMIT 1", "format": "time_series", "refId": "threshold" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" }, "unit": "volt" },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 20 },
      "id": 5,
      "title": "Voltaje de Red (24h)",
      "type": "timeseries",
      "targets": [
        { "rawSql": "SELECT time_bucket('1m', time) AS time, AVG(vac) AS voltage FROM fast_samples WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=$inverter_id GROUP BY 1 ORDER BY 1", "format": "time_series" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" }, "unit": "hertz" },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 20 },
      "id": 6,
      "title": "Frecuencia de Red (24h)",
      "type": "timeseries",
      "targets": [
        { "rawSql": "SELECT time_bucket('1m', time) AS time, AVG(fac) AS frequency FROM fast_samples WHERE time > NOW() - INTERVAL '24 hours' AND inverter_id=$inverter_id GROUP BY 1 ORDER BY 1", "format": "time_series" }
      ]
    }
  ],
  "refresh": "30s",
  "schemaVersion": 39,
  "tags": ["solar", "diagnostico"],
  "templating": {
    "list": [
      {
        "current": { "selected": true, "text": "1", "value": "1" },
        "datasource": { "type": "postgres", "uid": "timescaledb" },
        "name": "inverter_id",
        "query": "SELECT DISTINCT inverter_id FROM realtime",
        "type": "query"
      }
    ]
  },
  "time": { "from": "now-24h", "to": "now" },
  "title": "Solar Monitor - Diagnóstico",
  "uid": "solar-diagnostico",
  "version": 1
}
```

### `grafana/dashboards/academico.json`

```json
{
  "annotations": { "list": [] },
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 1,
  "id": null,
  "links": [],
  "panels": [
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" }, "unit": "h" },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 0 },
      "id": 1,
      "title": "Horas de Sol Equivalentes (último mes)",
      "type": "barchart",
      "targets": [
        { "rawSql": "SELECT date_trunc('day', time)::timestamp AS time, SUM(pac) / 4000.0 AS peak_hours FROM fast_samples WHERE time > NOW() - INTERVAL '30 days' AND pac > 0 AND inverter_id=$inverter_id GROUP BY 1 ORDER BY 1", "format": "time_series" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" }, "unit": "kWhkWp" },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 8 },
      "id": 2,
      "title": "Energía Específica (kWh/kWp por día)",
      "type": "barchart",
      "targets": [
        { "rawSql": "SELECT date_trunc('day', time)::timestamp AS time, SUM(pac) / 1000.0 / 4.0 AS specific_energy FROM fast_samples WHERE time > NOW() - INTERVAL '30 days' AND inverter_id=$inverter_id GROUP BY 1 ORDER BY 1", "format": "time_series" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" }, "unit": "kg" },
        "overrides": []
      },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 8 },
      "id": 3,
      "title": "CO2 Evitado Acumulado",
      "type": "timeseries",
      "targets": [
        { "rawSql": "SELECT time_bucket('1d', time)::timestamp AS time, MAX(co2_saved) AS co2_kg FROM cumulatives WHERE time > NOW() - INTERVAL '1 year' AND inverter_id=$inverter_id GROUP BY 1 ORDER BY 1", "format": "time_series" }
      ]
    },
    {
      "datasource": { "type": "postgres", "uid": "timescaledb" },
      "fieldConfig": {
        "defaults": { "color": { "mode": "palette-classic" } },
        "overrides": []
      },
      "gridPos": { "h": 10, "w": 24, "x": 0, "y": 16 },
      "id": 4,
      "title": "Resumen Diario (último mes)",
      "type": "table",
      "targets": [
        { "rawSql": "SELECT date(time) AS fecha, ROUND(SUM(pac)/1000.0, 2) AS energia_kwh, ROUND(MAX(temp), 1) AS temp_max, ROUND(AVG(vac), 1) AS vac_avg, ROUND(AVG(fac), 2) AS fac_avg FROM fast_samples WHERE time > NOW() - INTERVAL '30 days' AND inverter_id=$inverter_id GROUP BY 1 ORDER BY 1 DESC", "format": "table" }
      ]
    }
  ],
  "refresh": "1m",
  "schemaVersion": 39,
  "tags": ["solar", "academico"],
  "templating": {
    "list": [
      {
        "current": { "selected": true, "text": "1", "value": "1" },
        "datasource": { "type": "postgres", "uid": "timescaledb" },
        "name": "inverter_id",
        "query": "SELECT DISTINCT inverter_id FROM realtime",
        "type": "query"
      }
    ]
  },
  "time": { "from": "now-30d", "to": "now" },
  "title": "Solar Monitor - Académico",
  "uid": "solar-academico",
  "version": 1
}
```

> **Nota sobre provisioning**: Los dashboards se cargan automáticamente vía `grafana/provisioning/dashboards/dashboard.yml` (definido más arriba en este archivo). Los JSON se colocan en `grafana/dashboards/` y Grafana los importa al arrancar. El datasource UID `timescaledb` debe coincidir con el UID configurado en `datasource.yml` (por defecto Grafana asigna un UID aleatorio; para que los dashboards funcionen, se recomienda crear el datasource manualmente una vez y copiar el UID, o usar `uid: timescaledb` en el YAML de provisioning con `isDefault: true`).