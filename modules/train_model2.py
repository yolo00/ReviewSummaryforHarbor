#Train ini menggunakan label sentimen yang udah dibuat pada csv
import os

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC

try:
    from modules.check_terms import save_top_terms
    from modules.model_report import save_evaluation
except ModuleNotFoundError:  # dijalankan langsung dari folder modules
    from check_terms import save_top_terms
    from model_report import save_evaluation

# Ubah DATA_PATH jika file CSV berlabel kamu memakai nama lain
DATA_PATH = os.path.join("data", "processed", "review_processed(deepseek).csv")
MODEL_DIR = os.path.join("data", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "svm_pipeline.pkl")

# Lokasi file laporan model (dibaca oleh app.py)
EVAL_PATH = os.path.join(MODEL_DIR, "evaluation.json")   # accuracy, precision, recall, f1, confusion matrix
TERMS_PATH = os.path.join(MODEL_DIR, "top_terms.json")   # hasil check_terms (istilah paling berpengaruh)
TOP_N_TERMS = 10

LABELS = ["NEGATIF", "NETRAL", "POSITIF"]

# Normalisasi variasi penulisan label agar konsisten
LABEL_MAP = {
    "POSITIF": "POSITIF",
    "POSITIVE": "POSITIF",
    "POS": "POSITIF",
    "NEGATIF": "NEGATIF",
    "NEGATIVE": "NEGATIF",
    "NEG": "NEGATIF",
    "NETRAL": "NETRAL",
    "NEUTRAL": "NETRAL",
    "NET": "NETRAL",
}


def _to_bool(value):
    """Ubah nilai valid_text (True/False/'True'/1/0) menjadi boolean."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "1.0", "yes", "ya")


def train_svm_model():
    print("=" * 50)
    print("🚀 MEMULAI PELATIHAN MODEL SVM & TF-IDF (LABEL: SENTIMEN) 🚀")
    print("=" * 50)

    os.makedirs(MODEL_DIR, exist_ok=True)

    if not os.path.exists(DATA_PATH):
        print(f"❌ File {DATA_PATH} tidak ditemukan!")
        return False, "File dataset tidak ditemukan. Jalankan preprocessing terlebih dahulu."

    df = pd.read_csv(DATA_PATH)
    # Rapikan nama kolom (spasi berlebih / huruf besar-kecil)
    df.columns = df.columns.astype(str).str.strip().str.lower()

    print(f"📄 File: {DATA_PATH}")
    print(f"📄 Jumlah baris: {len(df)}")
    print(f"📄 Kolom: {list(df.columns)}")
    if "valid_text" in df.columns:
        print(f"📄 Nilai unik valid_text: {df['valid_text'].unique()[:10]}")
    if "sentimen" in df.columns:
        print(f"📄 Nilai unik sentimen (mentah): {df['sentimen'].unique()[:10]}")

    if df.empty:
        return False, "Dataset bersih kosong."

    # Pastikan kolom wajib ada
    required = ["final_text", "sentimen"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return False, f"Kolom wajib tidak ditemukan: {missing}"

    total_awal = len(df)

    # 1. Filter teks valid (jika kolom valid_text tersedia)
    # Filter valid_text hanya dipakai jika isinya benar-benar boolean.
    # Jika kolom itu berisi teks ulasan, filter dilewati (kebersihan data
    # dijamin oleh pengecekan final_text yang tidak kosong di bawah).
    if "valid_text" in df.columns:
        nilai = set(df["valid_text"].dropna().astype(str).str.strip().str.lower())
        bool_like = {"true", "false", "1", "0", "1.0", "0.0", "yes", "no", "ya", "tidak"}
        if nilai and nilai.issubset(bool_like):
            sebelum = len(df)
            df = df[df["valid_text"].apply(_to_bool)]
            print(f"🔎 Setelah filter valid_text: {len(df)} dari {sebelum} baris")
        else:
            print("ℹ️ Kolom valid_text bukan boolean (berisi teks), filter dilewati.")

    # 2. Normalisasi label sentimen dari kolom 'sentimen'
    label_mentah = df["sentimen"].astype(str).str.strip().str.upper()
    df["sentimen"] = label_mentah.map(LABEL_MAP)
    tak_dikenal = label_mentah[df["sentimen"].isna()].unique()
    if len(tak_dikenal) > 0:
        print(f"⚠️ Label tidak dikenali (baris dibuang): {tak_dikenal[:10]}")
    print(f"🔎 Setelah normalisasi label: {df['sentimen'].notna().sum()} baris berlabel valid")

    # 3. Buang baris tanpa label atau tanpa teks
    df = df.dropna(subset=["final_text", "sentimen"])
    df = df[df["final_text"].astype(str).str.strip() != ""]

    if df.empty:
        return False, "Tidak ada data valid setelah filtering."

    print(f"📊 Data awal: {total_awal} | Dipakai untuk training: {len(df)}")
    print("\nDistribusi label:")
    print(df["sentimen"].value_counts().to_string())

    X = df["final_text"].astype(str)
    y = df["sentimen"]

    # Validasi jumlah sampel minimum per kelas
    min_samples = y.value_counts().min()
    if y.nunique() < 2:
        return False, "Hanya ada satu kelas sentimen pada data."
    if min_samples < 2:
        return False, "Jumlah sampel pada salah satu kelas sentimen terlalu sedikit."

    # 4. Split dataset (stratified agar proporsi kelas terjaga)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # 5. Pipeline TF-IDF + SVM
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

    # 6. Training
    print("\n⏳ Melatih model pipeline...")
    sentiment_pipeline.fit(X_train, y_train)

    # 7. Evaluasi
    y_pred = sentiment_pipeline.predict(X_test)
    labels_present = [l for l in LABELS if l in set(y)]

    print("\n--- LAPORAN EVALUASI MODEL ---")
    print(classification_report(y_test, y_pred, labels=labels_present, zero_division=0))

    print("--- CONFUSION MATRIX (baris = aktual, kolom = prediksi) ---")
    cm = confusion_matrix(y_test, y_pred, labels=labels_present)
    print(pd.DataFrame(cm, index=labels_present, columns=labels_present).to_string())

    # 8. Simpan pipeline
    joblib.dump(sentiment_pipeline, MODEL_PATH)
    print(f"\n✅ Pipeline berhasil disimpan di: {MODEL_PATH}")

    # 9. Simpan evaluasi model ke file
    save_evaluation(
        y_test, y_pred, labels_present, EVAL_PATH,
        extra={
            "data_path": DATA_PATH,
            "n_total": int(total_awal),
            "n_train_data": int(len(X_train)),
            "label_distribution": {k: int(v) for k, v in y.value_counts().items()},
            "config": {
                "test_size": 0.2, "random_state": 42,
                "tfidf": {"ngram_range": [1, 2], "max_features": 5000, "sublinear_tf": True},
                "svm": {"kernel": "linear", "C": 1.0, "class_weight": "balanced"},
            },
        },
    )
    print(f"✅ Evaluasi model disimpan di: {EVAL_PATH}")

    # 10. Simpan hasil check_terms ke file
    save_top_terms(sentiment_pipeline, TERMS_PATH, TOP_N_TERMS)
    print(f"✅ Istilah penting (check_terms) disimpan di: {TERMS_PATH}")
    return True, "Pelatihan Model SVM dan TF-IDF Pipeline berhasil dilakukan!"


if __name__ == "__main__":
    ok, pesan = train_svm_model()
    print(("✅ " if ok else "❌ ") + pesan)