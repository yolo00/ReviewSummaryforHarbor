/* =========================================================
   LOGIKA LANDING PAGE (INDEX)
   ========================================================= */
document.addEventListener("DOMContentLoaded", () => {
    const btnMulai = document.getElementById('btnMulai');

    if (btnMulai) {
        btnMulai.addEventListener('click', function () {
            const port = document.getElementById('selectPelabuhan').value;
            const from = document.getElementById('indexTanggalFrom').value;
            const to   = document.getElementById('indexTanggalTo').value;

            if (from && to && from > to) {
                alert("Tanggal awal tidak boleh setelah tanggal akhir.");
                return;
            }

            // Simpan sebagai array JSON agar kompatibel dengan dashboard multi-select
            let portsArr = port === "ALL" ? ["ALL"] : [port];
            localStorage.setItem('selectedPorts', JSON.stringify(portsArr));
            localStorage.setItem('filterTanggalFrom', from || '');
            localStorage.setItem('filterTanggalTo',   to   || '');
        });
    }
});


/* =========================================================
   LOGIKA DASHBOARD
   ========================================================= */
let selectedPorts = [];
let rawReviewData = [];
let processedReviewData = [];

let chartDonut = null;
let chartPopularitas = null;
let chartRatingVolume = null;
let chartTrenVolume = null;
let chartTrenAspek = null;
let chartAspekStacked = null;

/* ============ PALET WARNA (SESUAI DESIGN SYSTEM) ============ */
const COLORS = {
    primary:   "#0D47A1",
    secondary: "#2196F3",
    accent:    "#90CAF9",
    positif:   "#00B809",
    netral:    "#FFCC00",
    negatif:   "#9D0003",
    muted:     "#525252",
    bg:        "#E3F2FD",
    card:      "#FFFFFF"
};

// Palet warna untuk grafik perbandingan pelabuhan
const PORT_COLORS = {
    "Batam Centre":   "#0D47A1",
    "Harbour Bay":    "#1565C0",
    "Telaga Punggur": "#1976D2",
    "Nongsapura":     "#42A5F5",
    "Sekupang":       "#90CAF9",
    "Default":        "#2196F3"
};

function getColorForPort(portName) {
    if (!portName) return PORT_COLORS["Default"];
    for (const key in PORT_COLORS) {
        if (portName.toLowerCase().includes(key.toLowerCase())) {
            return PORT_COLORS[key];
        }
    }
    return PORT_COLORS["Default"];
}

/* ============ SIDEBAR TOGGLE (MOBILE) ============ */
function initSidebar() {
    const sidebar  = document.getElementById('sidebar-wrapper');
    const overlay  = document.getElementById('sidebarOverlay');
    const toggle   = document.getElementById('sidebarToggle');
    const closeBtn = document.getElementById('sidebarClose');

    if (!sidebar) return;

    function openSidebar() {
        sidebar.classList.add('show');
        if (overlay) overlay.classList.add('show');
        document.body.style.overflow = 'hidden';
    }

    function closeSidebar() {
        sidebar.classList.remove('show');
        if (overlay) overlay.classList.remove('show');
        document.body.style.overflow = '';
    }

    if (toggle)   toggle.addEventListener('click', openSidebar);
    if (closeBtn) closeBtn.addEventListener('click', closeSidebar);
    if (overlay)  overlay.addEventListener('click', closeSidebar);

    // Tutup sidebar otomatis saat klik menu di mobile
    document.querySelectorAll('#sidebar-menu .list-group-item').forEach(item => {
        item.addEventListener('click', () => {
            if (window.innerWidth < 992) closeSidebar();
        });
    });

    // Tutup saat resize ke desktop
    window.addEventListener('resize', () => {
        if (window.innerWidth >= 992) closeSidebar();
    });

    // ESC untuk menutup
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeSidebar();
    });
}

document.addEventListener('DOMContentLoaded', initSidebar);

/* ============ Navigasi SPA ============ */
function switchPage(pageId, element) {
    document.querySelectorAll('.app-page').forEach(el => el.classList.add('d-none'));
    const target = document.getElementById('page-' + pageId);
    if (target) target.classList.remove('d-none');

    document.querySelectorAll('#sidebar-menu .list-group-item').forEach(el => {
        el.classList.remove('active', 'text-muted');
        el.classList.add('text-muted');
    });
    element.classList.remove('text-muted');
    element.classList.add('active');

    // Tutup sidebar di mobile setelah navigasi
    if (window.innerWidth < 992) {
        const sidebar = document.getElementById('sidebar-wrapper');
        const overlay = document.getElementById('sidebarOverlay');
        if (sidebar) sidebar.classList.remove('show');
        if (overlay) overlay.classList.remove('show');
        document.body.style.overflow = '';
    }

    if (pageId === 'popularitas') { renderChartPopularitas(); renderChartRatingVolume(); }
    if (pageId === 'tren')        { renderChartTrenVolume(); renderChartTrenAspek(); }
    if (pageId === 'aspek')       { renderChartAspekStacked(); }
    // Muat model hanya saat halaman Uji Sentimen dibuka
    if (pageId === 'uji')         { siapkanModelUji(); }
}

