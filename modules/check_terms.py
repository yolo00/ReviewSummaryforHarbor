"""Cek istilah (term) TF-IDF yang paling membedakan antar kelas pada SVM linear.

Bisa dijalankan langsung:  python modules/check_terms.py
atau dipakai sebagai modul (train_model2.py & app.py).

Mode diagnosis:
    python modules/check_terms.py --diagnose

Konvensi tanda koefisien SVC (kernel='linear'):
- Binary   : coef_.shape = (1, n_features). Positif → class[1] (kelas indeks
             lebih tinggi). Konsisten dengan scikit-learn predict convention
             setelah decision_function dinegasikan untuk binary.
- Multikelas: coef_.shape = (n_pairs, n_features). Urutan baris mengikuti
             combinations(range(n_classes), 2). Untuk pasangan (i, j) dengan
             i < j, nilai positif mengarah ke class[i] (indeks lebih kecil).
             Konvensi ini sudah diverifikasi secara empiris pada versi
             scikit-learn yang dipakai proyek ini (lihat --diagnose).
"""
import argparse
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


def compute_top_terms(pipeline, top_n=10, verbose=False):
    """
    Return list per pasangan kelas berisi term yang condong ke tiap kelas.

    - Binary   : positif → class[1].
    - Multikelas OvO: positif → class[i] (indeks lebih kecil) untuk
      pasangan (i, j) dengan i < j.
    """
    # [FIX 2] Validasi top_n.
    if top_n < 1:
        raise ValueError("top_n harus minimal 1.")

    tfidf = pipeline.named_steps["tfidf"]
    svm = pipeline.named_steps["svm"]

    terms = np.array(tfidf.get_feature_names_out())
    classes = list(svm.classes_)

    coefs = svm.coef_
    coefs = coefs.toarray() if hasattr(coefs, "toarray") else np.asarray(coefs)

    n_classes = len(classes)
    n_features = len(terms)

    if verbose:
        print(f"[check_terms] classes_    = {classes}")
        print(f"[check_terms] coef_.shape = {coefs.shape}")
        print(f"[check_terms] n_features  = {n_features}")
        print(f"[check_terms] n_classes   = {n_classes}")

    if n_classes < 2:
        raise ValueError(
            f"Model hanya memiliki {n_classes} kelas. Minimal 2 kelas diperlukan."
        )

    # ------------------------------------------------------------------
    # Binary
    # ------------------------------------------------------------------
    if n_classes == 2:
        # Positif → class[1]. Bangun (a=1, b=0) agar positif selalu ke class_a.
        pairs = [(1, 0)]
        if coefs.shape[0] != 1:
            raise RuntimeError(
                f"coef_.shape[0]={coefs.shape[0]} untuk binary, seharusnya 1. "
                f"Cek konfigurasi SVC."
            )

    # ------------------------------------------------------------------
    # Multikelas OvO
    # ------------------------------------------------------------------
    else:
        n_pairs = n_classes * (n_classes - 1) // 2
        if coefs.shape[0] != n_pairs:
            raise RuntimeError(
                f"coef_.shape[0]={coefs.shape[0]} tidak sesuai dengan OvO "
                f"untuk {n_classes} kelas ({n_pairs} pasangan). "
                f"Cek versi scikit-learn / konfigurasi SVC."
            )
        # [FIX 1] Positive → class[i] (indeks lebih kecil) untuk pair (i, j),
        # i < j. Ini sesuai konvensi OvO SVC pada scikit-learn versi yang
        # dipakai. Bangun pairs=(a, b) dengan a=i, b=j agar positif → class_a.
        pairs = [(a, b) for a, b in combinations(range(n_classes), 2)]

    result = []
    for row, (a, b) in zip(coefs, pairs):
        order = np.argsort(row)
        top_a = order[-top_n:][::-1]   # bobot positif terbesar → class_a
        top_b = order[:top_n]          # bobot negatif terbesar → class_b
        result.append({
            "pair": f"{classes[a]} vs {classes[b]}",
            "class_a": str(classes[a]),
            "class_b": str(classes[b]),
            "toward_a": [
                {"term": str(terms[i]), "weight": round(float(row[i]), 4)}
                for i in top_a
            ],
            "toward_b": [
                {"term": str(terms[i]), "weight": round(float(row[i]), 4)}
                for i in top_b
            ],
        })
    return result


