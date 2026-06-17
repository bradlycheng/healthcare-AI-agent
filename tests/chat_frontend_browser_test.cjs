const { chromium } = require('playwright');

const baseUrl = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:8080';
const widths = [320, 375, 768, 1024, 1440];
const height = 900;

const tableAnswer = [
  'Here are the patients requiring review.',
  '',
  '| Patient | Status | Findings |',
  '| --- | --- | --- |',
  '| Harold Bennett | CRITICAL | Systolic BP 185 |',
  '| Hannah Ortiz | CRITICAL | Glucose 55 |',
  '| David Martinez | WARNING | Glucose 250 |',
  '',
  '```text',
  'Clinical review recommended.',
  '```',
].join('\n');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function mockDashboardData(page) {
  await page.route('**/messages?**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ total: 0, items: [] }),
  }));
}

async function mockQuery(page, handler) {
  await page.route('**/api/query', handler);
}

async function openDashboard(browser, width) {
  const page = await browser.newPage({ viewport: { width, height } });
  await mockDashboardData(page);
  await page.goto(`${baseUrl}/dashboard.html`, { waitUntil: 'networkidle' });
  return page;
}

function successPayload() {
  return {
    success: true,
    answer: tableAnswer,
    highlights: ['Critical findings require immediate attention.'],
    sql_used: 'SELECT patient_id FROM observations',
    row_count: 3,
    sources: [],
    reasoning_trace: [],
    tools_used: ['query_database'],
    needs_clarification: false,
    clarification_question: null,
    clarification_options: [],
  };
}

async function assertControlsContained(page, width) {
  const state = await page.evaluate(() => {
    const viewportWidth = document.documentElement.clientWidth;
    const controls = [
      document.querySelector('#query-input'),
      document.querySelector('#query-submit'),
    ].map(el => {
      const rect = el.getBoundingClientRect();
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
    });
    const overlaps = controls.some((a, index) => controls.slice(index + 1).some(b => (
      Math.max(a.left, b.left) < Math.min(a.right, b.right)
      && Math.max(a.top, b.top) < Math.min(a.bottom, b.bottom)
    )));
    return {
      controls,
      overlaps,
      pageOverflow: document.documentElement.scrollWidth > viewportWidth,
      viewportWidth,
    };
  });

  assert(!state.pageOverflow, `${width}px: chat causes page-level horizontal overflow`);
  assert(!state.overlaps, `${width}px: chat controls overlap`);
  for (const control of state.controls) {
    assert(control.left >= 0 && control.right <= state.viewportWidth,
      `${width}px: a chat control is clipped`);
  }
}

async function testResponsiveSuccess(browser) {
  for (const width of widths) {
    const page = await openDashboard(browser, width);
    let queryCount = 0;
    await mockQuery(page, route => {
      queryCount += 1;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(successPayload()),
      });
    });

    const input = page.locator('#query-input');
    await input.fill('Which patients should I be worried about?');
    await input.press('Enter');
    await page.locator('.chat-table-scroll').waitFor({ state: 'visible' });

    const state = await page.evaluate(() => {
      const log = document.querySelector('#query-messages');
      const userMessage = log.querySelector('.message-user');
      const user = log.querySelector('.message-user .message-content');
      const wrapper = log.querySelector('.chat-table-scroll');
      const table = wrapper.querySelector('table');
      const input = document.querySelector('#query-input');
      const userMessageRect = userMessage.getBoundingClientRect();
      const userRect = user.getBoundingClientRect();
      const headerWidths = [...table.querySelectorAll('thead th')]
        .map(cell => Math.round(cell.getBoundingClientRect().width));
      const rowWidths = [...table.querySelectorAll('tbody tr:first-child td')]
        .map(cell => Math.round(cell.getBoundingClientRect().width));
      return {
        activeInput: document.activeElement === input,
        loadingCount: log.querySelectorAll('.message-loading').length,
        errorCount: log.querySelectorAll('.message-error').length,
        toolBadge: log.querySelector('.agent-tools-badge')?.textContent,
        tableDisplay: getComputedStyle(table).display,
        wrapperOverflow: getComputedStyle(wrapper).overflowX,
        wrapperWidth: Math.round(wrapper.getBoundingClientRect().width),
        wrapperScrollWidth: wrapper.scrollWidth,
        headerWidths,
        rowWidths,
        userRightGap: Math.round(userMessageRect.right - userRect.right),
        logAtBottom: Math.abs(log.scrollHeight - log.clientHeight - log.scrollTop) <= 2,
      };
    });

    assert(queryCount === 1, `${width}px: expected one query request`);
    assert(state.activeInput, `${width}px: input focus was not restored`);
    assert(state.loadingCount === 0, `${width}px: loading state was not removed`);
    assert(state.errorCount === 0, `${width}px: success rendered as an error`);
    assert(state.toolBadge?.includes('query_database'), `${width}px: tool badge missing`);
    assert(state.tableDisplay === 'table', `${width}px: markdown table lost native table layout`);
    assert(['auto', 'scroll'].includes(state.wrapperOverflow),
      `${width}px: table wrapper is not horizontally scrollable`);
    assert(JSON.stringify(state.headerWidths) === JSON.stringify(state.rowWidths),
      `${width}px: table header and body columns do not align`);
    assert(state.userRightGap <= 24, `${width}px: user message is not right aligned`);
    assert(state.logAtBottom, `${width}px: new response did not scroll into view`);
    if (width <= 375) {
      assert(state.wrapperScrollWidth > state.wrapperWidth,
        `${width}px: wide table should scroll inside the chat`);
    }

    await assertControlsContained(page, width);
    await page.close();
  }
}

