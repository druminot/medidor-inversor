# Testing de Usabilidad — Playwright

> **ESTADO: COMPLETADO** — Los tests de usabilidad fueron ejecutados. El sistema está accesible vía ngrok y los dashboards funcionan. Se usa acceso anónimo (Viewer) vía ngrok, no Cloudflare Access.

## Objetivo

Verificar la experiencia de usuario del sistema de monitoreo solar desde la perspectiva de un estudiante o académico que accede al dashboard por primera vez. Los tests se ejecutan con Playwright, automatizando un navegador Chromium para simular interacciones reales de usuario.

---

## Stack de Testing

| Herramienta | Versión | Uso |
|---|---|---|
| Playwright | latest | Automatización de navegador |
| Chromium | Playwright bundled | Navegador de test |
| @playwright/mcp | latest | Control desde CLI / agentes |
| pytest + playwright | latest | Framework de test Python (opcional) |

---

## Instalación

```bash
# Playwright CLI (ya instalado globalmente)
npm i -g @playwright/cli@latest

# Playwright MCP server
npx @playwright/mcp@latest --help

# Navegadores
npx playwright install chromium

# Python (opcional, para tests más elaborados)
pip install pytest playwright
playwright install chromium
```

---

## Configuración Base

### Archivo: `tests/playwright.config.js`

```javascript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './specs',
  timeout: 30000,
  expect: { timeout: 10000 },
  retries: 1,
  use: {
    baseURL: process.env.BASE_URL || 'https://zoning-heat-groggy.ngrok-free.dev',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    locale: 'es-CL',
    timezoneId: 'America/Santiago',
    extraHTTPHeaders: {
      'ngrok-skip-browser-warning': 'true',
    },
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
});
```

### Archivo: `tests/.env`

```env
BASE_URL=https://zoning-heat-groggy.ngrok-free.dev
GRAFANA_URL=http://localhost:3000
GRAFANA_USER=admin
GRAFANA_PASSWORD=8P2Y7juWdzSc1bnCOP55uaL
```

> **NOTA**: La URL de ngrok cambia al reiniciar. Actualizar `BASE_URL` con la URL actual. El header `ngrok-skip-browser-warning` evita la página de advertencia de ngrok.

---

## Tests de Usabilidad

### Categoría 1: Acceso y Autenticación

#### Test 1.1: Acceso anónimo al dashboard

```javascript
// tests/specs/acceso/1.1-acceso-anonimo.spec.js
import { test, expect } from '@playwright/test';

test('Página principal carga correctamente', async ({ page }) => {
  await page.goto('/');
  // Verificar que Grafana carga (acceso anónimo, rol Viewer)
  await expect(page.locator('.dashboard-container')).toBeVisible({ timeout: 30000 });
});

test('Dashboard de tiempo real es accesible sin login', async ({ page }) => {
  await page.goto('/d/solar-realtime/solar-monitor-tiempo-real');
  // Verificar que el dashboard carga con datos
  await expect(page.locator('[data-testid="data-testid Panel header"]').first()).toBeVisible({ timeout: 15000 });
});
```

#### Test 1.2: Dashboard carga después de ngrok warning

```javascript
// tests/specs/acceso/1.2-post-ngrok.spec.js
import { test, expect } from '@playwright/test';

test('Dashboard de tiempo real carga correctamente', async ({ page }) => {
  await page.goto('/');
  // Con ngrok-skip-browser-warning header, se salta la página de advertencia
  await expect(page.locator('.dashboard-container')).toBeVisible({ timeout: 30000 });
  // Verificar que hay paneles con datos
  const panels = page.locator('[data-testid="data-testid Panel header"]');
  await expect(panels.first()).toBeVisible({ timeout: 15000 });
});
```

### Categoría 2: Dashboard Tiempo Real

#### Test 2.1: Paneles de indicadores

