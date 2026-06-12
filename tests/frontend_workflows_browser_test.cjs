const { chromium } = require('playwright');

const baseUrl = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:8080';
const widths = [375, 1440];
const height = 900;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function parsePayload() {
  return {
    patient: {
      id: '12345',
      first_name: 'John',
      last_name: 'Smith',
      dob: '19750315',
      sex: 'M',
    },
    structured_observations: [
      {
        source: 'HL7',
        code: '49563-0',
        display: 'Troponin I',
        value: '0.12',
        unit: 'ng/mL',
        flag: 'HH',
        reference_low: '0.00',
        reference_high: '0.04',
        alert_level: 'CRITICAL',
        alert_message: 'Critical troponin result',
      },
    ],
    clinical_summary: 'Critical troponin elevation requires immediate clinical review.',
    fhir_bundle: { resourceType: 'Bundle', type: 'collection', entry: [] },
    hl7_ack: 'MSH|^~\\&|HealthDataAgent|ACK\rMSA|AA|MSG_CARDIAC',
  };
}

async function assertNoPageOverflow(page, label) {
  const state = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert(state.scrollWidth <= state.clientWidth,
    `${label}: page has horizontal overflow (${state.scrollWidth} > ${state.clientWidth})`);
}

async function testProcessData(browser, width) {
  const page = await browser.newPage({ viewport: { width, height } });
  const parseRequests = [];
  let savePayload = null;

  await page.route('**/oru/parse', async route => {
    parseRequests.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(parsePayload()),
    });
  });
  await page.route('**/messages', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    savePayload = route.request().postDataJSON();
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({ id: 42 }),
    });
  });

  await page.goto(`${baseUrl}/process-data.html`, { waitUntil: 'networkidle' });
  await page.locator('label.toggle-switch').click();
  assert(!(await page.locator('#ai-toggle').isChecked()),
    `${width}px: AI toggle did not switch off`);
  await page.locator('#process-btn').click();
  await page.locator('#results-area:not(.hidden)').waitFor();

  assert(parseRequests.length === 1, `${width}px: preview should make one parse request with AI disabled`);
  assert(parseRequests[0].persist === false, `${width}px: preview must not persist automatically`);
  assert(parseRequests[0].use_llm === false, `${width}px: disabled AI toggle was ignored`);
  assert((await page.locator('#res-patient').innerText()).includes('John Smith'),
    `${width}px: parsed patient was not rendered`);
  assert(await page.locator('#res-obs-body tr').count() === 1,
    `${width}px: parsed observation table was not rendered`);
  assert(await page.locator('#save-btn').isVisible(), `${width}px: save action is not visible`);

  await page.locator('#save-btn').click();
  await page.locator('#analyze-another-btn:not(.hidden)').waitFor();

  assert(savePayload !== null, `${width}px: save did not send a request`);
  assert(savePayload.raw_hl7.includes('ORU^R01'), `${width}px: save omitted the raw HL7`);
  assert(savePayload.structured_observations.length === 1,
    `${width}px: save omitted the selected observation`);
  assert(savePayload.structured_observations[0].display === 'Troponin I',
    `${width}px: save changed the observation display name`);

  await assertNoPageOverflow(page, `${width}px process data`);
  await page.close();
}

async function testResetDemo(browser, width) {
  const page = await browser.newPage({ viewport: { width, height } });
  let resetCount = 0;
  let resetPayload = null;

  await page.route('**/messages?**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ total: 0, items: [] }),
  }));
  await page.route('**/admin/reset', async route => {
    resetCount += 1;
    resetPayload = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true }),
    });
  });

  await page.goto(`${baseUrl}/dashboard.html`, { waitUntil: 'networkidle' });

  const headerActions = await page.locator('.header-actions').evaluate(container => {
    const refresh = container.querySelector('#refresh-btn').getBoundingClientRect();
    const reset = container.querySelector('#delete-btn').getBoundingClientRect();
    return {
      refreshHeight: Math.round(refresh.height),
      resetHeight: Math.round(reset.height),
      refreshWidth: Math.round(refresh.width),
      resetWidth: Math.round(reset.width),
      refreshClipped: container.querySelector('#refresh-btn').scrollWidth >
        container.querySelector('#refresh-btn').clientWidth,
      resetClipped: container.querySelector('#delete-btn').scrollWidth >
        container.querySelector('#delete-btn').clientWidth,
    };
  });
  assert(headerActions.refreshHeight === 46 && headerActions.resetHeight === 46,
    `${width}px: Refresh and Reset Demo controls are not equally sized`);
  assert(headerActions.refreshWidth > 100 && headerActions.resetWidth > 100,
    `${width}px: dashboard header controls are too narrow`);
  assert(!headerActions.refreshClipped && !headerActions.resetClipped,
    `${width}px: dashboard header control text is clipped`);

  await page.locator('#delete-btn').click();
  await page.locator('#reset-modal.visible').waitFor();
  await page.waitForFunction(() => document.activeElement?.id === 'reset-password');
  assert(await page.locator('#reset-password').evaluate(el => el === document.activeElement),
    `${width}px: reset password did not receive focus`);

  await page.locator('#reset-confirm-btn').click();
  assert(resetCount === 0, `${width}px: empty reset password triggered an API request`);
  assert((await page.locator('.toast-error').last().innerText()).includes('Please enter'),
    `${width}px: empty password guidance was not shown`);

  await page.locator('#reset-password').fill('test-password-not-sent-to-live-api');
  await page.locator('#reset-confirm-btn').click();
  await page.locator('#reset-modal').waitFor({ state: 'hidden' });

  assert(resetCount === 1, `${width}px: reset should send exactly one request`);
  assert(resetPayload.password === 'test-password-not-sent-to-live-api',
    `${width}px: reset password payload is incorrect`);
  assert((await page.locator('.toast-success').last().innerText()).includes('Database reset'),
    `${width}px: reset success confirmation was not shown`);

  await assertNoPageOverflow(page, `${width}px reset modal`);
  await page.close();
}

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    for (const width of widths) {
      await testProcessData(browser, width);
      await testResetDemo(browser, width);
    }
    console.log(`Process Data and Reset Demo browser tests passed at ${widths.join(', ')}px.`);
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
