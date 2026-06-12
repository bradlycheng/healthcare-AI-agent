from html.parser import HTMLParser
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
TOP_LEVEL_PAGES = sorted(WEB.glob("*.html"))


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.local_refs = []
        self.background_glows = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.add(values["id"])

        classes = values.get("class", "").split()
        if "background-glow" in classes:
            self.background_glows += 1

        attribute = "href" if tag in {"a", "link"} else "src"
        ref = values.get(attribute)
        if ref and not ref.startswith(
            ("http://", "https://", "mailto:", "tel:", "#", "data:")
        ):
            self.local_refs.append(ref)


def parse_page(path):
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def local_target(page, ref):
    clean_ref = ref.split("?", 1)[0].split("#", 1)[0]
    if not clean_ref or clean_ref == "/":
        clean_ref = "index.html"
    elif clean_ref.startswith("/"):
        clean_ref = clean_ref[1:]
    return WEB / clean_ref


def test_top_level_pages_use_current_shared_stylesheet():
    for page in TOP_LEVEL_PAGES:
        if page.name == "verify_full_reset.html":
            continue
        source = page.read_text(encoding="utf-8")
        assert 'href="style.css?v=33"' in source, page.name


def test_public_pages_use_current_signal_atlas_stylesheet():
    public_pages = (
        "index.html",
        "dashboard.html",
        "process-data.html",
        "warden.html",
        "about.html",
        "patient.html",
        "portfolio.html",
        "game.html",
    )
    for page_name in public_pages:
        source = (WEB / page_name).read_text(encoding="utf-8")
        assert 'href="signal-atlas.css?v=3"' in source, page_name


def test_portfolio_uses_shared_design_system_and_project_contract():
    source = (WEB / "portfolio.html").read_text(encoding="utf-8")
    assert "<style>" not in source
    assert source.count('class="portfolio-card ') == 3
    assert source.count('class="btn-primary portfolio-link"') == 3
    assert 'class="portfolio-kicker"' in source
    assert 'src="script.js?v=1.1.4"' in source


def test_patient_page_uses_shared_panel_system_and_versioned_script():
    source = (WEB / "patient.html").read_text(encoding="utf-8")
    assert '<body class="dashboard-page patient-page">' in source
    assert 'class="summary-title"' in source
    assert 'class="summary-actions"' in source
    assert 'src="patient.js?v=2"' in source


def test_process_data_has_page_heading():
    source = (WEB / "process-data.html").read_text(encoding="utf-8")
    assert "<h1>Process Data</h1>" in source


def test_game_page_uses_direct_launch_instead_of_blocked_embed():
    source = (WEB / "game.html").read_text(encoding="utf-8")
    assert "<iframe" not in source
    assert 'href="/game/index.html"' in source
    assert 'class="btn-primary game-launch-button"' in source


def test_local_page_assets_and_links_exist():
    missing = []
    for page in TOP_LEVEL_PAGES:
        parser = parse_page(page)
        for ref in parser.local_refs:
            target = local_target(page, ref)
            if not target.exists():
                missing.append(f"{page.name}: {ref}")
    assert missing == []


def test_dashboard_keeps_javascript_contract_ids():
    required_ids = {
        "alerts-banner",
        "alerts-view",
        "alerts-dismiss",
        "alert-patient-label",
        "refresh-btn",
        "delete-btn",
        "stat-total",
        "stat-patients",
        "stat-abnormal",
        "stat-recent",
        "query-messages",
        "query-input",
        "reasoning-depth",
        "query-submit",
        "search-input",
        "filter-flag",
        "filter-date",
        "messages-body",
        "prev-page",
        "next-page",
        "detail-modal",
        "reset-modal",
    }
    parser = parse_page(WEB / "dashboard.html")
    assert required_ids <= parser.ids


def test_dashboard_does_not_load_legacy_boxy_override():
    source = (WEB / "dashboard.html").read_text(encoding="utf-8")
    assert "boxy.css" not in source
    assert 'src="dashboard.js?v=14"' in source


