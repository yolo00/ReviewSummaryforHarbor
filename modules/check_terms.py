"""Cek istilah (term) TF-IDF yang paling membedakan antar kelas pada SVM linear.

Bisa dijalankan langsung:  python modules/check_terms.py
atau dipakai sebagai modul (train_model2.py & app.py).
"""
import os
from itertools import combinations

import joblib
import numpy as np

try:
    from modules.model_report import load_json, save_json
except ModuleNotFoundError:  # dijalankan langsung dari folder modules
    from model_report import load_json, save_json

DEFAULT_MODEL_PATH = os.path.join("data", "models", "svm_pipeline.pkl")
DEFAULT_TERMS_PATH = os.path.join("data", "models", "top_terms.json")


def compute_top_terms(pipeline, top_n=10):
    """Return list per pasangan kelas (one-vs-one) berisi term yang condong ke tiap kelas."""
    tfidf = pipeline.named_steps["tfidf"]
    svm = pipeline.named_steps["svm"]

    terms = np.array(tfidf.get_feature_names_out())
    classes = list(svm.classes_)

    coefs = svm.coef_
    coefs = coefs.toarray() if hasattr(coefs, "toarray") else np.asarray(coefs)

    # Biner: coef_ hanya 1 baris dan positif = kelas kedua.
    # Multikelas (OvO): urutan baris = combinations(classes, 2), positif = kelas pertama.
    if len(classes) == 2:
        pairs = [(1, 0)]
    else:
        pairs = list(combinations(range(len(classes)), 2))

    result = []
    for row, (a, b) in zip(coefs, pairs):
        order = np.argsort(row)
        top_a = order[-top_n:][::-1]  # bobot positif terbesar -> kelas a
        top_b = order[:top_n]         # bobot negatif terbesar -> kelas b
        result.append({
            "pair": f"{classes[a]} vs {classes[b]}",
            "class_a": str(classes[a]),
            "class_b": str(classes[b]),
            "toward_a": [{"term": str(terms[i]), "weight": round(float(row[i]), 4)} for i in top_a],
            "toward_b": [{"term": str(terms[i]), "weight": round(float(row[i]), 4)} for i in top_b],
        })
    return result


def save_top_terms(pipeline, path=DEFAULT_TERMS_PATH, top_n=10):
    """Hitung & simpan hasil check_terms ke file JSON."""
    data = {"top_n": top_n, "pairs": compute_top_terms(pipeline, top_n)}
    save_json(data, path)
    return data


def load_top_terms(path=DEFAULT_TERMS_PATH):
    return load_json(path)


def print_top_terms(data):
    for p in data["pairs"]:
        print(f"\n{p['pair']}")
        print(f"Condong ke {p['class_a']}:", [t["term"] for t in p["toward_a"]])
        print(f"Condong ke {p['class_b']}:", [t["term"] for t in p["toward_b"]])


if __name__ == "__main__":
    pipe = joblib.load(DEFAULT_MODEL_PATH)
    hasil = save_top_terms(pipe)
    print_top_terms(hasil)
    print(f"\n✅ Disimpan di: {DEFAULT_TERMS_PATH}")