/* ============ Inisialisasi Dashboard ============ */
document.addEventListener("DOMContentLoaded", () => {
    const tableBody = document.getElementById("tableBody");
    const portSelect = document.getElementById("filterPelabuhanSelect");

    if (tableBody) {
        const savedPortsStr = localStorage.getItem("selectedPorts");
        const savedFrom = localStorage.getItem("filterTanggalFrom");
        const savedTo   = localStorage.getItem("filterTanggalTo");

        if (savedPortsStr) {
            try { selectedPorts = JSON.parse(savedPortsStr); }
            catch (e) { selectedPorts = []; }
        }
        if (!selectedPorts || selectedPorts.length === 0) {
            selectedPorts = ["ALL"];
        }

        if (savedFrom) document.getElementById("filterTanggalFrom").value = savedFrom;
        if (savedTo)   document.getElementById("filterTanggalTo").value   = savedTo;

        renderPortChips();
        loadAllData();

        if (portSelect) {
            portSelect.addEventListener('change', function() {
                const val = this.value;
                if (!val) return;

                if (val === "ALL") {
                    selectedPorts = ["ALL"];
                } else {
                    selectedPorts = selectedPorts.filter(p => p !== "ALL");
                    if (!selectedPorts.includes(val)) {
                        selectedPorts.push(val);
                    }
                }

                this.value = "";
                updateFilterState();
            });
        }
    }
});

/* ============ Manajemen Multi-Select ============ */
function renderPortChips() {
    const container = document.getElementById("selectedPortsContainer");
    if (!container) return;

    container.innerHTML = "";

    if (selectedPorts.length === 0 || (selectedPorts.length === 1 && selectedPorts[0] === "ALL")) {
        container.innerHTML = `<span class="badge bg-secondary opacity-75">Semua Pelabuhan (Default)</span>`;
        return;
    }

    selectedPorts.forEach(port => {
        const chip = document.createElement("div");
        chip.className = "port-chip";
        chip.innerHTML = `
            ${escapeHtml(port)}
            <span class="remove-chip" onclick="removePort('${escapeHtml(port)}')">&times;</span>
        `;
        container.appendChild(chip);
    });
}

function removePort(portToRemove) {
    selectedPorts = selectedPorts.filter(p => p !== portToRemove);
    if (selectedPorts.length === 0) selectedPorts = ["ALL"];
    updateFilterState();
}

function clearAllPorts() {
    selectedPorts = ["ALL"];
    updateFilterState();
}

function resetTanggalFilter() {
    document.getElementById("filterTanggalFrom").value = "";
    document.getElementById("filterTanggalTo").value = "";
    updateFilterState();
}

function updateFilterState() {
    const fromISO = document.getElementById("filterTanggalFrom").value || null;
    const toISO   = document.getElementById("filterTanggalTo").value || null;

    if (fromISO && toISO && fromISO > toISO) {
        alert("Tanggal awal tidak boleh setelah tanggal akhir.");
        return;
    }

    localStorage.setItem("selectedPorts", JSON.stringify(selectedPorts));
    localStorage.setItem("filterTanggalFrom", fromISO || "");
    localStorage.setItem("filterTanggalTo",   toISO   || "");

    renderPortChips();
    loadAllData();
}

/* ============ Pemanggilan Data ============ */
async function loadAllData() {
    try {
        const portsParam = selectedPorts.includes("ALL") ? "" : selectedPorts.join(",");
        const fromParam = document.getElementById("filterTanggalFrom").value || "";
        const toParam = document.getElementById("filterTanggalTo").value || "";

        const qs = `?ports=${encodeURIComponent(portsParam)}&from=${fromParam}&to=${toParam}`;

        // Fetch RAW Data (Untuk Rating & Volume)
        const resRaw = await fetch(`/get-data${qs}&source=raw`);
        const resultRaw = await resRaw.json();

        // Fetch PROCESSED Data (Untuk Sentimen & NLP)
        const resProc = await fetch(`/get-data${qs}&source=processed`);
        const resultProc = await resProc.json();

        if (resultRaw.status === "success" && resultRaw.raw) {
            rawReviewData = resultRaw.raw;
        } else {
            console.warn("Gagal memuat data raw:", resultRaw.raw_error);
            rawReviewData = [];
        }

        if (resultProc.status === "success" && resultProc.processed) {
            processedReviewData = resultProc.processed;
            if (resultProc.warning) console.warn(resultProc.warning);
        } else {
            console.warn("Gagal memuat data processed:", resultProc.processed_error);
            processedReviewData = [];
        }

        applyFiltersToData();
    } catch (err) {
        console.error("Gagal memuat keseluruhan data:", err);
    }
}

