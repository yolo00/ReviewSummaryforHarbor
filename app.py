import os
import threading
import pandas as pd
from flask import Flask, render_template, jsonify, request

# Import modul dari folder modules
from modules.scraper import run_scraper
from modules.preprocessing import run_preprocessing_job
from modules.train_model import train_svm_model
from modules.predict import SVMSentimentAnalyzer

app = Flask(__name__)

# Status global untuk memantau proses background
PROCESS_STATUS = {
    "scraping": {"running": False, "message": "Belum berjalan", "success": False},
    "preprocessing": {"running": False, "message": "Belum berjalan", "success": False},
    "training": {"running": False, "message": "Belum berjalan", "success": False}
}

def update_status_callback(msg):
    PROCESS_STATUS["scraping"]["message"] = msg

# 1. Dashboard Utama
@app.route("/")
def index():
    return render_template("index.html")

# 2. Endpoint Scraping
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

    thread = threading.Thread(target=background_scraping)
    thread.start()
    return jsonify({"status": "success", "message": "Proses scraping telah dimulai di latar belakang."})

# 3. Endpoint Preprocessing
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

    thread = threading.Thread(target=background_preprocessing)
    thread.start()
    return jsonify({"status": "success", "message": "Proses preprocessing telah dimulai."})

# 4. Endpoint Training Model
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

    thread = threading.Thread(target=background_training)
    thread.start()
    return jsonify({"status": "success", "message": "Pelatihan model telah dimulai."})

# 5. Endpoint Cek Status Running
@app.route("/status", methods=["GET"])
def check_status():
    return jsonify(PROCESS_STATUS)

# 6. Endpoint Ambil Data Tabel
@app.route("/get-data", methods=["GET"])
def get_data():
    predicted_path = os.path.join("data", "processed", "review_predicted.csv")
    processed_path = os.path.join("data", "processed", "review_processed.csv")
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
            "summary": {"total": 0, "positif": 0, "negatif": 0, "netral": 0}
        })

    df = df.fillna("")
    
    # Hitung ringkasan sentimen (abaikan huruf besar/kecil)
    summary = {
        "total": len(df),
        "positif": 0,
        "negatif": 0,
        "netral": 0
    }

    if "sentiment" in df.columns:
        sentiment_counts = df["sentiment"].astype(str).str.upper().value_counts().to_dict()
        summary["positif"] = sentiment_counts.get("POSITIF", 0)
        summary["negatif"] = sentiment_counts.get("NEGATIF", 0)
        summary["netral"] = sentiment_counts.get("NETRAL", 0)

    return jsonify({
        "status": "success", 
        "data": df.to_dict(orient="records"), 
        "summary": summary
    })

# 7. Endpoint Prediksi Teks Tunggal
@app.route("/predict-single", methods=["POST"])
def predict_single():
    req = request.get_json() or {}
    text = req.get("text", "").strip()

    if not text:
        return jsonify({"status": "error", "message": "Teks tidak boleh kosong."}), 400

    try:
        # PERBAIKAN BUG: Menggunakan nama class yang benar
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

if __name__ == "__main__":
    app.run(debug=True, port=5000)