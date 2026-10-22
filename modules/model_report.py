"""Penyimpanan & pembacaan laporan model (evaluasi + istilah penting) ke file JSON."""
import json
import os
from datetime import datetime

from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)


def _r(x, nd=4):
    return round(float(x), nd)


def save_json(data, path):
    """Simpan dict ke file JSON (UTF-8, rapi)."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def load_json(path):
    """Baca file JSON. Return None jika file belum ada."""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_evaluation(y_true, y_pred, labels, extra=None):
    """Hitung accuracy, precision, recall, f1 (per kelas, macro, weighted) + confusion matrix."""
    prec, rec, f1, sup = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    per_class = {
        lbl: {
            "precision": _r(p), "recall": _r(r), "f1_score": _r(f), "support": int(s),
        }
        for lbl, p, r, f, s in zip(labels, prec, rec, f1, sup)
    }

    def avg(kind):
        p, r, f, _ = precision_recall_fscore_support(
            y_true, y_pred, labels=labels, average=kind, zero_division=0
        )
        return {"precision": _r(p), "recall": _r(r), "f1_score": _r(f)}

    cm = confusion_matrix(y_true, y_pred, labels=labels)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "labels": list(labels),
        "n_test": int(len(y_true)),
        "accuracy": _r(accuracy_score(y_true, y_pred)),
        "macro_avg": avg("macro"),
        "weighted_avg": avg("weighted"),
        "per_class": per_class,
        "confusion_matrix": {
            "labels": list(labels),  # baris = aktual, kolom = prediksi
            "matrix": cm.tolist(),
        },
    }
    if extra:
        report.update(extra)
    return report


def save_evaluation(y_true, y_pred, labels, path, extra=None):
    report = build_evaluation(y_true, y_pred, labels, extra)
    save_json(report, path)
    return report
