import os
import re
import time
import emoji
import pandas as pd
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory
from deep_translator import GoogleTranslator
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0

NEGATION_WORDS = {'tidak', 'tak', 'bukan', 'belum', 'jangan', 'kurang', 'tanpa'}

ALLOWED_LANGS = {'id', 'en', 'ms'}
TRANSLATE_LANGS = {'en'}

MIN_WORDS_FOR_DETECTION = 3
MAX_TRANSLATE_CHARS = 4900


class TextPreprocessor:
    def __init__(self):
        factory_stem = StemmerFactory()
        self.stemmer = factory_stem.create_stemmer()
        self._stem_cache = {}

        factory_stop = StopWordRemoverFactory()
        self.base_stopwords = set(factory_stop.get_stop_words())

        self.domain_stopwords = {
            'pelabuhan', 'ferry', 'terminal', 'batam', 'centre', 'center', 'sekupang',
            'punggur', 'telaga', 'nongsapura', 'harbour', 'bay', 'singapore', 'singapura',
            'bintan', 'tanjung', 'pinang', 'kapal', 'tiket', 'nya', 'yg', 'di', 'ke', 'dari',
            'ini', 'itu', 'untuk', 'dan', 'dengan', 'ada', 'bisa', 'sudah', 'sangat'
        }
        self.all_stopwords = (self.base_stopwords | self.domain_stopwords) - NEGATION_WORDS

        self.stemmed_domain_stopwords = {
            self._stem_word(w) for w in self.domain_stopwords
        } - {self._stem_word(w) for w in NEGATION_WORDS} - {''}

        self.slang_dict = {
            'bgus': 'bagus', 'bgt': 'banget', 'bgs': 'bagus', 'brg': 'barang',
            'klo': 'kalau', 'klw': 'kalau', 'kl': 'kalau',
            'tdk': 'tidak', 'gak': 'tidak', 'ga': 'tidak', 'gk': 'tidak',
            'nggak': 'tidak', 'ngga': 'tidak', 'enggak': 'tidak', 'engga': 'tidak',
            'nggk': 'tidak', 'tak': 'tidak',
            'dgn': 'dengan', 'dg': 'dengan', 'krn': 'karena', 'karna': 'karena',
            'tp': 'tapi', 'tapi': 'tapi', 'cpt': 'cepat', 'lmbat': 'lambat', 'lmbt': 'lambat',
            'udh': 'sudah', 'sdh': 'sudah', 'blm': 'belum', 'jgn': 'jangan',
            'bs': 'bisa', 'sy': 'saya', 'org': 'orang', 'jg': 'juga', 'sm': 'sama',
            'yg': 'yang', 'utk': 'untuk', 'dr': 'dari', 'trs': 'terus',
            'mantab': 'mantap', 'oke': 'ok', 'jelek': 'jelek'
        }

    def _stem_word(self, word):
        if word not in self._stem_cache:
            self._stem_cache[word] = self.stemmer.stem(word)
        return self._stem_cache[word]

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

    def clean_text(self, text):
        text = str(text).lower()
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
        stemmed = [w if w in NEGATION_WORDS else self._stem_word(w) for w in words]
        stemmed = [
            w for w in stemmed
            if w and (w in NEGATION_WORDS or w not in self.stemmed_domain_stopwords)
        ]
        return ' '.join(stemmed)


    def process_dataframe(self, df, text_col='review'):
        if df.empty or text_col not in df.columns:
            return df

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
        return df

def run_preprocessing_job():
    raw_path = os.path.join("data", "raw", "review_pelabuhan1.csv")
    out_dir = os.path.join("data", "processed")
    out_path = os.path.join(out_dir, "review_processed.csv")

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
        df_processed = preprocessor.process_dataframe(df_raw, text_col=text_col)
    except Exception as e:
        return False, f"Preprocessing gagal: {e}"

    if df_processed.empty:
        return False, "Tidak ada ulasan yang tersisa setelah preprocessing."

    os.makedirs(out_dir, exist_ok=True)
    df_processed.to_csv(out_path, index=False, encoding="utf-8-sig")

    return True, (
        f"Preprocessing selesai! {len(df_processed)} dari {len(df_raw)} ulasan "
        f"bersih tersimpan."
    )