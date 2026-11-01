import os
import re
import joblib
import pandas as pd

# Impor TextPreprocessor
try:
    from modules.preprocessing import TextPreprocessor
except ModuleNotFoundError:
    from preprocessing import TextPreprocessor


# Batas minimal kata untuk halaman Uji Sentimen
MIN_KATA_UJI = 6


class InputTidakValid(ValueError):
    """Teks yang dimasukkan pengguna tidak dapat dianalisis (pesan siap tampil ke pengguna)."""


def hitung_kata(text):
    """Jumlah kata (rangkaian huruf); angka, simbol, dan emoji tidak dihitung."""
    return len(re.findall(r"[^\W\d_]+", str(text)))


def validasi_teks_uji(text):
    text = (text or "").strip()
    if not text:
        raise InputTidakValid("Teks ulasan tidak boleh kosong.")
    jumlah = hitung_kata(text)
    if jumlah < MIN_KATA_UJI:
        raise InputTidakValid(
            f"Teks terlalu pendek: baru {jumlah} kata. "
            f"Tulis minimal {MIN_KATA_UJI} kata agar model dapat menganalisis."
        )
    return text


class SVMSentimentAnalyzer:
    def __init__(self, model_dir=os.path.join("data", "models"),
                 use_neutral_threshold=False, neutral_margin=0.10):
        self.model_path = os.path.join(model_dir, "svm_pipeline.pkl")
        self.pipeline = None
        self.preprocessor = TextPreprocessor()  # Inisialisasi preprocessor

        # [FIX 3] Threshold NETRAL dibuat opsional, default OFF.
        # Aktifkan hanya jika kamu sudah punya alasan metodologis &
        # hasil pengujian yang mendukung.
        self.use_neutral_threshold = bool(use_neutral_threshold)
        self.neutral_margin = float(neutral_margin)

        self._load_model()

    def _load_model(self):
        if os.path.exists(self.model_path):
            self.pipeline = joblib.load(self.model_path)
        else:
            raise FileNotFoundError(f"Model pipeline '{self.model_path}' tidak ditemukan!")

    def predict_single(self, text):
        if not self.pipeline:
            raise ValueError("Model pipeline belum dimuat.")

        text = validasi_teks_uji(text)

        # 1. Preprocessing untuk teks mentah dari pengguna.
        clean = self.preprocessor.clean_text(text)
        slang = self.preprocessor.normalize_slang(clean)
        final_text = self.preprocessor.remove_stopwords_and_stem(slang)

        # Tidak ada kata bermakna tersisa -> tolak, jangan paksa prediksi
        if final_text.strip() == "":
            raise InputTidakValid(
                "Teks tidak dapat dianalisis: tidak ada kata bermakna yang tersisa setelah "
                "pembersihan (hanya kata umum, angka, atau simbol). "
                "Tulis ulasan dengan kata yang lebih spesifik tentang pelabuhan."
            )
        input_for_model = final_text

        # 2. Prediksi
        probabilities = self.pipeline.predict_proba([input_for_model])[0]
        classes = self.pipeline.classes_
        prob_dict = {
            str(cls): float(round(prob, 4))
            for cls, prob in zip(classes, probabilities)
        }

        sorted_probs = sorted(prob_dict.items(), key=lambda x: x[1], reverse=True)
        top_class, top_prob = sorted_probs[0]
        second_class, second_prob = sorted_probs[1]

        # [FIX 3] Threshold NETRAL hanya dipakai kalau diaktifkan.
        if self.use_neutral_threshold and (top_prob - second_prob) < self.neutral_margin:
            prediction = "NETRAL"
        else:
            prediction = top_class

        return prediction, prob_dict

    def process_dataframe(self, df, text_column="final_text"):
        """
        Prediksi sentimen untuk seluruh baris pada DataFrame.

        [FIX 2] `final_text` diasumsikan sudah diproses sebelumnya
        (cleaning/slang/stemming). Jangan preprocessing ulang di sini
        untuk menghindari double preprocessing.
        """
        # [FIX 1c] Empty DF: pastikan dtype string, bukan list kosong.
        if df.empty:
            df["sentiment"] = pd.Series(dtype="object")
            return df

        # [FIX 1c] Kolom tidak ada → error jelas, bukan diam-diam kosong.
        if text_column not in df.columns:
            raise ValueError(
                f"Kolom '{text_column}' tidak ditemukan pada dataset. "
                f"Kolom tersedia: {list(df.columns)}"
            )

        texts = df[text_column].fillna("").astype(str).tolist()
        df["sentiment"] = self.pipeline.predict(texts)
        return df


def run_analysis_job(
    input_csv=os.path.join("data", "processed", "review_processed(fix).csv"),
    output_predicted_csv=os.path.join("data", "processed", "review_predicted(fix).csv"),
    output_recap_csv=os.path.join("data", "processed", "rekap_sentimen_pelabuhan(fix).csv"),
    use_neutral_threshold=False,
    neutral_margin=0.10,
):
    if not os.path.exists(input_csv):
        return False, (
            f"Data preprocessing tidak ditemukan: {input_csv}. "
            "Jalankan preprocessing terlebih dahulu."
        )

    try:
        df = pd.read_csv(input_csv)
    except Exception as e:
        return False, f"Gagal membaca data preprocessing: {e}"

    if df.empty:
        return False, "Data hasil preprocessing kosong."

    try:
        analyzer = SVMSentimentAnalyzer(
            use_neutral_threshold=use_neutral_threshold,
            neutral_margin=neutral_margin,
        )
    except FileNotFoundError:
        return False, "Model belum dilatih. Jalankan training model terlebih dahulu."

    try:
        # [FIX 1d] Pastikan folder output ada sebelum menyimpan.
        for path in (output_predicted_csv, output_recap_csv):
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)

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

        if use_neutral_threshold:
            msg += f" Threshold NETRAL aktif (margin={neutral_margin:.2f})."
        else:
            msg += " Threshold NETRAL OFF (prediksi asli SVM)."

        return True, msg
    except ValueError as e:
        # dari process_dataframe jika kolom tidak ada
        return False, str(e)
    except Exception as e:
        return False, f"Analisis gagal: {e}"


def analyze_and_recap_harbors(use_neutral_threshold=False, neutral_margin=0.10):
    success, msg = run_analysis_job(
        use_neutral_threshold=use_neutral_threshold,
        neutral_margin=neutral_margin,
    )
    print(("✅ " if success else "❌ ") + msg)


if __name__ == "__main__":
    # [FIX 3] Default: threshold NETRAL OFF.
    # Kalau nanti ingin mengaktifkan (mis. berdasarkan hasil validasi),
    # panggil dengan analyze_and_recap_harbors(use_neutral_threshold=True).
    analyze_and_recap_harbors()