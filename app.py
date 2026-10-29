import os
import threading
import pandas as pd
from flask import Flask, render_template, jsonify, request

# Import modul dari folder modules
from modules.scraper import run_scraper
from modules.preprocessing import run_preprocessing_job
from modules.train_model2 import train_svm_model, EVAL_PATH, TERMS_PATH
from modules.predict import SVMSentimentAnalyzer, run_analysis_job
from modules.model_report import load_json
from modules.check_terms import save_top_terms

app = Flask(__name__)

# Status global untuk memantau proses background
PROCESS_STATUS = {
    "scraping": {"running": False, "message": "Belum berjalan", "success": False},
    "preprocessing": {"running": False, "message": "Belum berjalan", "success": False},
    "training": {"running": False, "message": "Belum berjalan", "success": False},
    "analysis": {"running": False, "message": "Belum berjalan", "success": False}
}

def update_status_callback(msg):
    PROCESS_STATUS["scraping"]["message"] = msg

# ==========================================
# ROUTES UNTUK HALAMAN (UI)
# ==========================================

@app.route("/")
def index():
    """Landing Page"""
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    """Halaman Utama Dashboard"""
    return render_template("dashboard.html")


# ==========================================
# ROUTES UNTUK PROSES PIPELINE (BACKEND)
# ==========================================

@app.route("/run-scraper", methods=["POST"])
def run_scraper_endpoint():
    if PROCESS_STATUS["scraping"]["running"]:
        return jsonify({"status": "error", "message": "Proses scraping sedang berjalan..."}), 400

    def background_scraping():
        PROCESS_STATUS["scraping"]["running"] = True
        PROCESS_STATUS["scraping"]["message"] = "Scraping ulasan sedang berlangsung..."
        try:
            total, msg = run_scraper(update_status_callback)
            PROCESS_STATUS["scraping"]["message"] = f"Selesai! {total} ulasan didapatkan."
            PROCESS_STATUS["scraping"]["success"] = True if total > 0 else False
        except Exception as e:
            PROCESS_STATUS["scraping"]["message"] = f"Scraping gagal: {str(e)}"
            PROCESS_STATUS["scraping"]["success"] = False
        finally:
            PROCESS_STATUS["scraping"]["running"] = False

    threading.Thread(target=background_scraping, daemon=True).start()
    return jsonify({"status": "success", "message": "Proses scraping telah dimulai di latar belakang."})

@app.route("/run-preprocessing", methods=["POST"])
def run_preprocessing_endpoint():
    if PROCESS_STATUS["preprocessing"]["running"]:
        return jsonify({"status": "error", "message": "Proses preprocessing sedang berjalan..."}), 400

    def background_preprocessing():
        PROCESS_STATUS["preprocessing"]["running"] = True
        PROCESS_STATUS["preprocessing"]["message"] = "Preprocessing NLP sedang berlangsung..."
        try:
            success, msg = run_preprocessing_job()
            PROCESS_STATUS["preprocessing"]["message"] = msg
            PROCESS_STATUS["preprocessing"]["success"] = success
        except Exception as e:
            PROCESS_STATUS["preprocessing"]["message"] = f"Preprocessing gagal: {str(e)}"
            PROCESS_STATUS["preprocessing"]["success"] = False
        finally:
            PROCESS_STATUS["preprocessing"]["running"] = False

    threading.Thread(target=background_preprocessing, daemon=True).start()
    return jsonify({"status": "success", "message": "Proses preprocessing telah dimulai."})

@app.route("/train-model", methods=["POST"])
def train_model_endpoint():
    if PROCESS_STATUS["training"]["running"]:
        return jsonify({"status": "error", "message": "Pelatihan model sedang berjalan..."}), 400

    def background_training():
        PROCESS_STATUS["training"]["running"] = True
        PROCESS_STATUS["training"]["message"] = "Pelatihan model SVM & TF-IDF sedang berlangsung..."
        try:
            success, msg = train_svm_model()
            PROCESS_STATUS["training"]["message"] = msg
            PROCESS_STATUS["training"]["success"] = success
        except Exception as e:
            PROCESS_STATUS["training"]["message"] = f"Training gagal: {str(e)}"
            PROCESS_STATUS["training"]["success"] = False
        finally:
            PROCESS_STATUS["training"]["running"] = False

    threading.Thread(target=background_training, daemon=True).start()
    return jsonify({"status": "success", "message": "Pelatihan model telah dimulai."})

@app.route("/run-analysis", methods=["POST"])
def run_analysis_endpoint():
    if PROCESS_STATUS["analysis"]["running"]:
        return jsonify({"status": "error", "message": "Proses analisis sedang berjalan..."}), 400

    def background_analysis():
        PROCESS_STATUS["analysis"]["running"] = True
        PROCESS_STATUS["analysis"]["success"] = False
        PROCESS_STATUS["analysis"]["message"] = "Analisis sentimen sedang berlangsung..."
        try:
            success, msg = run_analysis_job()
            PROCESS_STATUS["analysis"]["message"] = msg
            PROCESS_STATUS["analysis"]["success"] = success
        except Exception as e:
            PROCESS_STATUS["analysis"]["message"] = f"Analisis gagal: {str(e)}"
            PROCESS_STATUS["analysis"]["success"] = False
        finally:
            PROCESS_STATUS["analysis"]["running"] = False

    threading.Thread(target=background_analysis, daemon=True).start()
    return jsonify({"status": "success", "message": "Analisis sentimen telah dimulai."})

