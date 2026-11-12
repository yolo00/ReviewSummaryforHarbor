import os
import threading
import numpy as np
import pandas as pd
from flask import Flask, render_template, jsonify, request

from modules.scraper import run_scraper
from modules.preprocessing import run_preprocessing_job
from modules.train_model2 import train_svm_model, EVAL_PATH, TERMS_PATH
from modules.predict import SVMSentimentAnalyzer, run_analysis_job, InputTidakValid
from modules.model_report import load_json
from modules.check_terms import save_top_terms

app = Flask(__name__)

RAW_CANDIDATES = [
    os.path.join("data", "raw", "review_pelabuhan(fix).csv"),
    os.path.join("data", "raw", "review_pelabuhan1.csv"),
    os.path.join("data", "raw", "review_pelabuhan.csv"),
]
PROCESSED_CANDIDATES = [
    os.path.join("data", "processed", "review_predicted(fix).csv"),
    os.path.join("data", "processed", "review_processed(fix).csv"),
    os.path.join("data", "processed", "review_processed.csv"),
]

def resolve_raw_path():
    for p in RAW_CANDIDATES:
        if os.path.exists(p): return p
    return None

def resolve_processed_path():
    for p in PROCESSED_CANDIDATES:
        if os.path.exists(p): return p
    return None

STATUS_LOCK = threading.Lock()
PROCESS_STATUS = {
    "scraping":      {"running": False, "message": "Belum berjalan", "success": False},
    "preprocessing": {"running": False, "message": "Belum berjalan", "success": False},
    "training":      {"running": False, "message": "Belum berjalan", "success": False},
    "analysis":      {"running": False, "message": "Belum berjalan", "success": False},
}

def try_start_process(name, start_message):
    with STATUS_LOCK:
        if PROCESS_STATUS[name]["running"]: return False
        PROCESS_STATUS[name].update(running=True, success=False, message=start_message)
        return True

def finish_process(name, success, message):
    with STATUS_LOCK:
        PROCESS_STATUS[name].update(running=False, success=bool(success), message=message)

def update_status_callback(msg):
    with STATUS_LOCK: PROCESS_STATUS["scraping"]["message"] = msg

def _run_in_background(name, start_msg, job_fn, success_message):
    if not try_start_process(name, start_msg):
        return jsonify({"status": "error", "message": f"Proses {name} sedang berjalan..."}), 400
    def worker():
        try:
            success, msg = job_fn()
            finish_process(name, success, msg or success_message)
        except Exception as e:
            finish_process(name, False, f"{name} gagal: {e}")
    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"status": "success", "message": f"Proses {name} telah dimulai di latar belakang."})

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
def _require_admin():
    if not ADMIN_TOKEN: return None
    if request.headers.get("X-Admin-Token", "") != ADMIN_TOKEN:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    return None

def _to_jsonable(value):
    if isinstance(value, np.integer): return int(value)
    if isinstance(value, np.floating): return float(value)
    if isinstance(value, np.bool_): return bool(value)
    if value is None: return None
    try:
        if pd.isna(value): return None
    except (TypeError, ValueError): pass
    return value

def df_records(df):
    return [{k: _to_jsonable(v) for k, v in row.items()} for row in df.to_dict(orient="records")]

def parse_ports_arg(ports_str):
    if not ports_str: return []
    return [p.strip() for p in ports_str.split(",") if p.strip()]

def _resolve_ports_from_request():
    ports = parse_ports_arg(request.args.get("ports", ""))
    legacy = (request.args.get("port") or "").strip()
    if not ports and legacy and legacy.upper() != "ALL":
        # `port` lama bisa berisi beberapa pelabuhan dipisah koma ("A,B")
        ports = [p for p in parse_ports_arg(legacy) if p.upper() != "ALL"]
    return ports

