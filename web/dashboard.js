// Dashboard JavaScript

// Global functions for agent UI (must be outside DOMContentLoaded for inline onclick)
function toggleTrace(traceId) {
    const container = document.getElementById(traceId);
    if (!container) return;
    const content = container.querySelector('.trace-content');
    const toggle = container.querySelector('.trace-toggle');
    const icon = toggle.querySelector('.toggle-icon i');

    if (content.style.display === 'none') {
        content.style.display = 'block';
        toggle.setAttribute('aria-expanded', 'true');
        icon.className = 'fa-solid fa-minus';
    } else {
        content.style.display = 'none';
        toggle.setAttribute('aria-expanded', 'false');
        icon.className = 'fa-solid fa-plus';
    }
}

function handleClarification(option) {
    const queryInput = document.getElementById('query-input');
    if (queryInput) {
        queryInput.value = option;
        queryInput.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter' }));
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // State
    let allMessages = [];
    let filteredMessages = [];
    let chatHistory = []; // Tracks user/AI conversation
    let currentPage = 1;
    const pageSize = 10;
    let isCriticalBannerDismissed = false; // Tracks if user hid the banner

    // DOM Elements
    const messagesBody = document.getElementById('messages-body');
    const searchInput = document.getElementById('search-input');
    const filterFlag = document.getElementById('filter-flag');
    const filterDate = document.getElementById('filter-date');
    const refreshBtn = document.getElementById('refresh-btn');
    const prevPageBtn = document.getElementById('prev-page');
    const nextPageBtn = document.getElementById('next-page');
    const pageInfo = document.getElementById('page-info');
    const showingCount = document.getElementById('showing-count');

    // Modal Elements
    const modal = document.getElementById('detail-modal');
    const closeModal = document.getElementById('close-modal');

    // Initialize
    console.log('Dashboard JS Loaded v7 (Custom Modal Reset)');



    // Determine API Base URL
    // If running from file://, default to localhost:8080
    // Otherwise (if served by Caddy or dev server), use relative path
    const API_BASE = (window.location.protocol === 'file:')
        ? 'http://localhost:8080'
        : '';

    console.log(`Determined API_BASE: "${API_BASE || '(Relative Path)'}"`);

    loadMessages();
    setupEventListeners();

    function setupEventListeners() {
        searchInput.addEventListener('input', debounce(applyFilters, 300));
        filterFlag.addEventListener('change', applyFilters);
        filterDate.addEventListener('change', applyFilters);
        refreshBtn.addEventListener('click', loadMessages);

        // Dismiss Critical Banner
        const alertsDismiss = document.getElementById('alerts-dismiss');
        if (alertsDismiss) {
            alertsDismiss.addEventListener('click', (e) => {
                e.stopPropagation(); // don't trigger banner click
                isCriticalBannerDismissed = true;
                const alertBanner = document.getElementById('alerts-banner');
                if (alertBanner) alertBanner.classList.add('hidden');
            });
        }

        // Event Delegation for Delete Button (More robust)
        document.addEventListener('click', (e) => {
            const btn = e.target.closest('#delete-btn');
            if (btn) {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                confirmDelete();
            }
        });

        prevPageBtn.addEventListener('click', () => changePage(-1));
        nextPageBtn.addEventListener('click', () => changePage(1));
        closeModal.addEventListener('click', hideModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) hideModal();
        });

        // Tab switching in modal
        document.querySelectorAll('.detail-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.detail-tab-content').forEach(c => c.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById(tab.dataset.tab).classList.add('active');
            });
        });
    }

    // Reset Modal Elements
    const resetModal = document.getElementById('reset-modal');
    const resetPasswordInput = document.getElementById('reset-password');
    const resetConfirmBtn = document.getElementById('reset-confirm-btn');
    const resetCancelBtn = document.getElementById('reset-cancel-btn');
    const closeResetModal = document.getElementById('close-reset-modal');

    // Show reset modal
    function showResetModal() {
        console.log('Opening reset modal');
        resetPasswordInput.value = '';
        resetModal.classList.add('visible');
        document.body.style.overflow = 'hidden';
        setTimeout(() => resetPasswordInput.focus(), 100);
    }

    // Hide reset modal
    function hideResetModal() {
        console.log('Closing reset modal');
        resetModal.classList.remove('visible');
        document.body.style.overflow = '';
        isResetting = false;
    }

    // Set up reset modal event listeners
    if (resetCancelBtn) {
        resetCancelBtn.addEventListener('click', hideResetModal);
    }
    if (closeResetModal) {
        closeResetModal.addEventListener('click', hideResetModal);
    }
    if (resetModal) {
        resetModal.addEventListener('click', (e) => {
            if (e.target === resetModal) hideResetModal();
        });
    }
    if (resetConfirmBtn) {
        resetConfirmBtn.addEventListener('click', performReset);
    }
    if (resetPasswordInput) {
        resetPasswordInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') performReset();
        });
    }

    let isResetting = false; // Prevent double-click issues

    // Called when Reset Demo button is clicked
    function confirmDelete() {
        if (isResetting) {
            console.log('Reset already in progress, ignoring click');
            return;
        }
        isResetting = true;
        console.log('Reset Demo Clicked');
        showResetModal();
    }

    // Called when user confirms reset in modal
    async function performReset() {
        const password = resetPasswordInput.value.trim();
        if (!password) {
            showToast('Please enter the admin password', 'error');
            return;
        }

        resetConfirmBtn.disabled = true;
        resetConfirmBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Resetting...';

        try {
            console.log('Sending RESET request...');
            console.log('Sending RESET request...');
            const response = await fetch(`${API_BASE}/messages`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ password: password })
            });

            console.log('Reset response:', response.status);



            if (!response.ok && response.status !== 409) {
                const txt = await response.text();
                throw new Error(txt || 'Failed to reset messages');
            }

            hideResetModal();
            showToast('Database reset to sample data', 'success');
            loadMessages(); // Refresh list to show empty state
        } catch (err) {
            console.error('Error resetting messages:', err);
            showToast('Failed: ' + err.message, 'error');
        } finally {
            resetConfirmBtn.disabled = false;
            resetConfirmBtn.innerHTML = 'Reset Database';
            isResetting = false;
        }
    }

    async function loadMessages() {
        refreshBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Loading...';
        refreshBtn.disabled = true;

        try {
            const response = await fetch(`${API_BASE}/messages?limit=1000`);
            if (!response.ok) throw new Error('Failed to fetch messages');

            const data = await response.json();
            allMessages = data.items || [];

            // Load observations for each message
            await loadAllObservations();

            // Scan for active alerts to toggle banner
            updateAlertBanner();

            // Render table and stats (via filters)
            applyFilters();
        } catch (err) {
            console.error('Error loading messages:', err);
            showToast('Failed to load messages', 'error');
        } finally {
            refreshBtn.innerHTML = '<i class="fa-solid fa-rotate"></i> Refresh';
            refreshBtn.disabled = false;
        }
    }

    // New: Check for alerts and update banner
    function updateAlertBanner() {
        const alertBanner = document.getElementById('alerts-banner');
        const alertCount = document.getElementById('alert-count');
        if (!alertBanner) return; // Guard clause

        // Check if any loaded message has a CRITICAL alert
        let criticalCount = 0;
        allMessages.forEach(msg => {
            if (msg.observations) {
                const hasCritical = msg.observations.some(o => o.alert_level === 'CRITICAL');
                if (hasCritical) criticalCount++;
            }
        });

        if (criticalCount > 0 && !isCriticalBannerDismissed) {
            alertBanner.classList.remove('hidden');
            // Add click-to-filter hint
            alertBanner.title = "Click to show only critical patients";
            alertBanner.style.cursor = "pointer";

            if (alertCount) {
                alertCount.textContent = criticalCount;
            }

            // Add one-time click listener (or check if already added? simpler to just overwrite onclick or use named function)
            alertBanner.onclick = () => {
                const filterFlag = document.getElementById('filter-flag');
                if (filterFlag) {
                    filterFlag.value = 'critical';
                    applyFilters();
                }
            };
        } else {
            alertBanner.classList.add('hidden');
        }
    }

    function applyFilters() {
        const query = searchInput.value.toLowerCase();
        const flagFilter = filterFlag.value;
        const dateFilter = filterDate.value;

        filteredMessages = allMessages.filter(msg => {
            // Search Text
            const searchable = `${msg.first_name} ${msg.last_name} ${msg.patient_id} ${(msg.observations || []).map(o => o.display).join(' ')}`.toLowerCase();
            if (query && !searchable.includes(query)) return false;

            // Flag Filter
            if (flagFilter === 'abnormal' && !msg.hasAbnormal) return false;
            if (flagFilter === 'critical' && !msg.isCritical) return false;
            if (flagFilter === 'normal' && msg.hasAbnormal) return false;

            // Date Filter
            if (dateFilter) {
                const msgDate = new Date(msg.timestamp);
                const now = new Date();
                if (dateFilter === 'today') {
                    if (msgDate.toDateString() !== now.toDateString()) return false;
                } else if (dateFilter === 'week') {
                    const weekAgo = new Date(now.setDate(now.getDate() - 7));
                    if (msgDate < weekAgo) return false;
                } else if (dateFilter === 'month') {
                    const monthAgo = new Date(now.setMonth(now.getMonth() - 1));
                    if (msgDate < monthAgo) return false;
                }
            }

            return true;
        });

        currentPage = 1;
        renderTable();
        updateStats();
    }

    function updateStats() {
        // Total
        const totalEl = document.getElementById('stat-total');
        if (totalEl) totalEl.textContent = allMessages.length;

        // Unique Patients
        const patients = new Set(allMessages.map(m => m.patient_id));
        const patientsEl = document.getElementById('stat-patients');
        if (patientsEl) patientsEl.textContent = patients.size;

        // Abnormal
        const abnormalCount = allMessages.filter(m => m.hasAbnormal).length;
        const abnormalEl = document.getElementById('stat-abnormal');
        if (abnormalEl) abnormalEl.textContent = abnormalCount;

        // Recent (24h)
        const dayAgo = new Date(new Date().getTime() - 24 * 60 * 60 * 1000);
        const recentCount = allMessages.filter(m => new Date(m.timestamp) > dayAgo).length;
        const recentEl = document.getElementById('stat-recent');
        if (recentEl) recentEl.textContent = recentCount;
    }

    function renderTable() {
        messagesBody.innerHTML = '';

        const start = (currentPage - 1) * pageSize;
        const end = start + pageSize;
        const pageData = filteredMessages.slice(start, end);

        if (pageData.length === 0) {
            messagesBody.innerHTML = '<tr><td colspan="8" class="empty-state">No messages found</td></tr>';
        } else {
            pageData.forEach(msg => {
                const rowHtml = createTableRow(msg);
                messagesBody.insertAdjacentHTML('beforeend', rowHtml);
            });

            // Re-attach event listeners for newly created buttons
            document.querySelectorAll('.expand-btn').forEach(btn => {
                btn.addEventListener('click', () => showMessageDetail(parseInt(btn.dataset.id)));
            });
        }

        // Pagination
        const total = filteredMessages.length;
        const totalPages = Math.ceil(total / pageSize);

        if (pageInfo) pageInfo.textContent = `Page ${currentPage} of ${totalPages || 1}`;
        if (showingCount) showingCount.textContent = `Showing ${Math.min(start + 1, total)}-${Math.min(end, total)} of ${total} messages`;

        if (prevPageBtn) prevPageBtn.disabled = currentPage <= 1;
        if (nextPageBtn) nextPageBtn.disabled = currentPage >= totalPages;
    }

    async function loadAllObservations() {
        // Load observations for all messages in parallel
        const promises = allMessages.map(async (msg) => {
            try {
                const response = await fetch(`${API_BASE}/messages/${msg.id}/observations`);
                if (response.ok) {
                    const data = await response.json();
                    msg.observations = data.items || [];
                    msg.hasAbnormal = msg.observations.some(o =>
                        o.flag && ['H', 'HH', 'L', 'LL'].some(f => o.flag.toUpperCase().includes(f))
                    );
                    // Check for Alerts
                    msg.hasAlert = msg.observations.some(o => o.alert_level === 'CRITICAL' || o.alert_level === 'WARNING');
                    msg.isCritical = msg.observations.some(o => o.alert_level === 'CRITICAL');
                }
            } catch (e) {
                msg.observations = [];
                msg.hasAbnormal = false;
            }
        });
        await Promise.all(promises);
    }

    // ... (updateStats remains same) ...

    // ... (renderTable remains same) ...

    function createTableRow(msg) {
        const name = `${msg.first_name || ''} ${msg.last_name || ''}`.trim() || 'Unknown';
        const obsCount = (msg.observations || []).length;

        // Custom Flag Rendering with Alerts priority
        const obsWithFlags = (msg.observations || []).filter(o => (o.flag && o.flag.trim()) || o.alert_level);

        const flags = obsWithFlags
            .map(o => {
                // If Critical Alert, show that instead of just H/L
                if (o.alert_level === 'CRITICAL') {
                    return `<span class="alert-badge"><i class="fa-solid fa-triangle-exclamation"></i> CRITICAL</span>`;
                }

                const f = (o.flag || '').toUpperCase();
                let cls = 'flag-normal';
                if (['H', 'HH'].some(x => f.includes(x))) cls = 'flag-high';
                if (['L', 'LL'].some(x => f.includes(x))) cls = 'flag-low';
                return `<span class="flag-badge ${cls}">${f}</span>`;
            })
            .slice(0, 3)
            .join('');

        const moreFlags = obsWithFlags.length > 3
            ? `<span class="flag-more">+${obsWithFlags.length - 3}</span>`
            : '';

        const timestamp = msg.timestamp ? new Date(msg.timestamp).toLocaleString() : '--';

        // Create patient timeline link
        const patientLink = msg.patient_id
            ? `/patient.html?id=${encodeURIComponent(msg.patient_id)}`
            : '#';

        // Row Class for Critical items
        const rowClass = msg.isCritical ? 'alert-row' : '';

        return `
            <tr class="${rowClass}">
                <td class="expand-col">
                    <button class="expand-btn" data-id="${msg.id}">
                        <i class="fa-solid fa-eye"></i>
                    </button>
                </td>
                <td class="patient-cell">
                    <span class="patient-name-text">${escapeHtml(name)}</span>
                </td>
                <td>${escapeHtml(msg.patient_id || '--')}</td>
                <td>${formatDob(msg.dob)}</td>
                <td>${msg.sex || '--'}</td>
                <td class="obs-count">${obsCount}</td>
                <td class="flags-cell">${flags}${moreFlags}</td>
                <td class="timestamp-cell">${timestamp}</td>
            </tr>
        `;
    }

    function formatDob(dob) {
        if (!dob) return '--';
        // Handle YYYYMMDD format
        if (dob.length === 8 && !dob.includes('-')) {
            return `${dob.slice(0, 4)}-${dob.slice(4, 6)}-${dob.slice(6, 8)}`;
        }
        return dob;
    }

    async function showMessageDetail(msgId) {
        // Find message in our list
        const msg = allMessages.find(m => m.id === msgId);
        if (!msg) return;

        // Load full message detail
        try {
            const response = await fetch(`${API_BASE}/messages/${msgId}`);
            const detail = await response.json();

            // Populate modal
            const name = `${msg.first_name || ''} ${msg.last_name || ''}`.trim() || 'Unknown';
            document.getElementById('modal-patient').innerHTML = `
                <div class="patient-detail-grid">
                    <div class="patient-field">
                        <label>Name</label>
                        <span>${escapeHtml(name)}</span>
                    </div>
                    <div class="patient-field">
                        <label>Patient ID</label>
                        <span>${escapeHtml(msg.patient_id || '--')}</span>
                    </div>
                    <div class="patient-field">
                        <label>Date of Birth</label>
                        <span>${formatDob(msg.dob)}</span>
                    </div>
                    <div class="patient-field">
                        <label>Sex</label>
                        <span>${msg.sex || '--'}</span>
                    </div>
                </div>
            `;

            // Clinical summary - generate from observations if not available
            const summary = generateClinicalSummary(msg.observations || []);
            document.getElementById('modal-summary').innerHTML = `<p>${escapeHtml(summary)}</p>`;

            // Observations table
            const obsBody = document.getElementById('modal-obs-body');
            if ((msg.observations || []).length === 0) {
                obsBody.innerHTML = '<tr><td colspan="5" class="empty-state">No observations</td></tr>';
            } else {
                obsBody.innerHTML = msg.observations.map(o => {
                    const flagClass = getFlagClass(o.flag);
                    const ref = (o.reference_low && o.reference_high)
                        ? `${o.reference_low} - ${o.reference_high}`
                        : (o.reference_low || o.reference_high || '--');
                    return `
                        <tr>
                            <td>${escapeHtml(o.display || o.code || '--')}</td>
                            <td><strong>${o.value !== null ? o.value : '--'}</strong></td>
                            <td>${escapeHtml(o.unit || '--')}</td>
                            <td><span class="flag-badge ${flagClass}">${escapeHtml(o.flag || 'N')}</span></td>
                            <td>${ref}</td>
                        </tr>
                    `;
                }).join('');
            }

            // FHIR bundle
            document.getElementById('modal-fhir-code').textContent =
                JSON.stringify(detail.fhir_bundle || {}, null, 2);

            // Raw HL7
            document.getElementById('modal-hl7-code').textContent = detail.raw_hl7 || 'Not available';

            // Show modal
            modal.classList.add('visible');
            document.body.style.overflow = 'hidden';

        } catch (err) {
            console.error('Error loading message detail:', err);
            showToast('Failed to load message details', 'error');
        }
    }

    function generateClinicalSummary(observations) {
        if (!observations || observations.length === 0) {
            return 'No observations available for clinical summary.';
        }

        const findings = [];
        observations.forEach(o => {
            const name = o.display || o.code || 'Unknown test';
            const flag = (o.flag || '').toUpperCase();

            if (flag.includes('H')) {
                findings.push(`${name} is elevated at ${o.value} ${o.unit || ''}`);
            } else if (flag.includes('L')) {
                findings.push(`${name} is low at ${o.value} ${o.unit || ''}`);
            }
        });

        if (findings.length === 0) {
            return 'All results are within normal limits.';
        }

        return findings.join('. ') + '.';
    }

    function getFlagClass(flag) {
        if (!flag) return 'flag-normal';
        const f = flag.toUpperCase();
        if (['H', 'HH', '>'].some(x => f.includes(x))) return 'flag-high';
        if (['L', 'LL', '<'].some(x => f.includes(x))) return 'flag-low';
        return 'flag-normal';
    }

    function hideModal() {
        modal.classList.remove('visible');
        document.body.style.overflow = '';
    }

    function changePage(delta) {
        const totalPages = Math.ceil(filteredMessages.length / pageSize);
        const newPage = currentPage + delta;
        if (newPage >= 1 && newPage <= totalPages) {
            currentPage = newPage;
            renderTable();
        }
    }

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    function showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);
        toast.offsetHeight; // reflow
        toast.classList.add('show');
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    // ============================================
    // AI Query Assistant
    // ============================================

    const queryInput = document.getElementById('query-input');
    const querySubmit = document.getElementById('query-submit');
    const queryMessages = document.getElementById('query-messages');
    const suggestionChips = document.querySelectorAll('.suggestion-chip');

    // Set up query assistant event listeners
    if (queryInput && querySubmit) {
        querySubmit.addEventListener('click', () => {
            const question = queryInput.value.trim();
            if (question) sendQuery(question);
        });

        queryInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                const question = queryInput.value.trim();
                if (question) sendQuery(question);
            }
        });
    }

    // Suggestion chips
    suggestionChips.forEach(chip => {
        chip.addEventListener('click', () => {
            const query = chip.dataset.query;
            const depth = chip.dataset.depth;
            if (query) {
                // Set depth if provided
                if (depth) {
                    const depthEl = document.getElementById('reasoning-depth');
                    if (depthEl) depthEl.value = depth;
                }
                queryInput.value = query;
                sendQuery(query);
            }
        });
    });

    async function sendQuery(question) {
        if (!question.trim()) return;

        // Clear input
        queryInput.value = '';
        querySubmit.disabled = true;

        // Add user message
        addMessage(question, 'user');

        // Add loading indicator
        const loadingId = addLoadingMessage();

        try {
            // Prepare history (last 5 messages)
            const context = chatHistory.slice(-5);

            // Get selected reasoning depth
            const depthEl = document.getElementById('reasoning-depth');
            const depth = depthEl ? depthEl.value : 'standard';

            const response = await fetch(`${API_BASE}/api/query`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    question,
                    history: context,
                    reasoning_depth: depth
                })
            });

            // Remove loading message
            removeMessage(loadingId);

            if (response.status === 429) {
                addMessage('Please wait a moment before asking another question.', 'ai', { isError: true });
                return;
            }

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || 'Failed to process query');
            }

            const data = await response.json();

            if (data.success) {
                // Handle clarification requests inline
                if (data.needs_clarification && data.clarification_question) {
                    addMessage(data.clarification_question, 'ai', {
                        isClarification: true,
                        clarificationOptions: data.clarification_options || [],
                        reasoningTrace: data.reasoning_trace || [],
                        toolsUsed: data.tools_used || []
                    });
                } else {
                    addMessage(data.answer, 'ai', {
                        highlights: data.highlights,
                        sql: data.sql_used,
                        rowCount: data.row_count,
                        sources: data.sources || [],
                        reasoningTrace: data.reasoning_trace || [],
                        toolsUsed: data.tools_used || []
                    });
                }
            } else {
                addMessage(data.answer || 'Sorry, I couldn\'t process that question.', 'ai', { isError: true });
            }

        } catch (err) {
            removeMessage(loadingId);
            console.error('Query error:', err);
            addMessage('Sorry, something went wrong. Please try again.', 'ai', { isError: true });
        } finally {
            querySubmit.disabled = false;
            queryInput.focus();
        }
    }

    function addMessage(text, sender, options = {}) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message message-${sender}`;
        messageDiv.id = `msg-${Date.now()}`;

        const avatarIcon = sender === 'ai' ? 'fa-robot' : 'fa-user';

        let contentHtml = sender === 'ai'
            ? `<div class="markdown-content">${marked.parse(text)}</div>`
            : `<p>${escapeHtml(text)}</p>`;

        // Add tool usage badge if present
        if (options.toolsUsed && options.toolsUsed.length > 0) {
            contentHtml = `
                <div class="agent-tools-badge">
                    <i class="fa-solid fa-wand-magic-sparkles"></i>
                    Used: ${options.toolsUsed.map(t => `<span class="tool-name">${escapeHtml(t)}</span>`).join(', ')}
                </div>` + contentHtml;
        }

        // Add clarification options if present
        if (options.isClarification && options.clarificationOptions && options.clarificationOptions.length > 0) {
            contentHtml += '<div class="clarification-options">';
            options.clarificationOptions.forEach(opt => {
                contentHtml += `<button class="clarification-btn" onclick="handleClarification('${escapeHtml(opt.replace(/'/g, "\\'"))}')">${escapeHtml(opt)}</button>`;
            });
            contentHtml += '</div>';
        }

        // Add reasoning trace (collapsible)
        if (options.reasoningTrace && options.reasoningTrace.length > 0) {
            const traceId = `trace-${Date.now()}`;
            contentHtml += `<div class="reasoning-trace" id="${traceId}">`;
            contentHtml += `<button class="trace-toggle" aria-expanded="false" onclick="toggleTrace('${traceId}')">
                <span class="toggle-icon"><i class="fa-solid fa-plus"></i></span>
                <span><i class="fa-solid fa-brain"></i> Agent Reasoning (${options.reasoningTrace.length} step${options.reasoningTrace.length > 1 ? 's' : ''})</span>
            </button>`;
            contentHtml += '<div class="trace-content" style="display: none;">';
            options.reasoningTrace.forEach((step, i) => {
                contentHtml += `<div class="trace-step">`;
                contentHtml += `<div class="trace-thought"><strong>Thought:</strong> ${escapeHtml(step.thought || '')}</div>`;
                if (step.tools && step.tools.length > 0) {
                    contentHtml += '<div class="trace-tools">';
                    step.tools.forEach(tool => {
                        contentHtml += `<span class="trace-tool"><i class="fa-solid fa-wrench"></i> ${escapeHtml(tool.tool)}</span>`;
                    });
                    contentHtml += '</div>';
                }
                if (step.results && step.results.length > 0) {
                    contentHtml += '<div class="trace-results">';
                    step.results.forEach(r => {
                        const icon = r.success ? 'fa-check' : 'fa-xmark';
                        const cls = r.success ? 'success' : 'error';
                        contentHtml += `<span class="trace-result ${cls}"><i class="fa-solid ${icon}"></i> ${escapeHtml(r.tool)} (${r.time_ms}ms)</span>`;
                    });
                    contentHtml += '</div>';
                }
                contentHtml += '</div>';
            });
            contentHtml += '</div></div>';
        }

        // Add highlights if present
        if (options.highlights && options.highlights.length > 0) {
            contentHtml += '<ul class="message-highlights">';
            options.highlights.forEach(h => {
                contentHtml += `<li>${marked.parseInline(h)}</li>`;
            });
            contentHtml += '</ul>';
        }

        // Add RAG sources if present (collapsible)
        if (options.sources && options.sources.length > 0) {
            // Find the highest relevance score
            const maxRelevance = Math.max(...options.sources.map(s => s.relevance || 0));
            const maxPercent = Math.round(maxRelevance * 100);

            const sourceId = `sources-${Date.now()}`;
            contentHtml += `<div class="sources-collapsible" id="${sourceId}">`;
            contentHtml += `<button class="sources-toggle" aria-expanded="false" onclick="toggleSources('${sourceId}')">
                <span class="toggle-icon"><i class="fa-solid fa-plus"></i></span>
                <span class="sources-summary">
                    <i class="fa-solid fa-book-medical"></i> 
                    Sources (${options.sources.length}) 
                    <span class="best-match">Best match: ${maxPercent}%</span>
                </span>
            </button>`;
            contentHtml += '<div class="sources-content" style="display: none;">';
            options.sources.forEach(src => {
                const relevancePercent = Math.round((src.relevance || 0) * 100);
                const relevanceClass = relevancePercent >= 80 ? 'high' : (relevancePercent >= 50 ? 'medium' : 'low');
                const sourceTitle = escapeHtml(src.title || 'Unknown Source');
                // Use filename if available, otherwise fallback to title
                const docIdentifier = src.filename || src.title || '';

                // Prepare snippet for JS string (escape backslashes, quotes, newlines)
                const rawSnippet = src.full_snippet || '';
                const safeSnippet = rawSnippet
                    .replace(/\\/g, '\\\\')
                    .replace(/'/g, "\\'")
                    .replace(/\n/g, '\\n')
                    .replace(/\r/g, '');

                // Escape HTML for attribute (mostly for double quotes if any, and general safety)
                // Note: We used escapeHtml above for title/id, but safeSnippet needs to be passed to JS.
                const attrSnippet = escapeHtml(safeSnippet);
                const attrId = escapeHtml(docIdentifier.replace(/'/g, "\\'"));
                const attrTitle = sourceTitle.replace(/'/g, "\\'"); // sourceTitle is ALREADY html escaped. prevent double escape of quotes?
                // actually title is html escaped. so ' -> &#039;. so attrTitle has &#039;.
                // if we use it in JS string '...', browser decodes &#039; -> '
                // so we need \' in JS. so we need to ensure title has \' instead of ' BEFORE html escape?
                // Too complex. Let's just use raw title and escape it properly for JS+HTML.

                // Simpler approach:
                // 1. Raw -> JS Escape -> HTML Escape
                const jsId = (src.filename || src.title || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                const jsTitle = (src.title || 'Unknown Source').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                const finalId = escapeHtml(jsId);
                const finalTitle = escapeHtml(jsTitle);

                contentHtml += `
                    <div class="source-card">
                        <div class="source-header">
                            <span class="source-title">${sourceTitle}</span>
                            <span class="source-relevance ${relevanceClass}">${relevancePercent}% match</span>
                        </div>
                        <p class="source-snippet">${escapeHtml(src.snippet || '')}</p>
                        <button class="view-doc-btn" onclick="showDocumentModal('${finalId}', '${finalTitle}', '${attrSnippet}')">
                            <i class="fa-solid fa-file-lines"></i> View Full Document
                        </button>
                    </div>
                `;
            });
            contentHtml += '</div></div>';
        }

        // Add error styling
        if (options.isError) {
            messageDiv.classList.add('message-error');
        }

        messageDiv.innerHTML = `
            <div class="message-avatar">
                <i class="fa-solid ${avatarIcon}"></i>
            </div>
            <div class="message-content">
                ${contentHtml}
            </div>
        `;

        queryMessages.appendChild(messageDiv);
        queryMessages.scrollTop = queryMessages.scrollHeight;

        // Add to history (unless it's an error or loading)
        if (sender !== 'system' && !options.isError) {
            chatHistory.push({ role: sender, content: text });
        }

        return messageDiv.id;
    }

    function addLoadingMessage() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message message-ai';
        messageDiv.id = `loading-${Date.now()}`;

        messageDiv.innerHTML = `
            <div class="message-avatar">
                <i class="fa-solid fa-robot"></i>
            </div>
            <div class="message-content">
                <div class="message-loading">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        `;

        queryMessages.appendChild(messageDiv);
        queryMessages.scrollTop = queryMessages.scrollHeight;

        return messageDiv.id;
    }

    function removeMessage(id) {
        const msg = document.getElementById(id);
        if (msg) msg.remove();
    }
});

// ==============================================
// Global Functions for Sources (outside DOMContentLoaded)
// ==============================================

// Toggle sources collapsible section
function toggleSources(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const toggle = container.querySelector('.sources-toggle');
    const content = container.querySelector('.sources-content');
    const icon = toggle.querySelector('.toggle-icon i');

    const isExpanded = toggle.getAttribute('aria-expanded') === 'true';

    if (isExpanded) {
        // Collapse
        content.style.display = 'none';
        toggle.setAttribute('aria-expanded', 'false');
        icon.className = 'fa-solid fa-plus';
    } else {
        // Expand
        content.style.display = 'block';
        toggle.setAttribute('aria-expanded', 'true');
        icon.className = 'fa-solid fa-minus';
    }
}

// Show document viewer modal
window.showDocumentModal = async function (filename, displayTitle, highlightText) {
    console.log(`[RAG] Opening document. Filename: "${filename}", Title: "${displayTitle}"`);
    if (highlightText) console.log(`[RAG] Highlighting snippet length: ${highlightText.length}`);

    if (!filename) {
        console.error('[RAG] No filename provided to showDocumentModal');
        alert("Cannot view document: Filename is missing.");
        return;
    }

    // Determine API Base URL
    const API_BASE = (window.location.protocol === 'file:')
        ? 'http://localhost:8080'
        : ''; // Relative path for served app

    // Create or get modal
    let modal = document.getElementById('doc-viewer-modal');
    // ... (modal creation logic same as before, simplified for this replace check) ...
    // Note: If I don't include the whole function, I need to be careful.
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'doc-viewer-modal';
        modal.className = 'doc-modal';
        modal.innerHTML = `
            <div class="doc-modal-content">
                <div class="doc-modal-header">
                    <h3 id="doc-modal-title">Document</h3>
                    <button class="doc-modal-close" onclick="closeDocumentModal()">
                        <i class="fa-solid fa-times"></i>
                    </button>
                </div>
                <div class="doc-modal-body" id="doc-modal-body">
                    <div class="doc-loading">
                        <i class="fa-solid fa-spinner fa-spin"></i> Loading...
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        // Close on outside click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeDocumentModal();
        });
    }

    // Reset content and show loading
    const body = document.getElementById('doc-modal-body');
    document.getElementById('doc-modal-title').textContent = displayTitle || filename;
    body.innerHTML = `
        <div class="doc-loading">
            <i class="fa-solid fa-circle-notch fa-spin"></i>
            <p>Loading document content...</p>
        </div>
    `;

    modal.classList.add('visible');
    document.body.style.overflow = 'hidden'; // Prevent background scrolling

    try {
        const url = `${API_BASE}/api/document/${encodeURIComponent(filename)}`;
        console.log(`[RAG] Fetching from: ${url}`);

        const response = await fetch(url);

        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`Server returned ${response.status}: ${errText}`);
        }

        const data = await response.json();

        // Use textContent for safety, but we want to allow formatting? 
        // Docs are raw text.
        body.innerHTML = '';
        const pre = document.createElement('pre');
        pre.className = 'doc-content';

        if (highlightText) {
            const content = data.content;

            // Robust Highlighting: Match regardless of whitespace differences (newlines, spaces)
            // 1. Escape regex special characters in the snippet
            const escapedHighlight = highlightText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            // 2. Replace all whitespace sequences with \s+ pattern to match any whitespace (including newlines)
            const flexibleHighlight = escapedHighlight.replace(/\s+/g, '\\s+');

            // Create regex (multiline matching not strictly needed if \s matches \n, but good to have)
            const regex = new RegExp(flexibleHighlight);
            const match = regex.exec(content);

            if (match) {
                const idx = match.index;
                const matchedStr = match[0];

                const before = escapeHtmlGlobal(content.substring(0, idx));
                const highlight = escapeHtmlGlobal(matchedStr);
                const after = escapeHtmlGlobal(content.substring(idx + matchedStr.length));

                pre.innerHTML = `${before}<mark class="highlight">${highlight}</mark>${after}`;

                // Scroll to highlight
                setTimeout(() => {
                    const mark = pre.querySelector('mark');
                    if (mark) mark.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }, 300);
            } else {
                pre.textContent = content; // Fallback
                console.warn('[RAG] Highlight text not found in document (regex match failed).');
                console.log('Snippet pattern:', flexibleHighlight);
            }
        } else {
            pre.textContent = data.content;
        }

        body.appendChild(pre);

    } catch (err) {
        console.error('[RAG] Error loading document:', err);
        body.innerHTML = `
            <div class="doc-error">
                <i class="fa-solid fa-triangle-exclamation"></i>
                <p>Could not load document.</p>
                <small>${escapeHtmlGlobal(err.message)}</small>
            </div>
        `;
    }
}

// Close document modal
function closeDocumentModal() {
    const modal = document.getElementById('doc-viewer-modal');
    if (modal) {
        modal.classList.remove('visible');
        document.body.style.overflow = '';
    }
}

// Helper for escaping HTML in global scope
function escapeHtmlGlobal(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
