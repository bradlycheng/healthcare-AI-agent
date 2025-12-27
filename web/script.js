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
    const hl7Input = document.getElementById('hl7-input');
    const resultsArea = document.getElementById('results-area');
    const aiToggle = document.getElementById('ai-toggle');

    // Track current request state
    let currentAbortController = null;
    let processingStartTime = null;
    let timerInterval = null;
    let rateLimitCooldown = null;

    // Thresholds for stalling detection (in milliseconds)
    const STALL_WARNING_THRESHOLD = 8000;  // Show warning after 8 seconds
    const STALL_CRITICAL_THRESHOLD = 15000; // Suggest canceling after 15 seconds
    const REQUEST_TIMEOUT = 30000;          // Total timeout 30 seconds

    // Create and inject rate limit banner
    function createRateLimitBanner() {
        const demoInput = document.querySelector('.demo-input');
        if (!demoInput) return null;

        const banner = document.createElement('div');
        banner.className = 'rate-limit-banner';
        banner.id = 'rate-limit-banner';
        banner.innerHTML = `
            <i class="fa-solid fa-clock"></i>
            <div class="message">
                <h4>Rate Limit Reached</h4>
                <p>Please wait before sending another AI request.</p>
            </div>
            <div class="countdown" id="rate-limit-countdown">5</div>
        `;

        demoInput.insertBefore(banner, demoInput.firstChild);
        return banner;
    }

    // Create processing timer and cancel button
    function createProcessingElements() {
        const inputHeader = document.querySelector('.input-header');
        if (!inputHeader) return;

        // Add timer display
        const timerDiv = document.createElement('div');
        timerDiv.className = 'processing-timer';
        timerDiv.id = 'processing-timer';
        timerDiv.innerHTML = '<i class="fa-solid fa-stopwatch"></i> Processing: <span id="timer-value">0s</span>';

        // Add stall warning
        const stallWarning = document.createElement('div');
        stallWarning.className = 'stall-warning';
        stallWarning.id = 'stall-warning';
        stallWarning.innerHTML = `
            <i class="fa-solid fa-triangle-exclamation"></i>
            <span id="stall-message">AI is taking longer than expected...</span>
        `;

        // Add cancel button
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'cancel-btn';
        cancelBtn.id = 'cancel-btn';
        cancelBtn.innerHTML = '<i class="fa-solid fa-xmark"></i> Cancel Request';
        cancelBtn.addEventListener('click', cancelCurrentRequest);

        // Insert after the textarea wrapper
        const textarea = document.getElementById('hl7-input');
        if (textarea) {
            textarea.parentNode.insertBefore(timerDiv, textarea.nextSibling);
            textarea.parentNode.insertBefore(stallWarning, timerDiv.nextSibling);
            textarea.parentNode.insertBefore(cancelBtn, stallWarning.nextSibling);
        }
    }

    // Initialize extra elements
    createRateLimitBanner();
    createProcessingElements();

    function cancelCurrentRequest() {
        if (currentAbortController) {
            currentAbortController.abort();
            showToast('Request cancelled', 'warning');
            resetProcessingUI();
        }
    }

    function startProcessingTimer() {
        processingStartTime = Date.now();
        const timerEl = document.getElementById('processing-timer');
        const timerValue = document.getElementById('timer-value');
        const stallWarning = document.getElementById('stall-warning');
        const stallMessage = document.getElementById('stall-message');
        const cancelBtn = document.getElementById('cancel-btn');

        if (timerEl) timerEl.classList.add('visible');
        if (cancelBtn) cancelBtn.classList.add('visible');

        timerInterval = setInterval(() => {
            const elapsed = Date.now() - processingStartTime;
            const seconds = Math.floor(elapsed / 1000);

            if (timerValue) timerValue.textContent = `${seconds}s`;

            // Check for stalling
            if (elapsed >= STALL_CRITICAL_THRESHOLD) {
                if (stallWarning) {
                    stallWarning.classList.add('visible');
                    if (stallMessage) {
                        stallMessage.innerHTML = `
                            <strong>AI appears to be stalling (${seconds}s).</strong> 
                            The service might be overloaded. Consider canceling and trying without AI.
                        `;
                    }
                }
            } else if (elapsed >= STALL_WARNING_THRESHOLD) {
                if (stallWarning) {
                    stallWarning.classList.add('visible');
                    if (stallMessage) {
                        stallMessage.textContent = `AI is taking longer than expected (${seconds}s)...`;
                    }
                }
            }
        }, 1000);
    }

    function stopProcessingTimer() {
        if (timerInterval) {
            clearInterval(timerInterval);
            timerInterval = null;
        }
    }

    function resetProcessingUI() {
        stopProcessingTimer();

        const timerEl = document.getElementById('processing-timer');
        const stallWarning = document.getElementById('stall-warning');
        const cancelBtn = document.getElementById('cancel-btn');
        const timerValue = document.getElementById('timer-value');

        if (timerEl) timerEl.classList.remove('visible');
        if (stallWarning) stallWarning.classList.remove('visible');
        if (cancelBtn) cancelBtn.classList.remove('visible');
        if (timerValue) timerValue.textContent = '0s';

        processBtn.innerHTML = '<i class="fa-solid fa-bolt"></i> Process Message';
        processBtn.disabled = false;
        currentAbortController = null;
    }

    function showRateLimitBanner(waitSeconds = 5) {
        const banner = document.getElementById('rate-limit-banner');
        const countdown = document.getElementById('rate-limit-countdown');

        if (!banner) return;

        banner.classList.add('visible');
        let remaining = waitSeconds;

        if (countdown) countdown.textContent = remaining;

        // Clear any existing cooldown interval
        if (rateLimitCooldown) clearInterval(rateLimitCooldown);

        rateLimitCooldown = setInterval(() => {
            remaining--;
            if (countdown) countdown.textContent = remaining;

            if (remaining <= 0) {
                clearInterval(rateLimitCooldown);
                rateLimitCooldown = null;
                banner.classList.remove('visible');
            }
        }, 1000);
    }

    if (processBtn && hl7Input) {
        processBtn.addEventListener('click', async () => {
            const text = hl7Input.value.trim();
            if (!text) {
                showToast("Please paste an HL7 message first.", 'warning');
                return;
            }

            // Check if we're in rate limit cooldown
            if (rateLimitCooldown) {
                showToast("Please wait for the cooldown to finish.", 'warning');
                return;
            }

            // Cancel any existing request
            if (currentAbortController) {
                currentAbortController.abort();
            }

            // Create new abort controller
            currentAbortController = new AbortController();
            const signal = currentAbortController.signal;

            // UI Loading state
            const useAI = aiToggle ? aiToggle.checked : true;

            if (useAI) {
                processBtn.innerHTML = '<i class="fa-solid fa-brain fa-pulse"></i> AI Analyzing...';
                startProcessingTimer();
            } else {
                processBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';
            }

            processBtn.disabled = true;
            resultsArea.classList.add('hidden');

            // Set up timeout
            const timeoutId = setTimeout(() => {
                if (currentAbortController) {
                    currentAbortController.abort();
                    showToast('Request timed out. Try disabling AI for faster processing.', 'error');
                }
            }, REQUEST_TIMEOUT);

            try {
                const response = await fetch('/oru/parse', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        hl7_text: text,
                        use_llm: useAI
                    }),
                    signal: signal
                });

                clearTimeout(timeoutId);

                if (!response.ok) {
                    const errData = await response.json().catch(() => ({}));

                    // Handle rate limiting specifically
                    if (response.status === 429) {
                        showRateLimitBanner(5);
                        showToast('Too many requests. Please wait a few seconds.', 'warning');
                        resetProcessingUI();
                        return;
                    }

                    throw new Error(errData.detail || `Server Error: ${response.status}`);
                }

                const data = await response.json();
                renderResults(data);
                resultsArea.classList.remove('hidden');

                // Show success toast
                const processingTime = processingStartTime ?
                    Math.round((Date.now() - processingStartTime) / 1000) : 0;
                if (processingTime > 0) {
                    showToast(`Processed in ${processingTime}s`, 'success');
                }

                // Scroll to results
                resultsArea.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

            } catch (err) {
                clearTimeout(timeoutId);

                if (err.name === 'AbortError') {
                    // Request was cancelled - don't show additional error
                    console.log('Request aborted');
                } else {
                    console.error(err);

                    // Provide helpful error messages
                    let errorMessage = err.message;
                    if (errorMessage.includes('Failed to fetch') || errorMessage.includes('NetworkError')) {
                        errorMessage = 'Network error. Please check if the server is running.';
                    } else if (errorMessage.includes('timeout') || errorMessage.includes('Timeout')) {
                        errorMessage = 'Request timed out. The AI service may be overloaded.';
                    }

                    showToast(`Error: ${errorMessage}`, 'error');
                }
            } finally {
                resetProcessingUI();
            }
        });
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
            obsBody.innerHTML = '<tr><td colspan="4" style="text-align:center; opacity:0.6;">No observations found.</td></tr>';
        } else {
            obs.forEach(o => {
                const tr = document.createElement('tr');

                // Format flag
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

                tr.innerHTML = `
                    <td>${o.display || o.code}</td>
                    <td><strong>${o.value || ''}</strong> <small class="text-muted">${o.unit || ''}</small></td>
                    <td>${flagHtml}</td>
                    <td>${ref}</td>
                `;
                obsBody.appendChild(tr);
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

});
