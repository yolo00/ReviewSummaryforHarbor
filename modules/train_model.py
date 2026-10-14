import os
import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC

DATA_PATH = os.path.join("data", "processed", "review_processed.csv")
MODEL_DIR = os.path.join("data", "models")


def train_svm_model():
    print("=" * 50)
    print("🚀 MEMULAI PELATIHAN MODEL SVM & TF-IDF 🚀")
    print("=" * 50)

    os.makedirs(MODEL_DIR, exist_ok=True)

    if not os.path.exists(DATA_PATH):
        print(f"❌ File {DATA_PATH} tidak ditemukan!")
        return False, "File dataset tidak ditemukan. Jalankan preprocessing terlebih dahulu."

    df = pd.read_csv(DATA_PATH)
    if df.empty:
        return False, "Dataset bersih kosong."

    # 1. Pemetaan Rating ke Sentimen (Positif, Negatif, Netral)
    df["rating_num"] = df["rating"].astype(str).str.extract(r"(\d+)").astype(float)

    def map_sentiment(r):
        if r >= 4:
            return "POSITIF"
        elif r <= 2:
            return "NEGATIF"
        else:
            return "NETRAL"

    df["sentiment_actual"] = df["rating_num"].apply(map_sentiment)
    
    # Pastikan data teks tidak kosong
    df = df.dropna(subset=["final_text", "sentiment_actual"])
    df = df[df["final_text"].astype(str).str.strip() != ""]

    X = df["final_text"].astype(str)
    y = df["sentiment_actual"]

    # Validasi jumlah sampel minimum per kelas
    min_samples = y.value_counts().min()
    if min_samples < 2:
        return False, "Jumlah sampel pada salah satu kelas sentimen terlalu sedikit."

    # 2. Split Dataset
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # 3. Buat Scikit-Learn Pipeline (TF-IDF + SVM dengan probability=True)
    sentiment_pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(
            ngram_range=(1, 2), 
            max_features=5000, 
            sublinear_tf=True
        )),
        ('svm', SVC(
            kernel='linear', 
            C=1.0, 
            class_weight='balanced', 
            probability=True, 
            random_state=42
        ))
    ])

    # 4. Fit/Train Pipeline
    print("⏳ Melatih model pipeline...")
    sentiment_pipeline.fit(X_train, y_train)

    # 5. Evaluasi Model
    y_pred = sentiment_pipeline.predict(X_test)
    print("\n--- LAPORAN EVALUASI MODEL ---")
    print(classification_report(y_test, y_pred, zero_division=0))

    # 6. Simpan Objek Pipeline Tunggal
    model_path = os.path.join(MODEL_DIR, "svm_pipeline.pkl")
    joblib.dump(sentiment_pipeline, model_path)
    
    print(f"✅ Pipeline berhasil disimpan di: {model_path}")
    return True, "Pelatihan Model SVM dan TF-IDF Pipeline berhasil dilakukan!"


if __name__ == "__main__":
    train_svm_model()