import argparse
import hashlib
import json
import os
import re
import sys
import time
import emoji
import pandas as pd
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory
from deep_translator import GoogleTranslator
from deep_translator.exceptions import TooManyRequests, RequestError, TranslationNotFound
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0

# =============================================================================
# KONFIGURASI
# =============================================================================
NEGATION_WORDS = {'tidak', 'tak', 'bukan', 'belum', 'jangan', 'kurang', 'tanpa'}

DOMAIN_STOPWORDS = {
    'pelabuhan', 'ferry', 'terminal', 'batam', 'centre', 'center', 'sekupang',
    'punggur', 'telaga', 'nongsapura', 'harbour', 'bay', 'singapore', 'singapura',
    'bintan', 'tanjung', 'pinang', 'kapal', 'tiket', 'nya', 'yg', 'di', 'ke', 'dari',
    'ini', 'itu', 'untuk', 'dan', 'dengan', 'ada', 'bisa', 'sudah', 'sangat',
}

CUSTOM_STOPWORDS = set()

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

# Input mengikuti output scraper.py
INPUT_PATH = os.path.join("data", "raw", "review_pelabuhan1.csv")

# Output standar yang dibaca predict.py / train_model2.py
OUTPUT_DIR = os.path.join("data", "processed")
OUTPUT_FILENAME = "review_processed.csv"

TEXT_COL = 'review'
SENTIMENT_COL = 'sentimen'

OUTPUT_COLUMNS = [
    'lokasi', 'pelabuhan', 'nama_reviewer', 'rating',
    'tanggal', 'tanggal_estimasi',
    'review',
    'ada_foto', 'scraped_at',
    'valid_text', 'lang', 'translated_text', 'semi_clean_text', 'final_text',
]

ALLOWED_LANGS = {'id', 'en', 'ms'}
TRANSLATE_LANGS = {'en'}     # bahasa sumber yang perlu diterjemahkan ke Indonesia
MIN_WORDS_FOR_DETECTION = 3
MAX_TRANSLATE_CHARS = 4900

# --- Rate limit & cache ---
TRANSLATE_MIN_INTERVAL = 0.35         # detik antar request (≈3 req/detik, di bawah limit 5)
TRANSLATE_MAX_RETRIES = 4
TRANSLATE_BACKOFF_BASE = 2.0          # 2, 4, 8, 16 detik
TRANSLATE_RATE_LIMIT_COOLDOWN = 30.0  # jeda tambahan saat kena TooManyRequests

# Env var untuk skip translate (berguna saat testing / dataset besar)
SKIP_TRANSLATE = os.environ.get("SKIP_TRANSLATE", "0") == "1"


def _norm_set(words):
    return {str(w).strip().lower() for w in words if str(w).strip()}