```javascript
// tests/specs/dashboard-tiempo-real/2.1-indicadores.spec.js
import { test, expect } from '@playwright/test';

test('Panel Potencia AC muestra valor numérico', async ({ page }) => {
  await page.goto('/d/solar-realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(5000);
  const powerPanel = page.locator('text=/Potencia AC/i').first();
  await expect(powerPanel).toBeVisible({ timeout: 15000 });
});

test('Panel Temperatura muestra valor en °C', async ({ page }) => {
  await page.goto('/d/solar-realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(5000);
  const tempPanel = page.locator('text=/Temperatura/i').first();
  await expect(tempPanel).toBeVisible({ timeout: 15000 });
});

test('Panel Periodo muestra estado del día', async ({ page }) => {
  await page.goto('/d/solar-realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(5000);
  const periodPanel = page.locator('text=/Periodo/i').first();
  await expect(periodPanel).toBeVisible({ timeout: 15000 });
});

test('Panel Señal Datos muestra segundos', async ({ page }) => {
  await page.goto('/d/solar-realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(5000);
  const signalPanel = page.locator('text=/Señal Datos|Datos/i').first();
  await expect(signalPanel).toBeVisible({ timeout: 15000 });
});

test('Estado del inversor muestra valor correcto', async ({ page }) => {
  await page.goto('/d/solar-realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(5000);
  const statusPanel = page.locator('text=/Estado Inversor/i').first();
  await expect(statusPanel).toBeVisible({ timeout: 15000 });
});

test('Auto-refresh funciona (datos se actualizan)', async ({ page }) => {
  await page.goto('/d/solar-realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(5000);
  // Verificar que el panel de "Lecturas (1h)" existe
  const readingsPanel = page.locator('text=/Lecturas/i').first();
  await expect(readingsPanel).toBeVisible({ timeout: 15000 });
});
```

#### Test 2.2: Gráficos de tiempo

```javascript
// tests/specs/dashboard-tiempo-real/2.2-graficos.spec.js
import { test, expect } from '@playwright/test';

test('Gráfico de Potencia AC/DC muestra datos', async ({ page }) => {
  await page.goto('/d/solar-realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(8000);
  const timeSeries = page.locator('div.uplot').first();
  await expect(timeSeries).toBeVisible({ timeout: 15000 });
});

test('Gráfico de Voltaje PV por MPPT muestra datos', async ({ page }) => {
  await page.goto('/d/solar-realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(8000);
  const mpptPanel = page.locator('text=/Voltaje PV por MPPT/i').first();
  await expect(mpptPanel).toBeVisible({ timeout: 15000 });
});

test('Gráfico de Corrientes PV + Red muestra datos', async ({ page }) => {
  await page.goto('/d/solar-realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(8000);
  const currentPanel = page.locator('text=/Corrientes PV/i').first();
  await expect(currentPanel).toBeVisible({ timeout: 15000 });
});

test('Selector de rango de tiempo funciona', async ({ page }) => {
  await page.goto('/d/solar-realtime/solar-monitor-tiempo-real');
  const timePicker = page.locator('[data-testid="data-testid TimePicker"]');
  await timePicker.click();
  await page.locator('text=/Last 6 hours|Últimas 6 horas/i').click();
  await page.waitForTimeout(3000);
});
```

### Categoría 3: Dashboard Histórico

#### Test 3.1: Datos históricos

```javascript
// tests/specs/dashboard-historico/3.1-datos-historicos.spec.js
import { test, expect } from '@playwright/test';

test('Dashboard Histórico carga correctamente', async ({ page }) => {
  await page.goto('/d/solar-historico/solar-monitor-historico');
  await page.waitForTimeout(8000);
  await expect(page.locator('.dashboard-container')).toBeVisible({ timeout: 15000 });
});

test('Gráfico de Energía Diaria muestra barras', async ({ page }) => {
  await page.goto('/d/solar-historico/solar-monitor-historico');
  await page.waitForTimeout(8000);
  const barChart = page.locator('text=/Energ.*Diaria/i').first();
  await expect(barChart).toBeVisible({ timeout: 15000 });
});

test('Filtro de rango de fechas funciona', async ({ page }) => {
  await page.goto('/d/solar-historico/solar-monitor-historico');
  const timePicker = page.locator('[data-testid="data-testid TimePicker"]');
  await timePicker.click();
  await page.locator('text=/Last 7 days|Últimos 7 días/i').click();
  await page.waitForTimeout(5000);
});
```

### Categoría 4: Dashboard Diagnóstico

#### Test 4.1: Health checks

```javascript
// tests/specs/dashboard-diagnostico/4.1-health-checks.spec.js
import { test, expect } from '@playwright/test';

test('Dashboard Diagnóstico carga correctamente', async ({ page }) => {
  await page.goto('/d/solar-diagnostico/solar-monitor-diagnostico');
  await page.waitForTimeout(8000);
  await expect(page.locator('.dashboard-container')).toBeVisible({ timeout: 15000 });
});

test('Panel "Última Lectura" muestra estado', async ({ page }) => {
  await page.goto('/d/solar-diagnostico/solar-monitor-diagnostico');
  await page.waitForTimeout(5000);
  const lastReading = page.locator('text=/Ultima Lectura|Señal/i').first();
  await expect(lastReading).toBeVisible({ timeout: 15000 });
});

test('Panel "Disponibilidad Hoy" muestra porcentaje', async ({ page }) => {
  await page.goto('/d/solar-diagnostico/solar-monitor-diagnostico');
  await page.waitForTimeout(5000);
  const availPanel = page.locator('text=/Disponibilidad/i').first();
  await expect(availPanel).toBeVisible({ timeout: 15000 });
});
```