def save_top_terms(pipeline, path=DEFAULT_TERMS_PATH, top_n=10, verbose=False):
    """Hitung & simpan hasil check_terms ke file JSON."""
    data = {
        "top_n": top_n,
        "pairs": compute_top_terms(pipeline, top_n, verbose=verbose),
    }
    save_json(data, path)
    return data


def load_top_terms(path=DEFAULT_TERMS_PATH):
    return load_json(path)


def print_top_terms(data):
    for p in data["pairs"]:
        print(f"\n{p['pair']}")
        print(f"Condong ke {p['class_a']}:",
              [t["term"] for t in p["toward_a"]])
        print(f"Condong ke {p['class_b']}:",
              [t["term"] for t in p["toward_b"]])


def _diagnose(pipeline):
    """
    Tampilkan struktur coef_ dan interpretasi arah tanda untuk memverifikasi
    asumsi OvO sebelum menyimpan top terms.
    """
    print("=" * 60)
    print("🔬 DIAGNOSIS STRUKTUR MODEL")
    print("=" * 60)
    tfidf = pipeline.named_steps["tfidf"]
    svm = pipeline.named_steps["svm"]
    terms = tfidf.get_feature_names_out()
    classes = list(svm.classes_)
    coefs = svm.coef_
    coefs_arr = coefs.toarray() if hasattr(coefs, "toarray") else np.asarray(coefs)

    n_classes = len(classes)
    n_features = len(terms)
    n_pairs = n_classes * (n_classes - 1) // 2 if n_classes > 1 else 0

    print(f"  classes_             : {classes}")
    print(f"  n_classes            : {n_classes}")
    print(f"  n_features (TF-IDF)  : {n_features}")
    print(f"  coef_.shape          : {coefs_arr.shape}")
    print(f"  jumlah pasangan OvO  : {n_pairs}")

    if n_classes == 2:
        ok_shape = coefs_arr.shape == (1, n_features)
        print(f"  interpretasi         : binary (1 baris)  "
              f"positif → class[1] = '{classes[1]}'")
    else:
        expected = (n_pairs, n_features)
        ok_shape = coefs_arr.shape == expected
        print(f"  bentuk yang diharapkan: {expected}  -> "
              f"{'OK' if ok_shape else 'TIDAK SESUAI'}")
        print(f"  interpretasi baris 0..{n_pairs - 1}:")
        for idx, (i, j) in enumerate(combinations(range(n_classes), 2)):
            # [FIX 1c] Positive → class[i] (indeks lebih kecil).
            print(f"    baris {idx}: pair ({classes[i]} vs {classes[j]}) "
                  f"→ positif = '{classes[i]}'")

    print(f"  status bentuk        : {'OK' if ok_shape else 'PERIKSA'}")
    print("=" * 60)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Cek istilah TF-IDF paling diskriminatif per kelas SVM."
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL_PATH,
        help=f"Path model pipeline (default: {DEFAULT_MODEL_PATH}).",
    )
    parser.add_argument(
        "--out", default=DEFAULT_TERMS_PATH,
        help=f"Path output JSON top terms (default: {DEFAULT_TERMS_PATH}).",
    )
    parser.add_argument(
        "--top-n", type=int, default=10,
        help="Jumlah term teratas per arah kelas (default: 10).",
    )
    parser.add_argument(
        "--diagnose", action="store_true",
        help="Tampilkan diagnosis struktur coef_ lalu keluar.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()

    if not os.path.exists(args.model):
        raise SystemExit(f"❌ Model tidak ditemukan: {args.model}")

    pipe = joblib.load(args.model)

    if args.diagnose:
        _diagnose(pipe)
        raise SystemExit(0)

    hasil = save_top_terms(
        pipe,
        path=args.out,
        top_n=args.top_n,
        verbose=True,
    )
    print_top_terms(hasil)
    print(f"\n✅ Disimpan di: {args.out}")