function applyFiltersToData() {
    renderFilteredData(processedReviewData, rawReviewData);

    try { renderChartDonut(); } catch (e) { console.error("Error Donut:", e); }
    try { renderChartPopularitas(); } catch (e) { console.error("Error Popularitas:", e); }
    try { renderChartRatingVolume(); } catch (e) { console.error("Error Rating:", e); }
    try { renderChartTrenVolume(); } catch (e) { console.error("Error Tren Volume:", e); }
    try { renderChartTrenAspek(); } catch (e) { console.error("Error Tren Aspek:", e); }
    try { renderChartAspekStacked(); } catch (e) { console.error("Error Aspek Stacked:", e); }

    const portsParam = selectedPorts.includes("ALL") ? "" : selectedPorts.join(",");
    const fromParam = document.getElementById("filterTanggalFrom").value || "";
    const toParam = document.getElementById("filterTanggalTo").value || "";
    refreshChartsFromPython(portsParam, fromParam, toParam);
}

/* ============ 1. RENDER CHART.JS ============ */
function renderChartDonut() {
    const dataToUse = processedReviewData;
    const pos = dataToUse.filter(r => getSentiment(r) === "POSITIF").length;
    const net = dataToUse.filter(r => getSentiment(r) === "NETRAL").length;
    const neg = dataToUse.filter(r => getSentiment(r) === "NEGATIF").length;

    const ctx = document.getElementById('sentimentChart');
    if (!ctx) return;
    if (chartDonut) chartDonut.destroy();

    chartDonut = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Positif', 'Netral', 'Negatif'],
            datasets: [{
                data: [pos, net, neg],
                backgroundColor: [COLORS.positif, COLORS.netral, COLORS.negatif],
                borderColor: '#ffffff',
                borderWidth: 3,
                hoverOffset: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '62%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        padding: 18,
                        font: { family: 'Inter', size: 13, weight: '600' },
                        usePointStyle: true,
                        pointStyle: 'circle'
                    }
                },
                tooltip: {
                    backgroundColor: COLORS.primary,
                    titleFont: { family: 'Inter', size: 13, weight: '700' },
                    bodyFont:  { family: 'Inter', size: 12 },
                    padding: 12,
                    cornerRadius: 8
                }
            }
        }
    });
}

function renderChartPopularitas() {
    const ctx = document.getElementById('chartPopularitas');
    if (!ctx) return;

    const dataToUse = rawReviewData;
    const counts = {};
    dataToUse.forEach(r => {
        const p = getPortName(r);
        counts[p] = (counts[p] || 0) + 1;
    });

    const labels = Object.keys(counts);
    const data = Object.values(counts);
    const bgColors = labels.map(label => getColorForPort(label));

    if (chartPopularitas) chartPopularitas.destroy();
    chartPopularitas = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Jumlah Ulasan (Total)',
                data: data,
                backgroundColor: bgColors,
                borderRadius: 8,
                borderSkipped: false,
                maxBarThickness: 60
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: COLORS.primary,
                    padding: 12,
                    cornerRadius: 8,
                    titleFont: { family: 'Inter', weight: '700' },
                    bodyFont:  { family: 'Inter' }
                }
            },
            scales: {
                x: {
                    ticks: { font: { family: 'Inter', size: 12 } },
                    grid: { display: false }
                },
                y: {
                    beginAtZero: true,
                    ticks: { font: { family: 'Inter', size: 12 }, precision: 0 },
                    grid: { color: 'rgba(13, 71, 161, 0.08)' }
                }
            }
        }
    });
}

function renderChartRatingVolume() {
    const ctx = document.getElementById('chartRatingVsVolume');
    if (!ctx) return;

    const dataToUse = rawReviewData;
    const agg = {};
    dataToUse.forEach(r => {
        const p = getPortName(r);
        const rat = parseFloat(r.rating);
        if (!isNaN(rat)) {
            if (!agg[p]) agg[p] = { sum: 0, count: 0 };
            agg[p].sum += rat; agg[p].count++;
        }
    });

    const datasets = Object.keys(agg).map(p => ({
        label: p,
        data: [{ x: agg[p].count, y: parseFloat((agg[p].sum / agg[p].count).toFixed(1)) }],
        backgroundColor: getColorForPort(p),
        pointRadius: 9,
        pointHoverRadius: 13,
        pointBorderColor: '#ffffff',
        pointBorderWidth: 2
    }));

    if (chartRatingVolume) chartRatingVolume.destroy();
    chartRatingVolume = new Chart(ctx, {
        type: 'scatter',
        data: { datasets: datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Volume Ulasan',
                        font: { family: 'Inter', weight: '700', size: 12 },
                        color: COLORS.muted
                    },
                    grid: { color: 'rgba(13, 71, 161, 0.08)' },
                    ticks: { font: { family: 'Inter', size: 11 } }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Rata-rata Rating',
                        font: { family: 'Inter', weight: '700', size: 12 },
                        color: COLORS.muted
                    },
                    min: 1, max: 5,
                    grid: { color: 'rgba(13, 71, 161, 0.08)' },
                    ticks: { font: { family: 'Inter', size: 11 }, stepSize: 1 }
                }
            },
            plugins: {
                legend: {
                    labels: {
                        font: { family: 'Inter', size: 12, weight: '600' },
                        usePointStyle: true,
                        pointStyle: 'circle',
                        padding: 14
                    }
                },
                tooltip: {
                    backgroundColor: COLORS.primary,
                    padding: 12,
                    cornerRadius: 8,
                    titleFont: { family: 'Inter', weight: '700' },
                    bodyFont:  { family: 'Inter' },
                    callbacks: {
                        label: (c) => `${c.dataset.label}: ${c.raw.y} ⭐ (${c.raw.x} ulasan)`
                    }
                }
            }
        }
    });
}

