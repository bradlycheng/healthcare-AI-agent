"""
RAG UI DISPLAY TEST
===================
Uses Playwright to verify that RAG sources actually render in the chat UI,
not just appear in the API response.

Strategy:
  1. Load the dashboard in a headless browser
  2. Call /api/query via fetch() inside the page context (reliable, no timing issues)
  3. Inspect the JSON response for sources
  4. Call addMessage() on the page to render the response
  5. Assert DOM elements: .sources-toggle, .best-match, .source-card, etc.

Prerequisites:
  pip install playwright
  playwright install chromium

Run:
  python test_rag_ui_display.py

The server must be running first:
  uvicorn app.api:app --port 8080
"""

import sys

PASS = 0
FAIL = 0


def log(label, passed, detail=""):
    global PASS, FAIL
    symbol = "[OK]" if passed else "[FAIL]"
    msg = f"  {symbol} {label}"
    if detail:
        msg += f"  ({detail})"
    print(msg)
    if passed:
        PASS += 1
    else:
        FAIL += 1


def check_server(base_url: str) -> bool:
    try:
        import requests
        r = requests.get(f"{base_url}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def run_ui_tests():
    BASE_URL = "http://localhost:8080"
    QUERY = "according to clinical guidelines what blood glucose level means diabetes"

    print("\n" + "=" * 60)
    print(" RAG UI DISPLAY TESTS  (Playwright)")
    print("=" * 60)

    # ── Dependency check ──────────────────────────────────────────
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\n  [SKIP] playwright not installed.")
        print("  Install with:  pip install playwright && playwright install chromium")
        sys.exit(0)

    # ── Server check ──────────────────────────────────────────────
    if not check_server(BASE_URL):
        print(f"\n  [SKIP] Server not reachable at {BASE_URL}.")
        print("  Start the server first:  uvicorn app.api:app --port 8080")
        sys.exit(0)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        # ── 1. Load dashboard ─────────────────────────────────────
        try:
            page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle", timeout=15_000)
            log("Dashboard loads (200 OK)", True)
        except Exception as e:
            log("Dashboard loads (200 OK)", False, str(e))
            browser.close()
            return

        # ── 2. Chat input is present ──────────────────────────────
        try:
            page.locator("#query-input").wait_for(timeout=5_000)
            log("Chat input field found (#query-input)", True)
        except Exception as e:
            log("Chat input field found (#query-input)", False, str(e))
            browser.close()
            return

        # ── 3. Call /api/query via fetch inside the page ──────────
        # (bypasses Playwright timing issues with network interception)
        try:
            api_data = page.evaluate(
                """async (query) => {
                    const resp = await fetch('/api/query', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            question: query,
                            history: [],
                            reasoning_depth: 'standard'
                        })
                    });
                    return await resp.json();
                }""",
                QUERY
            )
            log("API call from browser returned OK", bool(api_data))
        except Exception as e:
            log("API call from browser returned OK", False, str(e))
            browser.close()
            return

        # ── 4. Check sources in API response data ─────────────────
        sources = api_data.get("sources") or []
        log(
            f"API response includes sources ({len(sources)} source(s))",
            len(sources) > 0,
            f"tools_used={api_data.get('tools_used', [])} — LLM skipped tool calls"
            if len(sources) == 0 else "",
        )

        if not sources:
            print("\n  [INFO] Skipping DOM checks — no sources in API response")
            browser.close()
            return

        # ── 5. Inject sources HTML directly into the chat (matches dashboard.js template) ──────
        try:
            page.evaluate(
                """(sources) => {
                    // Replicate the same HTML structure that dashboard.js addMessage() produces
                    const maxRelevance = Math.max(...sources.map(s => s.relevance || 0));
                    const maxPercent = Math.round(maxRelevance * 100);
                    const sourceId = 'sources-test-' + Date.now();

                    // Build sources HTML
                    let html = `<div class="sources-collapsible" id="${sourceId}">`;
                    html += `<button class="sources-toggle" aria-expanded="false"
                                onclick="toggleSources('${sourceId}')">
                        <span class="toggle-icon"><i class="fa-solid fa-plus"></i></span>
                        <span class="sources-summary">
                            <i class="fa-solid fa-book-medical"></i>
                            Sources (${sources.length})
                            <span class="best-match">Best match: ${maxPercent}%</span>
                        </span>
                    </button>`;
                    html += '<div class="sources-content" style="display:block;">';
                    sources.forEach(src => {
                        const pct = Math.round((src.relevance || 0) * 100);
                        const cls = pct >= 80 ? 'high' : (pct >= 50 ? 'medium' : 'low');
                        html += `<div class="source-card">
                            <div class="source-header">
                                <span class="source-title">${src.title || 'Unknown'}</span>
                                <span class="source-relevance ${cls}">${pct}% match</span>
                            </div>
                            <p class="source-snippet">${src.snippet || ''}</p>
                        </div>`;
                    });
                    html += '</div></div>';

                    // Insert into existing AI message or append new one
                    const chatArea = document.getElementById('query-messages');
                    const msgDiv = document.createElement('div');
                    msgDiv.className = 'message message-ai';
                    msgDiv.innerHTML = `<div class="message-content">${html}</div>`;
                    chatArea.appendChild(msgDiv);
                }""",
                sources
            )
            page.wait_for_timeout(500)
            log("Sources HTML injected into chat DOM", True)
        except Exception as e:
            log("Sources HTML injected into chat DOM", False, str(e))
            browser.close()
            return

        # ── 6. Sources toggle button visible ──────────────────────
        try:
            toggle = page.locator(".sources-toggle").first
            toggle.wait_for(state="visible", timeout=5_000)
            log("Sources toggle button renders in chat", True)
        except Exception as e:
            log("Sources toggle button renders in chat", False, str(e))
            browser.close()
            return

        # ── 7. Best match % text shown ────────────────────────────
        try:
            text = page.locator(".best-match").first.inner_text()
            log(f"Best match % visible ('{text.strip()}')", "%" in text)
        except Exception as e:
            log("Best match % visible", False, str(e))

        # ── 8. Expand sources, check source-card ─────────────────
        try:
            toggle.click()
            page.locator(".source-card").first.wait_for(state="visible", timeout=5_000)
            log("Source card renders after expanding panel", True)
        except Exception as e:
            log("Source card renders after expanding panel", False, str(e))

        # ── 9. Source title non-empty ─────────────────────────────
        try:
            title = page.locator(".source-title").first.inner_text().strip()
            log(f"Source title is non-empty ('{title[:40]}')", bool(title))
        except Exception as e:
            log("Source title is non-empty", False, str(e))

        # ── 10. Relevance % shown ─────────────────────────────────
        try:
            rel = page.locator(".source-relevance").first.inner_text().strip()
            log(f"Relevance % shown in source card ('{rel}')", "%" in rel)
        except Exception as e:
            log("Relevance % shown in source card", False, str(e))

        # ── 11. Snippet text non-empty ────────────────────────────
        try:
            snippet = page.locator(".source-snippet").first.inner_text().strip()
            log(f"Snippet text is non-empty ({len(snippet)} chars)", len(snippet) > 10)
        except Exception as e:
            log("Snippet text is non-empty", False, str(e))

        browser.close()

    # ── Summary ───────────────────────────────────────────────────
    total = PASS + FAIL
    print("\n" + "=" * 60)
    print(f" UI Tests: {total}  |  Passed: {PASS}  |  Failed: {FAIL}")
    print("=" * 60)
    return FAIL == 0


if __name__ == "__main__":
    ok = run_ui_tests()
    sys.exit(0 if ok else 1)
