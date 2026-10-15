let sentimentChart = null;
let allReviewData = []; // Menyimpan data mentah dari server

document.addEventListener("DOMContentLoaded", () => {
    checkProcessStatus();
    loadTableData();
    setInterval(checkProcessStatus, 4000);
});

async function checkProcessStatus() {
    try {
        const res = await fetch("/status");
        const data = await res.json();

        if (data.scraping) updateStatusUI("statusScraping", "btnScrape", data.scraping);
        if (data.preprocessing) updateStatusUI("statusPreprocessing", "btnPreprocess", data.preprocessing);
        if (data.training) updateStatusUI("statusTraining", "btnTrain", data.training);
        if (data.predictBatch) updateStatusUI("statusPredictBatch", "btnPredictBatch", data.predictBatch);
    } catch (err) {
        console.error("Gagal memeriksa status:", err);
    }
}

function updateStatusUI(elementId, buttonId, statusObj) {
    const el = document.getElementById(elementId);
    const btn = document.getElementById(buttonId);

    if (!el || !btn) return;

    el.innerText = statusObj.message;
    if (statusObj.running) {
        btn.disabled = true;
        el.className = "mt-2 text-primary fw-bold small";
    } else {
        btn.disabled = false;
        el.className = statusObj.success ? "mt-2 text-success small" : "mt-2 text-muted small";
    }
}

async function triggerScrape() {
    await fetch("/run-scraper", { method: "POST" });
    checkProcessStatus();
}

async function triggerPreprocess() {
    await fetch("/run-preprocessing", { method: "POST" });
    checkProcessStatus();
}

async function triggerTrain() {
    await fetch("/train-model", { method: "POST" });
    checkProcessStatus();
}

async function triggerPredictBatch() {
    const el = document.getElementById("statusPredictBatch");
    const btn = document.getElementById("btnPredictBatch");
    
    el.innerText = "Memproses prediksi...";
    el.className = "mt-2 text-primary fw-bold small";
    btn.disabled = true;

    try {
        const res = await fetch("/run-predict-batch", { method: "POST" });
        const data = await res.json();

        if (res.ok && data.status === "success") {
            el.innerText = "Selesai!";
            el.className = "mt-2 text-success small";
            loadTableData();
        } else {
            el.innerText = "Gagal memproses";
            el.className = "mt-2 text-danger small";
        }
    } catch (err) {
        console.error("Gagal melakukan prediksi massal:", err);
        el.innerText = "Gagal terhubung server";
        el.className = "mt-2 text-danger small";
    } finally {
        btn.disabled = false;
    }
}

async function loadTableData() {
    try {
        const res = await fetch("/get-data");
        const result = await res.json();

        if (result.status !== "success" || !result.data || result.data.length === 0) {
            allReviewData = [];
            renderFilteredData([]);
            return;
        }

        allReviewData = result.data;
        applyPelabuhanFilter();

    } catch (err) {
        console.error("Gagal memuat data tabel:", err);
    }
}

function applyPelabuhanFilter() {
    const filterElem = document.getElementById("filterPelabuhan");
    const selectedPort = filterElem ? filterElem.value : "ALL";

    let filteredList = allReviewData;

    if (selectedPort !== "ALL") {
        filteredList = allReviewData.filter(row => {
            const portName = (row.pelabuhan || row.lokasi || "").toString().toLowerCase();
            return portName.includes(selectedPort.toLowerCase());
        });
    }

    renderFilteredData(filteredList);
}

function renderFilteredData(dataList) {
    const tbody = document.getElementById("tableBody");
    tbody.innerHTML = "";

    if (!dataList || dataList.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">Tidak ada data ulasan untuk pelabuhan ini.</td></tr>`;
        updateSummaryCounts(0, 0, 0, 0);
        updateChart(0, 0, 0);
        return;
    }

    let countPos = 0, countNeg = 0, countNet = 0;

    dataList.forEach((row, index) => {
        const rawSentiment = (row.sentiment || "").toString().trim().toUpperCase();
        let sentimentDisplay = rawSentiment || "BELUM DIPREDIKSI";
        let badgeClass = "bg-secondary";

        if (rawSentiment === "POSITIF") {
            badgeClass = "badge-positif bg-success";
            countPos++;
        } else if (rawSentiment === "NEGATIF") {
            badgeClass = "badge-negatif bg-danger";
            countNeg++;
        } else if (rawSentiment === "NETRAL") {
            badgeClass = "badge-netral bg-warning text-dark";
            countNet++;
        }

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${index + 1}</td>
            <td><span class="fw-bold">${row.pelabuhan || row.lokasi || "-"}</span></td>
            <td>${row.review || row.final_text || "-"}</td>
            <td><span class="badge ${badgeClass}">${sentimentDisplay}</span></td>
        `;
        tbody.appendChild(tr);
    });

    updateSummaryCounts(dataList.length, countPos, countNeg, countNet);
    updateChart(countPos, countNeg, countNet);
}

function updateSummaryCounts(total, pos, neg, net) {
    const elTotal = document.getElementById("totalReviews");
    const elPos = document.getElementById("totalPositif");
    const elNeg = document.getElementById("totalNegatif");
    const elNet = document.getElementById("totalNetral");

    if (elTotal) elTotal.innerText = total;
    if (elPos) elPos.innerText = pos;
    if (elNeg) elNeg.innerText = neg;
    if (elNet) elNet.innerText = net;
}

function updateChart(pos, neg, net) {
    const chartElem = document.getElementById("sentimentChart");
    if (!chartElem) return;

    const ctx = chartElem.getContext("2d");

    if (sentimentChart) {
        sentimentChart.destroy();
    }

    sentimentChart = new Chart(ctx, {
        type: "pie",
        data: {
            labels: ["Positif", "Negatif", "Netral"],
            datasets: [{
                data: [pos, neg, net],
                backgroundColor: ["#198754", "#dc3545", "#ffc107"]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    });
}

async function predictSingleText() {
    const textInput = document.getElementById("inputReview").value.trim();
    const resultDiv = document.getElementById("singleResult");

    if (!textInput) {
        alert("Silakan masukkan teks ulasan terlebih dahulu!");
        return;
    }

    try {
        const res = await fetch("/predict-single", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: textInput })
        });

        const data = await res.json();
        resultDiv.classList.remove("d-none");

        if (data.status === "success") {
            let probFormatted = "";
            if (data.probabilities) {
                probFormatted = Object.entries(data.probabilities)
                    .map(([key, val]) => `<b>${key}:</b> ${(val * 100).toFixed(1)}%`)
                    .join(" | ");
            }

            resultDiv.className = "alert alert-success mb-0 mt-3";
            resultDiv.innerHTML = `
                <strong>Hasil Prediksi:</strong> <span class="badge bg-dark">${data.prediction}</span><br>

            `;
        } else {
            resultDiv.className = "alert alert-danger mb-0 mt-3";
            resultDiv.innerHTML = `<strong>Error:</strong> ${data.message}`;
        }
    } catch (err) {
        console.error("Gagal memprediksi:", err);
    }
}