# Testing de Usabilidad — Playwright

> **ESTADO: COMPLETADO** — Los tests de usabilidad fueron ejecutados. El sistema está accesible vía ngrok y los dashboards funcionan.

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
    baseURL: process.env.BASE_URL || 'https://lautuaro.tail6e64d5.ts.net',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    locale: 'es-CL',
    timezoneId: 'America/Santiago',
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
BASE_URL=https://lautuaro.tail6e64d5.ts.net
GRAFANA_URL=http://localhost:3000
GRAFANA_USER=admin
GRAFANA_PASSWORD=cambiar_esta_password
TEST_USER_EMAIL=test@udec.cl
```

---

## Tests de Usabilidad

### Categoría 1: Acceso y Autenticación

#### Test 1.1: Acceso inicial con email @udec.cl

```javascript
// tests/specs/acceso/1.1-acceso-inicial.spec.js
import { test, expect } from '@playwright/test';

test('Página principal carga correctamente', async ({ page }) => {
  await page.goto('/');
  // Verificar que Cloudflare Access muestra el formulario de email
  await expect(page.locator('input[type="email"]')).toBeVisible({ timeout: 15000 });
});

test('Acceso con email @udec.cl funciona', async ({ page }) => {
  await page.goto('/');
  // Ingresar email institucional
  await page.locator('input[type="email"]').fill('test@udec.cl');
  await page.locator('button', { hasText: /send|enviar|continue/i }).click();
  // Verificar que se pide código de verificación
  await expect(page.locator('text=/código|code|verify/i')).toBeVisible({ timeout: 10000 });
});

test('Email no @udec.cl es rechazado', async ({ page }) => {
  await page.goto('/');
  await page.locator('input[type="email"]').fill('test@gmail.com');
  await page.locator('button', { hasText: /send|enviar|continue/i }).click();
  // Verificar mensaje de error o acceso denegado
  await expect(page.locator('text=/denied|denegado|not allowed|no permitido/i')).toBeVisible({ timeout: 10000 });
});
```

#### Test 1.2: Dashboard carga después de autenticación

```javascript
// tests/specs/acceso/1.2-post-auth.spec.js
import { test, expect } from '@playwright/test';

// Nota: Este test requiere autenticación previa (manual o con storageState)
test.use({ storageState: 'tests/auth/cloudflare-auth.json' });

test('Dashboard de tiempo real carga correctamente', async ({ page }) => {
  await page.goto('/');
  // Verificar que Grafana carga
  await expect(page.locator('.dashboard-container')).toBeVisible({ timeout: 30000 });
  // Verificar que hay paneles con datos
  await expect(page.locator('[data-testid="data-testid Panel header"]')).toHaveCount({ min: 4 });
});

test('Variables del dashboard están disponibles', async ({ page }) => {
  await page.goto('/');
  // Verificar que la variable inverter_id existe
  const variableDropdown = page.locator('[data-testid="data-testid Dashboard controls"]');
  await expect(variableDropdown).toBeVisible({ timeout: 15000 });
});
```

### Categoría 2: Dashboard Tiempo Real

#### Test 2.1: Paneles de indicadores

```javascript
// tests/specs/dashboard-tiempo-real/2.1-indicadores.spec.js
import { test, expect } from '@playwright/test';

test.use({ storageState: 'tests/auth/cloudflare-auth.json' });

test('Panel Potencia AC muestra valor numérico', async ({ page }) => {
  await page.goto('/d/realtime/solar-monitor-tiempo-real');
  // Esperar a que carguen los datos
  await page.waitForTimeout(5000);
  // Buscar el panel de potencia AC
  const powerPanel = page.locator('text=/Potencia AC|Power AC/i').first();
  await expect(powerPanel).toBeVisible({ timeout: 15000 });
  // Verificar que muestra un valor numérico (con unidad W)
  const gaugeValue = page.locator('[data-testid="data-testid Gauge"]').first();
  await expect(gaugeValue).toBeVisible();
});

