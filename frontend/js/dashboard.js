// Asia Restaurant - Sensor Dashboard (Chart.js)

const API = '';
const REFRESH_INTERVAL = 30000;

let state = {
    page: 1,
    perPage: 20,
    occupancyHours: 24,
    charts: {}
};

// ── Chart.js Defaults ──
Chart.defaults.color = '#8b8fa3';
Chart.defaults.borderColor = '#2a2d3a';
Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";

// ── Tab Navigation ──
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    });
});

// ── Chart Controls (Occupancy Hours) ──
document.querySelectorAll('.chart-controls .btn-sm').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.chart-controls .btn-sm').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.occupancyHours = parseInt(btn.dataset.hours);
        loadOccupancyHistory();
    });
});

// ── Pagination ──
document.getElementById('btnPrev').addEventListener('click', () => {
    if (state.page > 1) { state.page--; loadTable(); }
});
document.getElementById('btnNext').addEventListener('click', () => {
    state.page++;
    loadTable();
});

// ── API Helper ──
async function fetchApi(endpoint) {
    try {
        const res = await fetch(API + endpoint);
        const data = await res.json();
        return data;
    } catch (e) {
        console.error('API Fehler:', endpoint, e);
        return null;
    }
}

// ── Status Update ──
function setStatus(online) {
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    if (online) {
        dot.className = 'status-dot online';
        text.textContent = 'Verbunden';
    } else {
        dot.className = 'status-dot offline';
        text.textContent = 'Keine Verbindung';
    }
}

// ── Create/Update Line Chart ──
function createLineChart(canvasId, labels, datasets, yTitle) {
    if (state.charts[canvasId]) {
        state.charts[canvasId].data.labels = labels;
        datasets.forEach((ds, i) => {
            state.charts[canvasId].data.datasets[i].data = ds.data;
        });
        state.charts[canvasId].update('none');
        return;
    }

    const ctx = document.getElementById(canvasId).getContext('2d');
    state.charts[canvasId] = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            plugins: {
                legend: { display: datasets.length > 1, position: 'top' },
                tooltip: { backgroundColor: '#1a1d27', borderColor: '#2a2d3a', borderWidth: 1 }
            },
            scales: {
                x: {
                    ticks: { maxTicksLimit: 12, maxRotation: 0 },
                    grid: { display: false }
                },
                y: {
                    title: { display: !!yTitle, text: yTitle || '' },
                    beginAtZero: true
                }
            },
            elements: {
                point: { radius: 0, hoverRadius: 4 },
                line: { tension: 0.3 }
            }
        }
    });
}

// ── Format Timestamp ──
function formatTime(ts) {
    if (!ts) return '--';
    const d = new Date(ts.replace(' ', 'T'));
    return d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
}

// ── Load Dashboard Data ──
async function loadDashboard() {
    const [occ, stats] = await Promise.all([
        fetchApi('/api/occupancy/current'),
        fetchApi('/api/data/stats')
    ]);

    if (occ && occ.success) {
        setStatus(true);
        const d = occ.data;
        document.getElementById('currentOccupancy').textContent = d.estimated_occupancy ?? '--';
        document.getElementById('acLevel').textContent = 'Stufe ' + (d.ac_recommendation ?? '--');
        if (d.sensors) {
            document.getElementById('currentTemp').textContent =
                d.sensors.temperature != null ? d.sensors.temperature.toFixed(1) + ' °C' : '--';
            document.getElementById('currentHumidity').textContent =
                d.sensors.humidity != null ? d.sensors.humidity.toFixed(1) + ' %' : '--';
        }
    } else {
        setStatus(false);
    }

    if (stats && stats.success) {
        const s = stats.data;
        document.getElementById('sensorTempRange').textContent =
            s.min_temp != null ? `Min ${s.min_temp.toFixed(1)} / Max ${s.max_temp.toFixed(1)} °C` : '--';
    }

    document.getElementById('lastUpdate').textContent =
        new Date().toLocaleTimeString('de-DE');
}

// ── Load Occupancy Tab ──
async function loadOccupancy() {
    const [occ, est] = await Promise.all([
        fetchApi('/api/occupancy/current'),
        fetchApi('/api/estimator/status')
    ]);

    if (occ && occ.success) {
        const d = occ.data;
        document.getElementById('occPersons').textContent = d.estimated_occupancy ?? '--';
        document.getElementById('occPercent').textContent =
            (d.occupancy_percent ?? 0).toFixed(1) + ' % Auslastung';
        document.getElementById('occProgressBar').style.width =
            Math.min(100, d.occupancy_percent ?? 0) + '%';

        document.getElementById('occAcLevel').textContent = 'Stufe ' + (d.ac_recommendation ?? '--');
        if (d.climate_recommendation && d.climate_recommendation.note) {
            document.getElementById('occAcNote').textContent = d.climate_recommendation.note;
        }
    }

    if (est && est.success) {
        const s = est.data;
        document.getElementById('estimatorStatus').innerHTML = `
            <div class="info-item">
                <div class="label">Modell</div>
                <div class="value">${s.model_type === 'trained_regression' ? 'Trainiert' : 'Physikalisch'}</div>
            </div>
            <div class="info-item">
                <div class="label">Trainingspunkte</div>
                <div class="value">${s.training_samples} / 10</div>
            </div>
            <div class="info-item">
                <div class="label">Baseline kalibriert</div>
                <div class="value">${s.baseline.calibrated ? 'Ja' : 'Nein'}</div>
            </div>
            <div class="info-item">
                <div class="label">Baseline Temperatur</div>
                <div class="value">${s.baseline.temperature} °C</div>
            </div>
        `;
    }
}

