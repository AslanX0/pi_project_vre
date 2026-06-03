// Dashboard-Steuerung fuer das Restaurant-Sensor-Dashboard.
// Single Page Application: Es gibt nur eine HTML-Seite, das Tab-Routing
// passiert komplett im Browser per JavaScript (kein Seitenneulade).

// Alle Daten werden alle 30 Sekunden neu geladen
const REFRESH_INTERVAL = 30000;

// Zentrales State-Objekt:
//   page/perPage: aktuelle Seite der History-Tabelle
//   charts: Cache aller Chart.js-Instanzen (verhindert Doppelanlagen)
let state = { page: 1, perPage: 20, charts: {} };

// Globale Chart.js-Standardwerte fuer das dunkle Design
Chart.defaults.color = '#8b8fa3';
Chart.defaults.borderColor = '#2a2d3a';
Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";

// Mapping Tab-Name <-> URL-Pfad fuer die Browser-History-API
const TAB_ROUTES = { dashboard: '/', regression: '/regression', sensors: '/sensors', history: '/history' };
const PATH_TO_TAB = Object.fromEntries(Object.entries(TAB_ROUTES).map(([t, p]) => [p, t]));

function activateTab(tabName) {
    // aktiven Zustand aller Navigations-Buttons und Inhaltsbereich umschalten
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    const btn = document.querySelector(`.nav-btn[data-tab="${tabName}"]`);
    if (btn) btn.classList.add('active');
    const content = document.getElementById('tab-' + tabName);
    if (content) content.classList.add('active');
}

// Tab-Wechsel per Klick: URL in der Browserleiste aktualisieren ohne Seitenneulade
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        history.pushState({ tab }, '', TAB_ROUTES[tab] || '/');
        activateTab(tab);
    });
});

// Zurueck/Vorwaerts im Browser: richtigen Tab anzeigen
window.addEventListener('popstate', e => {
    activateTab(e.state?.tab || PATH_TO_TAB[window.location.pathname] || 'dashboard');
});

// Beim ersten Laden den passenden Tab anhand der aktuellen URL aktivieren
activateTab(PATH_TO_TAB[window.location.pathname] || 'dashboard');

// Tabellen-Paginierung: Seite zurueck/vorwaerts
document.getElementById('btnPrev').addEventListener('click', () => { if (state.page > 1) { state.page--; loadTable(); } });
document.getElementById('btnNext').addEventListener('click', () => { state.page++; loadTable(); });


function showError(msg) {
    // Fehlerbanner am oberen Bildschirmrand einblenden
    const banner = document.getElementById('errorBanner');
    document.getElementById('errorMessage').textContent = msg;
    banner.style.display = 'flex';
}

function hideError() {
    document.getElementById('errorBanner').style.display = 'none';
}

// Zentrale Fetch-Funktion: alle API-Aufrufe gehen ueber diese Funktion.
// Bei Fehler wird der Fehlerbanner angezeigt und null zurueckgegeben,
// damit die Aufrufer nicht abstuerzen.
async function fetchApi(endpoint) {
    try {
        const res = await fetch(endpoint);
        if (!res.ok) {
            showError('Server-Error Status: ' + res.status + ' bei ' + endpoint);
            return null;
        }
        const data = await res.json();
        hideError();
        return data;
    } catch (e) {
        console.error('API Fehler:', endpoint, e);
        showError('Keine Verbindung');
        return null;
    }
}

// Chart erstellen oder aktualisieren.
// Wenn ein Chart fuer diese Canvas-ID bereits existiert (state.charts), werden
// nur die Daten ausgetauscht statt das Diagramm komplett neu zu erstellen.
// Das spart Speicher und vermeidet Flackern beim automatischen Refresh.
function createLineChart(canvasId, labels, datasets, yTitle) {
    if (state.charts[canvasId]) {
        state.charts[canvasId].data.labels = labels;
        datasets.forEach((ds, i) => state.charts[canvasId].data.datasets[i].data = ds.data);
        state.charts[canvasId].update('none');  // 'none': ohne Animation fuer schnellere Updates
        return;
    }
    state.charts[canvasId] = new Chart(document.getElementById(canvasId).getContext('2d'), {
        type: 'line', data: { labels, datasets },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            plugins: { legend: { display: datasets.length > 1 }, tooltip: { backgroundColor: '#1a1d27', borderColor: '#2a2d3a', borderWidth: 1 } },
            scales: { x: { ticks: { maxTicksLimit: 12, maxRotation: 0 }, grid: { display: false } }, y: { title: { display: !!yTitle, text: yTitle || '' }, beginAtZero: false } },
            elements: { point: { radius: 0, hoverRadius: 4 }, line: { tension: 0.3 } }
        }
    });
}