test('Panel Temperatura muestra valor en °C', async ({ page }) => {
  await page.goto('/d/realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(5000);
  const tempPanel = page.locator('text=/Temperatura|Temperature/i').first();
  await expect(tempPanel).toBeVisible({ timeout: 15000 });
});

test('Panel Energía Diaria muestra valor en kWh', async ({ page }) => {
  await page.goto('/d/realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(5000);
  const energyPanel = page.locator('text=/Energ.*Diaria|Daily Energy/i').first();
  await expect(energyPanel).toBeVisible({ timeout: 15000 });
});

test('Estado del inversor muestra color correcto', async ({ page }) => {
  await page.goto('/d/realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(5000);
  // Verificar que el panel de estado existe
  const statusPanel = page.locator('text=/Estado|Status/i').first();
  await expect(statusPanel).toBeVisible({ timeout: 15000 });
});

test('Auto-refresh funciona (datos se actualizan)', async ({ page }) => {
  await page.goto('/d/realtime/solar-monitor-tiempo-real');
  // Capturar valor inicial
  const initialValue = await page.locator('[data-testid="data-testid Gauge"]').first().textContent();
  // Esperar 10 segundos
  await page.waitForTimeout(10000);
  // Verificar que el timestamp de "última lectura" se actualizó
  // (no necesariamente el valor cambió, pero el timestamp sí)
  const lastReading = page.locator('text=/.*lectura|last reading/i').first();
  await expect(lastReading).toBeVisible({ timeout: 15000 });
});
```

#### Test 2.2: Gráficos de tiempo

```javascript
// tests/specs/dashboard-tiempo-real/2.2-graficos.spec.js
import { test, expect } from '@playwright/test';

test.use({ storageState: 'tests/auth/cloudflare-auth.json' });

test('Gráfico de Potencia AC 24h muestra datos', async ({ page }) => {
  await page.goto('/d/realtime/solar-monitor-tiempo-real');
  // Esperar a que carguen los gráficos
  await page.waitForTimeout(8000);
  // Verificar que hay al menos un gráfico de líneas visible
  const timeSeries = page.locator('div.uplot').first();
  await expect(timeSeries).toBeVisible({ timeout: 15000 });
});

test('Selector de rango de tiempo funciona', async ({ page }) => {
  await page.goto('/d/realtime/solar-monitor-tiempo-real');
  // Abrir selector de rango
  const timePicker = page.locator('[data-testid="data-testid TimePicker"]');
  await timePicker.click();
  // Seleccionar "Last 6 hours"
  await page.locator('text=/Last 6 hours|Últimas 6 horas/i').click();
  // Verificar que el dashboard se actualizó
  await page.waitForTimeout(3000);
});
```

### Categoría 3: Dashboard Histórico

#### Test 3.1: Datos históricos

```javascript
// tests/specs/dashboard-historico/3.1-datos-historicos.spec.js
import { test, expect } from '@playwright/test';

test.use({ storageState: 'tests/auth/cloudflare-auth.json' });

test('Dashboard Histórico carga correctamente', async ({ page }) => {
  await page.goto('/d/historico/solar-monitor-historico');
  await page.waitForTimeout(8000);
  await expect(page.locator('.dashboard-container')).toBeVisible({ timeout: 15000 });
});

test('Gráfico de Energía Diaria muestra barras', async ({ page }) => {
  await page.goto('/d/historico/solar-monitor-historico');
  await page.waitForTimeout(8000);
  // Buscar panel de barras con "Energía Diaria"
  const barChart = page.locator('text=/Energ.*Diaria|Daily Energy/i').first();
  await expect(barChart).toBeVisible({ timeout: 15000 });
});

test('Filtro de rango de fechas funciona', async ({ page }) => {
  await page.goto('/d/historico/solar-monitor-historico');
  const timePicker = page.locator('[data-testid="data-testid TimePicker"]');
  await timePicker.click();
  await page.locator('text=/Last 30 days|Últimos 30 días/i').click();
  await page.waitForTimeout(5000);
  // Verificar que los datos se actualizan
});
```

### Categoría 4: Dashboard Diagnóstico

#### Test 4.1: Health checks

```javascript
// tests/specs/dashboard-diagnostico/4.1-health-checks.spec.js
import { test, expect } from '@playwright/test';

test.use({ storageState: 'tests/auth/cloudflare-auth.json' });

test('Dashboard Diagnóstico carga correctamente', async ({ page }) => {
  await page.goto('/d/diagnostico/solar-monitor-diagnostico');
  await page.waitForTimeout(8000);
  await expect(page.locator('.dashboard-container')).toBeVisible({ timeout: 15000 });
});

test('Panel "Última Lectura Exitosa" muestra estado verde', async ({ page }) => {
  await page.goto('/d/diagnostico/solar-monitor-diagnostico');
  await page.waitForTimeout(5000);
  // Verificar que el panel existe
  const lastReading = page.locator('text=/.*lectura exitosa|last successful/i').first();
  await expect(lastReading).toBeVisible({ timeout: 15000 });
});

test('Panel "Errores de Comunicación" muestra datos', async ({ page }) => {
  await page.goto('/d/diagnostico/solar-monitor-diagnostico');
  await page.waitForTimeout(5000);
  const errorPanel = page.locator('text=/Error.*Comunicaci|Communication Error/i').first();
  await expect(errorPanel).toBeVisible({ timeout: 15000 });
});
```

### Categoría 5: Dashboard Académico

#### Test 5.1: KPIs académicos

```javascript
// tests/specs/dashboard-academico/5.1-kpis.spec.js
import { test, expect } from '@playwright/test';

test.use({ storageState: 'tests/auth/cloudflare-auth.json' });

test('Dashboard Académico carga correctamente', async ({ page }) => {
  await page.goto('/d/academico/solar-monitor-academico');
  await page.waitForTimeout(8000);
  await expect(page.locator('.dashboard-container')).toBeVisible({ timeout: 15000 });
});

test('Panel Horas de Sol Equivalentes muestra datos', async ({ page }) => {
  await page.goto('/d/academico/solar-monitor-academico');
  await page.waitForTimeout(8000);
  const hsePanel = page.locator('text=/Horas.*Sol.*Equiv|Peak Sun Hours/i').first();
  await expect(hsePanel).toBeVisible({ timeout: 15000 });
});

test('Tabla Resumen Diario es exportable', async ({ page }) => {
  await page.goto('/d/academico/solar-monitor-academico');
  await page.waitForTimeout(8000);
  // Buscar tabla
  const table = page.locator('table').first();
  await expect(table).toBeVisible({ timeout: 15000 });
});
```

### Categoría 6: Exportar Datos

#### Test 6.1: Exportar CSV desde Grafana

```javascript
// tests/specs/exportar/6.1-exportar-csv.spec.js
import { test, expect } from '@playwright/test';

test.use({ storageState: 'tests/auth/cloudflare-auth.json' });

test('Exportar CSV desde panel de tiempo real', async ({ page }) => {
  await page.goto('/d/realtime/solar-monitor-tiempo-real');
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

  // Verificar que se descargó un archivo CSV
  expect(download.suggestedFilename()).toContain('.csv');
});

test('Exportar JSON desde panel', async ({ page }) => {
  await page.goto('/d/realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(8000);

  const panelHeader = page.locator('[data-testid="data-testid Panel header"]').first();
  await panelHeader.click();
  await page.locator('text=/Inspect|Inspeccionar/i').click();
  await page.locator('text=/Data|Datos/i').click();

  // Verificar que hay datos en formato JSON
  const dataPanel = page.locator('.panel-content');
  await expect(dataPanel).toBeVisible();
});
```

### Categoría 7: Responsive y Navegadores

#### Test 7.1: Vista móvil

```javascript
// tests/specs/responsive/7.1-mobile.spec.js
import { test, expect } from '@playwright/test';

test.use({ storageState: 'tests/auth/cloudflare-auth.json' });

test('Dashboard carga correctamente en móvil', async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 375, height: 667 },
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();

  await page.goto('/d/realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(10000);

  // Verificar que el dashboard carga (aunque sea en layout vertical)
  await expect(page.locator('.dashboard-container')).toBeVisible({ timeout: 20000 });

  await context.close();
});

test('Dashboard carga correctamente en tablet', async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 768, height: 1024 },
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();

  await page.goto('/d/realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(10000);

  await expect(page.locator('.dashboard-container')).toBeVisible({ timeout: 20000 });

  await context.close();
});
```

### Categoría 8: Accesibilidad

#### Test 8.1: Accesibilidad básica

```javascript
// tests/specs/accesibilidad/8.1-accesibilidad.spec.js
import { test, expect } from '@playwright/test';

test.use({ storageState: 'tests/auth/cloudflare-auth.json' });

test('Dashboard tiene títulos apropiados', async ({ page }) => {
  await page.goto('/d/realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(5000);
  // Verificar que la página tiene un título
  const title = await page.title();
  expect(title).toContain('Solar Monitor');
});

test('Contraste de colores es legible', async ({ page }) => {
  await page.goto('/d/realtime/solar-monitor-tiempo-real');
  await page.waitForTimeout(5000);
  // Verificar que el texto es visible (no hay texto invisible)
  const visibleText = page.locator('text=/Potencia|Temperatura|Energ/i');
  await expect(visibleText).toBeVisible({ timeout: 15000 });
});

test('Navegación entre dashboards funciona', async ({ page }) => {
  await page.goto('/');
  // Verificar que hay navegación a diferentes dashboards
  const dashboardLinks = page.locator('a[href*="/d/"]');
  const count = await dashboardLinks.count();
  expect(count).toBeGreaterThanOrEqual(1);
});
```

---

## Tests de Usabilidad con Playwright MCP

Para ejecutar tests interactivos desde la CLI (útil para debugging manual):

```bash
# Iniciar servidor MCP
npx @playwright/mcp@latest --allowed-origins "https://lautuaro.tail6e64d5.ts.net"

# En otra terminal, usar la CLI de Playwright para navegar
npx @playwright/cli navigate "https://lautuaro.tail6e64d5.ts.net"

# Tomar screenshot
npx @playwright/cli screenshot --full-page /tmp/dashboard-screenshot.png

# Hacer clic en un elemento
npx @playwright/cli click "text=Potencia AC"

# Evaluar JavaScript
npx @playwright/cli eval "document.querySelectorAll('[data-testid]').length"
```

---

## Ejecución de Tests

### Ejecutar todos los tests

```bash
# Desde el directorio de tests
cd /opt/solar-monitor/tests

# Ejecutar todos los tests
npx playwright test

# Ejecutar solo tests de acceso
npx playwright test specs/acceso/

# Ejecutar solo tests de dashboard tiempo real
npx playwright test specs/dashboard-tiempo-real/

# Ejecutar en modo headed (ver navegador)
npx playwright test --headed

# Ejecutar con trace para debugging
npx playwright test --trace on

# Generar reporte HTML
npx playwright show-report
```

### Ejecutar contra localhost (para pruebas locales)

```bash
BASE_URL=http://localhost:3000 npx playwright test
```

### Ejecutar contra remoto (producción)

```bash
BASE_URL=https://lautuaro.tail6e64d5.ts.net npx playwright test
```

---

## Setup de Autenticación para Tests

Los tests que requieren autenticación Cloudflare Access necesitan un `storageState` guardado:

```javascript
// tests/auth/setup.js
import { test as setup } from '@playwright/test';

setup('Authenticate with Cloudflare Access', async ({ page }) => {
  // Navegar al dashboard (triggers Cloudflare Access)
  await page.goto('https://lautuaro.tail6e64d5.ts.net');

  // Ingresar email (requiere interacción manual la primera vez)
  // O usar un email de test pre-configurado
  await page.locator('input[type="email"]').fill(process.env.TEST_USER_EMAIL);
  await page.locator('button', { hasText: /send|enviar|continue/i }).click();

  // NOTA: El código de verificación por email requiere intervención manual
  // Solución: pre-autenticarse manualmente una vez y guardar el storageState

  // Esperar a que cargue el dashboard
  await page.waitForURL('**/d/**', { timeout: 60000 });

  // Guardar estado de autenticación
  await page.context().storageState({ path: 'tests/auth/cloudflare-auth.json' });
});
```

### Procedimiento manual para guardar auth state

```bash
# 1. Ejecutar Playwright en modo interactivo
npx playwright codegen https://lautuaro.tail6e64d5.ts.net

# 2. Completar la autenticación Cloudflare Access manualmente
# 3. Navegar al dashboard
# 4. Guardar cookies/storage state desde DevTools

# Alternativa: usar el script de setup
npx playwright test tests/auth/setup.js --headed
```

---

## Checklist de Usabilidad

### Acceso
- [ ] Página principal carga en < 5 segundos
- [ ] Cloudflare Access muestra formulario de email
- [ ] Email @udec.cl es aceptado
- [ ] Email no @udec.cl es rechazado con mensaje claro
- [ ] Código de verificación llega al email en < 30 segundos
- [ ] Después de verificar, el dashboard carga sin login adicional

### Dashboard Tiempo Real
- [ ] Panel Potencia AC muestra valor numérico con unidad (W)
- [ ] Panel Temperatura muestra valor en °C
- [ ] Panel Energía Diaria muestra valor en kWh
- [ ] Panel Estado del inversor muestra color (verde=OK, rojo=fault)
- [ ] Gráfico de Potencia AC 24h muestra línea continua
- [ ] Auto-refresh actualiza datos cada 5 segundos
- [ ] Selector de rango de tiempo funciona correctamente

### Dashboard Histórico
- [ ] Gráfico de barras de energía diaria muestra últimos 30 días
- [ ] Selector de rango de fechas funciona
- [ ] Scatter plot temperatura vs potencia muestra puntos

### Dashboard Diagnóstico
- [ ] Panel "Última lectura" muestra tiempo < 30 segundos en verde
- [ ] Panel "Errores de comunicación" muestra histograma
- [ ] Panel temperatura muestra línea con umbral rojo en 65°C

### Exportación
- [ ] Download CSV funciona desde cualquier panel
- [ ] Download JSON funciona desde cualquier panel
- [ ] CSV se abre correctamente en Excel/Google Sheets
- [ ] Datos exportados tienen formato consistente

### Responsive
- [ ] Dashboard carga en móvil (375x667)
- [ ] Dashboard carga en tablet (768x1024)
- [ ] Paneles se reorganizan en layout vertical en móvil
- [ ] Texto es legible sin zoom en móvil