// ── Load Occupancy History Chart ──
async function loadOccupancyHistory() {
    const data = await fetchApi('/api/occupancy/history?hours=' + state.occupancyHours);
    if (!data || !data.success) return;

    const labels = data.data.map(r => formatTime(r.timestamp));
    createLineChart('chartOccupancyDetail', labels, [{
        label: 'Personen',
        data: data.data.map(r => r.estimated_occupancy ?? 0),
        borderColor: '#c41e3a',
        backgroundColor: 'rgba(196, 30, 58, 0.1)',
        fill: true
    }], 'Personen');
}

// ── Load Dashboard Charts (24h) ──
async function loadDashboardCharts() {
    const data = await fetchApi('/api/data/history?hours=24&limit=500');
    if (!data || !data.success || !data.data.length) return;

    const rows = data.data;
    const labels = rows.map(r => formatTime(r.timestamp));

    createLineChart('chartOccupancy', labels, [{
        label: 'Personen',
        data: rows.map(r => r.estimated_occupancy ?? 0),
        borderColor: '#c41e3a',
        backgroundColor: 'rgba(196, 30, 58, 0.1)',
        fill: true
    }], 'Personen');

    createLineChart('chartTempHumidity', labels, [
        {
            label: 'Temperatur (°C)',
            data: rows.map(r => r.temperature),
            borderColor: '#ef4444',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            fill: false
        },
        {
            label: 'Feuchtigkeit (%)',
            data: rows.map(r => r.humidity),
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            fill: false
        }
    ], '');
}

// ── Load Sensor Tab ──
async function loadSensors() {
    const [occ, stats] = await Promise.all([
        fetchApi('/api/occupancy/current'),
        fetchApi('/api/data/stats')
    ]);

    if (occ && occ.success && occ.data.sensors) {
        const s = occ.data.sensors;
        document.getElementById('sensorTemp').textContent =
            s.temperature != null ? s.temperature.toFixed(1) + ' °C' : '--';
        document.getElementById('sensorHumidity').textContent =
            s.humidity != null ? s.humidity.toFixed(1) + ' %' : '--';
        document.getElementById('sensorPressure').textContent =
            s.pressure != null ? s.pressure.toFixed(1) + ' hPa' : '--';
        document.getElementById('sensorMovement').textContent = s.movement_count_5min ?? 0;
        document.getElementById('sensorMovementStatus').textContent =
            s.movement_detected ? 'Aktiv' : 'Keine Bewegung';
    }

    if (stats && stats.success) {
        const d = stats.data;
        document.getElementById('sensorHumidityAvg').textContent =
            d.avg_humidity != null ? 'Durchschnitt: ' + d.avg_humidity.toFixed(1) + ' %' : '--';
        document.getElementById('sensorPressureAvg').textContent =
            d.avg_pressure != null ? 'Durchschnitt: ' + d.avg_pressure.toFixed(1) + ' hPa' : '--';
    }

    // Gas and Pressure charts
    const hist = await fetchApi('/api/data/history?hours=24&limit=500');
    if (hist && hist.success && hist.data.length) {
        const rows = hist.data;
        const labels = rows.map(r => formatTime(r.timestamp));

        createLineChart('chartGas', labels, [{
            label: 'Gasresistenz (Ohm)',
            data: rows.map(r => r.gas_resistance),
            borderColor: '#d4a853',
            backgroundColor: 'rgba(212, 168, 83, 0.1)',
            fill: true
        }], 'Ohm');

        createLineChart('chartPressure', labels, [{
            label: 'Luftdruck (hPa)',
            data: rows.map(r => r.pressure),
            borderColor: '#8b5cf6',
            backgroundColor: 'rgba(139, 92, 246, 0.1)',
            fill: true
        }], 'hPa');
    }
}

// ── Load History Table ──
async function loadTable() {
    const data = await fetchApi(`/api/data/table?page=${state.page}&per_page=${state.perPage}`);
    if (!data || !data.success) return;

    const tbody = document.getElementById('tableBody');
    if (!data.data.length) {
        tbody.innerHTML = '<tr><td colspan="9">Keine Daten vorhanden</td></tr>';
        return;
    }

    tbody.innerHTML = data.data.map(r => `
        <tr>
            <td>${r.id}</td>
            <td>${r.timestamp || '--'}</td>
            <td>${r.temperature != null ? r.temperature.toFixed(1) : '--'}</td>
            <td>${r.pressure != null ? r.pressure.toFixed(1) : '--'}</td>
            <td>${r.humidity != null ? r.humidity.toFixed(1) : '--'}</td>
            <td>${r.gas_resistance != null ? Math.round(r.gas_resistance).toLocaleString() : '--'}</td>
            <td><span class="badge ${r.movement_detected ? 'badge-yes' : 'badge-no'}">${r.movement_detected ? 'Ja' : 'Nein'}</span></td>
            <td>${r.estimated_occupancy ?? '--'}</td>
            <td>${r.ac_recommendation ?? '--'}</td>
        </tr>
    `).join('');

    const p = data.pagination;
    document.getElementById('pageInfo').textContent = `Seite ${p.page} von ${p.pages}`;
    document.getElementById('tableInfo').textContent = `${p.total} Eintraege`;
    document.getElementById('btnPrev').disabled = p.page <= 1;
    document.getElementById('btnNext').disabled = p.page >= p.pages;
}

// ── Initial Load ──
async function init() {
    await Promise.all([
        loadDashboard(),
        loadDashboardCharts(),
        loadTable()
    ]);

    // Preload other tabs in background
    loadOccupancy();
    loadOccupancyHistory();
    loadSensors();
}

init();

// ── Auto-refresh ──
setInterval(() => {
    loadDashboard();
    loadDashboardCharts();
    loadOccupancy();
    loadOccupancyHistory();
    loadSensors();
}, REFRESH_INTERVAL);
