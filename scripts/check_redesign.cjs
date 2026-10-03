/* Browser verification only. API fixtures never run in the application.
 * Start scripts/serve_staging.py first. Install playwright in a test environment.
 * PLAYWRIGHT_MODULE=/path/to/playwright node scripts/check_redesign.cjs
 */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.BROQUER_TEST_URL || 'http://127.0.0.1:8080';
const output = path.resolve('test-results/redesign');
const user = { id: '00000000-0000-4000-8000-000000000001', email: 'qa@example.test' };

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  try {
    const context = await browser.newContext();
    const productionRequests = [];
    context.on('request', request => {
      if (/api\.broquer\.app|urtgysmtnvoqaljuhntz\.supabase\.co/.test(request.url())) productionRequests.push(request.url());
    });
    await context.addInitScript(user => {
      localStorage.setItem('sb_token', 'qa-only-not-a-real-session');
      localStorage.setItem('sb_user', JSON.stringify(user));
    }, user);
    await context.route('**/__stage/**', async route => {
      const url = new URL(route.request().url());
      let data = [];
      if (url.pathname.includes('/rest/v1/usuarios')) data = [{ nombre: 'Alex', rol: 'agente', modulos_desactivados: [] }];
      else if (url.pathname.endsWith('/subscription/status')) data = { activa: true, active: true, plan: 'max' };
      else if (url.pathname.endsWith('/org')) data = { tiene_org: false };
      else if (url.pathname.includes('/finanzas/resumen')) data = { cuentas: [], ingresos: 0, gastos: 0, utilidad: 0 };
      else if (url.pathname.includes('/__stage/api/')) data = {};
      await route.fulfill({ status: 200, contentType: 'application/json', headers: { 'content-range': '0-0/0' }, body: JSON.stringify(data) });
    });
    const page = await context.newPage();
    let errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const reports = [];
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const name of ['index', 'clientes', 'propiedades', 'tareas', 'finanzas', 'facebook-ads', 'contactos']) {
        errors = [];
        await page.goto(`${base}/${name}.html`);
        await page.waitForSelector('.bk-design-header');
        await page.waitForFunction(() => !document.querySelector('#kanban')?.innerText.includes('Cargando clientes…'));
        await page.evaluate(() => document.fonts.ready);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
        assert.deepEqual(errors, [], `${name}: JavaScript errors`);
        assert.equal(overflow, false, `${name}: horizontal page overflow at ${width}px`);
        if (['clientes', 'propiedades', 'tareas'].includes(name)) {
          const title = page.locator('.page-head h1,.props-head h1,.tk-head h1').first();
          assert.equal(await title.evaluate(el => getComputedStyle(el).fontSize), width === 1440 ? '48px' : '34px');
        }
        if (width === 390) assert.equal(await page.locator('.bk-sheet').isVisible(), false, 'Old mobile menu stays hidden');
        if (name === 'index') {
          const color = await page.locator('.design-tool--dark h3').evaluate(el => getComputedStyle(el).color);
          assert.equal(color, 'rgb(255, 255, 255)', 'Campaign title must be visible on dark card');
        }
        await page.screenshot({ path: `${output}/${name}-${width}.png`, fullPage: true });
        reports.push({ page: name, width, javascriptErrors: 0, pageOverflow: false });
      }
    }
    await page.goto(`${base}/index.html`);
    await page.waitForSelector('.bk-design-header');
    await page.locator('[data-tool="clientes.html"] .design-favorite').click();
    await page.reload();
    await page.waitForSelector('.bk-design-header');
    assert.equal(await page.locator('[data-tool="clientes.html"] .design-favorite').getAttribute('aria-pressed'), 'true');
    await page.locator('[data-tool="clientes.html"] .design-tool-link').click();
    await page.waitForURL('**/clientes.html');
    await page.waitForSelector('.bk-design-header');
    await page.locator('#add-btn-top').click();
    await page.locator('#modal-ov').waitFor({ state: 'visible' });
    await page.goto(`${base}/propiedades.html`);
    await page.waitForSelector('.bk-design-header');
    await page.locator('.props-head .btn-new-prop').click();
    await page.locator('#prop-form').waitFor({ state: 'visible' });
    await page.goto(`${base}/tareas.html`);
    await page.waitForSelector('.bk-design-header');
    await page.locator('.btn-new-tarea').click();
    await page.locator('#tn-modal').waitFor({ state: 'visible' });
    await page.goto(`${base}/finanzas.html`);
    await page.waitForSelector('.bk-design-header');
    await page.locator('#fin-btn-nuevo').click();
    await page.locator('#fin-ov-mov').waitFor({ state: 'visible' });
    assert.deepEqual(productionRequests, []);

    const anonymous = await browser.newContext();
    const login = await anonymous.newPage();
    for (const width of [1440, 390]) {
      await login.setViewportSize({ width, height: 1000 });
      await login.goto(`${base}/login.html`);
      await login.locator('#splash').waitFor({ state: 'hidden' });
      await login.evaluate(() => document.fonts.ready);
      assert.equal(await login.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await login.screenshot({ path: `${output}/login-${width}.png`, fullPage: true });
    }
    await login.locator('#seg-signup').click();
    assert(await login.locator('#form-signup').isVisible());
    await login.locator('#seg-login').click();
    await login.locator('#l-email').fill('qa@example.test');
    await login.locator('#l-pass').fill('Test-only-password123!');
    await login.locator('#btn-login').click();
    await login.locator('#msg.is-err').waitFor();
    assert(login.url().endsWith('/login.html'));
    assert.equal((await anonymous.request.get(`${base}/__stage/api/config/public`)).status(), 503);
    assert.equal((await anonymous.request.get(`${base}/.git/config`)).status(), 404);
    assert.equal((await anonymous.request.get(`${base}/core/config.py`)).status(), 404);
    const report = { screenshots: 16, reports, checks: ['favorites survive reload', 'Clients link opens module', 'client/property/task/finance forms open', 'signup tab works', 'unconfigured login fails clearly', 'gateway blocks unconfigured API and private files'], productionRequests: 0, limitation: 'Browser API fixtures only. Live authentication, persistence and provider integrations require a separate staging environment.' };
    fs.writeFileSync(`${output}/report.json`, JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