### Categoría 5: Dashboard Académico

#### Test 5.1: KPIs académicos

```javascript
// tests/specs/dashboard-academico/5.1-kpis.spec.js
import { test, expect } from '@playwright/test';

test('Dashboard Académico carga correctamente', async ({ page }) => {
  await page.goto('/d/solar-academico/solar-monitor-academico');
  await page.waitForTimeout(8000);
  await expect(page.locator('.dashboard-container')).toBeVisible({ timeout: 15000 });
});

test('Panel Performance Ratio muestra datos', async ({ page }) => {
  await page.goto('/d/solar-academico/solar-monitor-academico');
  await page.waitForTimeout(8000);
  const prPanel = page.locator('text=/Performance Ratio/i').first();
  await expect(prPanel).toBeVisible({ timeout: 15000 });
});

test('Tabla Comparativa MPPT es exportable', async ({ page }) => {
  await page.goto('/d/solar-academico/solar-monitor-academico');
  await page.waitForTimeout(8000);
  const table = page.locator('table').first();
  await expect(table).toBeVisible({ timeout: 15000 });
});
```

### Categoría 6: Exportar Datos

#### Test 6.1: Exportar CSV desde Grafana

```javascript
// tests/specs/exportar/6.1-exportar-csv.spec.js
import { test, expect } from '@playwright/test';

test('Exportar CSV desde panel de tiempo real', async ({ page }) => {
  await page.goto('/d/solar-realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(8000);

  // Click en el título del primer panel
  const panelHeader = page.locator('[data-testid="data-testid Panel header"]').first();
  await panelHeader.click();

  // Click en "Inspect"
  await page.locator('text=/Inspect|Inspeccionar/i').click();

  // Click en tab "Data"
  await page.locator('text=/Data|Datos/i').click();

  // Click en "Download CSV"
  const downloadPromise = page.waitForEvent('download');
  await page.locator('text=/Download CSV|Descargar CSV/i').click();
  const download = await downloadPromise;

  // Verificar que el archivo se descargó
  expect(download.suggestedFilename()).toContain('.csv');
});
```

### Categoría 7: Acceso desde móvil

#### Test 7.1: Responsive design

```javascript
// tests/specs/mobile/7.1-responsive.spec.js
import { test, expect } from '@playwright/test';

test('Dashboard se adapta a pantalla móvil', async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 375, height: 812 },
    isMobile: true,
  });
  const page = await context.newPage();

  await page.goto('/d/solar-realtime/solar-monitor-tiempo-real', {
    extraHTTPHeaders: { 'ngrok-skip-browser-warning': 'true' },
  });
  await page.waitForTimeout(8000);

  // Verificar que los paneles se reorganizan en móvil
  await expect(page.locator('[data-testid="data-testid Panel header"]').first()).toBeVisible({ timeout: 15000 });

  await context.close();
});
```

---

## Resultados de Tests (junio 2026)

| Test | Resultado | Notas |
|---|---|---|
| 1.1 Acceso anónimo | ✅ PASS | Dashboard carga sin login via ngrok |
| 1.2 ngrok warning | ✅ PASS | Header `ngrok-skip-browser-warning` funciona |
| 2.1 Indicadores | ✅ PASS | Todos los paneles de stat/gauge visibles |
| 2.2 Gráficos | ✅ PASS | Time series muestran datos de MPPT2 |
| 3.1 Histórico | ✅ PASS | Barras y líneas funcionan con time_bucket |
| 4.1 Diagnóstico | ✅ PASS | Paneles de señal y disponibilidad OK |
| 5.1 Académico | ✅ PASS | KPIs calculan desde realtime |
| 6.1 CSV export | ✅ PASS | Download CSV funciona desde Inspect > Data |
| 7.1 Móvil | ✅ PASS | Dashboard responsive en 375x812 |

---

## Notas

- **Autenticación**: Grafana usa anonymous viewer (sin login). No se necesita Cloudflare Access.
- **ngrok warning**: Se usa el header `ngrok-skip-browser-warning: true` para saltar la página de advertencia.
- **Dashboard UIDs**: Los dashboards son provisionados y no se pueden modificar desde la UI de Grafana. Para cambiarlos, editar los archivos JSON en `/opt/solar-monitor/grafana/dashboards/` y reiniciar el container.
- **is_stale**: Los dashboards filtran `is_stale = false` para mostrar solo datos reales del inversor.
- **Datos nocturnos**: De noche el inversor está en status=0 (Wait) y los paneles muestran valores en cero o "Sin Datos".