async function testOldestPatientDeepModeRegression(browser) {
  const page = await openDashboard(browser, 375);
  let requestPayload = null;
  await mockQuery(page, route => {
    requestPayload = route.request().postDataJSON();
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ...successPayload(),
        answer: [
          'The oldest patient is **Elizabeth SearchTest**, age **78**.',
          '',
          '| Patient | Status | Findings |',
          '| :--- | :--- | :--- |',
          '| **Elizabeth SearchTest** | -- | Age: **78**; DOB: 1947-07-12 |',
        ].join('\n'),
        row_count: 1,
        sql_used: 'SELECT patient_first_name FROM hl7_messages ORDER BY patient_dob ASC LIMIT 1',
      }),
    });
  });

  assert(await page.locator('#reasoning-depth').count() === 0,
    'reasoning mode selector must stay removed');

  const input = page.locator('#query-input');
  await input.fill('Who is the oldest patient?');
  await input.press('Enter');
  await page.locator('.chat-table-scroll').waitFor({ state: 'visible' });

  assert(requestPayload?.question === 'Who is the oldest patient?',
    'frontend changed the exact oldest-patient question');
  assert(requestPayload?.reasoning_depth === 'deep',
    'frontend did not submit the oldest-patient question in Deep mode');
  assert((await page.locator('#query-messages').innerText()).includes('Elizabeth SearchTest'),
    'oldest-patient answer did not render in chat');
  assert(await page.locator('.message-error').count() === 0,
    'oldest-patient answer rendered as an error');

  await assertControlsContained(page, 375);
  await page.close();
}

async function testEmptyAndPendingSubmission(browser) {
  const page = await openDashboard(browser, 1024);
  let queryCount = 0;
  await mockQuery(page, async route => {
    queryCount += 1;
    await new Promise(resolve => setTimeout(resolve, 1500));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(successPayload()),
    });
  });

  const input = page.locator('#query-input');
  await input.fill('   ');
  await input.press('Enter');
  assert(queryCount === 0, 'whitespace-only input must not submit');
  assert(await page.locator('.message-user').count() === 0,
    'whitespace-only input must not create a user message');

  await input.fill('Show critical patients');
  await input.press('Enter');
  await page.locator('.message-loading').waitFor({ state: 'visible' });
  await input.fill('Second request while pending');
  await input.press('Enter');
  await page.locator('.suggestion-chip').first().click();
  await page.locator('.chat-table-scroll').waitFor({ state: 'visible' });

  assert(queryCount === 1, 'pending state must block repeated Enter and suggestion submissions');
  assert(await page.locator('.message-user').count() === 1,
    'pending state must not add duplicate user messages');
  await page.close();
}

