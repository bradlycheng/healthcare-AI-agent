// patient.js - Patient Timeline Page

// Determine API Base URL for local file access vs server access
const API_BASE = (window.location.protocol === 'file:')
    ? 'http://localhost:8080'
    : '';

// Get patient ID from URL
const urlParams = new URLSearchParams(window.location.search);
const patientId = urlParams.get('id');

// DOM Elements
const patientName = document.getElementById('patient-name');
const patientIdEl = document.getElementById('patient-id');
const patientDob = document.getElementById('patient-dob');
const patientSex = document.getElementById('patient-sex');
const visitCount = document.getElementById('visit-count');
const aiSummary = document.getElementById('ai-summary');
const timelineContainer = document.getElementById('timeline-container');
const generateSummaryBtn = document.getElementById('generate-summary-btn');
const chartMetricSelect = document.getElementById('chart-metric');

let timelineData = null;
let trendChart = null;

// Initialize page
document.addEventListener('DOMContentLoaded', () => {
    if (!patientId) {
        patientName.textContent = 'No patient selected';
        return;
    }

    loadPatientTimeline();

    generateSummaryBtn.addEventListener('click', generateSummary);
    chartMetricSelect.addEventListener('change', updateChart);
});

// Load patient timeline data
async function loadPatientTimeline() {
    try {
        const response = await fetch(`${API_BASE}/patients/${encodeURIComponent(patientId)}/timeline`);

        if (!response.ok) {
            throw new Error('Patient not found');
        }

        timelineData = await response.json();
        renderPatientInfo(timelineData.patient);
        renderTimeline(timelineData.visits);
        initChart();

    } catch (error) {
        console.error('Error loading timeline:', error);
        patientName.textContent = 'Error loading patient';
    }
}

// Render patient info header
function renderPatientInfo(patient) {
    const fullName = `${patient.first_name} ${patient.last_name}`.trim() || 'Unknown';
    patientName.textContent = fullName;
    patientIdEl.textContent = patient.id || '--';
    patientDob.textContent = formatDate(patient.dob) || '--';
    patientSex.textContent = formatSex(patient.sex) || '--';
    visitCount.textContent = timelineData.visit_count || 0;

    document.title = `${fullName} - Patient Timeline`;
}

// Format date for display
function formatDate(dateStr) {
    if (!dateStr) return null;
    // Handle YYYYMMDD format
    if (dateStr.length === 8 && !dateStr.includes('-')) {
        return `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(6, 8)}`;
    }
    return dateStr.split('T')[0];
}

// Format sex for display
function formatSex(sex) {
    const map = { 'M': 'Male', 'F': 'Female', 'O': 'Other', 'U': 'Unknown' };
    return map[sex?.toUpperCase()] || sex;
}

// Pagination State
let visibleVisits = 10;
const loadMoreBtn = document.getElementById('load-more-btn');

