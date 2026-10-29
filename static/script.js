/* =========================================================
   LOGIKA LANDING PAGE (INDEX)
   ========================================================= */
document.addEventListener("DOMContentLoaded", () => {
    const btnMulai = document.getElementById('btnMulai');
    
    // Cek apakah kita sedang di halaman Landing Page
    if (btnMulai) {
        btnMulai.addEventListener('click', function() {
            const port = document.getElementById('selectPelabuhan').value;
            const from = document.getElementById('indexTanggalFrom').value;
            const to   = document.getElementById('indexTanggalTo').value;

            // Simpan ke localStorage agar dibaca oleh Dashboard
            localStorage.setItem('selectedPelabuhan', port);
            localStorage.setItem('filterTanggalFrom', from || '');
            localStorage.setItem('filterTanggalTo',   to   || '');
        });
    }
});


/* =========================================================
   LOGIKA DASHBOARD
   ========================================================= */
let allReviewData = [];
let currentFilteredData = [];

// Instance Chart.js
let chartDonut = null;
let chartPopularitas = null;
let chartRatingVolume = null;
let chartTrenVolume = null;
let chartTrenAspek = null;
let chartAspekStacked = null;

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

    // Render ulang Chart.js saat halaman dibuka
    if (pageId === 'popularitas') { renderChartPopularitas(); renderChartRatingVolume(); }
    if (pageId === 'tren') { renderChartTrenVolume(); renderChartTrenAspek(); }
    if (pageId === 'aspek') { renderChartAspekStacked(); }
}

/* ============ Inisialisasi Dashboard ============ */
document.addEventListener("DOMContentLoaded", () => {
    const tableBody = document.getElementById("tableBody");
    
    // Cek apakah kita sedang di halaman Dashboard (ada tabel)
    if (tableBody) {
        const savedPort = localStorage.getItem("selectedPelabuhan");
        const savedFrom = localStorage.getItem("filterTanggalFrom");
        const savedTo   = localStorage.getItem("filterTanggalTo");
        
        if (savedPort) document.getElementById("filterPelabuhan").value = savedPort;
        if (savedFrom) document.getElementById("filterTanggalFrom").value = savedFrom;
        if (savedTo)   document.getElementById("filterTanggalTo").value = savedTo;
        
        loadTableData();
    }
});

async function loadTableData() {
    try {
        const res = await fetch("/get-data");
        const result = await res.json();
        if (result.status !== "success" || !result.data) {
            allReviewData = []; applyPelabuhanFilter(); return;
        }
        allReviewData = result.data;
        applyPelabuhanFilter();
    } catch (err) { console.error("Gagal memuat data:", err); }
}

function applyFilter() { applyPelabuhanFilter(); }

function resetTanggalFilter() {
    document.getElementById("filterTanggalFrom").value = "";
    document.getElementById("filterTanggalTo").value = "";
    localStorage.removeItem("filterTanggalFrom");
    localStorage.removeItem("filterTanggalTo");
    applyPelabuhanFilter();
}

function applyPelabuhanFilter() {
    const selectedPort = document.getElementById("filterPelabuhan").value;
    const fromISO = document.getElementById("filterTanggalFrom").value || null;
    const toISO   = document.getElementById("filterTanggalTo").value || null;

    if (fromISO) localStorage.setItem("filterTanggalFrom", fromISO);
    if (toISO)   localStorage.setItem("filterTanggalTo", toISO);

    let filteredList = allReviewData;
    if (selectedPort !== "ALL") {
        const needle = selectedPort.toLowerCase();
        filteredList = filteredList.filter(row => (row.lokasi || "").toLowerCase().includes(needle) || (row.pelabuhan || "").toLowerCase().includes(needle));
    }

    if (fromISO || toISO) {
        filteredList = filteredList.filter(row => {
            const dISO = getReviewDateISO(row);
            if (!dISO) return false;
            if (fromISO && dISO < fromISO) return false;
            if (toISO   && dISO > toISO)   return false;
            return true;
        });
    }

    currentFilteredData = filteredList;
    renderFilteredData(filteredList);

    // Render Chart.js
    try { renderChartDonut(); } catch(e) { console.error("Error Donut:", e); }
    try { renderChartPopularitas(); } catch(e) { console.error("Error Popularitas:", e); }
    try { renderChartRatingVolume(); } catch(e) { console.error("Error Rating:", e); }
    try { renderChartTrenVolume(); } catch(e) { console.error("Error Tren Volume:", e); }
    try { renderChartTrenAspek(); } catch(e) { console.error("Error Tren Aspek:", e); }
    try { renderChartAspekStacked(); } catch(e) { console.error("Error Aspek Stacked:", e); }

    // Fetch 3 Gambar Python
    refreshChartsFromPython(selectedPort, fromISO, toISO);
}

