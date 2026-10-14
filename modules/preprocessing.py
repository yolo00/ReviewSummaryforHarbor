import os
import re
import emoji
import pandas as pd
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory
from deep_translator import GoogleTranslator
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0

class TextPreprocessor:
    def __init__(self):
        factory_stem = StemmerFactory()
        self.stemmer = factory_stem.create_stemmer()
        
        factory_stop = StopWordRemoverFactory()
        self.base_stopwords = set(factory_stop.get_stop_words())
        
        self.custom_stopwords = {
            'pelabuhan', 'ferry', 'terminal', 'batam', 'centre', 'center', 'sekupang', 
            'punggur', 'telaga', 'nongsapura', 'harbour', 'bay', 'singapore', 'singapura',
            'bintan', 'tanjung', 'pinang', 'kapal', 'tiket', 'nya', 'yg', 'di', 'ke', 'dari', 
            'ini', 'itu', 'untuk', 'dan', 'dengan', 'ada', 'tidak', 'bisa', 'sudah', 'sangat'
        }
        self.all_stopwords = self.base_stopwords.union(self.custom_stopwords)
        
        self.slang_dict = {
            'bgus': 'bagus', 'bgt': 'banget', 'bgs': 'bagus', 'brg': 'barang',
            'klo': 'kalau', 'klw': 'kalau', 'tdk': 'tidak', 'gak': 'tidak', 
            'ga': 'tidak', 'gk': 'tidak', 'nggak': 'tidak', 'dgn': 'dengan', 
            'krn': 'karena', 'tp': 'tapi', 'cpt': 'cepat', 'lmbat': 'lambat'
        }

    def detect_and_filter_language(self, text):
        if not text or not str(text).strip():
            return None, None
            
        try:
            lang = detect(text)
            if lang in ['id', 'en', 'ms']:
                return text, lang
            else:
                return None, None
        except Exception:
            return None, None

    def translate_if_needed(self, text, lang):
        if lang in ['en', 'ms']:
            try:
                translator = GoogleTranslator(source='auto', target='id')
                return translator.translate(text)
            except Exception:
                return text
        return text

    def clean_text(self, text):
        text = str(text).lower()
        text = emoji.replace_emoji(text, replace='')
        text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)
        text = re.sub(r'[^a-z\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def normalize_slang(self, text):
        words = text.split()
        return ' '.join([self.slang_dict.get(w, w) for w in words])

    def remove_stopwords_and_stem(self, text):
        words = text.split()
        filtered = [w for w in words if w not in self.all_stopwords]
        return self.stemmer.stem(' '.join(filtered))

    def process_dataframe(self, df, text_col='review'):
        if df.empty or text_col not in df.columns:
            return df

        df = df.drop_duplicates(subset=[text_col]).copy()
        df[text_col] = df[text_col].fillna('')

        detected_results = df[text_col].apply(self.detect_and_filter_language)
        df['valid_text'] = [res[0] for res in detected_results]
        df['lang'] = [res[1] for res in detected_results]

        df = df.dropna(subset=['valid_text']).copy()

        df['translated_text'] = df.apply(
            lambda row: self.translate_if_needed(row['valid_text'], row['lang']), axis=1
        )

        df['semi_clean_text'] = df['translated_text'].apply(self.clean_text)
        df['semi_clean_text'] = df['semi_clean_text'].apply(self.normalize_slang)
        df['final_text'] = df['semi_clean_text'].apply(self.remove_stopwords_and_stem)

        df = df[df['final_text'].str.strip() != '']
        return df


def run_preprocessing_job():
    raw_path = os.path.join("data", "raw", "review_pelabuhan.csv")
    out_dir = os.path.join("data", "processed")
    out_path = os.path.join(out_dir, "review_processed.csv")

    if not os.path.exists(raw_path):
        return False, "File data mentah tidak ditemukan. Jalankan scraping terlebih dahulu."

    df_raw = pd.read_csv(raw_path)
    if df_raw.empty:
        return False, "Data mentah kosong."

    preprocessor = TextPreprocessor()
    df_processed = preprocessor.process_dataframe(df_raw, text_col='review')

    os.makedirs(out_dir, exist_ok=True)
    df_processed.to_csv(out_path, index=False, encoding="utf-8-sig")

    return True, f"Preprocessing selesai! {len(df_processed)} ulasan bersih tersimpan."