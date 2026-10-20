import argparse
import os
import sys
import re
import time
import emoji
import pandas as pd
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory
from deep_translator import GoogleTranslator
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0

# =============================================================================
# KONFIGURASI (bagian ini bebas diubah / diisi manual)
# =============================================================================

# Kata negasi: tidak dibuang sebagai stopword dan tidak di-stem,
# karena "tidak bagus" dan "bagus" berlawanan sentimen.
NEGATION_WORDS = {'tidak', 'tak', 'bukan', 'belum', 'jangan', 'kurang', 'tanpa'}

# Stopword khusus domain (nama tempat, istilah yang muncul di hampir semua ulasan).
DOMAIN_STOPWORDS = {
    'pelabuhan', 'ferry', 'terminal', 'batam', 'centre', 'center', 'sekupang',
    'punggur', 'telaga', 'nongsapura', 'harbour', 'bay', 'singapore', 'singapura',
    'bintan', 'tanjung', 'pinang', 'kapal', 'tiket', 'nya', 'yg', 'di', 'ke', 'dari',
    'ini', 'itu', 'untuk', 'dan', 'dengan', 'ada', 'bisa', 'sudah', 'sangat',
}

# Stopword kustom: isi dengan kata apa pun yang ingin DIBUANG dari teks.
#  - Tulis dalam huruf kecil, bentuk baku (dicocokkan SETELAH normalisasi slang,
#    jadi tulis 'banget', bukan 'bgt').
#  - Kata di sini SELALU dibuang, termasuk jika juga ada di NEGATION_WORDS.
#  - Varian berimbuhan ikut tersaring lewat pencocokan hasil stemming
#    (mis. 'kapal' juga membuang 'kapalnya').
CUSTOM_STOPWORDS = {
    # 'contoh', 'kata', 'lain',
}

# Kamus normalisasi slang: 'bentuk tidak baku': 'bentuk baku'
SLANG_DICT = {
    'bgus': 'bagus', 'bgt': 'banget', 'bgs': 'bagus', 'brg': 'barang',
    'klo': 'kalau', 'klw': 'kalau', 'kl': 'kalau',
    'tdk': 'tidak', 'gak': 'tidak', 'ga': 'tidak', 'gk': 'tidak',
    'nggak': 'tidak', 'ngga': 'tidak', 'enggak': 'tidak', 'engga': 'tidak',
    'nggk': 'tidak', 'tak': 'tidak',
    'dgn': 'dengan', 'dg': 'dengan', 'krn': 'karena', 'karna': 'karena',
    'tp': 'tapi', 'cpt': 'cepat', 'lmbat': 'lambat', 'lmbt': 'lambat',
    'udh': 'sudah', 'sdh': 'sudah', 'blm': 'belum', 'jgn': 'jangan',
    'bs': 'bisa', 'sy': 'saya', 'org': 'orang', 'jg': 'juga', 'sm': 'sama',
    'yg': 'yang', 'utk': 'untuk', 'dr': 'dari', 'trs': 'terus',
    'mantab': 'mantap', 'oke': 'ok',
}

# Default path & nama kolom. HANYA didefinisikan di sini; dipakai oleh
# run_preprocessing_job() (mis. dari app.py) dan oleh main() (terminal).
INPUT_PATH = os.path.join("data", "processed", "review_processed(4k).csv")
OUTPUT_DIR = os.path.join("data", "processed")
OUTPUT_FILENAME = "review_processed(4k)1.csv"
TEXT_COL = 'review'

# Nama kolom sentimen di CSV. Jika kolom ini ada, ikut disimpan ke CSV hasil
# (diletakkan tepat setelah kolom teks).
SENTIMENT_COL = 'sentimen'

# Urutan kolom pada CSV hasil. Kolom yang tidak ada di data dilewati;
# kolom lain yang tidak tercantum di sini ditaruh di paling akhir.
OUTPUT_COLUMNS = [
    'lokasi', 'pelabuhan', 'nama_reviewer', 'rating', 'tanggal', 'review',
    'has_photo', 'is_localguide', 'scraped_at',
    'valid_text', 'lang', 'translated_text', 'semi_clean_text', 'final_text',
]

# Bahasa yang diterima dan bahasa yang diterjemahkan.
# 'ms' sering salah deteksi untuk teks Indonesia informal, jadi tidak diterjemahkan.
ALLOWED_LANGS = {'id', 'en', 'ms'}
TRANSLATE_LANGS = {'en'}

# Teks yang terlalu pendek tidak bisa dideteksi bahasanya dengan andal.
MIN_WORDS_FOR_DETECTION = 3
MAX_TRANSLATE_CHARS = 4900


def _norm_set(words):
    """Huruf kecil + buang spasi/kosong, supaya isian manual tidak gampang salah."""
    return {str(w).strip().lower() for w in words if str(w).strip()}