/* ============ 1. RENDER CHART.JS ============ */
function renderChartDonut() {
    const pos = currentFilteredData.filter(r => getSentiment(r) === "POSITIF").length;
    const net = currentFilteredData.filter(r => getSentiment(r) === "NETRAL").length;
    const neg = currentFilteredData.filter(r => getSentiment(r) === "NEGATIF").length;

    const ctx = document.getElementById('sentimentChart');
    if (!ctx) return;
    if (chartDonut) chartDonut.destroy();
    
    chartDonut = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Positif', 'Netral', 'Negatif'],
            datasets: [{ data: [pos, net, neg], backgroundColor: ['#198754', '#ffc107', '#dc3545'] }]
        },
        options: { responsive: true, maintainAspectRatio: false, cutout: '60%', plugins: { legend: { position: 'bottom' } } }
    });
}

function renderChartPopularitas() {
    const ctx = document.getElementById('chartPopularitas');
    if (!ctx) return;
    
    const counts = {};
    currentFilteredData.forEach(r => {
        const p = getPortName(r);
        counts[p] = (counts[p] || 0) + 1;
    });
    const labels = Object.keys(counts);
    const data = Object.values(counts);

    if (chartPopularitas) chartPopularitas.destroy();
    chartPopularitas = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{ label: 'Jumlah Ulasan', data: data, backgroundColor: '#2196F3' }]
        },
        options: { responsive: true, maintainAspectRatio: false }
    });
}

function renderChartRatingVolume() {
    const ctx = document.getElementById('chartRatingVsVolume');
    if (!ctx) return;

    const agg = {};
    currentFilteredData.forEach(r => {
        const p = getPortName(r);
        const rat = parseFloat(r.rating);
        if (!isNaN(rat)) {
            if (!agg[p]) agg[p] = { sum: 0, count: 0 };
            agg[p].sum += rat; agg[p].count++;
        }
    });

    const dataPts = Object.keys(agg).map(p => ({
        x: agg[p].count, y: (agg[p].sum / agg[p].count).toFixed(1), label: p
    }));

    if (chartRatingVolume) chartRatingVolume.destroy();
    chartRatingVolume = new Chart(ctx, {
        type: 'scatter',
        data: {
            datasets: [{ label: 'Pelabuhan', data: dataPts, backgroundColor: '#0D47A1', pointRadius: 8 }]
        },
        options: { 
            responsive: true, maintainAspectRatio: false,
            scales: { x: { title: { display: true, text: 'Volume Ulasan' } }, y: { title: { display: true, text: 'Rata-rata Rating' }, min: 1, max: 5 } },
            plugins: { tooltip: { callbacks: { label: (c) => `${c.raw.label}: ${c.raw.y} ⭐ (${c.raw.x} ulasan)` } } }
        }
    });
}

function renderChartTrenVolume() {
    const ctx = document.getElementById('chartTrenVolume');
    if (!ctx) return;

    const months = {};
    currentFilteredData.forEach(r => {
        const d = getReviewDateISO(r);
        if (d) {
            const m = d.substring(0, 7); // YYYY-MM
            months[m] = (months[m] || 0) + 1;
        }
    });
    const sorted = Object.keys(months).sort();
    const data = sorted.map(m => months[m]);

    if (chartTrenVolume) chartTrenVolume.destroy();
    chartTrenVolume = new Chart(ctx, {
        type: 'line',
        data: {
            labels: sorted,
            datasets: [{ label: 'Volume Ulasan', data: data, borderColor: '#2196F3', tension: 0.4, fill: true, backgroundColor: 'rgba(33, 150, 243, 0.1)' }]
        },
        options: { responsive: true, maintainAspectRatio: false }
    });
}

function renderChartTrenAspek() {
    const ctx = document.getElementById('chartTrenAspek');
    if (!ctx) return;

    const ASPEK_UTAMA = ["Kebersihan", "Pelayanan", "Antrian & Waktu Tunggu"];
    const months = {};
    
    currentFilteredData.forEach(r => {
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
        borderColor: ['#dc3545', '#198754', '#ffc107'][i],
        tension: 0.4
    }));

    if (chartTrenAspek) chartTrenAspek.destroy();
    chartTrenAspek = new Chart(ctx, {
        type: 'line',
        data: { labels: sorted, datasets: datasets },
        options: { responsive: true, maintainAspectRatio: false }
    });
}