// Render visit timeline
function renderTimeline(visits) {
    if (!visits || visits.length === 0) {
        timelineContainer.innerHTML = '<p class="no-data">No visits recorded for this patient.</p>';
        loadMoreBtn.parentElement.style.display = 'none';
        return;
    }

    // Sort: newest first
    const sortedVisits = [...visits].reverse();

    // Setup Load More button if needed
    if (sortedVisits.length > visibleVisits) {
        loadMoreBtn.parentElement.style.display = 'block';
        loadMoreBtn.onclick = () => {
            visibleVisits += 10;
            renderTimeline(visits); // Re-render with new limit
        };
    } else {
        loadMoreBtn.parentElement.style.display = 'none';
    }

    // Slice for pagination
    const visitsToShow = sortedVisits.slice(0, visibleVisits);

    timelineContainer.innerHTML = visitsToShow.map((visit, index) => `
        <div class="timeline-card ${index === 0 ? 'latest' : ''}">
            <div class="timeline-marker">
                <div class="marker-dot"></div>
                ${index < visitsToShow.length - 1 ? '<div class="marker-line"></div>' : ''}
            </div>
            <div class="timeline-content">
                <div class="timeline-header">
                    <span class="visit-date">
                        <i class="fa-solid fa-calendar"></i>
                        ${formatDate(visit.date)}
                    </span>
                    ${index === 0 ? '<span class="latest-badge">Latest Visit</span>' : ''}
                </div>
                <div class="observations-grid">
                    ${visit.observations.map(obs => `
                        <div class="obs-item ${getFlagClass(obs.flag)}">
                            <span class="obs-name">${obs.display || obs.code}</span>
                            <span class="obs-value">${obs.value ?? '--'}</span>
                            <span class="obs-unit">${obs.unit || ''}</span>
                            ${obs.flag ? `<span class="obs-flag">${obs.flag}</span>` : ''}
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>
    `).join('');
}

// Get CSS class for flag
function getFlagClass(flag) {
    if (!flag) return '';
    const f = flag.toUpperCase();
    if (f === 'H' || f === 'HH') return 'flag-high';
    if (f === 'L' || f === 'LL') return 'flag-low';
    return '';
}

// Initialize trend chart
function initChart() {
    const ctx = document.getElementById('trend-chart').getContext('2d');

    trendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: []
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true, // Enable legend for multi-line support
                    labels: { color: '#94a3b8' }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleColor: '#f8fafc',
                    bodyColor: '#cbd5e1',
                    padding: 12,
                    cornerRadius: 8,
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#94a3b8' }
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#94a3b8' }
                }
            }
        }
    });

    updateChart();
}

// Helper to extract data points for a code
function getPointsForCode(code) {
    const points = [];
    for (const visit of timelineData.visits) {
        for (const obs of visit.observations) {
            if (obs.code === code && typeof obs.value === 'number') {
                points.push({
                    date: visit.date,
                    value: obs.value,
                    unit: obs.unit
                });
            }
        }
    }
    return points.sort((a, b) => new Date(a.date) - new Date(b.date));
}

// Update chart with selected metric
function updateChart() {
    if (!timelineData || !trendChart) return;

    const selectedValue = chartMetricSelect.value;
    const datasets = [];
    let labels = [];

    if (selectedValue === 'BP_COMBINED') {
        const sysPoints = getPointsForCode('8480-6');
        const diaPoints = getPointsForCode('8462-4');

        // Use systolic dates as master label source (usually same)
        labels = sysPoints.map(d => formatDate(d.date));

        datasets.push({
            label: 'Systolic BP (mmHg)',
            data: sysPoints.map(d => d.value),
            borderColor: '#f43f5e', // Red/Pink
            backgroundColor: 'rgba(244, 63, 94, 0.1)',
            borderWidth: 2,
            tension: 0.3,
            pointRadius: 4
        });

        datasets.push({
            label: 'Diastolic BP (mmHg)',
            data: diaPoints.map(d => d.value),
            borderColor: '#3b82f6', // Blue
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            borderWidth: 2,
            tension: 0.3,
            pointRadius: 4
        });

    } else {
        const points = getPointsForCode(selectedValue);
        const label = chartMetricSelect.options[chartMetricSelect.selectedIndex].text;

        labels = points.map(d => formatDate(d.date));

        datasets.push({
            label: label,
            data: points.map(d => d.value),
            borderColor: '#6366f1', // Indigo
            backgroundColor: 'rgba(99, 102, 241, 0.1)',
            borderWidth: 2,
            fill: true,
            tension: 0.3,
            pointRadius: 4
        });
    }

    trendChart.data.labels = labels;
    trendChart.data.datasets = datasets;
    trendChart.update();
}

// Generate AI summary
async function generateSummary() {
    generateSummaryBtn.disabled = true;
    generateSummaryBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generating...';
    aiSummary.innerHTML = '<p class="loading-text">Analyzing patient history...</p>';

    try {
        const response = await fetch(`${API_BASE}/patients/${encodeURIComponent(patientId)}/summary`);

        if (!response.ok) {
            if (response.status === 429) {
                throw new Error('Rate limited. Please wait a few seconds.');
            }
            throw new Error('Failed to generate summary');
        }

        const data = await response.json();
        aiSummary.innerHTML = `<p class="summary-text">${data.summary}</p>`;

    } catch (error) {
        console.error('Error generating summary:', error);
        aiSummary.innerHTML = `<p class="error-text"><i class="fa-solid fa-exclamation-circle"></i> ${error.message}</p>`;
    } finally {
        generateSummaryBtn.disabled = false;
        generateSummaryBtn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Generate';
    }
}
