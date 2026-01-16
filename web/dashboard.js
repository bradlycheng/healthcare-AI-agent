// Dashboard JavaScript
document.addEventListener('DOMContentLoaded', () => {
    // State
    let allMessages = [];
    let filteredMessages = [];
    let currentPage = 1;
    const pageSize = 10;

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
    console.log('Dashboard JS Loaded v2'); // verify script update
    loadMessages();
    setupEventListeners();

    function setupEventListeners() {
        searchInput.addEventListener('input', debounce(applyFilters, 300));
        filterFlag.addEventListener('change', applyFilters);
        filterDate.addEventListener('change', applyFilters);
        refreshBtn.addEventListener('click', loadMessages);

        // Event Delegation for Delete Button (More robust)
        document.addEventListener('click', (e) => {
            const btn = e.target.closest('#delete-btn');
            if (btn) {
                e.preventDefault();
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

    async function confirmDelete() {
        console.log('Reset Demo Clicked');
        // if (confirm('Are you sure...')) { 
        if (true) {
            try {
                console.log('Sending DELETE request...');
                const response = await fetch('/messages', { method: 'DELETE' });
                console.log('Delete response:', response.status);
                if (!response.ok) {
                    const txt = await response.text();
                    throw new Error(txt || 'Failed to reset messages');
                }
                showToast('Database reset to sample data', 'success');
                loadMessages(); // Refresh list to show empty state
            } catch (err) {
                console.error('Error resetting messages:', err);
                showToast('Failed to reset messages', 'error');
            }
        }
    }

    async function loadMessages() {
        refreshBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Loading...';
        refreshBtn.disabled = true;

        try {
            const response = await fetch('/messages?limit=200');
            if (!response.ok) throw new Error('Failed to fetch messages');

            const data = await response.json();
            allMessages = data.items || [];

            // Load observations for each message
            await loadAllObservations();

            updateStats();
            applyFilters();
        } catch (err) {
            console.error('Error loading messages:', err);
            showToast('Failed to load messages', 'error');
        } finally {
            refreshBtn.innerHTML = '<i class="fa-solid fa-rotate"></i> Refresh';
            refreshBtn.disabled = false;
        }
    }

    async function loadAllObservations() {
        // Load observations for all messages in parallel
        const promises = allMessages.map(async (msg) => {
            try {
                const response = await fetch(`/messages/${msg.id}/observations`);
                if (response.ok) {
                    const data = await response.json();
                    msg.observations = data.items || [];
                    msg.hasAbnormal = msg.observations.some(o =>
                        o.flag && ['H', 'HH', 'L', 'LL'].some(f => o.flag.toUpperCase().includes(f))
                    );
                }
            } catch (e) {
                msg.observations = [];
                msg.hasAbnormal = false;
            }
        });
        await Promise.all(promises);
    }

    function updateStats() {
        const total = allMessages.length;
        const uniquePatients = new Set(allMessages.map(m => m.patient_id)).size;
        const abnormal = allMessages.filter(m => m.hasAbnormal).length;

        // Recent (last 24 hours) - check timestamp
        const now = new Date();
        const oneDayAgo = new Date(now - 24 * 60 * 60 * 1000);
        const recent = allMessages.filter(m => {
            const msgDate = new Date(m.timestamp);
            return msgDate >= oneDayAgo;
        }).length;

        animateNumber('stat-total', total);
        animateNumber('stat-patients', uniquePatients);
        animateNumber('stat-abnormal', abnormal);
        animateNumber('stat-recent', recent);
    }

    function animateNumber(elementId, target) {
        const el = document.getElementById(elementId);
        const start = parseInt(el.textContent) || 0;
        const duration = 500;
        const startTime = performance.now();

        function update(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const current = Math.floor(start + (target - start) * easeOutQuad(progress));
            el.textContent = current;
            if (progress < 1) requestAnimationFrame(update);
        }
        requestAnimationFrame(update);
    }

    function easeOutQuad(t) {
        return t * (2 - t);
    }

    function applyFilters() {
        const searchTerm = searchInput.value.toLowerCase().trim();
        const flagFilter = filterFlag.value;
        const dateFilter = filterDate.value;

        filteredMessages = allMessages.filter(msg => {
            // Search filter
            if (searchTerm) {
                const searchableText = `${msg.first_name} ${msg.last_name} ${msg.patient_id}`.toLowerCase();
                const obsText = (msg.observations || []).map(o => `${o.code} ${o.display}`).join(' ').toLowerCase();
                if (!searchableText.includes(searchTerm) && !obsText.includes(searchTerm)) {
                    return false;
                }
            }

            // Flag filter
            if (flagFilter === 'abnormal' && !msg.hasAbnormal) return false;
            if (flagFilter === 'normal' && msg.hasAbnormal) return false;

            // Date filter
            if (dateFilter) {
                const msgDate = new Date(msg.timestamp);
                const now = new Date();
                if (dateFilter === 'today') {
                    if (msgDate.toDateString() !== now.toDateString()) return false;
                } else if (dateFilter === 'week') {
                    const weekAgo = new Date(now - 7 * 24 * 60 * 60 * 1000);
                    if (msgDate < weekAgo) return false;
                } else if (dateFilter === 'month') {
                    const monthAgo = new Date(now - 30 * 24 * 60 * 60 * 1000);
                    if (msgDate < monthAgo) return false;
                }
            }

            return true;
        });

        currentPage = 1;
        renderTable();
    }

    function renderTable() {
        const start = (currentPage - 1) * pageSize;
        const end = start + pageSize;
        const pageMessages = filteredMessages.slice(start, end);

        if (pageMessages.length === 0) {
            messagesBody.innerHTML = `
                <tr>
                    <td colspan="8" class="empty-state">
                        <i class="fa-solid fa-inbox"></i>
                        <p>No messages found</p>
                    </td>
                </tr>
            `;
        } else {
            messagesBody.innerHTML = pageMessages.map(msg => createTableRow(msg)).join('');

            // Add click handlers for expand
            messagesBody.querySelectorAll('.expand-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const msgId = parseInt(btn.dataset.id);
                    showMessageDetail(msgId);
                });
            });
        }

        // Update pagination
        const totalPages = Math.ceil(filteredMessages.length / pageSize);
        prevPageBtn.disabled = currentPage <= 1;
        nextPageBtn.disabled = currentPage >= totalPages;
        pageInfo.textContent = `Page ${currentPage} of ${totalPages || 1}`;
        showingCount.textContent = `Showing ${pageMessages.length} of ${filteredMessages.length} messages`;
    }

    function createTableRow(msg) {
        const name = `${msg.first_name || ''} ${msg.last_name || ''}`.trim() || 'Unknown';
        const obsCount = (msg.observations || []).length;
        const flags = (msg.observations || [])
            .filter(o => o.flag && o.flag.trim())
            .map(o => {
                const f = o.flag.toUpperCase();
                let cls = 'flag-normal';
                if (['H', 'HH'].some(x => f.includes(x))) cls = 'flag-high';
                if (['L', 'LL'].some(x => f.includes(x))) cls = 'flag-low';
                return `<span class="flag-badge ${cls}">${f}</span>`;
            })
            .slice(0, 3)
            .join('');

        const moreFlags = (msg.observations || []).filter(o => o.flag && o.flag.trim()).length > 3
            ? `<span class="flag-more">+${(msg.observations || []).filter(o => o.flag).length - 3}</span>`
            : '';

        const timestamp = msg.timestamp ? new Date(msg.timestamp).toLocaleString() : '--';

        return `
            <tr>
                <td class="expand-col">
                    <button class="expand-btn" data-id="${msg.id}">
                        <i class="fa-solid fa-eye"></i>
                    </button>
                </td>
                <td class="patient-cell">
                    <span class="patient-name">${escapeHtml(name)}</span>
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
            const response = await fetch(`/messages/${msgId}`);
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
});