function renderChartAspekStacked() {
    const ctx = document.getElementById('chartAspekStacked');
    if (!ctx) return;

    const stats = {};
    for (const [aspek, kws] of Object.entries(ASPECT_KEYWORDS)) {
        stats[aspek] = { POSITIF: 0, NETRAL: 0, NEGATIF: 0 };
    }

    currentFilteredData.forEach(r => {
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
                { label: 'Positif', data: posData, backgroundColor: '#198754' },
                { label: 'Netral', data: netData, backgroundColor: '#ffc107' },
                { label: 'Negatif', data: negData, backgroundColor: '#dc3545' }
            ]
        },
        options: { responsive: true, maintainAspectRatio: false, scales: { x: { stacked: true }, y: { stacked: true } } }
    });
}

/* ============ 2. FETCH GAMBAR PYTHON ============ */
async function refreshChartsFromPython(port, from, to) {
    const params = new URLSearchParams({ port: port || "ALL", from: from || "", to: to || "" });
    const imgIds = ["imgWordcloud", "imgHeatmap", "imgConfusion"];

    imgIds.forEach(id => {
        const imgEl = document.getElementById(id);
        if (imgEl && !imgEl.src.startsWith('data:image')) imgEl.alt = "⏳ Memuat...";
    });

    try {
        const res = await fetch(`/api/charts?${params.toString()}`);
        if (!res.ok) throw new Error(`Server status ${res.status}`);
        const data = await res.json();

        if (data.status !== "success") throw new Error(data.message);

        const mapping = {
            "imgWordcloud": data.charts.wordcloud,
            "imgHeatmap":   data.charts.heatmap,
            "imgConfusion": data.charts.confusion_matrix
        };

        for (const [id, base64] of Object.entries(mapping)) {
            const imgEl = document.getElementById(id);
            if (imgEl && base64) {
                imgEl.src = base64;
                imgEl.alt = "";
            }
        }
    } catch (err) {
        console.error("Gagal memuat grafik Python:", err);
        imgIds.forEach(id => {
            const imgEl = document.getElementById(id);
            if (imgEl) imgEl.alt = "❌ Gagal memuat (Cek Console)";
        });
    }
}

/* ============ RENDER TABEL & TEKS ============ */
function renderFilteredData(dataList) {
    const tbody = document.getElementById("tableBody");
    tbody.innerHTML = "";
    
    if (!dataList || dataList.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">Tidak ada data ulasan.</td></tr>`;
        updateSummaryCounts(0, 0, 0, 0, 0);
        renderNegativeReviews([]);
        renderAspectAnalysis([]);
        return;
    }

    let countPos = 0, countNeg = 0, countNet = 0, ratingSum = 0, ratingCount = 0;

    dataList.forEach((row, index) => {
        const rawSentiment = getSentiment(row);
        let badgeClass = "bg-secondary";
        if (rawSentiment === "POSITIF") { badgeClass = "badge-positif bg-success"; countPos++; }
        else if (rawSentiment === "NEGATIF") { badgeClass = "badge-negatif bg-danger"; countNeg++; }
        else if (rawSentiment === "NETRAL") { badgeClass = "badge-netral bg-warning text-dark"; countNet++; }

        const rating = parseFloat(row.rating);
        if (!isNaN(rating)) { ratingSum += rating; ratingCount++; }

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${index + 1}</td>
            <td><span class="fw-bold">${escapeHtml(getPortName(row))}</span></td>
            <td><small class="text-muted">${escapeHtml(row.tanggal_estimasi || row.tanggal || "-")}</small></td>
            <td>${escapeHtml(row.review || row.final_text || "-")}</td>
            <td><span class="badge ${badgeClass}">${rawSentiment || "BELUM"}</span></td>
        `;
        tbody.appendChild(tr);
    });

    const avgRating = ratingCount > 0 ? (ratingSum / ratingCount).toFixed(1) : 0;
    updateSummaryCounts(dataList.length, countPos, countNeg, countNet, avgRating);
    renderNegativeReviews(dataList);
    renderAspectAnalysis(dataList);
}

function updateSummaryCounts(total, pos, neg, net, avgRating) {
    document.getElementById("kpiTotal").innerText = total;
    document.getElementById("kpiPositif").innerText = pos;
    document.getElementById("kpiNetral").innerText = net;
    document.getElementById("kpiNegatif").innerText = neg;
    if (avgRating !== undefined) document.getElementById("kpiRating").innerText = avgRating;
}

function renderNegativeReviews(dataList) {
    const el = document.getElementById("listNegatif");
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
                    <span class="fw-bold small">${port}</span>
                    <span class="badge bg-danger">${r.rating || "-"} <i class="fa-solid fa-star text-warning"></i></span>
                </div>
                <p class="text-muted mb-1 mt-1" style="font-size:13px;">${text}</p>
            </div>`;
    }).join("");
}