@app.route("/status", methods=["GET"])
def check_status():
    return jsonify(PROCESS_STATUS)


# ==========================================
# ROUTES UNTUK DATA & VISUALISASI
# ==========================================

@app.route("/get-data", methods=["GET"])
def get_data():
    predicted_path = os.path.join("data", "processed", "review_predicted.csv")
    processed_path = os.path.join("data", "processed", "review_processed(deepseek).csv")
    raw_path = os.path.join("data", "raw", "review_pelabuhan1.csv")

    if os.path.exists(predicted_path):
        df = pd.read_csv(predicted_path)
    elif os.path.exists(processed_path):
        df = pd.read_csv(processed_path)
    elif os.path.exists(raw_path):
        df = pd.read_csv(raw_path)
    else:
        return jsonify({
            "status": "error", 
            "data": [], 
            "summary": {"total": 0, "positif": 0, "negatif": 0, "netral": 0, "avg_rating": 0}
        })

    df = df.fillna("")
    
    summary = {"total": len(df), "positif": 0, "negatif": 0, "netral": 0, "avg_rating": 0}

    if "sentiment" in df.columns:
        sentiment_counts = df["sentiment"].astype(str).str.upper().value_counts().to_dict()
        summary["positif"] = sentiment_counts.get("POSITIF", 0)
        summary["negatif"] = sentiment_counts.get("NEGATIF", 0)
        summary["netral"] = sentiment_counts.get("NETRAL", 0)

    if "rating" in df.columns:
        ratings = pd.to_numeric(df["rating"].astype(str).str.extract(r'(\d+)')[0], errors='coerce')
        summary["avg_rating"] = round(ratings.mean(), 1) if not ratings.isna().all() else 0

    return jsonify({
        "status": "success", 
        "data": df.to_dict(orient="records"), 
        "summary": summary
    })

@app.route("/predict-single", methods=["POST"])
def predict_single():
    req = request.get_json() or {}
    text = req.get("text", "").strip()

    if not text:
        return jsonify({"status": "error", "message": "Teks tidak boleh kosong."}), 400

    try:
        analyzer = SVMSentimentAnalyzer()
        prediction, probs = analyzer.predict_single(text)
        return jsonify({
            "status": "success",
            "text": text,
            "prediction": prediction,
            "probabilities": probs
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/get-evaluation", methods=["GET"])
def get_evaluation():
    report = load_json(EVAL_PATH)
    if report is None:
        return jsonify({"status": "error", "message": "Laporan evaluasi belum ada."}), 404
    return jsonify({"status": "success", "data": report})

@app.route("/get-terms", methods=["GET"])
def get_terms():
    terms = load_json(TERMS_PATH)
    if terms is None:
        try:
            pipeline = SVMSentimentAnalyzer().pipeline
            terms = save_top_terms(pipeline, TERMS_PATH)
        except FileNotFoundError:
            return jsonify({"status": "error", "message": "Model belum dilatih."}), 404
    return jsonify({"status": "success", "data": terms})


# ==========================================
# ENDPOINT VISUALISASI (HYBRID - 3 CHART PYTHON)
# ==========================================
@app.route("/api/charts", methods=["GET"])
def get_charts():
    """Hanya return 3 chart yang tidak bisa dibuat Chart.js."""
    try:
        from modules import visualization as viz
    except ImportError as e:
        return jsonify({"status": "error", "message": f"Gagal import: {e}. Pastikan matplotlib, seaborn, wordcloud sudah diinstall."}), 500

    port = request.args.get("port", "ALL")
    from_date = request.args.get("from", "").strip() or None
    to_date = request.args.get("to", "").strip() or None

    # Muat data
    predicted_path = os.path.join("data", "processed", "review_predicted.csv")
    deepseek_path  = os.path.join("data", "processed", "review_processed(deepseek).csv")
    processed_path = os.path.join("data", "processed", "review_processed.csv")
    raw_path       = os.path.join("data", "raw", "review_pelabuhan1.csv")

    path = None
    for p in (predicted_path, deepseek_path, processed_path, raw_path):
        if os.path.exists(p):
            path = p
            break

    if not path:
        return jsonify({"status": "error", "message": "Tidak ada data"}), 404

    try:
        df = pd.read_csv(path).fillna("")
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    # Filter pelabuhan & tanggal
    if port != "ALL":
        needle = port.lower()
        mask = (
            df.get("lokasi", pd.Series([""] * len(df))).astype(str).str.lower().str.contains(needle)
            | df.get("pelabuhan", pd.Series([""] * len(df))).astype(str).str.lower().str.contains(needle)
        )
        df = df[mask]

    if from_date or to_date:
        if "tanggal_estimasi" in df.columns:
            tgl = pd.to_datetime(df["tanggal_estimasi"], errors="coerce")
        else:
            tgl = pd.Series([pd.NaT] * len(df))
        mask = tgl.notna()
        if from_date:
            mask &= tgl >= pd.to_datetime(from_date)
        if to_date:
            mask &= tgl <= pd.to_datetime(to_date)
        df = df[mask]

    try:
        # Generate 3 Chart Python
        charts = {
            "wordcloud":         viz.chart_wordcloud(df),
            "heatmap":           viz.chart_heatmap(df),
            "confusion_matrix":  viz.chart_confusion_matrix(),
        }
        return jsonify({"status": "success", "charts": charts})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal membuat chart: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)