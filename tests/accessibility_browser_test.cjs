const { chromium } = require('playwright');
const AxeBuilder = require('@axe-core/playwright').default;

const baseUrl = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:8080';
const viewports = [
  { width: 320, height: 900 },
  { width: 1440, height: 900 },
];
const pages = [
  '/index.html',
  '/process-data.html',
  '/dashboard.html',
  '/warden.html',
  '/about.html',
  '/portfolio.html',
  '/patient.html?id=P10029',
  '/game.html',
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function mockDashboard(page) {
  await page.route('**/messages?**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ total: 0, items: [] }),
  }));
}

async function mockSupportingPages(page, path) {
  if (path.startsWith('/patient.html')) {
    await page.route('**/patients/P10029/timeline', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        patient: {
          id: 'P10029',
          first_name: 'Richard',
          last_name: 'Garcia',
          dob: '1961-08-19',
          sex: 'M',
        },
        visit_count: 1,
        visits: [{
          date: '2026-01-12',
          observations: [
            { code: '8867-4', display: 'Heart Rate', value: 82, unit: 'bpm', flag: '' },
          ],
        }],
      }),
    }));
  }
  if (path === '/game.html') {
    await page.route('**/game/index.html', route => route.fulfill({
      status: 200,
      contentType: 'text/html',
      body: '<!doctype html><html lang="en"><title>EvadeMan</title><body style="background:#000"></body></html>',
    }));
  }
}

async function scanPage(browser, path, viewport) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  if (path === '/dashboard.html') await mockDashboard(page);
  await mockSupportingPages(page, path);

  await page.goto(`${baseUrl}${path}`, { waitUntil: 'networkidle' });
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();

  const serious = results.violations.filter(violation =>
    ['serious', 'critical'].includes(violation.impact)
  );
  assert(
    serious.length === 0,
    `${viewport.width}px ${path}: ${serious.map(violation =>
      `${violation.id} (${violation.nodes.length})`
    ).join(', ')}`
  );

  await context.close();
}

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    for (const viewport of viewports) {
      for (const path of pages) {
        await scanPage(browser, path, viewport);
      }
    }
    console.log(`Accessibility scans passed for ${pages.length} pages at 320 and 1440px.`);
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