function renderAspectAnalysis(dataList) {
    const container = document.getElementById("aspekContent");
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
        container.innerHTML = `<div class="alert alert-success py-2"><i class="fa-solid fa-check me-1"></i> Tidak ada ulasan negatif pada filter ini.</div>`;
        return;
    }

    const byVolume = Object.entries(aspectStats).filter(([_, s]) => s.neg > 0).sort((a, b) => b[1].neg - a[1].neg);
    const byRate = Object.entries(aspectStats).filter(([_, s]) => s.total >= 3 && s.neg > 0).sort((a, b) => (b[1].neg / b[1].total) - (a[1].neg / a[1].total));
    const topPort = Object.entries(portNegatives).sort((a, b) => b[1] - a[1])[0];

    container.innerHTML = `
        <div class="alert alert-warning py-2 small fw-600 border-warning">
            <i class="fa-solid fa-triangle-exclamation me-1"></i> 
            ${totalNegatif} ulasan negatif dari ${dataList.length} total (${((totalNegatif/dataList.length)*100).toFixed(0)}%)
        </div>
        
        <div class="mb-3 mt-4">
            <strong class="d-block mb-1 text-dark" style="font-size: 14px;">• Volume Keluhan Tertinggi:</strong>
            <p class="text-muted mb-0" style="font-size: 13px;">
                ${byVolume[0] ? `<b>${byVolume[0][0]}</b> (${byVolume[0][1].neg} keluhan)` : "-"}
            </p>
        </div>
        
        <div class="mb-3">
            <strong class="d-block mb-1 text-dark" style="font-size: 14px;">• Aspek Masalah Utama:</strong>
            <p class="text-muted mb-0" style="font-size: 13px;">
                ${byRate[0] ? `<b>${byRate[0][0]}</b> (${((byRate[0][1].neg/byRate[0][1].total)*100).toFixed(0)}% negatif)` : "-"}
            </p>
        </div>

        <div class="mb-3">
            <strong class="d-block mb-1 text-dark" style="font-size: 14px;">• Pelabuhan Paling Dikeluhkan:</strong>
            <p class="text-muted mb-0" style="font-size: 13px;">
                ${topPort ? `<b>${topPort[0]}</b> (${topPort[1]} keluhan)` : "-"}
            </p>
        </div>
    `;
}

/* ============ Helpers ============ */
const ASPECT_KEYWORDS = {
    "Kebersihan": ["kotor", "jorok", "sampah", "bau", "debu", "kumuh", "kumal", "bersih", "wangi", "rapi", "higienis"],
    "Fasilitas": ["toilet", "ac", "kursi", "wifi", "ruang tunggu", "musholla", "mushola", "tempat duduk", "pendingin", "ventilasi", "lampu", "colokan", "charger", "eskalator", "lift", "kantin", "food court", "tempat makan"],
    "Pelayanan": ["pelayanan", "petugas", "staff", "staf", "ramah", "kasar", "layanan", "respon", "responsif", "sigap", "cuek", "judes", "jutek", "helpful", "informasi", "petunjuk", "arahan"],
    "Antrian & Waktu Tunggu": ["antri", "antre", "antrian", "lama", "lambat", "nunggu", "tunggu", "delay", "telat", "terlambat", "molor", "panjang", "ramai"],
    "Harga & Tiket": ["harga", "tiket", "mahal", "murah", "biaya", "bayar", "tarif", "pembayaran", "cash", "qris", "kartu"],
    "Keamanan": ["aman", "keamanan", "hilang", "copet", "curiga", "jaga", "satpam", "penjagaan", "pemeriksaan", "skrining"],
    "Akses & Parkir": ["akses", "parkir", "jalan", "transportasi", "ojek", "taksi", "grab", "gojek", "lokasi", "sulit", "macet", "jauh", "turun", "naik"],
    "Kapal & Jadwal": ["kapal", "jadwal", "keberangkatan", "kedatangan", "berangkat", "terlambat", "delay", "batal", "cancel", "reschedule", "booking"]
};

