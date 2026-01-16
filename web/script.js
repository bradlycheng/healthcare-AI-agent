document.addEventListener('DOMContentLoaded', () => {
    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            document.querySelector(this.getAttribute('href')).scrollIntoView({
                behavior: 'smooth'
            });
        });
    });

    // Reveal animations on scroll
    const observerOptions = {
        threshold: 0.1
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, observerOptions);

    const elementsToAnimate = document.querySelectorAll('.feature-card, .step');
    elementsToAnimate.forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(20px)';
        el.style.transition = 'opacity 0.6s ease-out, transform 0.6s ease-out';
        observer.observe(el);
    });

    // Toast Notification Logic
    const ctaForm = document.querySelector('.cta-form');
    if (ctaForm) {
        ctaForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const email = ctaForm.querySelector('input').value;
            showToast(`Thanks! We've added ${email} to the waitlist.`, 'success');
            ctaForm.reset();
        });
    }

    function showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);

        // Trigger reflow
        toast.offsetHeight;

        toast.classList.add('show');

        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    // Add visible class and toast styling dynamically
    const style = document.createElement('style');
    style.innerHTML = `
        .visible {
            opacity: 1 !important;
            transform: translateY(0) !important;
        }
        
        .toast {
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            background: rgba(0, 242, 255, 0.1);
            backdrop-filter: blur(10px);
            border: 1px solid var(--primary);
            color: white;
            padding: 1rem 2rem;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            transform: translateY(100px);
            opacity: 0;
            transition: all 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55);
            z-index: 2000;
            font-weight: 500;
            max-width: 400px;
        }

        .toast.show {
            transform: translateY(0);
            opacity: 1;
        }

        .toast-success {
            border-color: #22c55e;
            background: rgba(34, 197, 94, 0.15);
        }

        .toast-error {
            border-color: #ef4444;
            background: rgba(239, 68, 68, 0.15);
        }

        .toast-warning {
            border-color: #f59e0b;
            background: rgba(245, 158, 11, 0.15);
        }

        .toast-info {
            border-color: var(--primary);
            background: rgba(0, 242, 255, 0.1);
        }

        /* Cancel button styling */
        .cancel-btn {
            background: transparent;
            border: 1px solid #ef4444;
            color: #ef4444;
            padding: 0.5rem 1rem;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.875rem;
            margin-top: 0.75rem;
            transition: all 0.2s ease;
            display: none;
        }

        .cancel-btn:hover {
            background: rgba(239, 68, 68, 0.2);
        }

        .cancel-btn.visible {
            display: inline-block;
        }

        /* Processing timer styling */
        .processing-timer {
            font-size: 0.75rem;
            color: rgba(255, 255, 255, 0.6);
            margin-top: 0.5rem;
            display: none;
        }

        .processing-timer.visible {
            display: block;
        }

        /* Rate limit banner */
        .rate-limit-banner {
            background: linear-gradient(135deg, rgba(245, 158, 11, 0.2), rgba(239, 68, 68, 0.2));
            border: 1px solid #f59e0b;
            border-radius: 12px;
            padding: 1rem 1.5rem;
            margin-bottom: 1rem;
            display: none;
            align-items: center;
            gap: 1rem;
            animation: fadeIn 0.3s ease;
        }

        .rate-limit-banner.visible {
            display: flex;
        }

        .rate-limit-banner i {
            font-size: 1.5rem;
            color: #f59e0b;
        }

        .rate-limit-banner .message {
            flex: 1;
        }

        .rate-limit-banner .message h4 {
            margin: 0 0 0.25rem 0;
            color: #fbbf24;
            font-size: 0.9rem;
        }

        .rate-limit-banner .message p {
            margin: 0;
            font-size: 0.8rem;
            opacity: 0.8;
        }

        .rate-limit-banner .countdown {
            font-family: 'Outfit', monospace;
            font-size: 1.25rem;
            font-weight: 600;
            color: #fbbf24;
            min-width: 2rem;
            text-align: center;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Stall warning styling */
        .stall-warning {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid #ef4444;
            border-radius: 8px;
            padding: 0.75rem 1rem;
            margin-top: 0.75rem;
            font-size: 0.8rem;
            display: none;
            animation: pulse 2s infinite;
        }

        .stall-warning.visible {
            display: block;
        }

        .stall-warning i {
            color: #ef4444;
            margin-right: 0.5rem;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
    `;
    document.head.appendChild(style);

    // --- Live Demo Logic ---
    const processBtn = document.getElementById('process-btn');
    const saveBtn = document.getElementById('save-btn');
    const hl7Input = document.getElementById('hl7-input');
    const resultsArea = document.getElementById('results-area');
    const aiToggle = document.getElementById('ai-toggle');
    const selectAllCheck = document.getElementById('select-all');
    const addRowBtn = document.getElementById('add-row-btn');

    let currentAnalysisData = null;

    // Process Button Logic
    if (processBtn) {
        processBtn.addEventListener('click', async () => {
            // Reset UI
            if (resultsArea) resultsArea.classList.add('hidden');
            if (saveBtn) {
                saveBtn.classList.add('hidden');
                saveBtn.innerHTML = '<i class="fa-solid fa-check"></i> Confirm & Save';
                saveBtn.disabled = false;
            }

            // Get Input
            const hl7 = hl7Input ? hl7Input.value.trim() : '';
            if (!hl7) {
                showToast('Please enter an HL7 message.', 'warning');
                return;
            }

            // Show Loading
            processBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Analying...';
            processBtn.disabled = true;

            // Timer / Stall Logic (Optional, simplified here)
            const startTime = Date.now();

            try {
                // Construct payload
                // We use parsing endpoint first
                const useLLM = aiToggle && aiToggle.checked;
                const url = `/oru/parse?persist=false&use_llm=${useLLM}`;

                const response = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        hl7_text: hl7,
                        use_llm: useLLM,
                        persist: false
                    })
                });

                if (!response.ok) {
                    throw new Error(await response.text());
                }

                currentAnalysisData = await response.json();

                // Render
                renderResults(currentAnalysisData);
                if (resultsArea) resultsArea.classList.remove('hidden');

                // Show Save Button
                if (saveBtn) saveBtn.classList.remove('hidden');

                showToast('Analysis complete.', 'success');

            } catch (err) {
                console.error(err);
                showToast('Analysis failed: ' + err.message, 'error');
            } finally {
                processBtn.innerHTML = '<i class="fa-solid fa-bolt"></i> Analyze (Preview)';
                processBtn.disabled = false;
            }
        });
    }

    // Event Delegation for Add Row (More Robust)
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('#add-row-btn');
        if (btn) {
            e.preventDefault(); // Prevent any default form actions
            console.log("Add Row Clicked");
            addNewObservationRow();
        }
    });

    function createObservationRow(o, index) {
        const tr = document.createElement('tr');

        // Source Badge
        const isAi = o.source === 'AI_EXTRACTED';
        const isManual = o.source === 'MANUAL';
        let sourceHtml = '<span style="color:var(--text-muted);"><i class="fa-solid fa-file-code"></i> HL7</span>';

        if (isAi) {
            tr.style.backgroundColor = "rgba(0, 242, 255, 0.05)";
            sourceHtml = '<span style="color:var(--secondary); font-weight:bold;"><i class="fa-solid fa-wand-magic-sparkles"></i> AI</span>';
        } else if (isManual) {
            tr.style.backgroundColor = "rgba(42, 252, 152, 0.05)";
            sourceHtml = '<span style="color:var(--success); font-weight:bold;"><i class="fa-solid fa-user-pen"></i> User</span>';
        }

        // Flag Logic
        let flagHtml = '';
        if (o.flag) {
            const f = o.flag.toUpperCase();
            let cls = 'flag-normal';
            if (['H', 'HH', '>'].some(x => f.includes(x))) cls = 'flag-high';
            if (['L', 'LL', '<'].some(x => f.includes(x))) cls = 'flag-low';
            flagHtml = `<span class="obs-flag ${cls}">${f}</span>`;
        }

        const ref = (o.reference_low && o.reference_high)
            ? `${o.reference_low} - ${o.reference_high}`
            : (o.reference_low || o.reference_high || '--');

        const codeDisplay = o.code && o.code !== 'UNKNOWN' ? `<div style="font-size:0.75rem; color:var(--text-muted); margin-top:2px;">Code: ${o.code}</div>` : '';

        // Safely handle nulls
        const displayVal = o.display || (isManual ? '' : (o.code || ''));
        const valVal = o.value !== null ? o.value : '';
        const unitVal = o.unit || '';

        tr.innerHTML = `
            <td><input type="checkbox" class="obs-check" checked></td>
            <td>${sourceHtml}</td>
            <td class="editable-cell">
                <input type="text" class="edit-input test-name-input" value="${displayVal}" placeholder="Test Name" style="width:100%; font-weight:500;">
                ${codeDisplay}
                <input type="hidden" class="code-hidden" value="${o.code || ''}">
            </td>
            <td class="editable-cell">
                <input type="text" class="edit-input value-input" value="${valVal}" placeholder="Value">
            </td>
            <td class="editable-cell">
                 <input type="text" class="edit-input unit-input" value="${unitVal}" placeholder="Unit" style="width:60px;">
            </td>
            <td>${flagHtml}</td>
            <td>${ref}</td>
        `;
        return tr;
    }

    function addNewObservationRow() {
        const obsBody = document.getElementById('res-obs-body');
        // Clear "No observations" message if present
        if (obsBody.innerHTML.includes('No observations found')) {
            obsBody.innerHTML = '';
        }

        const newObs = {
            source: 'MANUAL',
            code: '',
            display: '',
            value: '',
            unit: '',
            flag: '',
            reference_low: '',
            reference_high: ''
        };

        const tr = createObservationRow(newObs, -1);

        // Add delete button for manual rows? For now, just add.
        obsBody.appendChild(tr);

        // Focus the name input
        const inputs = tr.querySelectorAll('input');
        if (inputs[1]) inputs[1].focus();
    }

    function renderResults(data) {
        // Patient
        const pat = data.patient || {};
        const name = `${pat.first_name || ''} ${pat.last_name || ''}`.trim() || 'Unknown';
        const dob = pat.dob ? pat.dob : 'N/A';
        const sex = pat.sex || 'N/A';

        document.getElementById('res-patient').innerHTML = `
            <strong>Name:</strong> ${name} &nbsp;|&nbsp; 
            <strong>DOB:</strong> ${dob} &nbsp;|&nbsp; 
            <strong>Sex:</strong> ${sex} &nbsp;|&nbsp; 
            <strong>ID:</strong> ${pat.id || '--'}
        `;

        // Summary
        document.getElementById('res-summary').textContent = data.clinical_summary || "No clinical summary available.";

        // Observations Table
        const obsBody = document.getElementById('res-obs-body');
        obsBody.innerHTML = '';
        const obs = data.structured_observations || [];

        if (obs.length === 0) {
            obsBody.innerHTML = '<tr><td colspan="7" style="text-align:center; opacity:0.6;">No observations found.</td></tr>';
        } else {
            obs.forEach((o, index) => {
                obsBody.appendChild(createObservationRow(o, index));
            });
        }

        // FHIR Bundle
        const fhirCode = document.getElementById('res-fhir');
        fhirCode.textContent = JSON.stringify(data.fhir_bundle, null, 2);
    }

    // Tabs Logic
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            // Add active
            btn.classList.add('active');
            const targetId = btn.getAttribute('data-tab');
            document.getElementById(targetId).classList.add('active');
        });
    });

    // Select All Logic
    if (selectAllCheck) {
        selectAllCheck.addEventListener('change', (e) => {
            document.querySelectorAll('.obs-check').forEach(cb => cb.checked = e.target.checked);
        });
    }

    // Confirm & Save Logic
    if (saveBtn) {
        saveBtn.addEventListener('click', async () => {
            if (!currentAnalysisData) return;

            // Gather verified data from DOM
            const verifiedObs = [];
            const rows = document.querySelectorAll('#res-obs-body tr');

            rows.forEach(row => {
                const cb = row.querySelector('.obs-check');
                if (cb && cb.checked) {
                    const testNameInput = row.querySelector('.test-name-input');
                    const codeHidden = row.querySelector('.code-hidden');
                    const valInput = row.querySelector('.value-input');
                    const unitInput = row.querySelector('.unit-input');

                    // Determine source from badge text
                    const sourceText = row.querySelector('td:nth-child(2)').innerText;
                    let source = 'HL7';
                    if (sourceText.includes('AI')) source = 'AI_EXTRACTED';
                    if (sourceText.includes('User')) source = 'MANUAL';

                    // Determine Display Name (fallback to text if input is empty/missing? No, input should govern)
                    const display = testNameInput ? testNameInput.value : '';

                    verifiedObs.push({
                        display: display,
                        code: codeHidden ? codeHidden.value : '',
                        value: valInput ? valInput.value : '',
                        unit: unitInput ? unitInput.value : '',
                        source: source,
                        // Preserve other fields if possible? 
                        // For simplicity, we just save what's visible + source. 
                        // The backend will persist this list.
                        flag: row.querySelector('.obs-flag') ? row.querySelector('.obs-flag').innerText : ''
                    });
                }
            });

            // Construct payload
            // We use currentAnalysisData for the patient info, but REPLACE observations
            // AND we must ensure raw_hl7 is present (it's required by backend but missing from parse response)
            const payload = {
                ...currentAnalysisData,
                structured_observations: verifiedObs,
                raw_hl7: hl7Input ? hl7Input.value.trim() : ''
            };

            saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';
            saveBtn.disabled = true;

            try {
                const response = await fetch('/messages', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) throw new Error('Failed to save message');

                showToast(`Saved ${verifiedObs.length} observations successfully!`, 'success');
                saveBtn.classList.add('hidden');

            } catch (err) {
                console.error(err);
                showToast('Failed to save: ' + err.message, 'error');
                saveBtn.innerHTML = '<i class="fa-solid fa-check"></i> Confirm & Save';
                saveBtn.disabled = false;
            }
        });
    }

});