function renderChartTrenVolume() {
    const ctx = document.getElementById('chartTrenVolume');
    if (!ctx) return;

    const dataToUse = rawReviewData;
    const months = {};
    const portsFound = new Set();

    dataToUse.forEach(r => {
        const d = getReviewDateISO(r);
        const p = getPortName(r);
        if (d && p) {
            const m = d.substring(0, 7);
            if (!months[m]) months[m] = {};
            months[m][p] = (months[m][p] || 0) + 1;
            portsFound.add(p);
        }
    });

    const sortedMonths = Object.keys(months).sort();

    const datasets = Array.from(portsFound).map(portName => {
        const color = getColorForPort(portName);
        const portData = sortedMonths.map(m => (months[m][portName] || 0));
        return {
            label: portName,
            data: portData,
            borderColor: color,
            backgroundColor: color + '22',
            tension: 0.4,
            borderWidth: 3,
            pointRadius: 4,
            pointHoverRadius: 7,
            pointBackgroundColor: color,
            pointBorderColor: '#fff',
            pointBorderWidth: 2,
            fill: portsFound.size === 1
        };
    });

    if (chartTrenVolume) chartTrenVolume.destroy();
    chartTrenVolume = new Chart(ctx, {
        type: 'line',
        data: { labels: sortedMonths, datasets: datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        font: { family: 'Inter', size: 12, weight: '600' },
                        usePointStyle: true,
                        pointStyle: 'circle',
                        padding: 14
                    }
                },
                tooltip: {
                    backgroundColor: COLORS.primary,
                    padding: 12,
                    cornerRadius: 8,
                    titleFont: { family: 'Inter', weight: '700' },
                    bodyFont:  { family: 'Inter' }
                }
            },
            scales: {
                x: {
                    ticks: { font: { family: 'Inter', size: 11 } },
                    grid: { display: false }
                },
                y: {
                    beginAtZero: true,
                    ticks: { font: { family: 'Inter', size: 11 }, precision: 0 },
                    grid: { color: 'rgba(13, 71, 161, 0.08)' }
                }
            }
        }
    });
}

function renderChartTrenAspek() {
    const ctx = document.getElementById('chartTrenAspek');
    if (!ctx) return;

    const ASPEK_UTAMA = ["Kebersihan", "Pelayanan", "Antrian & Waktu Tunggu"];
    const colors = [COLORS.primary, COLORS.positif, COLORS.netral];
    const months = {};
    const dataToUse = processedReviewData;

    dataToUse.forEach(r => {
        const d = getReviewDateISO(r);
        if (!d) return;
        const m = d.substring(0, 7);

        if (!months[m]) {
            months[m] = {};
            ASPEK_UTAMA.forEach(a => months[m][a] = 0);
        }

        const text = (r.review || r.final_text || "").toLowerCase();
        ASPEK_UTAMA.forEach(a => {
            if (ASPECT_KEYWORDS[a] && ASPECT_KEYWORDS[a].some(kw => text.includes(kw))) {
                months[m][a]++;
            }
        });
    });

    const sorted = Object.keys(months).sort();
    const datasets = ASPEK_UTAMA.map((a, i) => ({
        label: a,
        data: sorted.map(m => months[m][a]),
        borderColor: colors[i],
        backgroundColor: colors[i] + '22',
        tension: 0.4,
        borderWidth: 3,
        pointRadius: 4,
        pointHoverRadius: 7,
        pointBackgroundColor: colors[i],
        pointBorderColor: '#fff',
        pointBorderWidth: 2,
        fill: false
    }));

    if (chartTrenAspek) chartTrenAspek.destroy();
    chartTrenAspek = new Chart(ctx, {
        type: 'line',
        data: { labels: sorted, datasets: datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        font: { family: 'Inter', size: 12, weight: '600' },
                        usePointStyle: true,
                        pointStyle: 'circle',
                        padding: 14
                    }
                },
                tooltip: {
                    backgroundColor: COLORS.primary,
                    padding: 12,
                    cornerRadius: 8,
                    titleFont: { family: 'Inter', weight: '700' },
                    bodyFont:  { family: 'Inter' }
                }
            },
            scales: {
                x: {
                    ticks: { font: { family: 'Inter', size: 11 } },
                    grid: { display: false }
                },
                y: {
                    beginAtZero: true,
                    ticks: { font: { family: 'Inter', size: 11 }, precision: 0 },
                    grid: { color: 'rgba(13, 71, 161, 0.08)' }
                }
            }
        }
    });
}

