"""Semua fungsi visualisasi menggunakan Matplotlib, Seaborn, dan WordCloud.

Catatan metodologis penting:
- Semua visualisasi aspek memakai `final_text` (sudah melalui cleaning,
  slang normalization, stopword removal, dan stemming Sastrawi).
- Sentimen per aspek pada `chart_aspek_stacked()` memakai LABEL SENTIMEN
  KESELURUHAN ULASAN, bukan sentimen khusus aspek (bukan ABSA). Judul grafik
  menegaskan hal ini.
- Keyword aspek HARUS diverifikasi dengan `validate_keywords.py` terhadap
  hasil Sastrawi aktual. Jangan meng-hardcode bentuk stemmed berdasarkan
  perkiraan.
"""
import io
import base64
import os
import json
import re

import matplotlib
matplotlib.use("Agg")  # WAJIB: backend non-interaktif untuk Flask
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from wordcloud import WordCloud
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle

# Gaya konsisten
sns.set_style("whitegrid")
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.titlesize"] = 12
plt.rcParams["axes.titleweight"] = "bold"

COLORS = {
    "positif": "#198756",
    "netral":  "#ffc107",
    "negatif": "#dc3545",
    "primary": "#0D47A1",
    "secondary": "#2196F3",
}

# ---------------------------------------------------------------------------
# [FIX] ASPECT_KEYWORDS berisi bentuk kata yang masuk akal muncul di
# `final_text` (sudah di-stem). Tapi JANGAN menganggap daftar ini final:
# verifikasi dulu dengan `validate_keywords.py`. Keyword yang sering muncul
# di bentuk berbeda setelah stemming harus diperbarui manual berdasarkan
# hasil audit, bukan berdasarkan tebakan.
# ---------------------------------------------------------------------------
ASPECT_KEYWORDS = {
    "Kebersihan": [
        "kotor", "jorok", "sampah", "bau", "debu", "kumuh", "kumal",
        "bersih", "wangi", "rapi", "higienis",
    ],
    "Fasilitas": [
        "toilet", "wc", "ac", "kursi", "wifi", "ruang tunggu", "musholla",
        "mushola", "surau", "tempat duduk", "pendingin", "ventilasi",
        "lampu", "colokan", "charger", "eskalator", "lift", "kantin",
    ],
    "Pelayanan": [
        "pelayanan", "layan", "petugas", "staff", "staf",
        "ramah", "kasar", "layanan", "respon", "responsif", "sigap",
        "cuek", "judes", "informasi", "petunjuk", "tunjuk", "arahan",
    ],
    "Antrian": [
        "antri", "antre", "antrian", "lama", "lambat", "nunggu",
        "tunggu", "delay", "telat", "terlambat", "molor", "panjang",
    ],
    "Harga & Tiket": [
        "harga", "tiket", "mahal", "murah", "biaya", "bayar",
        "tarif", "pembayaran", "cash", "tunai", "qris", "kartu",
    ],
    "Keamanan": [
        "aman", "keamanan", "hilang", "copet", "curiga", "jaga",
        "satpam", "penjagaan", "pemeriksaan", "periksa", "skrining",
    ],
    "Akses & Parkir": [
        "akses", "parkir", "jalan", "transportasi", "ojek", "taksi",
        "grab", "gojek", "lokasi", "sulit", "macet",
    ],
    "Kapal & Jadwal": [
        "kapal", "jadwal", "keberangkatan", "berangkat",
        "kedatangan", "datang", "batal", "cancel", "reschedule", "booking",
    ],
}


def _compile_aspect_patterns():
    """Bangun regex word-boundary per aspek.

    Manfaat:
    - Hindari substring match (mis. 'lama' tidak cocok dengan 'kelamaan',
      'jalan' tidak cocok dengan 'jalankan').
    - Frasa multi-kata seperti 'ruang tunggu' tetap utuh karena di-escape
      sebagai satu alternatif.
    """
    compiled = {}
    for aspect, kws in ASPECT_KEYWORDS.items():
        # Urutkan panjang desc supaya frasa multi-kata diprioritaskan
        # saat regex alternation dievaluasi.
        sorted_kws = sorted(kws, key=len, reverse=True)
        alt = "|".join(re.escape(kw) for kw in sorted_kws)
        compiled[aspect] = re.compile(rf"\b(?:{alt})\b", re.IGNORECASE)
    return compiled