// Zeitstempel aus dem Format "YYYY-MM-DD HH:MM:SS" in deutsches Kurzformat umwandeln
function formatTime(ts) {
    if (!ts) return '--';
    // Leerzeichen zwischen Datum und Uhrzeit durch 'T' ersetzen, damit new Date() es korrekt parst
    const d = new Date(ts.replace(' ', 'T'));
    return d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

// --- Dashboard-Tab ---

async function loadDashboard() {
    // Aktuelle Kennzahlen (neuester Datensatz) in die Anzeigefelder schreiben
    const res = await fetchApi('/api/data/latest');
    if (res?.success && res.data) {
        const d = res.data;
        document.getElementById('currentTemp').textContent = d.temperature != null ? d.temperature.toFixed(1) + ' °C' : '--';
        document.getElementById('currentHumidity').textContent = d.humidity != null ? d.humidity.toFixed(1) + ' %' : '--';
        document.getElementById('currentVOC').textContent = d.gas_resistance != null ? Math.round(d.gas_resistance).toLocaleString() + ' Ω' : '--';
        const persons = d.estimated_occupancy ?? 0;
        document.getElementById('currentOccupancy').textContent = persons != null ? persons + ' Personen' : '--';
        const percent = persons != null ? (persons / 120 * 100).toFixed(1) : '0.0';
        document.getElementById('currentOccPercent').textContent = percent + ' % Auslastung';
    }
    document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString('de-DE');
}

async function loadDashboardCharts() {
    // Zeitreihencharts fuer die letzten 7 Tage laden (168h), maximal 2000 Datenpunkte
    const data = await fetchApi('/api/data/history?hours=168&limit=2000');
    if (!data?.success || !data.data.length) return;
    const rows = data.data, labels = rows.map(r => formatTime(r.timestamp));
    createLineChart('chartTemperature', labels, [{ label: 'Temperatur (°C)', data: rows.map(r => r.temperature), borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.1)', fill: true }], '°C');
    createLineChart('chartHumidity', labels, [{ label: 'Luftfeuchtigkeit (%)', data: rows.map(r => r.humidity), borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', fill: true }], '%');
    createLineChart('chartOccupancy', labels, [{ label: 'Geschaetzte Personen', data: rows.map(r => r.estimated_occupancy ?? 0), borderColor: '#d4a853', backgroundColor: 'rgba(212,168,83,0.1)', fill: true }], 'Personen');
}

// --- Regressions-Tab ---

async function loadRegression() {
    // Modellstatus und Streudiagramm-Daten parallel laden
    const [regStatus, scatter] = await Promise.all([
        fetchApi('/api/regression/status'),
        fetchApi('/api/regression/scatter?hours=48')
    ]);

    if (regStatus?.success) {
        const s = regStatus.data;
        if (s.trained) {
            document.getElementById('regSlope').textContent = s.slope.toFixed(4) + ' °C/Person';
            document.getElementById('regIntercept').textContent = s.intercept.toFixed(2) + ' °C';
            document.getElementById('regR2').textContent = s.r_squared.toFixed(4);
            document.getElementById('regR2Detail').textContent = (s.r_squared * 100).toFixed(1) + '%';
            document.getElementById('regSamples').textContent = s.n_samples;
            document.getElementById('regTrainedAt').textContent = s.trained_at
                ? 'Stand: ' + new Date(s.trained_at).toLocaleString('de-DE') : '';
            document.getElementById('regFormula').textContent =
                `T = ${s.slope.toFixed(4)} · x + ${s.intercept.toFixed(2)} °C`;

            // Scenarios table
            if (s.scenarios) {
                document.getElementById('scenariosBody').innerHTML = s.scenarios.map(sc =>
                    `<tr><td style="padding:0.4rem 0.75rem;">${sc.label}</td><td style="padding:0.4rem 0.75rem;">${sc.persons}</td><td style="padding:0.4rem 0.75rem;">${sc.predicted_temp != null ? sc.predicted_temp.toFixed(2) + ' °C' : '--'}</td></tr>`
                ).join('');
            }
        } else {
            ['regSlope', 'regIntercept', 'regR2'].forEach(id =>
                document.getElementById(id).textContent = '--');
            document.getElementById('regR2Detail').textContent =
                s.last_error || 'Noch nicht trainissert';
            document.getElementById('regSamples').textContent = '0';
            document.getElementById('regFormula').textContent = 'T = a · x + b';
            document.getElementById('scenariosBody').innerHTML =
                '<tr><td colspan="3" style="padding:0.4rem 0.75rem;color:var(--text-muted);">Noch nicht trainiert</td></tr>';
        }
    }

    if (scatter?.success) {
        const d = scatter.data;
        const points = d.points || [];
        const datasets = [];

        if (points.length > 0) {
            datasets.push({
                label: `Messpunkte (${points.length})`,
                data: points,
                backgroundColor: 'rgba(212,168,83,0.5)',
                borderColor: '#d4a853',
                pointRadius: 3,
                pointHoverRadius: 5,
                order: 2
            });
        }

        if (d.regression_line) {
            const rl = d.regression_line;
            datasets.push({
                label: `Regressionsgerade (R²=${rl.r_squared.toFixed(4)})`,
                data: rl.points,
                type: 'line',
                borderColor: '#ef4444',
                borderWidth: 2,
                pointRadius: 0,
                fill: false,
                tension: 0,
                order: 1
            });
        }

        if (state.charts['chartScatter']) {
            state.charts['chartScatter'].data.datasets = datasets;
            state.charts['chartScatter'].update();
        } else {
            state.charts['chartScatter'] = new Chart(
                document.getElementById('chartScatter').getContext('2d'), {
                    type: 'scatter',
                    data: { datasets },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { position: 'top' },
                            tooltip: {
                                backgroundColor: '#1a1d27',
                                borderColor: '#2a2d3a',
                                borderWidth: 1,
                                callbacks: {
                                    label: ctx => `${ctx.parsed.x} Personen  –  ${ctx.parsed.y.toFixed(2)} °C`
                                }
                            }
                        },
                        scales: {
                            x: {
                                title: { display: true, text: 'Geschaetzte Personen' },
                                grid: { color: 'rgba(42, 45, 58, 0.5)' }
                            },
                            y: {
                                title: { display: true, text: 'Temperatur (°C)' },
                                grid: { color: 'rgba(42, 45, 58, 0.5)' }
                            }
                        }
                    }
                }
            );
        }
    }
}

// --- Sensor-Tab ---

async function loadSensors() {
    // Alle drei API-Anfragen gleichzeitig starten um Ladezeit zu sparen
    const [occ, stats, estStatus] = await Promise.all([
        fetchApi('/api/occupancy/current'),
        fetchApi('/api/data/stats'),
        fetchApi('/api/estimator/status')
    ]);
    if (occ?.success && occ.data.sensors) {
        const s = occ.data.sensors;
        document.getElementById('sensorTemp').textContent = s.temperature != null ? s.temperature.toFixed(1) + ' °C' : '--';
        document.getElementById('sensorHumidity').textContent = s.humidity != null ? s.humidity.toFixed(1) + ' %' : '--';
        document.getElementById('sensorGas').textContent = s.gas_resistance != null ? Math.round(s.gas_resistance).toLocaleString() + ' Ω' : '--';
        document.getElementById('sensorMovement').textContent = s.movement_detected ? 'Ja' : 'Nein';
        document.getElementById('sensorMovementStatus').textContent = s.movement_detected ? 'Bewegung erkannt' : 'Keine Bewegung';
    }
    if (stats?.success) {
        document.getElementById('sensorTempRange').textContent = stats.data.min_temp != null ? `Min ${stats.data.min_temp.toFixed(1)} / Max ${stats.data.max_temp.toFixed(1)} °C` : '--';
        document.getElementById('sensorHumidityAvg').textContent = stats.data.avg_humidity != null ? 'Durchschnitt: ' + stats.data.avg_humidity.toFixed(1) + ' %' : '--';
    }
    if (estStatus?.success) {
        const e = estStatus.data;
        const baseline = e.baseline || {};
        document.getElementById('calibGasBaseline').textContent = baseline.gas_resistance != null
            ? Math.round(baseline.gas_resistance).toLocaleString() + ' Ω' : '--';
        document.getElementById('calibState').textContent = baseline.calibrated ? 'Kalibriert' : 'Standard (nicht kalibriert)';
    }
    const hist = await fetchApi('/api/data/history?hours=168&limit=2000');
    if (hist?.success && hist.data.length) {
        const rows = hist.data, labels = rows.map(r => formatTime(r.timestamp));
        createLineChart('chartTemperatureSensor', labels, [{ label: 'Temperatur (°C)', data: rows.map(r => r.temperature), borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.1)', fill: true }], '°C');
        createLineChart('chartGas', labels, [{ label: 'VOC (Ohm)', data: rows.map(r => r.gas_resistance), borderColor: '#d4a853', backgroundColor: 'rgba(212,168,83,0.1)', fill: true }], 'Ohm');
        createLineChart('chartPressure', labels, [{ label: 'Luftdruck (hPa)', data: rows.map(r => r.pressure), borderColor: '#8b5cf6', backgroundColor: 'rgba(139,92,246,0.1)', fill: true }], 'hPa');
    }
}

// Kalibrierungsbutton: Setzt den aktuellen VOC-Wert als Baseline (Referenz fuer leeren Raum).
// Ablauf: aktuellen Sensorwert holen -> als Baseline per POST an API senden -> Sensoransicht neu laden.
document.getElementById('btnCalibBaseline').addEventListener('click', async () => {
    const statusEl = document.getElementById('calibStatus');
    const latest = await fetchApi('/api/data/latest');
    if (!latest?.success || latest.data.gas_resistance == null) {
        statusEl.textContent = 'Kein aktueller VOC-Wert verfuegbar';
        statusEl.style.color = 'var(--danger)';
        return;
    }
    const gas = latest.data.gas_resistance;
    statusEl.style.color = 'var(--text-muted)';
    statusEl.textContent = `Setze VOC-Baseline auf ${Math.round(gas).toLocaleString()} Ω ...`;
    try {
        const res = await fetch('/api/estimator/baseline', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gas_resistance: gas })
        });
        const data = await res.json();
        if (data.success) {
            statusEl.style.color = 'var(--success)';
            statusEl.textContent = `VOC-Baseline auf ${Math.round(gas).toLocaleString()} Ω gesetzt`;
            loadSensors();  // Kalibrierungsstatus in der Anzeige aktualisieren
        } else {
            statusEl.style.color = 'var(--danger)';
            statusEl.textContent = data.error || 'Fehler';
        }
    } catch (e) {
        statusEl.style.color = 'var(--danger)';
        statusEl.textContent = 'Verbindungsfehler';
    }
});

// --- History-Tab ---

async function loadTable() {
    // Paginierte Rohdaten laden und in die Tabelle rendern
    const data = await fetchApi(`/api/data/table?page=${state.page}&per_page=${state.perPage}`);
    if (!data?.success) {
        document.getElementById('tableBody').innerHTML = '<tr><td colspan="7" style="color:var(--danger)">Fehler beim Laden der Daten</td></tr>';
        return;
    }
    const tbody = document.getElementById('tableBody');
    if (!data.data.length) { tbody.innerHTML = '<tr><td colspan="7">Keine Daten</td></tr>'; return; }
    tbody.innerHTML = data.data.map(r => `<tr><td>${r.id}</td><td>${r.timestamp||'--'}</td><td>${r.temperature?.toFixed(1)??'--'}</td><td>${r.humidity?.toFixed(1)??'--'}</td><td>${r.gas_resistance?Math.round(r.gas_resistance).toLocaleString():'--'}</td><td><span class="badge ${r.movement_detected?'badge-yes':'badge-no'}">${r.movement_detected?'Ja':'Nein'}</span></td><td>${r.estimated_occupancy??'--'}</td></tr>`).join('');
    const p = data.pagination;
    document.getElementById('pageInfo').textContent = `Seite ${p.page} von ${p.pages}`;
    document.getElementById('tableInfo').textContent = `${p.total} Eintraege`;
    // Paginierungsbuttons deaktivieren wenn keine weitere Seite existiert
    document.getElementById('btnPrev').disabled = p.page <= 1;
    document.getElementById('btnNext').disabled = p.page >= p.pages;
}

// Manueller Retrain-Button: loest ein Neutrainieren des Regressionsmodells aus.
// Button wird waehrend des Trainings deaktiviert damit kein Doppelklick moeglich ist.
document.getElementById('btnRetrain').addEventListener('click', async () => {
    const statusEl = document.getElementById('retrainStatus');
    const btn = document.getElementById('btnRetrain');
    btn.disabled = true;
    statusEl.style.color = 'var(--text-muted)';
    statusEl.textContent = 'Trainiere...';
    try {
        const res = await fetch('/api/regression/train?hours=48', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            statusEl.style.color = 'var(--success)';
            statusEl.textContent = `Trainiert: R²=${data.data.r_squared?.toFixed(4)}, n=${data.data.n_samples} Punkte`;
            loadRegression();
        } else {
            statusEl.style.color = 'var(--danger)';
            statusEl.textContent = data.error || 'Fehler beim Training';
        }
    } catch (e) {
        statusEl.style.color = 'var(--danger)';
        statusEl.textContent = 'Verbindungsfehler';
    } finally {
        btn.disabled = false;
    }
});

// Initialisierung: Dashboard, Charts und Tabelle parallel laden, dann Regression und Sensoren.
// Regression und Sensoren werden nachgelagert gestartet damit das Dashboard schnell sichtbar wird.
async function init() { await Promise.all([loadDashboard(), loadDashboardCharts(), loadTable()]); loadRegression(); loadSensors(); }
init();

// Automatisches Neuladen aller Daten alle 30 Sekunden (REFRESH_INTERVAL)
setInterval(() => { loadDashboard(); loadDashboardCharts(); loadRegression(); loadSensors(); }, REFRESH_INTERVAL);