function renderChartAspekStacked() {
    const ctx = document.getElementById('chartAspekStacked');
    if (!ctx) return;

    const dataToUse = processedReviewData;
    const stats = {};
    for (const [aspek] of Object.entries(ASPECT_KEYWORDS)) {
        stats[aspek] = { POSITIF: 0, NETRAL: 0, NEGATIF: 0 };
    }

    dataToUse.forEach(r => {
        const text = (r.review || r.final_text || "").toLowerCase();
        const sent = getSentiment(r);
        for (const [aspek, kws] of Object.entries(ASPECT_KEYWORDS)) {
            if (kws.some(kw => text.includes(kw)) && stats[aspek][sent] !== undefined) {
                stats[aspek][sent]++;
            }
        }
    });

    const labels = Object.keys(stats).filter(a => (stats[a].POSITIF + stats[a].NETRAL + stats[a].NEGATIF) > 0);
    const posData = labels.map(a => stats[a].POSITIF);
    const netData = labels.map(a => stats[a].NETRAL);
    const negData = labels.map(a => stats[a].NEGATIF);

    if (chartAspekStacked) chartAspekStacked.destroy();
    chartAspekStacked = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                { label: 'Positif', data: posData, backgroundColor: COLORS.positif, borderRadius: 4 },
                { label: 'Netral',  data: netData, backgroundColor: COLORS.netral,  borderRadius: 4 },
                { label: 'Negatif', data: negData, backgroundColor: COLORS.negatif, borderRadius: 4 }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    stacked: true,
                    ticks: { font: { family: 'Inter', size: 11 }, maxRotation: 45, minRotation: 0 },
                    grid: { display: false }
                },
                y: {
                    stacked: true,
                    beginAtZero: true,
                    ticks: { font: { family: 'Inter', size: 11 }, precision: 0 },
                    grid: { color: 'rgba(13, 71, 161, 0.08)' }
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        font: { family: 'Inter', size: 12, weight: '600' },
                        usePointStyle: true,
                        pointStyle: 'rectRounded',
                        padding: 14
                    }
                },
                tooltip: {
                    backgroundColor: COLORS.primary,
                    padding: 12,
                    cornerRadius: 8,
                    titleFont: { family: 'Inter', weight: '700' },
                    bodyFont:  { family: 'Inter' }
                }
            }
        }
    });
}

/* ============ 2. FETCH GAMBAR PYTHON ============ */
let chartRequestSeq = 0;

async function refreshChartsFromPython(port, from, to) {
    const mySeq = ++chartRequestSeq;
    const params = new URLSearchParams({
        port: port || "ALL",
        from: from || "",
        to:   to   || ""
    });
    const imgIds = ["imgWordcloud", "imgHeatmap", "imgConfusion"];

    imgIds.forEach(id => {
        const imgEl = document.getElementById(id);
        if (imgEl && !imgEl.src.startsWith('data:image')) imgEl.alt = "⏳ Memuat...";
    });

    try {
        const res = await fetch(`/api/charts?${params.toString()}`);
        if (mySeq !== chartRequestSeq) return;
        const data = await res.json();
        if (mySeq !== chartRequestSeq) return;

        if (!res.ok || data.status !== "success") {
            throw new Error(data.message || `Server status ${res.status}`);
        }

        const mapping = {
            "imgWordcloud": data.charts && data.charts.wordcloud,
            "imgHeatmap":   data.charts && data.charts.heatmap,
            "imgConfusion": data.charts && data.charts.confusion_matrix
        };

        for (const [id, base64] of Object.entries(mapping)) {
            const imgEl = document.getElementById(id);
            if (imgEl && base64) {
                imgEl.src = base64;
                imgEl.alt = "";
                imgEl.style.display = ""; // pastikan tampil kembali
                const fallback = document.getElementById(id + 'Fallback');
                if (fallback) fallback.style.display = 'none';
            }
        }
    } catch (err) {
        if (mySeq !== chartRequestSeq) return;
        console.error("Gagal memuat grafik Python:", err);
        imgIds.forEach(id => {
            const imgEl = document.getElementById(id);
            if (imgEl) imgEl.alt = "❌ Gagal memuat (Cek Console)";
        });
    }
}

/* ============ RENDER TABEL & TEKS ============ */
function renderFilteredData(processedList, rawList) {
    const tbody = document.getElementById("tableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!processedList || processedList.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">Tidak ada data teks untuk ditampilkan.</td></tr>`;
        updateSummaryCounts(0, 0, 0, 0, 0);
        renderNegativeReviews([]);
        renderAspectAnalysis([]);
        return;
    }

    let countPos = 0, countNeg = 0, countNet = 0;

    processedList.forEach((row, index) => {
        const rawSentiment = getSentiment(row);
        let badgeClass = "bg-secondary";
        if (rawSentiment === "POSITIF") { badgeClass = "badge-positif"; countPos++; }
        else if (rawSentiment === "NEGATIF") { badgeClass = "badge-negatif"; countNeg++; }
        else if (rawSentiment === "NETRAL") { badgeClass = "badge-netral"; countNet++; }

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${index + 1}</td>
            <td><span class="fw-bold" style="color: var(--primary);">${escapeHtml(getPortName(row))}</span></td>
            <td><small class="text-muted">${escapeHtml(row.tanggal_estimasi || row.tanggal || "-")}</small></td>
            <td>${escapeHtml(row.review || row.final_text || "-")}</td>
            <td><span class="badge ${badgeClass}">${rawSentiment || "BELUM"}</span></td>
        `;
        tbody.appendChild(tr);
    });

    let ratingSum = 0, ratingCount = 0;
    const totalRaw = rawList.length;

    rawList.forEach(row => {
        const rating = parseFloat(row.rating);
        if (!isNaN(rating)) {
            ratingSum += rating;
            ratingCount++;
        }
    });

    const avgRating = ratingCount > 0 ? (ratingSum / ratingCount).toFixed(1) : 0;

    updateSummaryCounts(totalRaw, countPos, countNeg, countNet, avgRating);
    renderNegativeReviews(processedList);
    renderAspectAnalysis(processedList);
}