def test_critical_alert_banner_has_single_accessible_surface():
    source = (WEB / "dashboard.html").read_text(encoding="utf-8")
    assert source.count('id="alerts-banner"') == 1
    assert "active-alerts-box" not in source
    assert 'id="alerts-banner" class="alerts-banner hidden" role="alert"' in source
    assert 'id="alerts-view" class="alerts-view" type="button"' in source
    assert 'id="alerts-dismiss" class="alerts-dismiss" type="button"' in source
    assert 'aria-label="Dismiss critical alerts"' in source

    script = (WEB / "dashboard.js").read_text(encoding="utf-8")
    required_behavior = (
        "criticalCount > 0 && !isCriticalBannerDismissed",
        "const criticalPatientIds = new Set();",
        "criticalPatientIds.add(msg.patient_id || `message-${msg.id ?? index}`);",
        "const criticalCount = criticalPatientIds.size;",
        "alertCount.textContent = criticalCount;",
        "criticalCount === 1 ? 'patient requires' : 'patients require'",
        "filterFlag.value = 'critical';",
        "isCriticalBannerDismissed = true;",
        "alertBanner.classList.add('hidden');",
    )
    for expected in required_behavior:
        assert expected in script
    assert "alertBanner.onclick" not in script
    assert 'alertsView.addEventListener(\'click\'' in script


def test_no_duplicate_background_decorations():
    duplicates = {}
    for page in TOP_LEVEL_PAGES:
        count = parse_page(page).background_glows
        if count > 1:
            duplicates[page.name] = count
    assert duplicates == {}


def test_chat_has_explicit_desktop_and_mobile_size_constraints():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert "grid-template-rows: auto minmax(420px, 500px) auto auto auto;" in css
    assert "grid-template-rows: auto minmax(360px, 52vh) auto auto auto;" in css
    assert "grid-template-rows: auto minmax(330px, 50vh) auto auto auto;" in css
    assert re.search(r"\.query-messages\s*\{[^}]*overflow-y:\s*auto;", css, re.S)
    assert re.search(r"\.message-content\s*\{[^}]*min-width:\s*0;", css, re.S)
    assert re.search(r"\.markdown-content table\s*\{[^}]*overflow-x:\s*auto", css, re.S)


def test_chat_messages_keep_directional_alignment_contract():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert re.search(
        r"\.query-messages \.message\s*\{[^}]*display:\s*flex;[^}]*width:\s*100%;",
        css,
        re.S,
    )
    assert re.search(
        r"\.query-messages \.message-user\s*\{[^}]*justify-content:\s*flex-end;",
        css,
        re.S,
    )
    assert re.search(
        r"\.query-messages \.message-ai\s*\{[^}]*justify-content:\s*flex-start;",
        css,
        re.S,
    )
    assert re.search(
        r"\.query-messages \.message-user \.message-content\s*\{"
        r"[^}]*width:\s*fit-content;"
        r"[^}]*max-width:\s*min\(78%,\s*980px\);"
        r"[^}]*margin-left:\s*auto;",
        css,
        re.S,
    )


def test_chat_submission_and_rendering_workflow_contract():
    script = (WEB / "dashboard.js").read_text(encoding="utf-8")
    required_workflow = (
        "queryInput.addEventListener('keydown', (e) => {",
        "!e.isComposing && !e.repeat",
        "e.preventDefault();",
        "let isQueryPending = false;",
        "querySubmit.disabled = isQueryPending || !queryInput.value.trim();",
        "const question = typeof rawQuestion === 'string' ? rawQuestion.trim() : '';",
        "if (!question || isQueryPending) {",
        "if (isQueryPending) return;",
        "chip.addEventListener('click', () => {\n            if (isQueryPending) return;",
        "isQueryPending = true;",
        "querySubmit.disabled = true;",
        "addMessage(question, 'user');",
        "const loadingId = addLoadingMessage();",
        "removeMessage(loadingId);",
        "isQueryPending = false;",
        "querySubmit.disabled = !queryInput.value.trim();",
        "queryInput.focus();",
        "queryMessages.scrollTop = queryMessages.scrollHeight;",
        "? `<div class=\"markdown-content\">${marked.parse(text)}</div>`",
        ": `<p>${escapeHtml(text)}</p>`",
        "messageDiv.classList.add('message-error');",
        "messageDiv.setAttribute('role', 'alert');",
        "messageDiv.setAttribute('role', 'status');",
    )
    for expected in required_workflow:
        assert expected in script
    assert "queryInput.addEventListener('keypress'" not in script
    assert "KeyboardEvent('keypress'" not in script