def apply_data_filters(df, ports, from_date, to_date):
    if ports and len(ports) > 0:
        mask = pd.Series(False, index=df.index)
        for col in ("lokasi", "pelabuhan"):
            if col in df.columns:
                series = df[col].astype(str).str.lower()
                for needle in ports:
                    mask |= series.str.contains(needle.lower(), regex=False, na=False)
        df = df[mask]

    if from_date or to_date:
        if "tanggal_estimasi" in df.columns:
            tgl = pd.to_datetime(df["tanggal_estimasi"], errors="coerce")
            mask = tgl.notna()
            if from_date: mask &= tgl >= pd.to_datetime(from_date)
            if to_date: mask &= tgl < (pd.to_datetime(to_date) + pd.Timedelta(days=1))
            df = df[mask]
    return df

@app.route("/")
def index(): return render_template("index.html")

@app.route("/dashboard")
def dashboard(): return render_template("dashboard.html")

@app.route("/run-scraper", methods=["POST"])
def run_scraper_endpoint():
    denied = _require_admin()
    if denied: return denied
    def job():
        total, msg = run_scraper(update_status_callback)
        return (True, f"Selesai! {total} ulasan didapatkan.") if total > 0 else (False, msg or "Scraping selesai tanpa ulasan.")
    return _run_in_background("scraping", "Scraping ulasan sedang berlangsung...", job, "Scraping selesai.")

@app.route("/run-preprocessing", methods=["POST"])
def run_preprocessing_endpoint():
    denied = _require_admin()
    if denied: return denied
    return _run_in_background("preprocessing", "Preprocessing NLP sedang berlangsung...", run_preprocessing_job, "Preprocessing selesai.")

@app.route("/train-model", methods=["POST"])
def train_model_endpoint():
    denied = _require_admin()
    if denied: return denied
    return _run_in_background("training", "Pelatihan model SVM & TF-IDF sedang berlangsung...", train_svm_model, "Pelatihan selesai.")

@app.route("/run-analysis", methods=["POST"])
def run_analysis_endpoint():
    denied = _require_admin()
    if denied: return denied
    return _run_in_background("analysis", "Analisis sentimen sedang berlangsung...", run_analysis_job, "Analisis selesai.")

@app.route("/status", methods=["GET"])
def check_status():
    with STATUS_LOCK: snapshot = {k: dict(v) for k, v in PROCESS_STATUS.items()}
    return jsonify(snapshot)

@app.route("/get-data", methods=["GET"])
def get_data():
    source = (request.args.get("source") or "all").lower()
    ports = _resolve_ports_from_request()
    from_date = (request.args.get("from") or "").strip() or None
    to_date = (request.args.get("to") or "").strip() or None

    result = {"status": "success"}

    if source in ("all", "raw"):
        raw_path = resolve_raw_path()
        if raw_path:
            try:
                df_raw = pd.read_csv(raw_path).fillna("")
                df_raw = apply_data_filters(df_raw, ports, from_date, to_date)
                result["raw"] = df_records(df_raw)
                result["raw_meta"] = {"source": os.path.basename(raw_path), "count": int(len(df_raw))}
            except Exception as e:
                result["raw"] = []
                result["raw_error"] = f"Gagal membaca raw CSV: {e}"
        else:
            result["raw"], result["raw_error"] = [], "CSV raw tidak ditemukan."

    if source in ("all", "processed"):
        proc_path = resolve_processed_path()
        if proc_path:
            try:
                df_proc = pd.read_csv(proc_path).fillna("")
                df_proc = apply_data_filters(df_proc, ports, from_date, to_date)
                result["processed"] = df_records(df_proc)
                result["processed_meta"] = {"source": os.path.basename(proc_path), "count": int(len(df_proc))}
                if "sentiment" not in df_proc.columns and "sentimen" not in df_proc.columns:
                    result["warning"] = "Processed CSV belum memiliki kolom sentimen; jalankan prediksi terlebih dahulu."
            except Exception as e:
                result["processed"] = []
                result["processed_error"] = f"Gagal membaca processed CSV: {e}"
        else:
            result["processed"], result["processed_error"] = [], "CSV processed tidak ditemukan."

    result["data"] = result.get("processed") or result.get("raw") or []
    return jsonify(result)