class TextPreprocessor:
    def __init__(
        self,
        negation_words=None,
        domain_stopwords=None,
        custom_stopwords=None,
        slang_dict=None,
    ):
        """Semua argumen opsional; jika None dipakai konfigurasi di bagian atas file."""
        factory_stem = StemmerFactory()
        self.stemmer = factory_stem.create_stemmer()
        self._stem_cache = {}

        factory_stop = StopWordRemoverFactory()
        self.base_stopwords = set(factory_stop.get_stop_words())

        self.negation_words = _norm_set(
            NEGATION_WORDS if negation_words is None else negation_words
        )
        self.domain_stopwords = _norm_set(
            DOMAIN_STOPWORDS if domain_stopwords is None else domain_stopwords
        )
        self.custom_stopwords = _norm_set(
            CUSTOM_STOPWORDS if custom_stopwords is None else custom_stopwords
        )
        raw_slang = SLANG_DICT if slang_dict is None else slang_dict
        self.slang_dict = {
            str(k).strip().lower(): str(v).strip().lower() for k, v in raw_slang.items()
        }

        # Stopword bawaan Sastrawi + domain, dikurangi negasi; lalu stopword kustom
        # ditambahkan terakhir sehingga selalu menang.
        self.all_stopwords = (
            (self.base_stopwords | self.domain_stopwords) - self.negation_words
        ) | self.custom_stopwords

        # Versi hasil stemming, agar varian seperti "pelabuhannya" / "kapalnya"
        # yang lolos sebelum stemming tetap tersaring.
        stemmed_negation = {self._stem_word(w) for w in self.negation_words}
        stemmed_domain = {self._stem_word(w) for w in self.domain_stopwords}
        self.stemmed_custom_stopwords = {
            self._stem_word(w) for w in self.custom_stopwords
        } - {''}
        self.stemmed_domain_stopwords = (stemmed_domain - stemmed_negation) - {''}

    # ------------------------------------------------------------------ helpers
    def _stem_word(self, word):
        if word not in self._stem_cache:
            self._stem_cache[word] = self.stemmer.stem(word)
        return self._stem_cache[word]

    # ------------------------------------------------------- language detection
    def detect_and_filter_language(self, text):
        if text is None:
            return None, None
        text = str(text)
        if not text.strip():
            return None, None

        # Bersihkan URL & emoji hanya untuk keperluan deteksi
        probe = re.sub(r'http\S+|www\S+', '', text)
        probe = emoji.replace_emoji(probe, replace='')
        words = re.findall(r'[A-Za-z]+', probe)

        if not words:
            # Tidak ada huruf (hanya emoji/angka/simbol) -> tidak ada isi yang bisa dianalisis
            return None, None

        if len(words) < MIN_WORDS_FOR_DETECTION:
            # Terlalu pendek (mis. "bagus", "mantap"): langdetect tidak andal,
            # jadi diasumsikan bahasa Indonesia agar ulasan singkat tidak terbuang.
            return text, 'id'

        try:
            lang = detect(probe)
        except Exception:
            return None, None

        if lang in ALLOWED_LANGS:
            return text, lang
        return None, None

    # -------------------------------------------------------------- translation
    def translate_if_needed(self, text, lang, retries=2):
        if lang not in TRANSLATE_LANGS:
            return text

        for attempt in range(retries + 1):
            try:
                translator = GoogleTranslator(source='auto', target='id')
                result = translator.translate(text[:MAX_TRANSLATE_CHARS])
                if isinstance(result, str) and result.strip():
                    return result
                return text
            except Exception:
                if attempt < retries:
                    time.sleep(1 + attempt)
        return text

    # ----------------------------------------------------------------- cleaning
    def clean_text(self, text):
        text = str(text).lower()
        text = emoji.replace_emoji(text, replace='')
        text = re.sub(r'(https?://\S+|www\.\S+)', ' ', text)
        text = re.sub(r'[^a-z\s]', ' ', text)
        # "baguuuus" / "mantapppp" -> "bagus" / "mantap"
        text = re.sub(r'(.)\1{2,}', r'\1', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def normalize_slang(self, text):
        return ' '.join(self.slang_dict.get(w, w) for w in text.split())

    def remove_stopwords_and_stem(self, text):
        words = [w for w in text.split() if w not in self.all_stopwords]
        # Kata negasi tidak di-stem agar tidak berubah makna (mis. "bukan" -> "buka")
        stemmed = [
            w if (w in self.negation_words and w not in self.custom_stopwords)
            else self._stem_word(w)
            for w in words
        ]

        result = []
        for w in stemmed:
            if not w or w in self.stemmed_custom_stopwords:
                continue
            is_negation = w in self.negation_words
            if not is_negation and w in self.stemmed_domain_stopwords:
                continue
            result.append(w)
        return ' '.join(result)

    # ----------------------------------------------------------------- pipeline
    def process_dataframe(self, df, text_col=TEXT_COL, sentiment_col=SENTIMENT_COL):
        """
        Jika kolom `sentiment_col` ada, ia dipertahankan dan diletakkan tepat setelah
        kolom teks. Jika tidak ada, tidak ada kolom sentimen di hasil.
        """
        if df.empty or text_col not in df.columns:
            return df

        if sentiment_col not in df.columns:
            sentiment_col = None

        df = df.dropna(subset=[text_col]).copy()
        df[text_col] = df[text_col].astype(str)
        df = df.drop_duplicates(subset=[text_col]).copy()

        detected = [self.detect_and_filter_language(t) for t in df[text_col]]
        df['valid_text'] = [r[0] for r in detected]
        df['lang'] = [r[1] for r in detected]
        df = df.dropna(subset=['valid_text']).copy()

        if df.empty:
            return df

        df['translated_text'] = [
            self.translate_if_needed(t, l) for t, l in zip(df['valid_text'], df['lang'])
        ]

        df['semi_clean_text'] = df['translated_text'].apply(self.clean_text)
        df['semi_clean_text'] = df['semi_clean_text'].apply(self.normalize_slang)
        df['final_text'] = df['semi_clean_text'].apply(self.remove_stopwords_and_stem)

        df = df[df['final_text'].str.strip() != ''].reset_index(drop=True)

        # Susun kolom sesuai OUTPUT_COLUMNS; sentimen (jika ada) tepat setelah kolom teks;
        # kolom lain yang tidak terdaftar ditaruh di akhir agar datanya tidak hilang.
        ordered = [c for c in OUTPUT_COLUMNS if c in df.columns]
        if text_col not in ordered:
            ordered.append(text_col)
        if sentiment_col:
            ordered = [c for c in ordered if c != sentiment_col]
            ordered.insert(ordered.index(text_col) + 1, sentiment_col)
        rest = [c for c in df.columns if c not in ordered]
        df = df[ordered + rest]
        df.attrs['sentiment_col'] = sentiment_col
        return df


def run_preprocessing_job(
    raw_path=INPUT_PATH,
    out_dir=OUTPUT_DIR,
    text_col=TEXT_COL,
    sentiment_col=SENTIMENT_COL,
):
    out_path = os.path.join(out_dir, OUTPUT_FILENAME)

    if not os.path.exists(raw_path):
        return False, "File data mentah tidak ditemukan. Jalankan scraping terlebih dahulu."

    try:
        df_raw = pd.read_csv(raw_path)
    except Exception as e:
        return False, f"Gagal membaca file data mentah: {e}"

    if df_raw.empty:
        return False, "Data mentah kosong."

    if text_col not in df_raw.columns:
        return False, f"Kolom '{text_col}' tidak ditemukan pada data mentah."

    try:
        preprocessor = TextPreprocessor()
        df_processed = preprocessor.process_dataframe(
            df_raw, text_col=text_col, sentiment_col=sentiment_col
        )
    except Exception as e:
        return False, f"Preprocessing gagal: {e}"

    if df_processed.empty:
        return False, "Tidak ada ulasan yang tersisa setelah preprocessing."

    os.makedirs(out_dir, exist_ok=True)
    df_processed.to_csv(out_path, index=False, encoding="utf-8-sig")

    used_sentiment = df_processed.attrs.get('sentiment_col')
    sentiment_note = (
        f" Kolom sentimen '{used_sentiment}' ikut disimpan."
        if used_sentiment
        else " Kolom sentimen tidak ditemukan, tidak disimpan."
    )
    return True, (
        f"Preprocessing selesai! {len(df_processed)} dari {len(df_raw)} ulasan "
        f"bersih tersimpan." + sentiment_note
    )

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Preprocessing ulasan: deteksi bahasa, terjemahan, pembersihan, "
                    "normalisasi slang, stopword, dan stemming (Sastrawi)."
    )
    # Semua default sengaja None: nilai default hanya didefinisikan satu kali di
    # bagian KONFIGURASI (dipakai run_preprocessing_job). Opsi hanya diteruskan
    # jika diisi di terminal.
    parser.add_argument(
        "-i", "--input", default=None,
        help=f"path CSV input (default: {INPUT_PATH})",
    )
    parser.add_argument(
        "-o", "--output-dir", default=None,
        help=f"folder hasil; nama file: {OUTPUT_FILENAME} (default folder: {OUTPUT_DIR})",
    )
    parser.add_argument(
        "--text-col", default=None,
        help=f"nama kolom teks ulasan (default: {TEXT_COL})",
    )
    parser.add_argument(
        "--sentiment-col", default=None,
        help=f"nama kolom sentimen; disimpan jika ada (default: {SENTIMENT_COL})",
    )
    args = parser.parse_args(argv)

    overrides = {
        "raw_path": args.input,
        "out_dir": args.output_dir,
        "text_col": args.text_col,
        "sentiment_col": args.sentiment_col,
    }
    ok, message = run_preprocessing_job(
        **{k: v for k, v in overrides.items() if v is not None}
    )
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1
 
 
if __name__ == "__main__":
    sys.exit(main())