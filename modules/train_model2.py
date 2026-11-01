# Train ini menggunakan label sentimen yang udah dibuat pada csv.
# Jika CSV tidak punya kolom 'sentimen', label dibuat otomatis dari 'rating'
# (fungsi lama train_model.py digabung ke sini).
import os

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC

try:
    from modules.check_terms import save_top_terms
    from modules.model_report import save_evaluation
except ModuleNotFoundError:
    from check_terms import save_top_terms
    from model_report import save_evaluation

# ---------------------------------------------------------------------------
# KONFIGURASI
# ---------------------------------------------------------------------------
# Satu file dataset hasil preprocessing terbaru.
# Pastikan file ini sudah dibuat oleh preprocessing.py sebelum training.
DATA_PATH = os.path.join("data", "processed", "review_processed(fix).csv")

MODEL_DIR = os.path.join("data", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "svm_pipeline.pkl")

EVAL_PATH = os.path.join(MODEL_DIR, "evaluation.json")
TERMS_PATH = os.path.join(MODEL_DIR, "top_terms.json")
TOP_N_TERMS = 10

LABELS = ["NEGATIF", "NETRAL", "POSITIF"]

LABEL_MAP = {
    "POSITIF": "POSITIF", "POSITIVE": "POSITIF", "POS": "POSITIF",
    "NEGATIF": "NEGATIF", "NEGATIVE": "NEGATIF", "NEG": "NEGATIF",
    "NETRAL": "NETRAL", "NEUTRAL": "NETRAL", "NET": "NETRAL",
}


def _to_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "1.0", "yes", "ya")


def _rating_to_sentiment(rating_value):
    """Label dari rating: >=4 POSITIF, <=2 NEGATIF, 3 NETRAL."""
    try:
        r = float(str(rating_value).strip().split()[0])
    except (ValueError, IndexError):
        return None
    if r >= 4:
        return "POSITIF"
    if r <= 2:
        return "NEGATIF"
    return "NETRAL"