function updateSummaryCounts(total, pos, neg, net, avgRating) {
    const setText = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.innerText = val;
    };
    setText("kpiTotal", total);
    setText("kpiPositif", pos);
    setText("kpiNetral", net);
    setText("kpiNegatif", neg);
    if (avgRating !== undefined) setText("kpiRating", avgRating);
}

function renderNegativeReviews(dataList) {
    const el = document.getElementById("listNegatif");
    if (!el) return;
    const negatives = (dataList || []).filter(r => getSentiment(r) === "NEGATIF").slice(0, 10);
    if (!negatives.length) {
        el.innerHTML = '<p class="text-muted small mb-0">Tidak ada ulasan negatif.</p>';
        return;
    }
    el.innerHTML = negatives.map(r => {
        const port = escapeHtml(getPortName(r));
        const text = escapeHtml(r.review || r.final_text || "-");
        return `
            <div class="border-bottom pb-2 mb-2">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <span class="fw-bold small" style="color: var(--primary);">${port}</span>
                    <span class="rating-badge">${escapeHtml(r.rating || "-")} <i class="fa-solid fa-star"></i></span>
                </div>
                <p class="text-muted mb-1 mt-1" style="font-size:13px;">${text}</p>
            </div>`;
    }).join("");
}

function renderAspectAnalysis(dataList) {
    const container = document.getElementById("aspekContent");
    if (!container) return;
    if (!dataList || dataList.length === 0) {
        container.innerHTML = '<p class="text-muted small mb-0">Tidak ada data.</p>';
        return;
    }

    const aspectStats = {}, portNegatives = {};
    let totalNegatif = 0;

    dataList.forEach(row => {
        const sentiment = getSentiment(row);
        const text = (row.review || row.final_text || "").toLowerCase();
        const port = getPortName(row);

        if (sentiment === "NEGATIF") { totalNegatif++; portNegatives[port] = (portNegatives[port] || 0) + 1; }

        for (const [aspect, keywords] of Object.entries(ASPECT_KEYWORDS)) {
            if (keywords.some(kw => text.includes(kw))) {
                if (!aspectStats[aspect]) aspectStats[aspect] = { pos: 0, neg: 0, total: 0 };
                const a = aspectStats[aspect]; a.total++;
                if (sentiment === "POSITIF") a.pos++;
                else if (sentiment === "NEGATIF") a.neg++;
            }
        }
    });

    if (totalNegatif === 0) {
        container.innerHTML = `<div class="alert alert-success py-2 mb-0" style="background-color: rgba(0,184,9,0.1); border: 1px solid var(--positif); color: var(--positif);">
            <i class="fa-solid fa-check me-1"></i> Tidak ada ulasan negatif pada filter ini.
        </div>`;
        return;
    }

    const byVolume = Object.entries(aspectStats).filter(([_, s]) => s.neg > 0).sort((a, b) => b[1].neg - a[1].neg);
    const byRate   = Object.entries(aspectStats).filter(([_, s]) => s.total >= 3 && s.neg > 0).sort((a, b) => (b[1].neg / b[1].total) - (a[1].neg / a[1].total));
    const topPort  = Object.entries(portNegatives).sort((a, b) => b[1] - a[1])[0];

    container.innerHTML = `
        <div class="alert py-2 small fw-600 mb-3"
             style="background-color: rgba(157,0,3,0.08); border: 1px solid rgba(157,0,3,0.3); color: var(--negatif);">
            <i class="fa-solid fa-triangle-exclamation me-1"></i>
            ${totalNegatif} ulasan negatif dari ${dataList.length} total
            (${((totalNegatif / dataList.length) * 100).toFixed(0)}%)
        </div>
        <div class="mb-3 mt-4">
            <strong class="d-block mb-1" style="font-size: 14px; color: var(--primary);">• Volume Keluhan Tertinggi:</strong>
            <p class="text-muted mb-0" style="font-size: 13px;">
                ${byVolume[0] ? `<b>${escapeHtml(byVolume[0][0])}</b> (${byVolume[0][1].neg} keluhan)` : "-"}
            </p>
        </div>
        <div class="mb-3">
            <strong class="d-block mb-1" style="font-size: 14px; color: var(--primary);">• Aspek dengan Proporsi Sentimen Negatif Tertinggi:</strong>
            <p class="text-muted mb-0" style="font-size: 13px;">
                ${byRate[0] ? `<b>${escapeHtml(byRate[0][0])}</b> (${((byRate[0][1].neg / byRate[0][1].total) * 100).toFixed(0)}% negatif, minimal 3 ulasan)` : "-"}
            </p>
        </div>
        <div class="mb-3">
            <strong class="d-block mb-1" style="font-size: 14px; color: var(--primary);">• Pelabuhan Paling Dikeluhkan:</strong>
            <p class="text-muted mb-0" style="font-size: 13px;">
                ${topPort ? `<b>${escapeHtml(topPort[0])}</b> (${topPort[1]} keluhan)` : "-"}
            </p>
        </div>
    `;
}