def test_chat_rich_content_and_error_states_stay_contained():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    containment_rules = (
        r"\.message-content pre,\s*\.message-content code,[^{]*\{"
        r"[^}]*max-width:\s*100%;"
        r"[^}]*overflow-x:\s*auto;"
        r"[^}]*overflow-wrap:\s*anywhere;",
        r"\.markdown-content table\s*\{"
        r"[^}]*display:\s*block\s*!important;"
        r"[^}]*max-width:\s*100%;"
        r"[^}]*overflow-x:\s*auto\s*!important;",
        r"\.agent-tools-badge,\s*\.sources-collapsible,\s*\.reasoning-trace\s*\{"
        r"[^}]*max-width:\s*100%;",
        r"\.query-messages \.message-error \.message-content\s*\{"
        r"[^}]*background:\s*#211615\s*!important;"
        r"[^}]*border-left:\s*2px solid #d06a62\s*!important;"
        r"[^}]*color:\s*#efc3be\s*!important;",
    )
    for pattern in containment_rules:
        assert re.search(pattern, css, re.S)


def test_chat_tables_share_columns_and_scroll_as_one_unit():
    script = (WEB / "dashboard.js").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert "messageDiv.querySelectorAll('.markdown-content table').forEach(table => {" in script
    assert "wrapper.className = 'chat-table-scroll';" in script
    assert "wrapper.setAttribute('aria-label', 'Scrollable response table');" in script
    assert "wrapper.tabIndex = 0;" in script
    assert re.search(
        r"\.chat-table-scroll \.markdown-content table,"
        r"\s*\.markdown-content \.chat-table-scroll table\s*\{"
        r"[^}]*display:\s*table\s*!important;"
        r"[^}]*border-collapse:\s*collapse;"
        r"[^}]*table-layout:\s*auto;",
        css,
        re.S,
    )
    assert re.search(r"\.chat-table-scroll thead\s*\{[^}]*display:\s*table-header-group;", css, re.S)
    assert re.search(r"\.chat-table-scroll tbody\s*\{[^}]*display:\s*table-row-group;", css, re.S)
    assert re.search(r"\.chat-table-scroll tr\s*\{[^}]*display:\s*table-row;", css, re.S)


def test_chat_controls_and_log_have_accessible_names():
    source = (WEB / "dashboard.html").read_text(encoding="utf-8")
    required_markup = (
        'id="query-messages" role="log" aria-live="polite"',
        'id="query-input" placeholder="Ask about your patient data..."',
        'aria-label="Ask about your patient data"',
        'id="reasoning-depth" class="query-depth-select" aria-label="Reasoning depth"',
        'id="query-submit" class="btn-query-submit" aria-label="Send question"',
    )
    for expected in required_markup:
        assert expected in source


def test_no_known_mojibake_in_frontend_sources():
    bad_tokens = ("â€", "â€¢", "â†", "Ã", "\ufffd")
    failures = []
    for extension in ("*.html", "*.css", "*.js"):
        for path in WEB.rglob(extension):
            source = path.read_text(encoding="utf-8")
            for token in bad_tokens:
                if token in source:
                    failures.append(f"{path.relative_to(ROOT)}: {token}")
    assert failures == []


def test_displayed_email_uses_name_casing():
    failures = []
    for page in TOP_LEVEL_PAGES:
        source = page.read_text(encoding="utf-8")
        if "mailto:bradly@healthdataagent.com" in source:
            failures.append(page.name)
        if ">bradly@healthdataagent.com" in source:
            failures.append(page.name)
    assert failures == []


def test_landing_updates_cta_uses_mailto():
    source = (WEB / "index.html").read_text(encoding="utf-8")
    script = (WEB / "script.js").read_text(encoding="utf-8")
    required_markup = (
        'href="mailto:Bradly@healthdataagent.com?subject=Health%20Data%20Agent%20Updates"',
        'class="btn-primary large updates-mailto"',
        'Subscribe for Updates',
        'Request a governance review',
    )
    for expected in required_markup:
        assert expected in source
    assert 'id="updates-form"' not in source
    assert "fetch('/api/contact'" not in script