ASPECT_PATTERNS = _compile_aspect_patterns()


def _aspect_hits(text):
    """Return set aspek yang terdeteksi pada satu teks (word boundary)."""
    if not text:
        return set()
    text = str(text)
    return {a for a, pat in ASPECT_PATTERNS.items() if pat.search(text)}


def audit_aspect_coverage(df, sample_missing=8, sample_hits=3):
    """
    Audit keyword aspek terhadap `final_text`.

    Output:
    - jumlah ulasan yang tersentuh tiap aspek + persentase
    - keyword yang TIDAK pernah muncul
    - contoh ulasan yang terdeteksi (agar bisa dicek apakah konteksnya relevan)
    """
    if "final_text" not in df.columns:
        print("❌ Kolom 'final_text' tidak tersedia.")
        return
    texts = df["final_text"].dropna().astype(str).tolist()
    total = len(texts)
    if total == 0:
        print("❌ Data kosong.")
        return

    print(f"📋 Audit coverage ASPECT_KEYWORDS terhadap {total} ulasan\n")
    print(f"{'Aspek':<18}{'Hit':>6}{'%':>8}  Keyword tidak muncul")
    print("-" * 110)

    for aspect, kws in ASPECT_KEYWORDS.items():
        pat = ASPECT_PATTERNS[aspect]
        hits = 0
        kw_seen = set()
        examples = []
        for t in texts:
            if pat.search(t):
                hits += 1
                if len(examples) < sample_hits:
                    examples.append(t)
            for kw in kws:
                if kw in kw_seen:
                    continue
                if re.search(rf"\b{re.escape(kw)}\b", t, re.IGNORECASE):
                    kw_seen.add(kw)
        pct = hits / total * 100
        missing = [kw for kw in kws if kw not in kw_seen]
        missing_str = ", ".join(missing[:sample_missing])
        if len(missing) > sample_missing:
            missing_str += f" ... (+{len(missing) - sample_missing})"
        print(f"{aspect:<18}{hits:>6}{pct:>7.1f}%  {missing_str}")

        if examples:
            print(f"    Contoh ulasan terdeteksi:")
            for ex in examples:
                ex_short = ex if len(ex) <= 110 else ex[:107] + "…"
                print(f"      · {ex_short}")


def _fig_to_base64(fig, dpi=110):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=dpi, facecolor="white")
    buf.seek(0)
    img = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return f"data:image/png;base64,{img}"


def _get_sentiment_col(df):
    for c in ("sentiment", "sentimen"):
        if c in df.columns:
            return c
    return None


def _normalize_sentiment(df):
    col = _get_sentiment_col(df)
    if not col:
        return df
    df = df.copy()
    df["_sentimen"] = df[col].astype(str).str.strip().str.upper()
    return df


def chart_donut_sentimen(df):
    df = _normalize_sentiment(df)
    if "_sentimen" not in df.columns:
        return _placeholder("Data sentimen tidak tersedia")

    counts = df["_sentimen"].value_counts()
    pos = int(counts.get("POSITIF", 0))
    net = int(counts.get("NETRAL", 0))
    neg = int(counts.get("NEGATIF", 0))

    total = pos + net + neg
    if total == 0:
        return _placeholder("Belum ada data sentimen")

    def _label(name, count):
        return f"{name}\n{count} ({count / total * 100:.1f}%)"

    sizes = [pos, net, neg]
    labels = [_label("Positif", pos), _label("Netral", net), _label("Negatif", neg)]
    colors = [COLORS["positif"], COLORS["netral"], COLORS["negatif"]]

    fig, ax = plt.subplots(figsize=(6, 4))
    wedges, _ = ax.pie(
        sizes, colors=colors, startangle=90,
        wedgeprops=dict(width=0.4, edgecolor="white", linewidth=2),
    )
    ax.legend(
        wedges, labels, loc="center left", bbox_to_anchor=(1, 0.5),
        frameon=False, fontsize=10,
    )
    ax.set_title(
        f"Distribusi Sentimen (total {total} ulasan)",
        fontsize=13, fontweight="bold", pad=15,
    )
    ax.axis("equal")
    return _fig_to_base64(fig)