def train_svm_model(data_path=None):
    print("=" * 50)
    print("🚀 MEMULAI PELATIHAN MODEL SVM & TF-IDF 🚀")
    print("=" * 50)

    os.makedirs(MODEL_DIR, exist_ok=True)

    # --- resolve path: hanya satu dataset ---
    if data_path is None:
        data_path = DATA_PATH

    if not os.path.exists(data_path):
        print(f"❌ File dataset tidak ditemukan: {data_path}")
        return False, (
            f"File dataset tidak ditemukan: {data_path}. "
            "Jalankan preprocessing terlebih dahulu untuk menghasilkan "
            "review_processed(fix).csv."
        )

    df = pd.read_csv(data_path)
    df.columns = df.columns.astype(str).str.strip().str.lower()

    print(f"📄 File: {data_path}")
    print(f"📄 Jumlah baris: {len(df)}")
    print(f"📄 Kolom: {list(df.columns)}")

    if df.empty:
        return False, "Dataset bersih kosong."

    if "final_text" not in df.columns:
        return False, "Kolom wajib 'final_text' tidak ditemukan."

    total_awal = len(df)

    # --- filter valid_text kalau boolean-like ---
    if "valid_text" in df.columns:
        nilai = set(df["valid_text"].dropna().astype(str).str.strip().str.lower())
        bool_like = {"true", "false", "1", "0", "1.0", "0.0", "yes", "no", "ya", "tidak"}
        if nilai and nilai.issubset(bool_like):
            sebelum = len(df)
            df = df[df["valid_text"].apply(_to_bool)]
            print(f"🔎 Setelah filter valid_text: {len(df)} dari {sebelum} baris")
        else:
            print("ℹ️ Kolom valid_text bukan boolean, filter dilewati.")

    # --- tentukan sumber label ---
    label_source = None
    if "sentimen" in df.columns:
        label_mentah = df["sentimen"].astype(str).str.strip().str.upper()
        df["sentimen"] = label_mentah.map(LABEL_MAP)
        tak_dikenal = label_mentah[df["sentimen"].isna()].unique()
        tak_dikenal = [t for t in tak_dikenal if t not in ("NAN", "", "NONE")]
        if tak_dikenal:
            print(f"⚠️ Label tidak dikenali (baris dibuang): {tak_dikenal[:10]}")
        # kalau setelah mapping semua NaN, anggap tidak ada label sentimen
        if df["sentimen"].notna().any():
            label_source = "sentimen"
            print(f"🔎 Label dari kolom 'sentimen': {df['sentimen'].notna().sum()} baris valid")
        else:
            print("⚠️ Kolom 'sentimen' ada tapi semua kosong → fallback ke rating.")

    if label_source is None:
        if "rating" in df.columns:
            df["sentimen"] = df["rating"].apply(_rating_to_sentiment)
            label_source = "rating"
            print(f"🔎 Label dari kolom 'rating': {df['sentimen'].notna().sum()} baris valid")
        else:
            return False, "Tidak ada kolom 'sentimen' maupun 'rating' untuk dijadikan label."

    # --- buang baris tanpa label / tanpa teks ---
    df = df.dropna(subset=["final_text", "sentimen"])
    df = df[df["final_text"].astype(str).str.strip() != ""]

    if df.empty:
        return False, "Tidak ada data valid setelah filtering."

    # --- dedup teks+label ---
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["final_text", "sentimen"]).copy()
    print(f"🧹 Duplikat final_text+label dibuang: {before_dedup - len(df)} baris")

    # --- buang teks dengan label konflik ---
    konflik = df.groupby("final_text")["sentimen"].nunique()
    teks_konflik = konflik[konflik > 1].index
    if len(teks_konflik) > 0:
        print(f"⚠️ {len(teks_konflik)} teks punya label konflik dan dibuang.")
        df = df[~df["final_text"].isin(teks_konflik)].copy()

    if df.empty:
        return False, "Tidak ada data valid setelah deduplikasi."

    print(f"📊 Data awal: {total_awal} | Dipakai untuk training: {len(df)}")
    print("\nDistribusi label:")
    print(df["sentimen"].value_counts().to_string())

    X = df["final_text"].astype(str)
    y = df["sentimen"]

    # --- validasi kelas ---
    if y.nunique() < 2:
        return False, "Hanya ada satu kelas sentimen pada data."

    # Pastikan ketiga kelas sentimen tersedia.
    missing_labels = set(LABELS) - set(y.unique())
    if missing_labels:
        return False, (
            f"Kelas sentimen tidak lengkap. "
            f"Kelas yang belum tersedia: {sorted(missing_labels)}. "
            f"Dataset harus memiliki ketiga kelas: {LABELS}. "
            f"Jalankan preprocessing/labeling terlebih dahulu."
        )

    min_samples = int(y.value_counts().min())
    if min_samples < 2:
        return False, (
            f"Jumlah sampel pada salah satu kelas terlalu sedikit "
            f"(min={min_samples}). Perlu minimal 2 per kelas."
        )

    # --- split ---
    # Stratified split membutuhkan minimal 1 sampel per kelas pada test set.
    n_classes = int(y.nunique())
    n_samples = len(df)
    test_size = max(0.2, n_classes / n_samples)

    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )
    except ValueError as e:
        return False, (
            f"Pembagian data training dan testing gagal: {e}. "
            f"Periksa kembali jumlah sampel setiap kelas."
        )

    print(
        f"\n📊 Split: train={len(X_train)} | test={len(X_test)} "
        f"(test_size={test_size:.3f})"
    )

    # Distribusi label train/test — pastikan ketiga kelas terwakili.
    print("\nDistribusi label data training:")
    print(y_train.value_counts().to_string())
    print("\nDistribusi label data testing:")
    print(y_test.value_counts().to_string())

    # --- pipeline ---
    sentiment_pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=5000,
            sublinear_tf=True,
        )),
        ("svm", SVC(
            kernel="linear",
            C=1.0,
            class_weight="balanced",
            probability=True,
            random_state=42,
        )),
    ])

    print("\n⏳ Melatih model pipeline...")
    sentiment_pipeline.fit(X_train, y_train)

    y_pred = sentiment_pipeline.predict(X_test)
    labels_present = [l for l in LABELS if l in set(y)]

    joblib.dump(sentiment_pipeline, MODEL_PATH)
    print(f"\n✅ Pipeline berhasil disimpan di: {MODEL_PATH}")

    # Perhitungan metrik (accuracy, precision, recall, F1, confusion matrix)
    # dan penyimpanannya dilakukan sepenuhnya oleh modules/model_report.py.
    save_evaluation(
        y_test, y_pred, labels_present, EVAL_PATH,
        extra={
            "n_after_dedup": int(len(df)),
            "data_path": data_path,
            "label_source": label_source,   # "sentimen" atau "rating"
            "n_total": int(total_awal),
            "n_train_data": int(len(X_train)),
            "n_test_data": int(len(X_test)),
            "label_distribution": {k: int(v) for k, v in y.value_counts().items()},
            "label_distribution_train": {
                k: int(v) for k, v in y_train.value_counts().items()
            },
            "label_distribution_test": {
                k: int(v) for k, v in y_test.value_counts().items()
            },
            "config": {
                "test_size": test_size, "random_state": 42,
                "tfidf": {"ngram_range": [1, 2], "max_features": 5000, "sublinear_tf": True},
                "svm": {"kernel": "linear", "C": 1.0, "class_weight": "balanced"},
            },
        },
    )
    print(f"✅ Evaluasi model disimpan di: {EVAL_PATH}")

    save_top_terms(sentiment_pipeline, TERMS_PATH, TOP_N_TERMS)
    print(f"✅ Istilah penting (check_terms) disimpan di: {TERMS_PATH}")

    return True, (
        f"Pelatihan berhasil (label dari '{label_source}'). "
        f"Model disimpan di {MODEL_PATH}."
    )


if __name__ == "__main__":
    ok, pesan = train_svm_model()
    print(("✅ " if ok else "❌ ") + pesan)