async function testErrorAndRateLimitStates(browser) {
  const errorPage = await openDashboard(browser, 375);
  await mockQuery(errorPage, route => route.fulfill({
    status: 500,
    contentType: 'application/json',
    body: JSON.stringify({ detail: 'Test failure' }),
  }));
  await errorPage.locator('#query-input').fill('Trigger an error');
  await errorPage.locator('#query-input').press('Enter');
  await errorPage.locator('.message-error').waitFor({ state: 'visible' });
  assert(await errorPage.locator('.message-error').getAttribute('role') === 'alert',
    'server error must use alert semantics');
  assert((await errorPage.locator('.message-error').innerText()).includes('Please try again'),
    'server error fallback message missing');
  assert(await errorPage.locator('.message-loading').count() === 0,
    'server error must remove loading state');
  await assertControlsContained(errorPage, 375);
  await errorPage.close();

  const ratePage = await openDashboard(browser, 320);
  await mockQuery(ratePage, route => route.fulfill({
    status: 429,
    contentType: 'application/json',
    body: JSON.stringify({ detail: 'Rate limited' }),
  }));
  await ratePage.locator('#query-input').fill('Ask too quickly');
  await ratePage.locator('#query-submit').click();
  await ratePage.locator('.message-error').waitFor({ state: 'visible' });
  assert((await ratePage.locator('.message-error').innerText()).includes('Please wait'),
    'rate-limit guidance missing');
  assert(await ratePage.locator('.message-loading').count() === 0,
    'rate limit must remove loading state');
  await assertControlsContained(ratePage, 320);
  await ratePage.close();
}

async function testSourceDocumentViewer(browser) {
  const page = await openDashboard(browser, 1024);
  const agentContent = [
    '# Agent Expertise: Critical Rules & Use Cases',
    '',
    '## Expert Refinement of Critical Rules',
    '',
    'The "Data Primacy" Rule treats tool results as the patient\'s ground truth.',
  ].join('\n');
  const labContent = '# Medical Reference: Common Lab Values\n\nReference ranges.';

  await mockQuery(page, route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      ...successPayload(),
      sources: [
        {
          title: 'Agent Expertise: Critical Rules & Use Cases',
          filename: 'agent_expertise.md',
          snippet: 'Expert refinement of critical rules.',
          full_snippet: agentContent,
          relevance: 0.92,
        },
        {
          title: 'Common Lab Values',
          filename: 'lab_values_reference.txt',
          snippet: 'Common laboratory reference ranges.',
          full_snippet: labContent,
          relevance: 0.84,
        },
      ],
    }),
  }));

  await page.route('**/api/document/*', route => {
    const filename = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop());
    const documents = {
      'agent_expertise.md': agentContent,
      'lab_values_reference.txt': labContent,
    };
    const content = documents[filename];
    return route.fulfill({
      status: content ? 200 : 404,
      contentType: 'application/json',
      body: JSON.stringify(content
        ? { filename, content }
        : { detail: 'Document not found' }),
    });
  });

  await page.locator('#query-input').fill('Explain critical rules');
  await page.locator('#query-submit').click();
  const sourcesToggle = page.locator('.sources-toggle');
  await sourcesToggle.waitFor({ state: 'visible' });
  await sourcesToggle.click();

  const sourceCards = page.locator('.source-card');
  assert(await sourceCards.count() === 2, 'expected both RAG source cards');

  const agentCard = sourceCards.filter({ hasText: 'Agent Expertise: Critical Rules & Use Cases' });
  assert(await agentCard.count() === 1, 'agent expertise source card missing');
  const agentButton = agentCard.getByRole('button', { name: 'View Full Document' });
  assert(await agentButton.count() === 1, 'agent expertise document button missing');
  await agentButton.click();

  const modal = page.locator('#doc-viewer-modal.visible');
  await modal.waitFor({ state: 'visible' });
  assert((await page.locator('#doc-modal-title').innerText())
    === 'Agent Expertise: Critical Rules & Use Cases',
  'agent expertise modal title is incorrect');
  assert((await page.locator('#doc-modal-body').innerText()).includes('Data Primacy'),
    'agent expertise document content did not load');

  const closeButton = modal.locator('.doc-modal-close');
  assert(await closeButton.count() === 1, 'document modal close button missing');
  await closeButton.click();

  const labCard = sourceCards.filter({ hasText: 'Common Lab Values' });
  assert(await labCard.count() === 1, 'common lab values source card missing');
  const labButton = labCard.getByRole('button', { name: 'View Full Document' });
  assert(await labButton.count() === 1, 'common lab values document button missing');
  await labButton.click();
  await modal.waitFor({ state: 'visible' });
  assert((await page.locator('#doc-modal-body').innerText()).includes('Reference ranges'),
    'existing text document source no longer loads');

  await page.close();
}

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    await testResponsiveSuccess(browser);
    await testOldestPatientDeepModeRegression(browser);
    await testEmptyAndPendingSubmission(browser);
    await testErrorAndRateLimitStates(browser);
    await testSourceDocumentViewer(browser);
    console.log(`Chat frontend browser tests passed at ${widths.join(', ')}px.`);
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
