const { chromium } = require('playwright');

const baseUrl = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:8080';
const widths = [320, 375, 768, 1024, 1440];
const height = 900;
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

async function inspectPage(browser, path, width) {
  const page = await browser.newPage({ viewport: { width, height } });
  const errors = [];
  const failedSameOrigin = [];
  const origin = new URL(baseUrl).origin;

  page.on('console', message => {
    if (message.type() === 'error' && !message.text().startsWith('Failed to load resource:')) {
      errors.push(message.text());
    }
  });
  page.on('pageerror', error => errors.push(error.message));
  page.on('requestfailed', request => {
    if (request.url().startsWith(origin)) {
      failedSameOrigin.push(`${request.method()} ${request.url()}`);
    }
  });
  page.on('response', response => {
    if (response.url().startsWith(origin) && response.status() >= 400) {
      failedSameOrigin.push(`${response.status()} ${response.url()}`);
    }
  });

  if (path === '/dashboard.html') {
    await page.route('**/messages?**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total: 0, items: [] }),
    }));
  }
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

  const response = await page.goto(`${baseUrl}${path}`, { waitUntil: 'networkidle' });
  assert(response && response.ok(), `${width}px ${path}: page returned ${response?.status()}`);

  const state = await page.evaluate(() => {
    const ids = [...document.querySelectorAll('[id]')].map(el => el.id);
    const duplicateIds = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
    const brokenImages = [...document.images]
      .filter(image => image.complete && image.naturalWidth === 0)
      .map(image => image.getAttribute('src'));
    return {
      title: document.title,
      lang: document.documentElement.lang,
      duplicateIds,
      brokenImages,
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    };
  });

  assert(state.title.trim(), `${width}px ${path}: document title is empty`);
  assert(state.lang === 'en', `${width}px ${path}: document language is not English`);
  assert(state.duplicateIds.length === 0,
    `${width}px ${path}: duplicate IDs: ${state.duplicateIds.join(', ')}`);
  assert(state.brokenImages.length === 0,
    `${width}px ${path}: broken images: ${state.brokenImages.join(', ')}`);
  assert(state.scrollWidth <= state.clientWidth,
    `${width}px ${path}: horizontal overflow (${state.scrollWidth} > ${state.clientWidth})`);
  assert(errors.length === 0, `${width}px ${path}: console errors: ${errors.join(' | ')}`);
  assert(failedSameOrigin.length === 0,
    `${width}px ${path}: failed same-origin requests: ${failedSameOrigin.join(' | ')}`);

  await page.close();
}

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    for (const width of widths) {
      for (const path of pages) {
        await inspectPage(browser, path, width);
      }
    }
    console.log(`Site smoke tests passed for ${pages.length} pages at ${widths.join(', ')}px.`);
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
