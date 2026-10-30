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

# Kata generik — dihapus baik dari semi_clean_text maupun final_text.
DOMAIN_STOPWORDS = {
    'pelabuhan', 'ferry', 'terminal', 'batam', 'centre', 'center',
    'sekupang', 'punggur', 'telaga', 'nongsapura',
    'harbour', 'bay',
}

# [FIX B] Nama lokasi tujuan TIDAK dihapus dari semi_clean_text (untuk relevance
# filter & audit). Hanya dihapus setelah stemming untuk final_text.
# Kalau penelitian tidak butuh info rute, boleh dibiarkan aktif.
LOCATION_STOPWORDS_FOR_FINAL = {
    'singapore', 'singapura', 'bintan', 'tanjung', 'pinang',
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

# Kata kunci ID: prioritaskan kata bermakna, bukan penghubung.
ID_KEYWORDS = {
    # eksisting — kata bermakna
    'bagus', 'baik', 'buruk', 'jelek', 'sangat', 'nyaman',
    'pelayanan', 'pelayanannya', 'fasilitas', 'fasilitasnya',
    'bersih', 'kotor', 'ramai', 'sepi', 'parkir', 'parkirnya',
    'susah', 'mudah', 'sulit', 'dekat', 'jauh',
    'tidak', 'bukan', 'nggak', 'gak', 'tak',
    'saya', 'kami', 'kita', 'mereka',
    'dengan', 'yang', 'untuk', 'karena', 'tetapi', 'tapi',
    'bisa', 'sudah', 'belum', 'udah',
    'mantap', 'mantab', 'lumayan', 'oke', 'keren',
    'senang', 'seneng', 'suka', 'benci', 'puas', 'kecewa',
    'mahal', 'murah', 'cepat', 'lambat',
    'banyak', 'sedikit', 'juga', 'atau', 'saja',
    'selalu', 'sering', 'jarang',
    'banget', 'bgt', 'sekali',

    # [TAMBAHAN] kata kerja & kata benda umum
    'bayar', 'beli', 'pesan', 'pergi', 'datang', 'masuk', 'keluar',
    'tunggu', 'antri', 'antre', 'jalan', 'bawa', 'beri',
    'uang', 'harga', 'biaya', 'ongkos', 'tiket',
    'makanan', 'minuman', 'toilet', 'kamar',

    # [TAMBAHAN] kata sifat
    'panas', 'dingin', 'bau', 'lama', 'baru', 'besar', 'kecil',

    # [TAMBAHAN] kata hubung khas ID — 'dan', 'di', 'ke', 'dari' dst.
    'dan', 'di', 'ke', 'dari', 'pada', 'dalam', 'ini', 'itu',
    'masih', 'hanya', 'telah', 'pernah', 'lagi', 'harus', 'mau', 'ada',

    # [TAMBAHAN] loanword umum di review ID
    'checkin', 'online', 'taxi', 'order',
}

# Kata kunci EN: prioritaskan kata bermakna. Kata hubung umum
# ('and', 'or', 'if', 'to', 'of', 'in', 'out', 'get', 'got',
#  'do', 'does', 'did', 'can', 'will', 'for', 'on', 'at', 'by',
#  'just', 'only', 'also', 'still', 'even') SENGAJA DIHAPUS agar
# teks campur ID-EN tidak keliru dianggap Inggris.
EN_KEYWORDS = {
    # eksisting — kata bermakna
    'good', 'bad', 'great', 'poor', 'nice', 'terrible', 'worst', 'best',
    'awful', 'excellent', 'amazing', 'wonderful', 'horrible', 'fantastic',
    'perfect', 'disgusting', 'disappointing', 'disappointed',
    'clean', 'dirty', 'fast', 'slow', 'expensive', 'cheap', 'friendly',
    'rude', 'crowded', 'comfortable', 'convenient', 'quality', 'worth',
    'waste', 'sucks', 'awesome', 'love', 'hate', 'recommend', 'recommended',
    'very', 'really', 'so', 'too', 'much', 'way',
    'weekend', 'weekday', 'busy', 'quiet', 'calm',
    'beautiful', 'antique', 'view', 'sunset', 'relax', 'picnic', 'suitable',
    'small', 'large', 'big', 'long', 'short', 'quick',
    'wait', 'walk', 'queue', 'queuing', 'boarding', 'lift', 'escalator',
    'aircon', 'wifi', 'bridge', 'mall', 'shop', 'store', 'restaurant',
    'cafe', 'pub', 'staff', 'service', 'ticket',
    'visit', 'vist', 'ride', 'come', 'go', 'back', 'there', 'here',
    'people', 'folks', 'minute', 'hour',
    'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'this', 'that', 'these', 'those', 'with', 'from', 'have', 'has',
    'not', 'no', 'but', 'like', 'they', 'them', 'their',
    'don', 'doesn', 'didn', 'isn', 'aren', 'wasn', 'weren',
    'won', 'wouldn', 'couldn', 'shouldn',
    'could', 'would', 'should',
    'ever', 'never', 'always',
}

# Kata khas Melayu — 'lah', 'tandas', 'dah', 'nak', 'je', 'jer', 'kot'
# dibuang karena juga umum di bahasa Indonesia.
MS_KEYWORDS = {
    'teruk', 'mesra', 'selesa', 'kualiti', 'berbaloi', 'syor',
    'korang', 'sahaja', 'lori',
}

NO_TEXT_MARKERS = {
    '', '[tanpa teks]', 'tanpa teks', '[no text]', 'no text',
    '[empty]', '(empty)',
}

INPUT_PATH = os.path.join("data", "raw", "review_pelabuhan(fix).csv")
INPUT_FALLBACK_PATHS = [
    os.path.join("data", "raw", "review_pelabuhan(fix).csv"),
    os.path.join("data", "raw", "review_pelabuhan(test).csv"),
    os.path.join("data", "raw", "review_pelabuhan1.csv"),
]

OUTPUT_DIR = os.path.join("data", "processed")
OUTPUT_FILENAME = "review_processed(fix).csv"

SAVE_DROPPED_AUDIT = True
AUDIT_DROPPED_FILENAME = "audit_dropped_rows.csv"
DROP_REASON_LABELS = {
    'no_text': 'Ulasan [Tanpa Teks]',
    'no_meaningful_text': 'Tidak ada teks bermakna (emoji/angka saja)',
    'duplicate': 'Duplikat',
    'unsupported_language': 'Bahasa tidak terdeteksi atau tidak didukung',
    'empty_after_stemming': 'Kosong setelah stemming',
}

TEXT_COL = 'review'
SENTIMENT_COL = 'sentimen'

OUTPUT_COLUMNS = [
    'lokasi', 'pelabuhan', 'nama_reviewer', 'rating',
    'tanggal', 'tanggal_estimasi',
    'review',
    'memiliki_foto', 'scraped_at',
    'valid_text', 'lang', 'translated_text', 'translation_status',
    'semi_clean_text', 'final_text',
]

# Bahasa yang dianggap valid untuk keluaran deteksi (termasuk 'und'
# yang menandakan bahasa ambigu namun ulasan TETAP DIPERTAHANKAN).
ALLOWED_LANGS = {'id', 'en', 'ms'}
LANG_UND = 'und'
TRANSLATE_LANGS = {'en', 'ms'}

MIN_WORDS_FOR_DETECTION = 5
MAX_TRANSLATE_CHARS = 4900

TRANSLATE_MIN_INTERVAL = 0.35
TRANSLATE_MAX_RETRIES = 2
TRANSLATE_BACKOFF_BASE = 2.0
TRANSLATE_RATE_LIMIT_COOLDOWN = 30.0

TRANSLATE_CIRCUIT_BREAKER_THRESHOLD = 3
TRANSLATE_CACHE_SAVE_INTERVAL = 5

SKIP_TRANSLATE = os.environ.get("SKIP_TRANSLATE", "0") == "1"

TRANSLATION_STATUSES = {
    "success": "✅ Berhasil diterjemahkan",
    "cached": "📦 Dari cache",
    "not_needed": "➖ Tidak perlu translate",
    "failed_rate_limit": "❌ Gagal: rate limit",
    "failed_other": "❌ Gagal: error lain",
    "skipped_circuit_open": "⏸  Skip: circuit breaker",
}


def _norm_set(words):
    return {str(w).strip().lower() for w in words if str(w).strip()}


def _resolve_input_path(path=None):
    """
    Jika path eksplisit diberikan: strict (tidak fallback).
    Jika None: coba INPUT_FALLBACK_PATHS berurutan.
    """
    if path:
        return path if os.path.isfile(path) else None
    for p in INPUT_FALLBACK_PATHS:
        if os.path.isfile(p):
            return p
    return None


def _print_audit_trail(no_text_stats):
    if not no_text_stats:
        return
    print("\n" + "=" * 60, file=sys.stderr, flush=True)
    print("📊 AUDIT TRAIL DATA", file=sys.stderr, flush=True)
    print("=" * 60, file=sys.stderr, flush=True)
    print(f"  Total data mentah              : {no_text_stats.get('total_awal', 0)}",
          file=sys.stderr, flush=True)
    print(f"  - Ulasan [Tanpa Teks]          : {no_text_stats.get('removed_no_text', 0)}",
          file=sys.stderr, flush=True)
    print(f"  - Tanpa teks bermakna (emoji)  : {no_text_stats.get('removed_no_meaningful', 0)}",
          file=sys.stderr, flush=True)
    print(f"  - Duplikat                     : {no_text_stats.get('removed_dedup', 0)}",
          file=sys.stderr, flush=True)
    print(f"  - Bahasa tidak terdeteksi/didukung: {no_text_stats.get('removed_lang', 0)}",
          file=sys.stderr, flush=True)
    print(f"  - Kosong setelah stemming      : {no_text_stats.get('removed_empty_final', 0)}",
          file=sys.stderr, flush=True)
    print(f"  = Ulasan siap analisis         : {no_text_stats.get('kept', 0)}",
          file=sys.stderr, flush=True)
    print("=" * 60 + "\n", file=sys.stderr, flush=True)


class TextPreprocessor:
    def __init__(self, negation_words=None, domain_stopwords=None,
                 custom_stopwords=None, slang_dict=None,
                 skip_translate=None, out_dir=None,
                 drop_location_from_final=True):
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
        # [FIX B] Nama lokasi hanya dihapus dari final_text (opsional, lewat flag).
        self.drop_location_from_final = bool(drop_location_from_final)
        self.location_stopwords_for_final = (
            _norm_set(LOCATION_STOPWORDS_FOR_FINAL)
            if self.drop_location_from_final else set()
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
        stemmed_location = {self._stem_word(w) for w in self.location_stopwords_for_final}
        self.stemmed_custom_stopwords = {
            self._stem_word(w) for w in self.custom_stopwords
        } - {''}
        self.stemmed_domain_stopwords = (
            (stemmed_domain | stemmed_location) - stemmed_negation
        ) - {''}

        self.skip_translate = SKIP_TRANSLATE if skip_translate is None else skip_translate

        cache_dir = out_dir if out_dir else OUTPUT_DIR
        self._translate_cache_path = os.path.join(cache_dir, ".translate_cache.json")
        self._translate_cache = self._load_translate_cache()
        self._last_translate_ts = 0.0
        self._dirty_cache = False
        self._translator_disabled = False
        self._consecutive_failures = 0
        self._success_since_save = 0

        self.stats = {
            "success": 0, "cached": 0, "failed_rate_limit": 0,
            "failed_other": 0, "skipped_circuit_open": 0, "not_needed": 0,
        }

        self.no_text_stats = {
            "total_awal": 0, "removed_no_text": 0, "removed_no_meaningful": 0,
            "removed_lang": 0, "removed_dedup": 0, "removed_empty_final": 0,
            "kept": 0,
        }

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------
    def _load_translate_cache(self):
        if os.path.exists(self._translate_cache_path):
            try:
                with open(self._translate_cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_translate_cache(self, force=False):
        # [FIX F] Jangan tulis cache kosong (log "Cache saved (0 entri)").
        if not self._translate_cache:
            return
        if not self._dirty_cache and not force:
            return
        try:
            os.makedirs(os.path.dirname(self._translate_cache_path), exist_ok=True)
            tmp = self._translate_cache_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._translate_cache, f, ensure_ascii=False)
            os.replace(tmp, self._translate_cache_path)
            self._dirty_cache = False
            self._success_since_save = 0
            print(f"   💾 Cache saved ({len(self._translate_cache)} entri)",
                  file=sys.stderr, flush=True)
        except Exception as e:
            print(f"⚠️  Gagal menyimpan cache: {e}", file=sys.stderr, flush=True)

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
        subset = [c for c in ("pelabuhan", "nama_reviewer", "rating", "tanggal", text_col)
                  if c in df.columns]
        if text_col not in subset:
            subset = [text_col]
        before = len(df)
        df = df.drop_duplicates(subset=subset, keep="first").copy()
        stats = {"before": before, "after": len(df),
                 "removed": before - len(df), "subset": subset}
        df.attrs["dedup_stats"] = stats
        return df, stats

    # ------------------------------------------------------------------
    # [FIX A, D, E] Deteksi bahasa:
    #   - keyword dihitung berdasarkan FREKUENSI (bukan set unik)
    #   - teks pendek seri → 'und' (bukan default 'id')
    #   - fallback akhir → 'und' (bukan 'id') agar tidak salah klaim
    # ------------------------------------------------------------------
    def detect_and_filter_language(self, text):
        if text is None:
            return None, None, None, 'none'
        text = str(text).strip()
        if not text:
            return None, None, None, 'empty'

        probe = re.sub(r'http\S+|www\S+', '', text)
        probe = emoji.replace_emoji(probe, replace='')
        words = re.findall(r'[A-Za-z]+', probe)

        if not words:
            return None, None, None, 'no_words'

        # [FIX A] Hitung berdasarkan frekuensi, bukan himpunan unik.
        lower_words = [w.lower() for w in words]
        n_words = len(lower_words)
        n_unique = len(set(lower_words))

        id_hits = sum(1 for w in lower_words if w in ID_KEYWORDS)
        en_hits = sum(1 for w in lower_words if w in EN_KEYWORDS)
        ms_hits = sum(1 for w in lower_words if w in MS_KEYWORDS)
        prefix = (f"words={n_words} uniq={n_unique} "
                  f"id={id_hits} en={en_hits} ms={ms_hits}")

        ranked = sorted(
            [('id', id_hits), ('en', en_hits), ('ms', ms_hits)],
            key=lambda x: x[1], reverse=True,
        )
        top_lang, top_hits = ranked[0]
        second_hits = ranked[1][1]

        # (1) Pemenang jelas: >= 2 hit dan >= 2x runner-up
        if top_hits >= 2 and top_hits >= 2 * max(second_hits, 1):
            return text, top_lang, top_lang, f"{prefix} decision={top_lang}(clear)"

        # (2) [FIX D] Teks pendek — tangani skor seri
        if n_words < MIN_WORDS_FOR_DETECTION:
            if top_hits > 0 and top_hits == second_hits:
                return text, LANG_UND, None, (
                    f"{prefix} decision=und(ambiguous_short)"
                )
            if top_lang in ('en', 'ms') and top_hits >= 1 and id_hits == 0:
                return text, top_lang, top_lang, (
                    f"{prefix} decision={top_lang}(short_keyword_only)"
                )
            return text, 'id', 'id', (
                f"{prefix} decision=id(short_default)"
            )

        # (3) Teks panjang → langdetect sebagai tiebreak
        try:
            ld_result = detect(probe)
            ld_note = f"langdetect={ld_result}"
        except Exception as e:
            ld_result = None
            ld_note = f"langdetect_error={type(e).__name__}"

        if ld_result in ALLOWED_LANGS:
            return text, ld_result, ld_result, f"{prefix} {ld_note}"

        # (4) langdetect unsupported → keyword_override, tapi TIDAK fallback ke id
        if id_hits >= 1 and id_hits > max(en_hits, ms_hits):
            return text, 'id', ld_result, (
                f"{prefix} {ld_note} decision=id(keyword_override)"
            )
        if en_hits >= 1 and en_hits > max(id_hits, ms_hits):
            return text, 'en', ld_result, (
                f"{prefix} {ld_note} decision=en(keyword_override)"
            )
        if ms_hits >= 1 and ms_hits > max(id_hits, en_hits):
            return text, 'ms', ld_result, (
                f"{prefix} {ld_note} decision=ms(keyword_override)"
            )

        # [FIX E] Tidak ada pemenang jelas → 'und' (tetap dipertahankan).
        return text, LANG_UND, ld_result, (
            f"{prefix} {ld_note} decision=und(fallback)"
        )

    # ------------------------------------------------------------------
    # Translasi + circuit breaker
    # ------------------------------------------------------------------
    def _throttle(self):
        elapsed = time.time() - self._last_translate_ts
        if elapsed < TRANSLATE_MIN_INTERVAL:
            time.sleep(TRANSLATE_MIN_INTERVAL - elapsed)

    def translate_if_needed(self, text, lang):
        if self.skip_translate:
            return text, "not_needed"
        # 'und' sengaja masuk sini — teks ambigu dibiarkan apa adanya.
        if lang not in TRANSLATE_LANGS:
            self.stats["not_needed"] += 1
            return text, "not_needed"
        text = str(text)
        if not text.strip():
            return text, "not_needed"
        if self._translator_disabled:
            self.stats["skipped_circuit_open"] += 1
            return text, "skipped_circuit_open"

        key = self._cache_key(text)
        if key in self._translate_cache:
            self.stats["cached"] += 1
            return self._translate_cache[key], "cached"

        self._throttle()
        result = text
        success = False
        failure_type = None

        to_translate = text
        if len(text) > MAX_TRANSLATE_CHARS:
            print(f"⚠️  Teks panjang dipotong ({len(text)} → {MAX_TRANSLATE_CHARS}): "
                  f"{text[:50]}...", file=sys.stderr, flush=True)
            to_translate = text[:MAX_TRANSLATE_CHARS]

        for attempt in range(TRANSLATE_MAX_RETRIES + 1):
            try:
                translator = GoogleTranslator(source='auto', target='id')
                out = translator.translate(to_translate)
                if isinstance(out, str) and out.strip():
                    result = out
                    success = True
                break
            except TooManyRequests:
                self._consecutive_failures += 1
                failure_type = "rate_limit"
                if self._consecutive_failures >= TRANSLATE_CIRCUIT_BREAKER_THRESHOLD:
                    print(f"\n🛑 CIRCUIT BREAKER: {self._consecutive_failures} "
                          f"TooManyRequests beruntun. Translasi DIMATIKAN.",
                          file=sys.stderr, flush=True)
                    self.save_translate_cache(force=True)
                    self._translator_disabled = True
                    self.stats["failed_rate_limit"] += 1
                    return text, "failed_rate_limit"
                wait = min(TRANSLATE_RATE_LIMIT_COOLDOWN * (attempt + 1), 60)
                print(f"⚠️  TooManyRequests ({attempt+1}). Tunggu {wait:.0f}s...",
                      file=sys.stderr, flush=True)
                time.sleep(wait)
            except (RequestError, TranslationNotFound) as e:
                failure_type = "other"
                time.sleep(TRANSLATE_BACKOFF_BASE ** attempt)
                print(f"⚠️  Translasi error ({type(e).__name__}). Retry...",
                      file=sys.stderr, flush=True)
            except Exception as e:
                failure_type = "other"
                print(f"⚠️  Translasi gagal ({type(e).__name__}: {e}).",
                      file=sys.stderr, flush=True)
                self.stats["failed_other"] += 1
                return text, "failed_other"

        self._last_translate_ts = time.time()
        if success:
            self._consecutive_failures = 0
            self._translate_cache[key] = result
            self._dirty_cache = True
            self._success_since_save += 1
            self.stats["success"] += 1
            if self._success_since_save >= TRANSLATE_CACHE_SAVE_INTERVAL:
                self.save_translate_cache()
            return result, "success"
        if failure_type == "rate_limit":
            self.stats["failed_rate_limit"] += 1
            return text, "failed_rate_limit"
        self.stats["failed_other"] += 1
        return text, "failed_other"

    # ------------------------------------------------------------------
    # Cleaning
    # ------------------------------------------------------------------
    def clean_text(self, text):
        text = str(text).lower()
        for pat in [
            r"lihat terjemahan\s*\([^)]*\)", r"lihat terjemahan\b",
            r"lihat terjemahan lainnya\b", r"terjemahkan ulasan ini\b",
            r"see translation\s*\([^)]*\)", r"see translation\b",
            r"see original\s*\([^)]*\)", r"see original\b",
            r"translated by google\b", r"diterjemahkan oleh google\b",
            r"\(translated by google\)", r"\(diterjemahkan oleh google\)",
            r"\(original\)", r"\(asli\)",
        ]:
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
    # Finalize
    # ------------------------------------------------------------------
    def _finalize(self, df, sentiment_col, dedup_stats, dropped_frames):
        df.attrs['sentiment_col'] = sentiment_col
        df.attrs['dedup_stats'] = dedup_stats
        df.attrs['translate_stats'] = self.stats
        df.attrs['no_text_stats'] = self.no_text_stats
        if dropped_frames:
            df.attrs['dropped_audit'] = pd.concat(
                dropped_frames, ignore_index=True, sort=False
            )
        else:
            df.attrs['dropped_audit'] = pd.DataFrame()
        return df

    @staticmethod
    def _has_letters(t):
        if not isinstance(t, str):
            return False
        probe = re.sub(r'http\S+|www\S+', '', t)
        probe = emoji.replace_emoji(probe, replace='')
        return bool(re.search(r'[A-Za-z]', probe))

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------
    def process_dataframe(self, df, text_col=TEXT_COL, sentiment_col=SENTIMENT_COL):
        if df.empty or text_col not in df.columns:
            return df
        if sentiment_col not in df.columns:
            sentiment_col = None

        dropped_frames = []
        self.no_text_stats["total_awal"] = len(df)

        df = df.copy()
        df[text_col] = df[text_col].fillna('').astype(str).str.strip()

        # ============================================================
        # 1. FILTER ULASAN TANPA TEKS
        # ============================================================
        mask_no_text = df[text_col].str.lower().isin(NO_TEXT_MARKERS)
        n_no_text = int(mask_no_text.sum())
        self.no_text_stats["removed_no_text"] = n_no_text
        if n_no_text:
            dropped = df[mask_no_text].copy()
            dropped['_drop_reason'] = 'no_text'
            dropped_frames.append(dropped)
        df = df[~mask_no_text].copy()

        print("\n" + "=" * 60, file=sys.stderr, flush=True)
        print("📊 FILTER AWAL DATA", file=sys.stderr, flush=True)
        print("=" * 60, file=sys.stderr, flush=True)
        print(f"  Total data mentah         : {self.no_text_stats['total_awal']}",
              file=sys.stderr, flush=True)
        print(f"  Ulasan [Tanpa Teks]       : {n_no_text} (dibuang)",
              file=sys.stderr, flush=True)
        print(f"  Ulasan dengan teks        : {len(df)}",
              file=sys.stderr, flush=True)
        print("=" * 60 + "\n", file=sys.stderr, flush=True)

        if df.empty:
            self.no_text_stats["kept"] = 0
            return self._finalize(
                df, sentiment_col,
                {"before": 0, "after": 0, "removed": 0, "subset": []},
                dropped_frames,
            )

        # ============================================================
        # 1b. FILTER TANPA TEKS BERMAKNA (emoji/angka saja)
        # ============================================================
        mask_no_meaning = ~df[text_col].apply(self._has_letters)
        n_no_meaning = int(mask_no_meaning.sum())
        self.no_text_stats["removed_no_meaningful"] = n_no_meaning
        if n_no_meaning:
            dropped = df[mask_no_meaning].copy()
            dropped['_drop_reason'] = 'no_meaningful_text'
            dropped_frames.append(dropped)
        df = df[~mask_no_meaning].copy()

        if n_no_meaning:
            print(f"🗑  {n_no_meaning} ulasan tanpa teks bermakna "
                  f"(emoji/angka saja) dibuang.", file=sys.stderr, flush=True)

        if df.empty:
            self.no_text_stats["kept"] = 0
            return self._finalize(
                df, sentiment_col,
                {"before": 0, "after": 0, "removed": 0, "subset": []},
                dropped_frames,
            )

        # ============================================================
        # 2. DEDUP
        # ============================================================
        df['_audit_row_id'] = range(len(df))
        before_dedup_df = df.copy()
        df, dedup_stats = self.deduplicate_reviews(df, text_col)
        if dedup_stats['removed'] > 0:
            kept_ids = set(df['_audit_row_id'].tolist())
            dropped = before_dedup_df[
                ~before_dedup_df['_audit_row_id'].isin(kept_ids)
            ].copy()
            dropped['_drop_reason'] = 'duplicate'
            dropped_frames.append(dropped)
        self.no_text_stats["removed_dedup"] = dedup_stats['removed']

        # ============================================================
        # 3. DETEKSI BAHASA
        # ============================================================
        print(f"🌐 Mendeteksi bahasa untuk {len(df)} baris...",
              file=sys.stderr, flush=True)
        results = []
        for i, text in enumerate(df[text_col], 1):
            results.append(self.detect_and_filter_language(text))
            if i % 500 == 0:
                print(f"   · deteksi bahasa {i}/{len(df)}", file=sys.stderr, flush=True)

        df['valid_text'] = [r[0] for r in results]
        df['lang'] = [r[1] for r in results]
        df['_detected_lang'] = [r[2] for r in results]
        df['_detail_deteksi'] = [r[3] for r in results]

        # Ringkasan untuk audit
        n_short = int(df['_detail_deteksi'].str.contains(
            'short_default|short_keyword_only', na=False).sum())
        if n_short:
            print(f"   ℹ️  {n_short} baris memakai aturan teks pendek "
                  f"(short_default / short_keyword_only).",
                  file=sys.stderr, flush=True)
        n_override = int(df['_detail_deteksi'].str.contains(
            'keyword_override', na=False).sum())
        if n_override:
            print(f"   ℹ️  {n_override} baris di-override ke id/en/ms karena "
                  f"langdetect tidak mendukung.", file=sys.stderr, flush=True)
        n_ambig = int(df['_detail_deteksi'].str.contains(
            'ambiguous_short|und\\(', na=False).sum())
        if n_ambig:
            print(f"   ℹ️  {n_ambig} baris ambigu (lang='und', tetap dipertahankan).",
                  file=sys.stderr, flush=True)

        mask_invalid_lang = df['valid_text'].isna()
        n_invalid = int(mask_invalid_lang.sum())
        if n_invalid:
            dropped = df[mask_invalid_lang].copy()
            dropped['_drop_reason'] = 'unsupported_language'
            dropped_frames.append(dropped)
        self.no_text_stats["removed_lang"] = n_invalid
        df = df[~mask_invalid_lang].copy()

        print(f"✅ Deteksi selesai. {len(df)} valid ({n_invalid} dibuang).",
              file=sys.stderr, flush=True)

        if df.empty:
            self.no_text_stats["kept"] = 0
            return self._finalize(df, sentiment_col, dedup_stats, dropped_frames)

        total = len(df)

        # ============================================================
        # 4. TRANSLASI
        # ============================================================
        need_translate = int(sum(1 for l in df['lang'] if l in TRANSLATE_LANGS))
        if self.skip_translate and need_translate > 0:
            print(f"\n⚠️  SKIP_TRANSLATE aktif: {need_translate} ulasan EN/MS "
                  f"akan MELEWATI translasi.", file=sys.stderr, flush=True)
        elif need_translate and not self.skip_translate:
            cached_count = sum(
                1 for text, lang in zip(df['valid_text'], df['lang'])
                if lang in TRANSLATE_LANGS
                and self._cache_key(str(text)) in self._translate_cache
            )
            print(f"\n🌐 Translasi: {need_translate} baris perlu diterjemahkan "
                  f"(cache hit: {cached_count}). Total: {total}.",
                  file=sys.stderr, flush=True)
        elif self.skip_translate:
            print("\n🌐 Translasi dimatikan (SKIP_TRANSLATE=1).",
                  file=sys.stderr, flush=True)

        translated, statuses = [], []
        try:
            for i, (txt, lang) in enumerate(zip(df['valid_text'], df['lang']), 1):
                tr_text, tr_status = self.translate_if_needed(txt, lang)
                translated.append(tr_text)
                statuses.append(tr_status)
                if i % 25 == 0:
                    print(f"   · translasi {i}/{total} | "
                          f"✓{self.stats['success']} 📦{self.stats['cached']} "
                          f"⏸{self.stats['skipped_circuit_open']} "
                          f"❌{self.stats['failed_rate_limit'] + self.stats['failed_other']}",
                          file=sys.stderr, flush=True)
                if self._translator_disabled:
                    remaining = total - i
                    if remaining > 0:
                        for j in range(i, total):
                            remaining_text = df['valid_text'].iloc[j]
                            remaining_lang = df['lang'].iloc[j]
                            if remaining_lang in TRANSLATE_LANGS:
                                translated.append(remaining_text)
                                statuses.append("skipped_circuit_open")
                                self.stats["skipped_circuit_open"] += 1
                            else:
                                translated.append(remaining_text)
                                statuses.append("not_needed")
                                self.stats["not_needed"] += 1
                    break
        finally:
            self.save_translate_cache(force=True)

        df['translated_text'] = translated
        df['translation_status'] = statuses

        # ============================================================
        # 5. CLEANING
        # ============================================================
        print(f"\n🧹 Cleaning teks ({total} baris)...", file=sys.stderr, flush=True)
        df['semi_clean_text'] = df['translated_text'].apply(self.clean_text)
        print("✅ Cleaning selesai.", file=sys.stderr, flush=True)

        # ============================================================
        # 6. NORMALISASI SLANG
        # ============================================================
        print(f"🔄 Normalisasi slang ({total} baris)...", file=sys.stderr, flush=True)
        df['semi_clean_text'] = df['semi_clean_text'].apply(self.normalize_slang)
        print("✅ Normalisasi slang selesai.", file=sys.stderr, flush=True)

        # ============================================================
        # 7. [FIX G] STEMMING dengan progres
        # ============================================================
        print(f"🌱 Stemming & stopword removal ({total} baris)...",
              file=sys.stderr, flush=True)
        final_texts = []
        for i, text in enumerate(df['semi_clean_text'], 1):
            final_texts.append(self.remove_stopwords_and_stem(text))
            if i % 250 == 0 or i == total:
                print(
                    f"   · stemming {i}/{total} baris "
                    f"| cache kata: {len(self._stem_cache)}",
                    file=sys.stderr, flush=True
                )
        df['final_text'] = final_texts
        print("✅ Stemming selesai.", file=sys.stderr, flush=True)

        # ============================================================
        # 8. FILTER KOSONG SETELAH STEMMING
        # ============================================================
        mask_empty = df['final_text'].str.strip() == ''
        n_empty = int(mask_empty.sum())
        if n_empty:
            dropped = df[mask_empty].copy()
            dropped['_drop_reason'] = 'empty_after_stemming'
            dropped_frames.append(dropped)
        self.no_text_stats["removed_empty_final"] = n_empty
        df = df[~mask_empty].reset_index(drop=True)
        if n_empty > 0:
            print(f"🗑  {n_empty} baris kosong dibuang setelah stemming.",
                  file=sys.stderr, flush=True)

        self.no_text_stats["kept"] = len(df)
        if df.empty:
            return self._finalize(df, sentiment_col, dedup_stats, dropped_frames)

        # ============================================================
        # 9. REORDER KOLOM
        # ============================================================
        ordered = [c for c in OUTPUT_COLUMNS if c in df.columns]
        if text_col not in ordered:
            ordered.append(text_col)
        if sentiment_col:
            ordered = [c for c in ordered if c != sentiment_col]
            ordered.insert(ordered.index(text_col) + 1, sentiment_col)
        rest = [c for c in df.columns
                if c not in ordered and not c.startswith('_')]
        df = df[ordered + rest]
        return self._finalize(df, sentiment_col, dedup_stats, dropped_frames)


# =============================================================================
# Entry point
# =============================================================================
def _save_dropped_audit(df_processed, out_dir):
    if not SAVE_DROPPED_AUDIT:
        return
    dropped_audit = df_processed.attrs.get('dropped_audit')
    if dropped_audit is None or dropped_audit.empty:
        return
    audit_export = dropped_audit.copy()

    if '_drop_reason' in audit_export.columns:
        audit_export['alasan_dibuang'] = audit_export['_drop_reason'].map(
            lambda r: DROP_REASON_LABELS.get(r, r)
        )

    rename_map = {
        '_detected_lang': 'bahasa_terdeteksi',
        '_detail_deteksi': 'detail_deteksi',
    }
    audit_export = audit_export.rename(
        columns={k: v for k, v in rename_map.items() if k in audit_export.columns}
    )

    internal_cols = [c for c in audit_export.columns if c.startswith('_')]
    audit_export = audit_export.drop(columns=internal_cols, errors='ignore')

    audit_path = os.path.join(out_dir, AUDIT_DROPPED_FILENAME)
    try:
        audit_export.to_csv(audit_path, index=False, encoding="utf-8-sig")
        print(f"📋 Audit baris dibuang: {audit_path} ({len(audit_export)} baris)",
              file=sys.stderr, flush=True)
        if 'alasan_dibuang' in audit_export.columns:
            dist = audit_export['alasan_dibuang'].value_counts()
            for reason, cnt in dist.items():
                print(f"     · {reason}: {cnt}", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"⚠️  Gagal simpan audit: {e}", file=sys.stderr, flush=True)


def run_preprocessing_job(raw_path=None, out_dir=OUTPUT_DIR,
                          text_col=TEXT_COL, sentiment_col=SENTIMENT_COL,
                          skip_translate=None,
                          drop_location_from_final=True):
    """
    raw_path=None → pakai INPUT_FALLBACK_PATHS.
    raw_path eksplisit → strict (gagal keras jika file tidak ada).
    """
    out_path = os.path.join(out_dir, OUTPUT_FILENAME)

    resolved = _resolve_input_path(raw_path)
    if not resolved:
        if raw_path:
            return False, f"File yang diberikan tidak ditemukan: {raw_path}"
        tried = "\n  - ".join(INPUT_FALLBACK_PATHS)
        return False, (f"File data mentah tidak ditemukan. Dicoba:\n  - {tried}\n"
                       "Jalankan scraper terlebih dahulu.")

    try:
        df_raw = pd.read_csv(resolved)
    except Exception as e:
        return False, f"Gagal membaca: {e}"
    if df_raw.empty:
        return False, "Data mentah kosong."
    if text_col not in df_raw.columns:
        return False, f"Kolom '{text_col}' tidak ditemukan."

    print(f"\n📂 Input: {resolved} ({len(df_raw)} baris)",
          file=sys.stderr, flush=True)

    try:
        pre = TextPreprocessor(
            skip_translate=skip_translate,
            out_dir=out_dir,
            drop_location_from_final=drop_location_from_final,
        )
        df_processed = pre.process_dataframe(
            df_raw, text_col=text_col, sentiment_col=sentiment_col
        )
    except KeyboardInterrupt:
        print("\n⚠️  Dihentikan (Ctrl+C).", file=sys.stderr, flush=True)
        return False, "Dihentikan oleh pengguna."
    except Exception as e:
        import traceback; traceback.print_exc()
        return False, f"Preprocessing gagal: {e}"

    _print_audit_trail(df_processed.attrs.get("no_text_stats", {}))
    os.makedirs(out_dir, exist_ok=True)
    _save_dropped_audit(df_processed, out_dir)

    if df_processed.empty:
        return False, ("Tidak ada ulasan tersisa. Audit baris dibuang tetap "
                       f"disimpan di {os.path.join(out_dir, AUDIT_DROPPED_FILENAME)}.")

    df_processed.to_csv(out_path, index=False, encoding="utf-8-sig")

    if "lang" in df_processed.columns:
        print("📊 Distribusi bahasa (data valid):", file=sys.stderr, flush=True)
        for lang, cnt in df_processed['lang'].value_counts().items():
            label = "und (ambigu, tetap dipertahankan)" if lang == LANG_UND else lang
            print(f"  {label}: {cnt}", file=sys.stderr, flush=True)
        print("", file=sys.stderr, flush=True)

    tstats = df_processed.attrs.get("translate_stats", {})
    if tstats:
        print("=" * 60, file=sys.stderr, flush=True)
        print("📊 TRANSLATE STATS", file=sys.stderr, flush=True)
        print("=" * 60, file=sys.stderr, flush=True)
        for key in ("success", "cached", "not_needed",
                    "failed_rate_limit", "failed_other", "skipped_circuit_open"):
            print(f"  {TRANSLATION_STATUSES.get(key, key):30s}: {tstats.get(key, 0)}",
                  file=sys.stderr, flush=True)
        print("=" * 60 + "\n", file=sys.stderr, flush=True)

    used_sentiment = df_processed.attrs.get('sentiment_col')
    note = (f" Kolom sentimen '{used_sentiment}' ikut disimpan."
            if used_sentiment
            else " Kolom sentimen tidak ditemukan.")
    return True, (f"Preprocessing selesai! {len(df_processed)} dari {len(df_raw)} "
                  f"ulasan bersih tersimpan di {out_path}. {note}")


def _run_detection_tests():
    """
    Uji regresi deteksi bahasa.
    expected dapat berupa string atau list (untuk kasus ambigu).
    """
    samples = [
        # (review, expected_lang, catatan)
        # --- sanity ---
        ("Bagus saya senang", "id", "sanity"),
        ("Pelayanannya sangat bagus", "id", "sanity"),
        ("Musholla yg nyaman", "id", "short_default"),
        ("very friendly staff", "en", "clear EN"),
        ("Ok.But Indonesia net is very poor", "en", "clear EN"),
        ("Don't vist on weekend.", "en", "clear EN"),
        ("Good, pelayanan sangat bagus", "id", "clear ID (3 vs 1)"),
        ("The parkir is very crowded", "en", "clear EN (4 vs 1)"),
        ("I like this tempat", "en", "clear EN (2 vs 0)"),
        ("Keren, elite, bersih", "id", "clear ID"),
        ("Fasilitas yang nyaman", "id", "clear ID"),
        ("So small terminal", "en", "clear EN"),
        ("Its a hell. No aircon no proper queuing", "en", "clear EN"),
        ("Tempat ini kotor dan bau", "id", "clear ID (3 keywords)"),
        ("Makanan enak tapi mahal", "id", "clear ID (2)"),
        ("Gas gas nyebrang", "id", "short_default"),
        ("Good.", "en", "short_keyword_only"),
        ("Bad.", "en", "short_keyword_only"),
        ("Teruk.", "ms", "short_keyword_only"),
        ("Bagus.", "id", "short_default"),

        # --- [BARU] regresi dari audit_dropped_rows.csv ---
        ("Check in online bikin susah", "id",
         "was: rejected (tr); now: keyword_override"),
        ("HELM KU HILANG BEJIRRRRR PADAHAL PARKIR DI DALAM", "id",
         "was: rejected (de); now: keyword_override"),
        ("Bayarnya masih cash, hadeehh thn 2024 ini", "id",
         "was: rejected (so); now: keyword_override/fallback"),
        ("Tak di bolehkan order taxi online. 1", "id",
         "was: rejected (tr); now: keyword_override"),
        ("GM(pak Gazali) Nongsapura mantap", "id",
         "was: rejected (tl); now: keyword_override"),
        ("Quick get in and get out.", "en",
         "was: rejected (nl); now: clear EN (langdetect)"),
        ("ferry terminal domestik dan internasional", "id",
         "was: rejected (it); now: keyword_override"),

        # --- [BARU] kasus ambigu & frekuensi keyword ---
        ("Good pelayanan", "und", "tie: en=1 id=1 → und(ambiguous_short)"),
        ("Good good good good pelayanan bagus", "en",
         "frekuensi: en=4 id=2 → clear EN"),
        ("Nice jelek", "und", "tie: en=1 id=1 → und(ambiguous_short)"),
        ("Tujuan pinang, tg. Uban, dabo singkep, natuna", ["id", "und"],
         "was: rejected (tl); now: kept (id/en/ms/und semua OK)"),
    ]
    pre = TextPreprocessor()
    print(f"{'':2}{'Review':<58}| {'Expect':<14}| {'Got':<7}| Detail")
    print("-" * 180)
    ok = 0
    for review, expected, note in samples:
        _, lang, _, detail = pre.detect_and_filter_language(review)
        if isinstance(expected, list):
            passed = lang in expected
            exp_display = "/".join(str(e) for e in expected)
        else:
            passed = lang == expected
            exp_display = str(expected)
        status = "✓" if passed else "✗"
        ok += int(passed)
        print(f"{status:2}{review[:55]:<58}| "
              f"{exp_display:<14}| {str(lang):<7}| {detail}")
    print("-" * 180)
    print(f"Hasil: {ok}/{len(samples)} cocok")
    return 0 if ok == len(samples) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Preprocessing ulasan: deteksi bahasa, terjemahan, pembersihan, "
                    "normalisasi slang, stopword, dan stemming."
    )
    parser.add_argument("-i", "--input", default=None,
                        help="Path file CSV input. Jika tidak diberikan, pakai "
                             "INPUT_FALLBACK_PATHS. Jika diberikan tapi tidak ada, "
                             "program gagal (tidak fallback).")
    parser.add_argument("-o", "--output-dir", default=None)
    parser.add_argument("--text-col", default=None)
    parser.add_argument("--sentiment-col", default=None)
    parser.add_argument("--no-translate", action="store_true")
    parser.add_argument("--clear-cache", action="store_true")
    parser.add_argument("--keep-location-in-final", action="store_true",
                        help="Jangan hapus nama lokasi (singapore, bintan, dst.) "
                             "dari final_text.")
    parser.add_argument("--test-detection", action="store_true",
                        help="Jalankan contoh uji deteksi bahasa lalu keluar.")
    args = parser.parse_args(argv)

    if args.test_detection:
        return _run_detection_tests()

    if args.clear_cache:
        cache_path = os.path.join(args.output_dir or OUTPUT_DIR, ".translate_cache.json")
        if os.path.exists(cache_path):
            os.remove(cache_path)
            print(f"🧹 Cache dihapus: {cache_path}", file=sys.stderr, flush=True)

    overrides = {
        "raw_path": args.input,
        "out_dir": args.output_dir,
        "text_col": args.text_col,
        "sentiment_col": args.sentiment_col,
        "skip_translate": True if args.no_translate else None,
        "drop_location_from_final": (not args.keep_location_in_final),
    }
    ok, message = run_preprocessing_job(
        **{k: v for k, v in overrides.items() if v is not None}
    )
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())