/* ============ Helpers ============ */
const ASPECT_KEYWORDS = {
    "Kebersihan": ["kotor", "jorok", "sampah", "bau", "debu", "kumuh", "kumal", "bersih", "wangi", "rapi", "higienis"],
    "Fasilitas": ["toilet", "ac", "kursi", "wifi", "ruang tunggu", "musholla", "mushola", "tempat duduk", "dingin", "ventilasi", "lampu", "colok", "charger", "eskalator", "lift", "kantin", "food court", "tempat makan"],
    "Pelayanan": ["layan", "tugas", "staff", "staf", "ramah", "kasar", "respon", "responsif", "sigap", "cuek", "judes", "jutek", "helpful", "informasi", "tunjuk", "arah"],
    "Antrian & Waktu Tunggu": ["antri", "antre", "lama", "lambat", "nunggu", "tunggu", "delay", "telat", "molor", "panjang", "ramai"],
    "Harga & Tiket": ["harga", "tiket", "mahal", "murah", "biaya", "bayar", "tarif", "cash", "qris", "kartu"],
    "Keamanan": ["aman", "hilang", "copet", "curiga", "jaga", "satpam", "periksa", "skrining"],
    "Akses & Parkir": ["akses", "parkir", "jalan", "transportasi", "ojek", "taksi", "grab", "gojek", "lokasi", "sulit", "macet", "jauh", "turun", "naik"],
    "Kapal & Jadwal": ["kapal", "jadwal", "berangkat", "datang", "batal", "cancel", "reschedule", "booking"]
};

function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function getSentiment(row) { return (row.sentiment || row.sentimen || "").toString().trim().toUpperCase(); }
function getPortName(row)  { return (row.lokasi || "").toString().trim() || (row.pelabuhan || "").toString().trim() || "-"; }

const BULAN_ID_JS = {
    januari: 1, februari: 2, maret: 3, april: 4, mei: 5, juni: 6,
    juli: 7, agustus: 8, september: 9, oktober: 10, november: 11, desember: 12,
    jan: 1, feb: 2, mar: 3, apr: 4, jun: 6, jul: 7, agu: 8, agt: 8,
    sep: 9, okt: 10, nov: 11, des: 12
};

function parseRelativeToDate(label, baseDate) {
    if (!label) return null;
    const base = baseDate instanceof Date && !isNaN(baseDate) ? baseDate : new Date();
    let text = String(label).toLowerCase().trim().replace(/\bdiedit\b/g, "").replace(/[()]/g, "").replace(/\s+/g, " ").trim();
    if (!text) return null;

    for (const [name, num] of Object.entries(BULAN_ID_JS)) {
        const m = text.match(new RegExp(`(\\d{1,2})\\s+${name}\\s+(\\d{4})`));
        if (m) return new Date(parseInt(m[2], 10), num - 1, parseInt(m[1], 10));
    }

    if (["baru", "new", "baru saja", "barusan"].includes(text)) return new Date(base);
    if (text === "kemarin" || text === "yesterday") { const d = new Date(base); d.setDate(d.getDate() - 1); return d; }

    const enToId = { minute: "menit", minutes: "menit", hour: "jam", hours: "jam", day: "hari", days: "hari", week: "minggu", weeks: "minggu", month: "bulan", months: "bulan", year: "tahun", years: "tahun" };
    for (const [en, idw] of Object.entries(enToId)) text = text.replace(new RegExp(`\\b${en}\\b`, "g"), idw);

    text = text.replace(/\ba\b|\ban\b/g, "1").replace(/\byesterday\b/g, "kemarin").replace(/\bago\b/g, "lalu")
               .replace(/\bsehari\b/g, "1 hari").replace(/\bseminggu\b/g, "1 minggu")
               .replace(/\bsebulan\b/g, "1 bulan").replace(/\bsetahun\b/g, "1 tahun")
               .replace(/\bsejam\b/g, "1 jam").replace(/\bsemenit\b/g, "1 menit")
               .replace(/\blebih dari\b/g, "").trim();

    const m = text.match(/(\d+)\s*(menit|jam|hari|minggu|bulan|tahun)/);
    if (!m) return null;
    const n = parseInt(m[1], 10), unit = m[2], d = new Date(base);
    if (unit === "menit") d.setMinutes(d.getMinutes() - n);
    else if (unit === "jam") d.setHours(d.getHours() - n);
    else if (unit === "hari") d.setDate(d.getDate() - n);
    else if (unit === "minggu") d.setDate(d.getDate() - n * 7);
    else if (unit === "bulan") d.setDate(d.getDate() - n * 30);
    else if (unit === "tahun") d.setDate(d.getDate() - n * 365);
    return d;
}