class TextPreprocessor:
    def __init__(
        self,
        negation_words=None,
        domain_stopwords=None,
        custom_stopwords=None,
        slang_dict=None,
        skip_translate=None,
    ):
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

        self.all_stopwords = (
            (self.base_stopwords | self.domain_stopwords) - self.negation_words
        ) | self.custom_stopwords

        stemmed_negation = {self._stem_word(w) for w in self.negation_words}
        stemmed_domain = {self._stem_word(w) for w in self.domain_stopwords}
        self.stemmed_custom_stopwords = {
            self._stem_word(w) for w in self.custom_stopwords
        } - {''}
        self.stemmed_domain_stopwords = (stemmed_domain - stemmed_negation) - {''}

        # --- translasi: cache + throttle ---
        self.skip_translate = SKIP_TRANSLATE if skip_translate is None else skip_translate
        self._translate_cache_path = os.path.join(OUTPUT_DIR, ".translate_cache.json")
        self._translate_cache = self._load_translate_cache()
        self._last_translate_ts = 0.0
        self._dirty_cache = False

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------
    def _load_translate_cache(self):
        if os.path.exists(self._translate_cache_path):
            try:
                with open(self._translate_cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_translate_cache(self):
        if not self._dirty_cache:
            return
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(self._translate_cache_path, "w", encoding="utf-8") as f:
                json.dump(self._translate_cache, f, ensure_ascii=False)
            self._dirty_cache = False
        except Exception as e:
            print(f"⚠️  Gagal menyimpan cache translasi: {e}", file=sys.stderr)

    @staticmethod
    def _cache_key(text):
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Stems
    # ------------------------------------------------------------------
    def _stem_word(self, word):
        if word not in self._stem_cache:
            self._stem_cache[word] = self.stemmer.stem(word)
        return self._stem_cache[word]

    # ------------------------------------------------------------------
    # Dedup
    # ------------------------------------------------------------------
    def deduplicate_reviews(self, df, text_col=TEXT_COL):
        if df.empty or text_col not in df.columns:
            stats = {"before": len(df), "after": len(df), "removed": 0, "subset": []}
            df.attrs["dedup_stats"] = stats
            return df, stats

        subset = [
            c for c in ("pelabuhan", "nama_reviewer", "rating", text_col)
            if c in df.columns
        ]
        if text_col not in subset:
            subset = [text_col]

        before = len(df)
        df = df.drop_duplicates(subset=subset, keep="first").copy()
        stats = {
            "before": before,
            "after": len(df),
            "removed": before - len(df),
            "subset": subset,
        }
        df.attrs["dedup_stats"] = stats
        return df, stats

    # ------------------------------------------------------------------
    # Deteksi bahasa
    # ------------------------------------------------------------------
    def detect_and_filter_language(self, text):
        if text is None:
            return None, None
        text = str(text)
        if not text.strip():
            return None, None

        probe = re.sub(r'http\S+|www\S+', '', text)
        probe = emoji.replace_emoji(probe, replace='')
        words = re.findall(r'[A-Za-z]+', probe)

        if not words:
            return None, None

        if len(words) < MIN_WORDS_FOR_DETECTION:
            return text, 'id'

        try:
            lang = detect(probe)
        except Exception:
            return None, None

        if lang in ALLOWED_LANGS:
            return text, lang
        return None, None

    # ------------------------------------------------------------------
    # Translasi (throttle + cache + retry)
    # ------------------------------------------------------------------
    def _throttle(self):
        elapsed = time.time() - self._last_translate_ts
        if elapsed < TRANSLATE_MIN_INTERVAL:
            time.sleep(TRANSLATE_MIN_INTERVAL - elapsed)

    def translate_if_needed(self, text, lang, retries=None):
        if self.skip_translate or lang not in TRANSLATE_LANGS:
            return text

        retries = TRANSLATE_MAX_RETRIES if retries is None else retries
        text = str(text)
        if not text.strip():
            return text

        key = self._cache_key(text)
        if key in self._translate_cache:
            return self._translate_cache[key]

        self._throttle()
        result = text

        for attempt in range(retries + 1):
            try:
                translator = GoogleTranslator(source='auto', target='id')
                out = translator.translate(text[:MAX_TRANSLATE_CHARS])
                if isinstance(out, str) and out.strip():
                    result = out
                break

            except TooManyRequests:
                wait = TRANSLATE_RATE_LIMIT_COOLDOWN * (attempt + 1)
                print(
                    f"⚠️  TooManyRequests (attempt {attempt+1}/{retries+1}). "
                    f"Tunggu {wait:.0f}s...",
                    file=sys.stderr,
                )
                time.sleep(wait)

            except (RequestError, TranslationNotFound) as e:
                wait = TRANSLATE_BACKOFF_BASE ** attempt
                print(
                    f"⚠️  Translasi error ({type(e).__name__}, attempt "
                    f"{attempt+1}/{retries+1}). Retry dalam {wait:.0f}s...",
                    file=sys.stderr,
                )
                time.sleep(wait)

            except Exception as e:
                # exception tak terduga: jangan buang seluruh proses
                print(
                    f"⚠️  Translasi gagal tak terduga ({type(e).__name__}: {e}). "
                    f"Pakai teks asli.",
                    file=sys.stderr,
                )
                break

            # kalau berhasil, break
        else:
            print("⚠️  Batas retry translasi tercapai. Pakai teks asli.", file=sys.stderr)

        self._last_translate_ts = time.time()
        self._translate_cache[key] = result
        self._dirty_cache = True
        return result

    # ------------------------------------------------------------------
    # Cleaning
    # ------------------------------------------------------------------
    def clean_text(self, text):
        text = str(text).lower()

        # --- FIX: hapus tombol UI Google Maps (SEBELUM lowercase hilang) ---
        ui_patterns = [
            r"lihat terjemahan\s*\([^)]*\)",
            r"lihat terjemahan\b",
            r"lihat terjemahan lainnya\b",
            r"terjemahkan ulasan ini\b",
            r"see translation\s*\([^)]*\)",
            r"see translation\b",
            r"see original\s*\([^)]*\)",
            r"see original\b",
            r"translated by google\b",
            r"diterjemahkan oleh google\b",
            r"\(translated by google\)",
            r"\(diterjemahkan oleh google\)",
            r"\(original\)",
            r"\(asli\)",
        ]
        for pat in ui_patterns:
            text = re.sub(pat, " ", text, flags=re.IGNORECASE)

        text = emoji.replace_emoji(text, replace='')
        text = re.sub(r'(https?://\S+|www\.\S+)', ' ', text)
        text = re.sub(r'[^a-z\s]', ' ', text)
        text = re.sub(r'(.)\1{2,}', r'\1', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def normalize_slang(self, text):
        return ' '.join(self.slang_dict.get(w, w) for w in text.split())

    def remove_stopwords_and_stem(self, text):
        words = [w for w in text.split() if w not in self.all_stopwords]
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

    # ------------------------------------------------------------------
    # Pipeline dataframe
    # ------------------------------------------------------------------
    def process_dataframe(self, df, text_col=TEXT_COL, sentiment_col=SENTIMENT_COL):
        if df.empty or text_col not in df.columns:
            return df

        if sentiment_col not in df.columns:
            sentiment_col = None

        df = df.dropna(subset=[text_col]).copy()
        df[text_col] = df[text_col].astype(str)

        df, dedup_stats = self.deduplicate_reviews(df, text_col)

        detected = [self.detect_and_filter_language(t) for t in df[text_col]]
        df['valid_text'] = [r[0] for r in detected]
        df['lang'] = [r[1] for r in detected]
        df = df.dropna(subset=['valid_text']).copy()

        if df.empty:
            df.attrs['sentiment_col'] = sentiment_col
            df.attrs['dedup_stats'] = dedup_stats
            return df

        # --- Translasi dengan progress ---
        total = len(df)
        need_translate = int(sum(1 for l in df['lang'] if l in TRANSLATE_LANGS))
        if need_translate and not self.skip_translate:
            cached_count = int(sum(
                1 for t in df['valid_text']
                if self._cache_key(str(t)) in self._translate_cache
            ))
            print(
                f"🌐 Translasi: {need_translate} baris perlu diterjemahkan "
                f"(cache hit: {cached_count}). Skip={self.skip_translate}",
                file=sys.stderr,
            )
        elif self.skip_translate:
            print("🌐 Translasi dimatikan (SKIP_TRANSLATE=1).", file=sys.stderr)

        translated = []
        for i, (txt, lang) in enumerate(zip(df['valid_text'], df['lang']), 1):
            translated.append(self.translate_if_needed(txt, lang))
            if need_translate and i % 25 == 0:
                print(f"   · translasi {i}/{total}", file=sys.stderr)

        df['translated_text'] = translated
        self.save_translate_cache()  # simpan cache segera setelah batch

        df['semi_clean_text'] = df['translated_text'].apply(self.clean_text)
        df['semi_clean_text'] = df['semi_clean_text'].apply(self.normalize_slang)
        df['final_text'] = df['semi_clean_text'].apply(self.remove_stopwords_and_stem)

        df = df[df['final_text'].str.strip() != ''].reset_index(drop=True)

        if df.empty:
            df.attrs['sentiment_col'] = sentiment_col
            df.attrs['dedup_stats'] = dedup_stats
            return df

        ordered = [c for c in OUTPUT_COLUMNS if c in df.columns]
        if text_col not in ordered:
            ordered.append(text_col)
        if sentiment_col:
            ordered = [c for c in ordered if c != sentiment_col]
            ordered.insert(ordered.index(text_col) + 1, sentiment_col)
        rest = [c for c in df.columns if c not in ordered]
        df = df[ordered + rest]

        df.attrs['sentiment_col'] = sentiment_col
        df.attrs['dedup_stats'] = dedup_stats
        return df


# =============================================================================
# Entry point
# =============================================================================
def run_preprocessing_job(
    raw_path=INPUT_PATH,
    out_dir=OUTPUT_DIR,
    text_col=TEXT_COL,
    sentiment_col=SENTIMENT_COL,
    skip_translate=None,
):
    out_path = os.path.join(out_dir, OUTPUT_FILENAME)

    if not os.path.exists(raw_path):
        return False, (
            f"File data mentah tidak ditemukan: {raw_path}. "
            "Jalankan scraping terlebih dahulu (data/raw/review_pelabuhan1.csv)."
        )

    try:
        df_raw = pd.read_csv(raw_path)
    except Exception as e:
        return False, f"Gagal membaca file data mentah: {e}"

    if df_raw.empty:
        return False, "Data mentah kosong."

    if text_col not in df_raw.columns:
        return False, f"Kolom '{text_col}' tidak ditemukan pada data mentah."

    if 'tanggal_estimasi' not in df_raw.columns:
        print(
            "⚠️  Kolom 'tanggal_estimasi' tidak ada di data mentah. "
            "Filter tanggal di dashboard hanya bisa memakai fallback parser di JS. "
            "Jalankan ulang scraper untuk hasil paling akurat.",
            file=sys.stderr,
        )

    try:
        preprocessor = TextPreprocessor(skip_translate=skip_translate)
        df_processed = preprocessor.process_dataframe(
            df_raw, text_col=text_col, sentiment_col=sentiment_col
        )
        # simpan cache sekali lagi (jika ada baris sisa)
        preprocessor.save_translate_cache()
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
        else " Kolom sentimen tidak ditemukan (normal — label dibuat saat prediksi)."
    )

    dedup_stats = df_processed.attrs.get("dedup_stats", {})
    dedup_note = (
        f" Duplikat dibuang: {dedup_stats.get('removed', 0)} baris."
        if dedup_stats
        else ""
    )

    return True, (
        f"Preprocessing selesai! {len(df_processed)} dari {len(df_raw)} ulasan "
        f"bersih tersimpan di {out_path}." + dedup_note + sentiment_note
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Preprocessing ulasan: deteksi bahasa, terjemahan, pembersihan, "
                    "normalisasi slang, stopword, dan stemming (Sastrawi)."
    )
    parser.add_argument("-i", "--input", default=None,
                        help=f"path CSV input (default: {INPUT_PATH})")
    parser.add_argument("-o", "--output-dir", default=None,
                        help=f"folder hasil; nama file: {OUTPUT_FILENAME} "
                             f"(default folder: {OUTPUT_DIR})")
    parser.add_argument("--text-col", default=None,
                        help=f"nama kolom teks ulasan (default: {TEXT_COL})")
    parser.add_argument("--sentiment-col", default=None,
                        help=f"nama kolom sentimen; disimpan jika ada (default: {SENTIMENT_COL})")
    parser.add_argument("--no-translate", action="store_true",
                        help="Lewati translasi (berguna saat rate-limited).")
    parser.add_argument("--clear-cache", action="store_true",
                        help="Hapus cache translasi sebelum mulai.")

    args = parser.parse_args(argv)

    if args.clear_cache:
        cache_path = os.path.join(
            args.output_dir or OUTPUT_DIR, ".translate_cache.json"
        )
        if os.path.exists(cache_path):
            os.remove(cache_path)
            print(f"🧹 Cache dihapus: {cache_path}", file=sys.stderr)

    overrides = {
        "raw_path": args.input,
        "out_dir": args.output_dir,
        "text_col": args.text_col,
        "sentiment_col": args.sentiment_col,
        "skip_translate": True if args.no_translate else None,
    }
    ok, message = run_preprocessing_job(
        **{k: v for k, v in overrides.items() if v is not None}
    )
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())