def chart_popularitas(df):
    if "lokasi" not in df.columns:
        return _placeholder("Kolom lokasi tidak tersedia")

    # [FIX F] Validasi data kosong.
    counts = df["lokasi"].dropna().value_counts().head(10)
    if counts.empty:
        return _placeholder("Belum ada data popularitas")

    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.barh(
        counts.index[::-1], counts.values[::-1],
        color=COLORS["secondary"], edgecolor="white",
    )
    ax.set_xlabel("Jumlah Ulasan")
    ax.set_title("Distribusi Popularitas Pelabuhan", fontsize=13, pad=10)
    for bar, val in zip(bars, counts.values[::-1]):
        ax.text(
            bar.get_width() + max(counts.values) * 0.01,
            bar.get_y() + bar.get_height() / 2,
            str(val), va="center", fontsize=9, fontweight="bold",
        )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return _fig_to_base64(fig)


def chart_rating_volume(df):
    if "lokasi" not in df.columns or "rating" not in df.columns:
        return _placeholder("Data rating/lokasi tidak tersedia")
    df = df.copy()
    df["_rating"] = pd.to_numeric(
        df["rating"].astype(str).str.extract(r"(\d+)")[0], errors="coerce"
    )
    df = df.dropna(subset=["_rating"])
    if df.empty:
        return _placeholder("Belum ada rating valid")
    agg = (
        df.groupby("lokasi")
        .agg(volume=("_rating", "size"), rating=("_rating", "mean"))
        .reset_index()
    )
    if agg.empty:
        return _placeholder("Data tidak cukup")

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.scatter(
        agg["volume"], agg["rating"], s=agg["volume"] * 2,
        c=COLORS["primary"], alpha=0.6, edgecolors="white", linewidths=2,
    )
    for _, row in agg.iterrows():
        label = str(row["lokasi"])
        if len(label) > 18:
            label = label[:16] + "…"
        ax.annotate(
            label, (row["volume"], row["rating"]),
            fontsize=8, ha="center", va="bottom",
        )
    ax.set_xlabel("Volume Ulasan")
    ax.set_ylabel("Rata-rata Rating")
    ax.set_ylim(0.5, 5.5)
    ax.set_title("Kualitas Rating vs Volume Ulasan", fontsize=13, pad=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return _fig_to_base64(fig)


def chart_tren_volume(df):
    if "tanggal_estimasi" not in df.columns:
        return _placeholder("Kolom tanggal_estimasi tidak ada")
    df = df.copy()
    df["_tgl"] = pd.to_datetime(df["tanggal_estimasi"], errors="coerce")
    df = df.dropna(subset=["_tgl"])
    if df.empty:
        return _placeholder("Belum ada tanggal valid")
    df["_bulan"] = df["_tgl"].dt.to_period("M")
    counts = df.groupby("_bulan").size().sort_index()
    if len(counts) == 0:
        return _placeholder("Data terlalu sedikit")

    fig, ax = plt.subplots(figsize=(7, 4))
    x = counts.index.astype(str)
    ax.plot(
        x, counts.values, marker="o", linewidth=2.5,
        color=COLORS["primary"], markersize=8,
        markerfacecolor="white", markeredgewidth=2,
    )
    ax.fill_between(range(len(x)), counts.values, alpha=0.15, color=COLORS["primary"])
    ax.set_xticks(range(len(x)))
    ax.set_xticklabels(x, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Jumlah Ulasan")
    ax.set_title("Tren Volume Ulasan per Bulan", fontsize=13, pad=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return _fig_to_base64(fig)


def chart_tren_aspek(df):
    if "tanggal_estimasi" not in df.columns or "final_text" not in df.columns:
        return _placeholder("Data tidak cukup")
    df = df.copy()
    df["_tgl"] = pd.to_datetime(df["tanggal_estimasi"], errors="coerce")
    df = df.dropna(subset=["_tgl"])
    if df.empty:
        return _placeholder("Belum ada tanggal valid")
    df["_bulan"] = df["_tgl"].dt.to_period("M")
    months = sorted(df["_bulan"].unique())
    if len(months) < 2:
        return _placeholder("Butuh minimal 2 bulan")

    # [FIX H] Optimasi lookup: pakai dict, bukan months.index() berulang.
    month_idx = {m: i for i, m in enumerate(months)}

    data = {a: [0] * len(months) for a in ASPECT_KEYWORDS}
    for _, row in df.iterrows():
        idx = month_idx.get(row["_bulan"])
        if idx is None:
            continue
        for aspek in _aspect_hits(row.get("final_text", "")):
            data[aspek][idx] += 1

    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = ["#dc3545", "#fd7e14", "#ffc107", "#20c997",
              "#0dcaf0", "#0d6efd", "#6f42c1", "#d63384"]
    for i, (aspek, values) in enumerate(data.items()):
        if sum(values) > 0:
            ax.plot(
                [str(m) for m in months], values,
                marker="o", linewidth=1.8, label=aspek,
                color=colors[i % len(colors)], markersize=5,
            )
    ax.set_ylabel("Jumlah Ulasan yang Menyebut Aspek")
    ax.set_title("Tren Aspek per Bulan", fontsize=13, pad=10)
    ax.legend(loc="upper left", fontsize=7, ncol=2, frameon=False)
    plt.xticks(rotation=45, ha="right", fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return _fig_to_base64(fig)


def chart_aspek_stacked(df):
    """
    Distribusi sentimen keseluruhan ulasan untuk setiap aspek.

    PENTING (lihat reviewer D): fungsi ini BUKAN Aspect-Based Sentiment
    Analysis. Satu ulasan bisa menyebut 'toilet kotor, tapi petugas ramah'
    dan diberi label keseluruhan POSITIF oleh model. Grafik akan menghitung
    'Kebersihan=POSITIF' padahal sentimen di dalam kalimat itu negatif.

    Judul grafik sengaja menegaskan hal ini agar tidak disalahartikan.
    Untuk ABSA yang sebenarnya, dibutuhkan modul terpisah (di luar scope PBL).
    """
    df = _normalize_sentiment(df)
    if "final_text" not in df.columns or "_sentimen" not in df.columns:
        return _placeholder("Data tidak cukup")

    stats = {a: {"POSITIF": 0, "NETRAL": 0, "NEGATIF": 0} for a in ASPECT_KEYWORDS}
    for _, row in df.iterrows():
        s = row["_sentimen"]
        if s not in ("POSITIF", "NETRAL", "NEGATIF"):
            continue
        for aspek in _aspect_hits(row.get("final_text", "")):
            stats[aspek][s] += 1

    stats = {k: v for k, v in stats.items() if sum(v.values()) > 0}
    if not stats:
        return _placeholder("Tidak ada aspek terdeteksi")

    aspects = list(stats.keys())
    pos_vals = [stats[a]["POSITIF"] for a in aspects]
    net_vals = [stats[a]["NETRAL"] for a in aspects]
    neg_vals = [stats[a]["NEGATIF"] for a in aspects]

    fig, ax = plt.subplots(figsize=(8, 5))
    x = range(len(aspects))
    ax.bar(x, pos_vals, label="Positif", color=COLORS["positif"])
    ax.bar(x, net_vals, bottom=pos_vals, label="Netral", color=COLORS["netral"])
    bottom2 = [p + n for p, n in zip(pos_vals, net_vals)]
    ax.bar(x, neg_vals, bottom=bottom2, label="Negatif", color=COLORS["negatif"])
    ax.set_xticks(x)
    ax.set_xticklabels(aspects, rotation=30, ha="right", fontsize=9)
    ax.set_ylabel("Jumlah Ulasan yang Menyebut Aspek")
    # [FIX D] Judul eksplisit: sentimen = label keseluruhan ulasan, bukan ABSA.
    ax.set_title(
        "Aspek vs Sentimen Keseluruhan Ulasan\n"
        "(bukan ABSA; satu ulasan bisa masuk >1 aspek)",
        fontsize=12, pad=10,
    )
    ax.legend(frameon=False, loc="upper right")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return _fig_to_base64(fig)


def chart_wordcloud(df, only_negative=False, extra_stopwords=None):
    if "final_text" not in df.columns:
        return _placeholder("Data teks tidak tersedia")

    if only_negative:
        df = _normalize_sentiment(df)
        if "_sentimen" not in df.columns:
            return _placeholder("Data sentimen tidak tersedia untuk filter negatif")
        df = df[df["_sentimen"] == "NEGATIF"]
        if df.empty:
            return _placeholder("Tidak ada ulasan negatif")

    texts = df["final_text"].dropna().astype(str)
    combined = " ".join(texts.tolist()).strip()
    if not combined:
        return _placeholder("Tidak ada teks")

    # Stopwords dasar + kata-kata umum/penghubung/bahasa inggris yang ingin dibuang
    stopwords = {
        "a", "i", "u", "e", "o", "nya", "pun", "lah", "kah", "yg", "aja", "udah",
        # Bahasa Inggris umum & artikel
        "the", "and", "to", "is", "it", "in", "for", "of", "are", "you", "from",
        "not", "there", "this", "with", "on", "at", "but", "be", "as", "so",
        "have", "that", "or", "if", "we", "was", "my", "can", "will", "like",
        "no", "your", "about", "they", "what", "which", "who", "when", "where",
        "why", "how", "all", "any", "both", "each", "few", "more", "most", "other",
        "some", "such", "nor", "only", "own", "same", "than", "too", "don", "should",
        "now", "am", "were", "been", "being", "has", "had", "do", "does", "did",
        "doing", "an", "because", "until", "while", "by", "against", "between",
        "into", "through", "during", "before", "after", "above", "below", "up",
        "down", "out", "off", "over", "under", "again", "further", "then", "once",
        "here", "just", "very", "its", "so", "as", "to",
        # Kata hubung & kata umum Bahasa Indonesia yang sering muncul
        "tidak", "di", "dan", "yang", "untuk", "dari", "ini", "itu", "ke", "ada",
        "mereka", "kami", "kita", "saya", "pada", "adalah", "sebagai", "karena",
        "bahwa", "oleh", "juga", "sudah", "bisa", "atau", "namun", "masih", "mau",
        "jadi", "akan", "saat", "lagi", "perlu", "jika", "lain", "setelah", "beberapa",
        "sampai", "tetapi", "dapat", "gak", "ga", "agak", "semua", "sekitar",
        "seperti", "salah", "saja", "sih", "ya", "terus", "padahal", "walaupun",
        "meskipun", "sedang", "telah", "sering", "kadang", "jarang", "pasti",
        "mungkin", "boleh", "wajib", "serta", "pun", "kok", "kan", "dong", "deh"
    }
    
    if extra_stopwords:
        stopwords |= set(extra_stopwords)

    try:
        wc = WordCloud(
            width=800, height=400, background_color="white",
            colormap="Blues", max_words=60, collocations=False, # Menggunakan colormap 'Blues' agar selaras dengan tema web
            min_font_size=10, stopwords=stopwords,
        ).generate(combined)
    except ValueError:
        return _placeholder("Teks terlalu sedikit")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    ax.set_title(
        "Word Cloud" + (" Ulasan Negatif" if only_negative else ""),
        fontsize=13, pad=10,
    )
    fig.tight_layout()
    return _fig_to_base64(fig)


# Urutan & warna sentimen untuk heatmap/confusion matrix. Disamakan dengan
# dashboard (donut, KPI) supaya konsisten: Positif -> Netral -> Negatif.
SENTIMENT_ORDER = ("POSITIF", "NETRAL", "NEGATIF")
SENTIMENT_LABELS = {"POSITIF": "Positif", "NETRAL": "Netral", "NEGATIF": "Negatif"}
SENTIMENT_COLORS = {"POSITIF": "#00B809", "NETRAL": "#FFCC00", "NEGATIF": "#9D0003"}
# Batas atas skala warna heatmap (dalam %). Tetap (tidak bergantung filter) agar
# arti warna sama untuk satu pelabuhan maupun banyak pelabuhan.
HEATMAP_VMAX = {"POSITIF": 100.0, "NETRAL": 50.0, "NEGATIF": 50.0}
_MUTED = "#6c757d"


def _sentiment_cmap(sentiment):
    """Putih -> warna sentimen. Intensitas = besar nilai, hue = jenis sentimen."""
    return LinearSegmentedColormap.from_list(
        f"w_{sentiment}", ["#FFFFFF", SENTIMENT_COLORS[sentiment]]
    )


def chart_heatmap(df):
    """
    Heatmap komposisi sentimen per pelabuhan.

    - Angka utama = persentase ulasan pelabuhan tsb. (tiap baris berjumlah 100%),
      angka dalam kurung = jumlah ulasan. Dengan begitu pelabuhan ber-volume
      besar tidak otomatis tampak "lebih baik".
    - Warna per kolom memakai hue sentimennya (hijau/kuning/merah) dengan skala
      tetap (HEATMAP_VMAX), jadi intensitas berarti sama untuk filter apa pun.
    - Baris diurutkan dari volume ulasan terbanyak; volume ditulis di label baris.
    """
    df = _normalize_sentiment(df)
    if "lokasi" not in df.columns or "_sentimen" not in df.columns:
        return _placeholder("Data tidak cukup")

    counts = pd.crosstab(df["lokasi"], df["_sentimen"])
    for col in SENTIMENT_ORDER:
        if col not in counts.columns:
            counts[col] = 0
    counts = counts[list(SENTIMENT_ORDER)]
    counts = counts[counts.sum(axis=1) > 0]
    if counts.empty:
        return _placeholder("Data terlalu sedikit")

    totals = counts.sum(axis=1).sort_values(ascending=False)
    counts = counts.loc[totals.index]
    pct = counts.div(totals, axis=0) * 100

    annot = pd.DataFrame(
        [
            [f"{pct.iloc[i, j]:.1f}%\n({int(counts.iloc[i, j])})" for j in range(len(SENTIMENT_ORDER))]
            for i in range(len(counts))
        ],
        index=counts.index, columns=counts.columns,
    )

    n_rows = len(counts)
    fig, ax = plt.subplots(figsize=(7.5, 2.0 + 0.8 * n_rows))
    for j, sent in enumerate(SENTIMENT_ORDER):
        mask = np.ones(pct.shape, dtype=bool)
        mask[:, j] = False  # gambar satu kolom per panggilan, skala warna sendiri
        sns.heatmap(
            pct, mask=mask, annot=annot, fmt="",
            cmap=_sentiment_cmap(sent), vmin=0, vmax=HEATMAP_VMAX[sent],
            cbar=False, linewidths=3, linecolor="white",
            annot_kws={"fontsize": 10, "fontweight": "bold"}, ax=ax,
        )

    ax.grid(False)
    ax.set_xticklabels([SENTIMENT_LABELS[c] for c in SENTIMENT_ORDER], rotation=0, fontsize=10)
    ax.set_yticklabels(
        [f"{name}\n(n={int(totals[name])})" for name in counts.index], rotation=0, fontsize=10
    )
    ax.tick_params(axis="both", length=0)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_title("Komposisi Sentimen per Pelabuhan", fontsize=13, pad=34)
    ax.text(
        0.5, 1.03,
        "Angka = % ulasan pelabuhan (jumlah ulasan). Skala warna tetap: "
        "Positif 0-100%, Netral & Negatif 0-50%.",
        transform=ax.transAxes, ha="center", va="bottom", fontsize=8, color=_MUTED,
    )
    fig.tight_layout()
    return _fig_to_base64(fig, dpi=140)


def chart_confusion_matrix(eval_path="data/models/evaluation.json"):
    """
    Confusion matrix dari evaluation.json (evaluasi global, tidak mengikuti filter).

    - Baris = kelas aktual, kolom = prediksi, urutan Positif -> Netral -> Negatif.
    - Warna & persentase dinormalisasi PER BARIS (porsi dari kelas aktual),
      jadi diagonal = recall. Kelas minoritas (mis. Netral) tetap terbaca
      meski jumlahnya jauh lebih kecil dari kelas Positif.
    - Jumlah mentah tetap tampil di tiap sel; n per kelas ada di label baris.
    """
    if not os.path.exists(eval_path):
        return _placeholder("Model belum dilatih")
    try:
        with open(eval_path, "r", encoding="utf-8") as f:
            report = json.load(f)
    except Exception:
        return _placeholder("Gagal membaca evaluation.json")

    cm_data = report.get("confusion_matrix", {})
    matrix = cm_data.get("matrix")
    labels = cm_data.get("labels", [])
    if not matrix or not labels:
        return _placeholder("Confusion matrix tidak tersedia")

    arr = np.array(matrix, dtype=float)
    # [FIX G] Validasi dimensi matriks vs jumlah label.
    if arr.ndim != 2 or arr.shape != (len(labels), len(labels)):
        return _placeholder(
            f"Format confusion matrix tidak valid: "
            f"shape={arr.shape}, labels={len(labels)}"
        )

    # Samakan urutan label dengan bagian dashboard lain.
    labels = [str(l).strip().upper() for l in labels]
    order = [l for l in SENTIMENT_ORDER if l in labels] + [l for l in labels if l not in SENTIMENT_ORDER]
    idx = [labels.index(l) for l in order]
    arr = arr[np.ix_(idx, idx)]
    labels = order

    support = arr.sum(axis=1)
    total = float(arr.sum())
    norm = np.divide(arr, support[:, None], out=np.zeros_like(arr), where=support[:, None] > 0)
    accuracy = report.get("accuracy")
    if accuracy is None:
        accuracy = float(np.trace(arr) / total) if total else 0.0

    annot = np.array(
        [[f"{int(arr[i, j])}\n{norm[i, j] * 100:.1f}%" for j in range(len(labels))] for i in range(len(labels))]
    )
    names = [SENTIMENT_LABELS.get(l, l.title()) for l in labels]

    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    sns.heatmap(
        norm, annot=annot, fmt="", cmap="Blues", vmin=0, vmax=1,
        xticklabels=names,
        yticklabels=[f"{n}\n(n={int(s)})" for n, s in zip(names, support)],
        linewidths=3, linecolor="white", cbar=False,
        annot_kws={"fontsize": 11, "fontweight": "bold"}, ax=ax,
    )
    # Bingkai tipis pada diagonal (prediksi benar) agar mudah dibedakan.
    for i in range(len(labels)):
        ax.add_patch(Rectangle((i, i), 1, 1, fill=False, edgecolor=COLORS["primary"], lw=2.4, clip_on=False))

    ax.grid(False)
    ax.tick_params(axis="both", length=0)
    ax.tick_params(axis="x", labelrotation=0)
    ax.tick_params(axis="y", labelrotation=0)
    ax.set_xlabel("Prediksi", labelpad=10)
    ax.set_ylabel("Aktual", labelpad=12)
    ax.set_title(
        f"Confusion Matrix\nAkurasi {accuracy:.2%}  •  {int(total)} data uji",
        fontsize=12, pad=12,
    )
    fig.text(
        0.5, -0.01,
        "Warna & persentase = porsi dari kelas aktual (diagonal = recall). Angka besar = jumlah ulasan.",
        ha="center", va="top", fontsize=8, color=_MUTED,
    )
    fig.tight_layout()
    return _fig_to_base64(fig, dpi=140)


def _placeholder(msg):
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.text(
        0.5, 0.5, msg, ha="center", va="center", fontsize=12, color="#6c757d",
        bbox=dict(boxstyle="round", facecolor="#f8f9fa", edgecolor="#dee2e6"),
    )
    ax.axis("off")
    return _fig_to_base64(fig)