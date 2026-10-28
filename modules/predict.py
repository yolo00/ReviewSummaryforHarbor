import os
import joblib
import pandas as pd

# Impor TextPreprocessor
try:
    from modules.preprocessing import TextPreprocessor
except ModuleNotFoundError:
    from preprocessing import TextPreprocessor


class SVMSentimentAnalyzer:
    def __init__(self, model_dir=os.path.join("data", "models")):
        self.model_path = os.path.join(model_dir, "svm_pipeline.pkl")
        self.pipeline = None
        self.preprocessor = TextPreprocessor()  # Inisialisasi preprocessor
        self._load_model()

    def _load_model(self):
        if os.path.exists(self.model_path):
            self.pipeline = joblib.load(self.model_path)
        else:
            raise FileNotFoundError(f"Model pipeline '{self.model_path}' tidak ditemukan!")

    def predict_single(self, text):
        if not self.pipeline:
            raise ValueError("Model pipeline belum dimuat.")
        
        # 1. Terapkan Preprocessing (Clean -> Slang -> Stemmer & Stopwords)
        clean = self.preprocessor.clean_text(text)
        slang = self.preprocessor.normalize_slang(clean)
        final_text = self.preprocessor.remove_stopwords_and_stem(slang)
        
        # Gunakan final_text jika tidak kosong
        input_for_model = final_text if final_text.strip() != "" else text
        
        # 2. Lakukan Prediksi
        probabilities = self.pipeline.predict_proba([input_for_model])[0]
        classes = self.pipeline.classes_
        prob_dict = {str(cls): float(round(prob, 4)) for cls, prob in zip(classes, probabilities)}
        
        sorted_probs = sorted(prob_dict.items(), key=lambda x: x[1], reverse=True)
        top_class, top_prob = sorted_probs[0]
        second_class, second_prob = sorted_probs[1]
        
        # Threshold selisih tipis (< 10%) dikategorikan NETRAL
        if (top_prob - second_prob) < 0.10:
            prediction = "NETRAL"
        else:
            prediction = top_class
            
        return prediction, prob_dict

    def process_dataframe(self, df, text_column="final_text"):
        """Memprediksi sentimen untuk seluruh baris pada DataFrame."""
        if df.empty or text_column not in df.columns:
            df["sentiment"] = []
            return df

        texts = df[text_column].fillna("").astype(str).tolist()
        df["sentiment"] = self.pipeline.predict(texts)
        return df


def run_analysis_job(
    input_csv=os.path.join("data", "processed", "review_processed.csv"),
    output_predicted_csv=os.path.join("data", "processed", "review_predicted.csv"),
    output_recap_csv=os.path.join("data", "processed", "rekap_sentimen_pelabuhan.csv"),
):
    if not os.path.exists(input_csv):
        return False, "Data preprocessing tidak ditemukan. Jalankan preprocessing terlebih dahulu."

    try:
        df = pd.read_csv(input_csv)
    except Exception as e:
        return False, f"Gagal membaca data preprocessing: {e}"

    if df.empty:
        return False, "Data hasil preprocessing kosong."

    try:
        analyzer = SVMSentimentAnalyzer()
    except FileNotFoundError:
        return False, "Model belum dilatih. Jalankan training model terlebih dahulu."

    try:
        df_predicted = analyzer.process_dataframe(df, text_column="final_text")
        df_predicted.to_csv(output_predicted_csv, index=False, encoding="utf-8-sig")

        msg = f"Analisis selesai! {len(df_predicted)} ulasan berhasil diberi label sentimen."

        if "pelabuhan" in df_predicted.columns:
            rekap = (
                pd.crosstab(
                    df_predicted["pelabuhan"],
                    df_predicted["sentiment"],
                    margins=True,
                    margins_name="TOTAL",
                )
                .fillna(0)
                .astype(int)
            )
            rekap.to_csv(output_recap_csv)
        else:
            msg += " (Rekap per pelabuhan dilewati: kolom 'pelabuhan' tidak ada.)"

        return True, msg
    except Exception as e:
        return False, f"Analisis gagal: {e}"


def analyze_and_recap_harbors():
    success, msg = run_analysis_job()
    print(("✅ " if success else "❌ ") + msg)


if __name__ == "__main__":
    analyze_and_recap_harbors()