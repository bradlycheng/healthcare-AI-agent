const { chromium } = require('playwright');

const baseUrl = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:8765';
const widths = [320, 375, 768, 1024, 1440];
const height = 900;

const messages = [
  {
    id: 1,
    patient_id: 'P-100',
    first_name: 'Alex',
    last_name: 'Rivera',
    message_type: 'ORU',
    received_at: '2026-06-10T12:00:00Z',
  },
  {
    id: 2,
    patient_id: 'P-100',
    first_name: 'Alex',
    last_name: 'Rivera',
    message_type: 'ORU',
    received_at: '2026-06-10T12:05:00Z',
  },
  {
    id: 3,
    patient_id: 'P-200',
    first_name: 'Sam',
    last_name: 'Lee',
    message_type: 'ORU',
    received_at: '2026-06-10T12:10:00Z',
  },
];

const observations = {
  1: [{ display: 'Heart rate', value: '130', flag: 'HH', alert_level: 'CRITICAL' }],
  2: [{ display: 'Blood pressure', value: '180/110', flag: 'HH', alert_level: 'CRITICAL' }],
  3: [{ display: 'Glucose', value: '160', flag: 'H', alert_level: 'WARNING' }],
};

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function mockApi(page, options = {}) {
  const {
    failObservationId = null,
    messageItems = messages,
    observationItems = observations,
  } = options;
  await page.route('**/messages?**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ items: messageItems, total: messageItems.length }),
  }));
  await page.route(/\/messages\/(\d+)\/observations$/, route => {
    const id = Number(route.request().url().match(/\/messages\/(\d+)\/observations$/)[1]);
    if (id === failObservationId) {
      return route.fulfill({ status: 500, body: 'observation failure' });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message_id: id, items: observationItems[id] || [] }),
    });
  });
}

async function bannerState(page) {
  return page.locator('#alerts-banner').evaluate(el => {
    const rect = el.getBoundingClientRect();
    return {
      hidden: el.classList.contains('hidden'),
      count: document.querySelector('#alert-count')?.textContent,
      label: document.querySelector('#alert-patient-label')?.textContent,
      role: el.getAttribute('role'),
      live: el.getAttribute('aria-live'),
      left: rect.left,
      right: rect.right,
      viewport: document.documentElement.clientWidth,
      pageOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      viewButtonHeight: document.querySelector('#alerts-view')?.getBoundingClientRect().height,
      dismissButtonHeight: document.querySelector('#alerts-dismiss')?.getBoundingClientRect().height,
      dismissButtonWidth: document.querySelector('#alerts-dismiss')?.getBoundingClientRect().width,
      dismissIconCount: document.querySelectorAll('#alerts-dismiss .fa-xmark').length,
    };
  });
}

async function testResponsiveAndUniqueCount(browser) {
  for (const width of widths) {
    const page = await browser.newPage({ viewport: { width, height } });
    await mockApi(page);
    await page.goto(`${baseUrl}/dashboard.html`, { waitUntil: 'networkidle' });
    const state = await bannerState(page);
    assert(!state.hidden, `${width}px: critical banner should be visible`);
    assert(state.count === '1', `${width}px: duplicate messages must count as one patient`);
    assert(state.label === 'patient requires', `${width}px: singular label is incorrect`);
    assert(state.role === 'alert' && state.live === 'assertive', `${width}px: alert semantics missing`);
    assert(state.left >= 0 && state.right <= state.viewport, `${width}px: banner overflows viewport`);
    assert(!state.pageOverflow, `${width}px: page has horizontal overflow`);
    assert(state.viewButtonHeight >= 40 && state.dismissButtonHeight >= 40,
      `${width}px: alert controls are smaller than 40px`);
    assert(state.dismissButtonWidth === state.dismissButtonHeight,
      `${width}px: dismiss control is not square`);
    assert(state.dismissIconCount === 1,
      `${width}px: dismiss control is missing its close icon`);

    const flagState = await page.locator('#messages-body').evaluate(body => {
      const cells = [...body.querySelectorAll('.flags-cell')];
      const lists = [...body.querySelectorAll('.flags-list')];
      const badgeHeights = [...body.querySelectorAll('.flags-list > *')]
        .map(element => Math.round(element.getBoundingClientRect().height));
      return {
        cellDisplays: cells.map(cell => getComputedStyle(cell).display),
        listDisplays: lists.map(list => getComputedStyle(list).display),
        cellCount: cells.length,
        listCount: lists.length,
        badgeHeights,
      };
    });
    assert(flagState.cellCount === messages.length && flagState.listCount === messages.length,
      `${width}px: each patient row must have one flag badge group`);
    assert(flagState.cellDisplays.every(display => display === 'table-cell'),
      `${width}px: flag cells must preserve table-cell layout`);
    assert(flagState.listDisplays.every(display => display === 'inline-flex'),
      `${width}px: flag groups must remain inline`);
    assert(flagState.badgeHeights.every(height => height === 26),
      `${width}px: flag badges do not share a 26px height`);
    await page.close();
  }
}