function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function getSentiment(row) { return (row.sentiment || row.sentimen || "").toString().trim().toUpperCase(); }
function getPortName(row) { return (row.lokasi || "").toString().trim() || (row.pelabuhan || "").toString().trim() || "-"; }

const BULAN_ID_JS = { januari: 1, februari: 2, maret: 3, april: 4, mei: 5, juni: 6, juli: 7, agustus: 8, september: 9, oktober: 10, november: 11, desember: 12, jan: 1, feb: 2, mar: 3, apr: 4, jun: 6, jul: 7, agu: 8, agt: 8, sep: 9, okt: 10, nov: 11, des: 12 };
function parseRelativeToDate(label, baseDate) {
    if (!label) return null;
    const base = baseDate instanceof Date && !isNaN(baseDate) ? baseDate : new Date();
    let text = String(label).toLowerCase().trim().replace(/\bdiedit\b/g, "").replace(/[()]/g, "").replace(/\s+/g, " ").trim();
    if (!text) return null;
    for (const [name, num] of Object.entries(BULAN_ID_JS)) {
        const m = text.match(new RegExp(`(\\d{1,2})\\s+${name}\\s+(\\d{4})`));
        if (m) { const d = new Date(parseInt(m[2], 10), num - 1, parseInt(m[1], 10)); if (!isNaN(d)) return d; }
    }
    if (["baru", "new", "baru saja", "barusan"].includes(text)) return new Date(base);
    if (text === "kemarin" || text === "yesterday") { const d = new Date(base); d.setDate(d.getDate() - 1); return d; }
    const enToId = { minute: "menit", minutes: "menit", hour: "jam", hours: "jam", day: "hari", days: "hari", week: "minggu", weeks: "minggu", month: "bulan", months: "bulan", year: "tahun", years: "tahun" };
    for (const [en, idw] of Object.entries(enToId)) text = text.replace(new RegExp(`\\b${en}\\b`, "g"), idw);
    text = text.replace(/\ba\b|\ban\b/g, "1").replace(/\byesterday\b/g, "kemarin").replace(/\bago\b/g, "lalu")
               .replace(/\bsehari\b/g, "1 hari").replace(/\bseminggu\b/g, "1 minggu").replace(/\bsebulan\b/g, "1 bulan").replace(/\bsetahun\b/g, "1 tahun").replace(/\bsejam\b/g, "1 jam").replace(/\bsemenit\b/g, "1 menit").replace(/\blebih dari\b/g, "").trim();
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
function toLocalISODate(d) { return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; }
function getReviewDateISO(row) {
    if (row.tanggal_estimasi) {
        const s = String(row.tanggal_estimasi).slice(0, 10);
        if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    }
    let base = new Date();
    if (row.scraped_at) { const p = new Date(String(row.scraped_at).replace(" ", "T")); if (!isNaN(p)) base = p; }
    const d = parseRelativeToDate(row.tanggal, base);
    return d ? toLocalISODate(d) : null;
}

async function predictSingleText() {
    const text = document.getElementById("inputReview").value.trim();
    const resultDiv = document.getElementById("singleResult");
    if (!text) { alert("Masukkan teks ulasan!"); return; }
    resultDiv.classList.remove("d-none");
    resultDiv.innerHTML = `<div class="spinner-border spinner-border-sm text-primary"></div> Memproses...`;
    try {
        const res = await fetch("/predict-single", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
        const data = await res.json();
        if (data.status === "success") {
            let prob = data.probabilities ? Object.entries(data.probabilities).map(([k,v]) => `${k}: ${(v*100).toFixed(1)}%`).join(" | ") : "";
            resultDiv.className = "alert alert-success mt-3 mb-0 shadow-sm";
            resultDiv.innerHTML = `<strong>Hasil:</strong> <span class="badge bg-dark fs-6">${data.prediction}</span><br><small class="text-muted mt-2 d-block">${prob}</small>`;
        } else {
            resultDiv.className = "alert alert-danger mt-3 mb-0 shadow-sm";
            resultDiv.innerHTML = data.message;
        }
    } catch (err) {
        resultDiv.className = "alert alert-danger mt-3 mb-0 shadow-sm";
        resultDiv.innerHTML = "Gagal terhubung ke server.";
    }
}