function toLocalISODate(d) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function getReviewDateISO(row) {
    if (row.tanggal_estimasi) {
        const s = String(row.tanggal_estimasi).slice(0, 10);
        if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    }
    let base = new Date();
    if (row.scraped_at) {
        const p = new Date(String(row.scraped_at).replace(" ", "T"));
        if (!isNaN(p)) base = p;
    }
    const d = parseRelativeToDate(row.tanggal, base);
    return d ? toLocalISODate(d) : null;
}

/* ============ Uji Sentimen ============ */
const MIN_KATA_UJI = 6;
let modelUjiSiap = false;
let modelUjiPromise = null;

function hitungKata(text) {
    const m = text.match(/\p{L}+/gu);
    return m ? m.length : 0;
}

// Minta server memuat model sekali; tombol Uji dinonaktifkan selama memuat.
function siapkanModelUji() {
    if (modelUjiSiap) return Promise.resolve(true);
    if (modelUjiPromise) return modelUjiPromise;
    const btn    = document.getElementById("btnUji");
    const status = document.getElementById("statusModelUji");
    if (btn) btn.disabled = true;
    if (status) {
        status.className = "small text-muted mb-3";
        status.innerHTML = '<div class="spinner-border spinner-border-sm me-2" style="color: var(--primary);"></div>Memuat model...';
    }
    modelUjiPromise = fetch("/load-model", { method: "POST" })
        .then(res => res.json())
        .then(data => {
            if (data.status !== "success") throw new Error(data.message || "Model gagal dimuat.");
            modelUjiSiap = true;
            if (status) status.innerHTML = "";
            return true;
        })
        .catch(err => {
            modelUjiPromise = null;  // izinkan coba lagi
            if (status) {
                status.className = "small text-danger mb-3";
                status.textContent = "Model belum dapat dimuat: " + err.message;
            }
            return false;
        })
        .finally(() => { if (btn) btn.disabled = false; });
    return modelUjiPromise;
}

async function predictSingleText() {
    const inputEl   = document.getElementById("inputReview");
    const resultDiv = document.getElementById("singleResult");

    if (!inputEl || !resultDiv) return;

    const tampilkanError = (pesan) => {
        resultDiv.classList.remove("d-none");
        resultDiv.removeAttribute("style");
        resultDiv.className = "alert alert-danger mt-3 mb-0 shadow-sm";
        resultDiv.textContent = pesan;
    };

    const text = (inputEl.value || "").trim();
    if (!text) {
        tampilkanError("Teks ulasan tidak boleh kosong.");
        return;
    }
    const jumlahKata = hitungKata(text);
    if (jumlahKata < MIN_KATA_UJI) {
        tampilkanError(`Teks terlalu pendek: baru ${jumlahKata} kata. Tulis minimal ${MIN_KATA_UJI} kata agar model dapat menganalisis.`);
        return;
    }

    resultDiv.classList.remove("d-none");
    resultDiv.removeAttribute("style");
    resultDiv.className = "alert alert-secondary mt-3 mb-0 shadow-sm";
    resultDiv.innerHTML = '<div class="spinner-border spinner-border-sm me-2" style="color: var(--primary);"></div> Memproses...';

    if (!(await siapkanModelUji())) {
        tampilkanError("Model belum dapat dimuat. Pastikan model sudah dilatih, lalu coba lagi.");
        return;
    }

    try {
        const res = await fetch("/predict-single", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text })
        });
        const data = await res.json();

        if (res.ok && data.status === "success" && data.prediction) {
            const pred = String(data.prediction).toUpperCase();
            const colorMap = {
                "POSITIF": COLORS.positif,
                "NEGATIF": COLORS.negatif,
                "NETRAL":  COLORS.netral
            };
            const bgMap = {
                "POSITIF": "rgba(0,184,9,0.10)",
                "NEGATIF": "rgba(157,0,3,0.08)",
                "NETRAL":  "rgba(255,204,0,0.15)"
            };
            const color = colorMap[pred] || COLORS.primary;
            const bg    = bgMap[pred]   || "rgba(13,71,161,0.08)";

            const prob = data.probabilities
                ? Object.entries(data.probabilities).map(([k, v]) => `${k}: ${(Number(v) * 100).toFixed(1)}%`).join(" | ")
                : "";

            resultDiv.className = "alert mt-3 mb-0 shadow-sm";
            resultDiv.style.backgroundColor = bg;
            resultDiv.style.border = `1px solid ${color}`;
            resultDiv.style.color = color;
            resultDiv.innerHTML = `<strong>Hasil:</strong> <span class="badge fs-6" style="background-color:${color}; color:#fff;">${escapeHtml(pred)}</span>` +
                (prob ? `<br><small class="mt-2 d-block" style="color: var(--muted);">${escapeHtml(prob)}</small>` : "");
        } else {
            resultDiv.className = "alert alert-danger mt-3 mb-0 shadow-sm";
            resultDiv.textContent = data.message || "Terjadi kesalahan pada server.";
        }
    } catch (err) {
        resultDiv.className = "alert alert-danger mt-3 mb-0 shadow-sm";
        resultDiv.textContent = "Gagal terhubung ke server.";
        console.error(err);
    }
}