async function testWarningAndFailureStates(browser) {
  const emptyPage = await browser.newPage({ viewport: { width: 320, height } });
  await mockApi(emptyPage, { messageItems: [] });
  await emptyPage.goto(`${baseUrl}/dashboard.html`, { waitUntil: 'networkidle' });
  assert((await bannerState(emptyPage)).hidden, 'empty data must not show critical banner');
  await emptyPage.close();

  const warningPage = await browser.newPage({ viewport: { width: 375, height } });
  await mockApi(warningPage, { messageItems: [messages[2]] });
  await warningPage.goto(`${baseUrl}/dashboard.html`, { waitUntil: 'networkidle' });
  assert((await bannerState(warningPage)).hidden, 'warning-only data must not show critical banner');
  await warningPage.close();

  const failurePage = await browser.newPage({ viewport: { width: 375, height } });
  await mockApi(failurePage, { failObservationId: 1, messageItems: [messages[0]] });
  await failurePage.goto(`${baseUrl}/dashboard.html`, { waitUntil: 'networkidle' });
  assert((await bannerState(failurePage)).hidden, 'failed observation request must not create a critical alert');
  await failurePage.close();
}

async function testPluralCount(browser) {
  const page = await browser.newPage({ viewport: { width: 768, height } });
  const twoCriticalPatients = {
    ...observations,
    3: [{ display: 'Glucose', value: '500', flag: 'HH', alert_level: 'CRITICAL' }],
  };
  await mockApi(page, { observationItems: twoCriticalPatients });
  await page.goto(`${baseUrl}/dashboard.html`, { waitUntil: 'networkidle' });
  const state = await bannerState(page);
  assert(state.count === '2', 'two distinct critical patients must produce count 2');
  assert(state.label === 'patients require', 'plural label is incorrect');
  await page.close();
}

async function testActionsAndRefresh(browser) {
  const dismissPage = await browser.newPage({ viewport: { width: 375, height } });
  await mockApi(dismissPage);
  await dismissPage.goto(`${baseUrl}/dashboard.html`, { waitUntil: 'networkidle' });
  assert(await dismissPage.locator('#filter-flag').inputValue() === '',
    'filter must start at All Results');
  await dismissPage.locator('#alerts-dismiss').click();
  assert((await bannerState(dismissPage)).hidden, 'dismiss must hide the banner');
  assert(await dismissPage.locator('#filter-flag').inputValue() === '',
    'dismiss must not trigger the critical filter');
  await dismissPage.close();

  const page = await browser.newPage({ viewport: { width: 1024, height } });
  await mockApi(page);
  await page.goto(`${baseUrl}/dashboard.html`, { waitUntil: 'networkidle' });

  await page.locator('#alerts-view').focus();
  assert(await page.locator('#alerts-view').evaluate(el => el === document.activeElement),
    'View critical button must receive keyboard focus');
  await page.keyboard.press('Enter');
  assert(await page.locator('#filter-flag').inputValue() === 'critical',
    'Enter on View critical must apply the critical filter');
  assert(await page.locator('#messages-body tr.alert-row').count() === 2,
    'critical filter should show both critical messages');

  await page.locator('#alerts-dismiss').click();
  assert((await bannerState(page)).hidden, 'dismiss must hide the banner');

  await page.locator('#refresh-btn').click();
  await page.waitForLoadState('networkidle');
  assert((await bannerState(page)).hidden, 'dismissal must persist across in-page refreshes');
  await page.locator('#refresh-btn').click();
  await page.waitForLoadState('networkidle');
  assert(await page.locator('#messages-body tr.alert-row').count() === 2,
    'repeated refreshes must not duplicate critical rows');
  await page.close();
}

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    await testResponsiveAndUniqueCount(browser);
    await testWarningAndFailureStates(browser);
    await testPluralCount(browser);
    await testActionsAndRefresh(browser);
    console.log(`Critical banner browser tests passed at ${widths.join(', ')}px.`);
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