_analyzer = None
_analyzer_key = None
_analyzer_lock = threading.Lock()
MODEL_PIPELINE_PATH = os.path.join("data", "models", "svm_pipeline.pkl")

def get_analyzer():
    """Model dimuat sekali, dan dimuat ulang otomatis bila file model berubah (mis. setelah training)."""
    global _analyzer, _analyzer_key
    with _analyzer_lock:
        mtime = os.path.getmtime(MODEL_PIPELINE_PATH) if os.path.exists(MODEL_PIPELINE_PATH) else None
        if _analyzer is None or mtime != _analyzer_key:
            _analyzer = SVMSentimentAnalyzer()
            _analyzer_key = mtime
        return _analyzer

@app.route("/load-model", methods=["POST"])
def load_model():
    """Dipanggil dashboard saat halaman Uji Sentimen dibuka, agar model siap sebelum dipakai."""
    try:
        get_analyzer()
        return jsonify({"status": "success", "message": "Model siap."})
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "Model belum dilatih."}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": f"Model gagal dimuat: {e}"}), 500

@app.route("/predict-single", methods=["POST"])
def predict_single():
    req = request.get_json(silent=True) or {}
    text = req.get("text", "")
    if not isinstance(text, str) or not text.strip(): return jsonify({"status": "error", "message": "Masukkan teks ulasan yang valid."}), 400
    try:
        prediction, probs = get_analyzer().predict_single(text.strip())
        return jsonify({"status": "success", "text": text, "prediction": prediction, "probabilities": probs})
    except InputTidakValid as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "Model belum dilatih."}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/get-evaluation", methods=["GET"])
def get_evaluation():
    report = load_json(EVAL_PATH)
    if report is None: return jsonify({"status": "error", "message": "Laporan evaluasi belum ada."}), 404
    return jsonify({"status": "success", "data": report})

_terms_cache = None
_terms_lock = threading.Lock()
@app.route("/get-terms", methods=["GET"])
def get_terms():
    global _terms_cache
    terms = load_json(TERMS_PATH)
    if terms is not None: return jsonify({"status": "success", "data": terms})
    if _terms_cache is not None: return jsonify({"status": "success", "data": _terms_cache})
    try:
        with _terms_lock:
            if _terms_cache is None: _terms_cache = save_top_terms(get_analyzer().pipeline, TERMS_PATH)
        return jsonify({"status": "success", "data": _terms_cache})
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "Model belum dilatih."}), 404

@app.route("/api/charts", methods=["GET"])
def get_charts():
    try: from modules import visualization as viz
    except ImportError as e: return jsonify({"status": "error", "message": f"Gagal import visualization: {e}."}), 500

    ports = _resolve_ports_from_request()
    from_date = (request.args.get("from") or "").strip() or None
    to_date = (request.args.get("to") or "").strip() or None
    proc_path = resolve_processed_path()
    if not proc_path: return jsonify({"status": "error", "message": "Data processed belum tersedia."}), 404

    try: df = pd.read_csv(proc_path).fillna("")
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

    df = apply_data_filters(df, ports, from_date, to_date)

    try:
        # Confusion matrix = evaluasi global model, tidak bergantung pada filter,
        # jadi selalu dikirim walaupun filter tidak menghasilkan baris.
        charts = {"confusion_matrix": viz.chart_confusion_matrix()}
        message = None
        if df.empty:
            message = "Tidak ada data setelah filter."
        else:
            charts["wordcloud"] = viz.chart_wordcloud(df)
            charts["heatmap"] = viz.chart_heatmap(df)
        return jsonify({
            "status": "success",
            "message": message,
            "charts": charts,
            "meta": { "source": os.path.basename(proc_path), "rows_after_filter": int(len(df)) }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal membuat chart: {e}"}), 500

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=5000, debug=debug)