"""Penjadwal pembaruan data otomatis (UC-19 / US-10).

Setiap INTERVAL_HARI hari (default 3) menjalankan urutan:
    1. scraping ulasan terbaru (menambah ke CSV lama, tidak menimpa)
    2. preprocessing
    3. analisis sentimen (prediksi + rekap)
Training model TIDAK ikut: model dilatih manual.

Cara pakai
----------
A. Di dalam aplikasi web (thread latar belakang), pada app.py:

        from modules.scheduler import mulai_penjadwalan
        mulai_penjadwalan()

   Catatan: pembaruan pertama harus dijalankan sekali secara manual
   (lihat B), supaya scraper tidak tiba-tiba membuka browser saat server
   dinyalakan. Setelah itu penjadwal berjalan sendiri tiap 3 hari.

B. Dari terminal / cron / Windows Task Scheduler (jalankan dari folder utama proyek):

        python -m modules.scheduler --sekali          # paksa jalan sekarang
        python -m modules.scheduler --jika-waktunya   # jalan hanya bila sudah 3 hari
        python -m modules.scheduler --loop            # terus berjalan, cek tiap jam
        python -m modules.scheduler --status          # lihat status terakhir

Status disimpan di data/scheduler_state.json, sehingga jadwal tidak
hilang saat aplikasi dimatikan atau dimulai ulang.
"""
import argparse
import json
import logging
import os
import sys
import threading
from datetime import datetime, timedelta

import pandas as pd

# ---------------------------------------------------------------------------
# KONFIGURASI
# ---------------------------------------------------------------------------
INTERVAL_HARI = 3            # jarak antar pembaruan yang berhasil
INTERVAL_CEK_MENIT = 60      # seberapa sering thread memeriksa apakah sudah waktunya
JEDA_ULANG_JAM = 6           # jarak minimal antar percobaan bila pembaruan gagal
KUNCI_KEDALUWARSA_JAM = 6    # kunci yang lebih tua dianggap sisa proses yang mati

# Harus sama dengan CSV_PATH di scraper.py dan keluaran default predict.run_analysis_job
RAW_CSV_PATH = os.path.join("data", "raw", "review_pelabuhan(fix).csv")
PREDICTED_CSV_PATH = os.path.join("data", "processed", "review_predicted(fix).csv")
STATE_PATH = os.path.join("data", "scheduler_state.json")
LOCK_PATH = os.path.join("data", "scheduler.lock")

FORMAT_WAKTU = "%Y-%m-%d %H:%M:%S"

log = logging.getLogger("scheduler")

_THREAD = None
_THREAD_LOCK = threading.Lock()
_STOP = threading.Event()


# ---------------------------------------------------------------------------
# STATUS (disimpan ke file agar tahan restart)
# ---------------------------------------------------------------------------
def _baca_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _simpan_state(**perubahan):
    state = _baca_state()
    state.update(perubahan)
    os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
    path_tmp = STATE_PATH + ".tmp"
    with open(path_tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(path_tmp, STATE_PATH)
    return state


def _parse_waktu(teks):
    try:
        return datetime.strptime(teks, FORMAT_WAKTU)
    except (TypeError, ValueError):
        return None


def _belum_pernah_jalan():
    state = _baca_state()
    return _parse_waktu(state.get("terakhir_dijalankan")) is None and \
        _parse_waktu(state.get("terakhir_percobaan")) is None


def _sudah_waktunya(sekarang=None):
    """True bila pembaruan sudah jatuh tempo.

    - Belum pernah jalan                       -> True
    - Pembaruan berhasil terakhir < 3 hari lalu -> False
    - Percobaan terakhir (gagal) < 6 jam lalu   -> False (jangan menghantam terus)
    - Selain itu                               -> True
    """
    sekarang = sekarang or datetime.now()
    state = _baca_state()
    terakhir = _parse_waktu(state.get("terakhir_dijalankan"))
    percobaan = _parse_waktu(state.get("terakhir_percobaan"))

    if terakhir is None and percobaan is None:
        return True
    if terakhir is not None and sekarang - terakhir < timedelta(days=INTERVAL_HARI):
        return False
    if percobaan is not None and sekarang - percobaan < timedelta(hours=JEDA_ULANG_JAM):
        return False
    return True


# ---------------------------------------------------------------------------
# KUNCI (mencegah dua pembaruan berjalan bersamaan, termasuk antar proses)
# ---------------------------------------------------------------------------
def _ambil_kunci():
    os.makedirs(os.path.dirname(LOCK_PATH) or ".", exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                umur = datetime.now().timestamp() - os.path.getmtime(LOCK_PATH)
            except OSError:
                continue  # kunci baru saja dilepas, coba lagi
            if umur > KUNCI_KEDALUWARSA_JAM * 3600:
                log.warning("Kunci lama (%.1f jam) dihapus.", umur / 3600)
                try:
                    os.remove(LOCK_PATH)
                except OSError:
                    pass
                continue
            return False
        else:
            with os.fdopen(fd, "w") as f:
                f.write(str(os.getpid()))
            return True
    return False


def _lepas_kunci():
    try:
        os.remove(LOCK_PATH)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# LANGKAH PEMBARUAN
# ---------------------------------------------------------------------------
def _muat_pipeline():
    """Impor fungsi pipeline (ditunda agar scheduler ringan saat diimpor)."""
    try:
        from modules.scraper import run_scraper
        from modules.preprocessing import run_preprocessing_job
        from modules.predict import run_analysis_job
    except ModuleNotFoundError as e:
        if (e.name or "").split(".")[0] != "modules":
            raise  # library yang kurang (mis. selenium), tampilkan apa adanya
        from scraper import run_scraper
        from preprocessing import run_preprocessing_job
        from predict import run_analysis_job
    return run_scraper, run_preprocessing_job, run_analysis_job


def _hitung_ulasan(path_csv):
    try:
        return len(pd.read_csv(path_csv, encoding="utf-8-sig", usecols=["review"]))
    except (FileNotFoundError, ValueError, pd.errors.EmptyDataError):
        return 0


def _perlu_diproses(ulasan_baru):
    """Proses bila ada ulasan baru, atau hasil analisis lebih tua dari data mentah
    (mis. pembaruan sebelumnya gagal setelah scraping berhasil)."""
    if ulasan_baru > 0:
        return True
    if not os.path.exists(PREDICTED_CSV_PATH) or not os.path.exists(RAW_CSV_PATH):
        return True
    return os.path.getmtime(RAW_CSV_PATH) > os.path.getmtime(PREDICTED_CSV_PATH)


def _catat_status(pesan):
    if ": scroll #" not in str(pesan):  # pesan scroll terlalu ramai
        log.info(pesan)


def _proses_pembaruan():
    """Jalankan scraping, preprocessing, analisis. Return (berhasil, pesan, ulasan_baru)."""
    run_scraper, run_preprocessing_job, run_analysis_job = _muat_pipeline()
    sebelum = _hitung_ulasan(RAW_CSV_PATH)

    log.info("[1/3] Scraping ulasan terbaru...")
    try:
        # run_scraper selalu menambah ke CSV lama (ulasan yang sudah ada dilewati)
        scrape_ok, pesan_scrape = run_scraper(_catat_status)
    except Exception as e:
        return False, f"Scraping gagal: {e}", 0
    ulasan_baru = max(0, _hitung_ulasan(RAW_CSV_PATH) - sebelum)
    ringkas = str(pesan_scrape).splitlines()[0] if pesan_scrape else ""
    if not scrape_ok and ulasan_baru == 0:
        return False, f"Scraping tidak berhasil. {ringkas}", 0
    # scrape_ok False tetapi ada ulasan baru: sebagian target gagal, ulasan yang
    # sudah tersimpan tetap diproses agar tidak terbuang.
    (log.info if scrape_ok else log.warning)(ringkas)

    if not _perlu_diproses(ulasan_baru):
        return True, "Tidak ada ulasan baru, tidak ada pembaruan.", 0

    log.info("[2/3] Preprocessing...")
    berhasil, pesan = run_preprocessing_job()
    if not berhasil:
        return False, f"Preprocessing gagal: {pesan}", ulasan_baru

    log.info("[3/3] Analisis sentimen...")
    berhasil, pesan = run_analysis_job()
    if not berhasil:
        return False, f"Analisis gagal: {pesan}", ulasan_baru

    return True, f"Pembaruan selesai: {ulasan_baru} ulasan baru. {pesan}", ulasan_baru


def jalankan_pembaruan():
    """Jalankan satu putaran pembaruan sekarang juga. Return (berhasil, pesan).

    Bila gagal, data lama tetap utuh dan jadwal berikutnya dicoba lagi
    setelah JEDA_ULANG_JAM jam. Jadwal 3 hari hanya maju bila berhasil.
    """
    if not _ambil_kunci():
        return False, "Pembaruan lain sedang berjalan."
    try:
        try:
            berhasil, pesan, ulasan_baru = _proses_pembaruan()
        except Exception as e:  # jaga agar thread penjadwal tidak mati
            log.exception("Pembaruan gagal tak terduga")
            berhasil, pesan, ulasan_baru = False, f"Pembaruan gagal: {e}", 0

        sekarang = datetime.now().strftime(FORMAT_WAKTU)
        perubahan = {
            "terakhir_percobaan": sekarang,
            "sukses": berhasil,
            "hasil_terakhir": pesan,
            "ulasan_baru": ulasan_baru,
        }
        if berhasil:
            perubahan["terakhir_dijalankan"] = sekarang
        _simpan_state(**perubahan)

        (log.info if berhasil else log.error)(pesan)
        return berhasil, pesan
    finally:
        _lepas_kunci()


def jalankan_jika_waktunya():
    """Jalankan pembaruan hanya bila sudah jatuh tempo.

    Return (berhasil, pesan) bila dijalankan, atau None bila belum waktunya.
    """
    if not _sudah_waktunya():
        return None
    return jalankan_pembaruan()


# ---------------------------------------------------------------------------
# PENJADWALAN
# ---------------------------------------------------------------------------
def _loop(detik_antar_cek, jalankan_pertama):
    peringatan_tampil = False
    while not _STOP.is_set():
        try:
            if _belum_pernah_jalan() and not jalankan_pertama:
                if not peringatan_tampil:
                    log.warning(
                        "Pembaruan belum pernah dijalankan. Jalankan sekali secara manual: "
                        "python -m modules.scheduler --sekali  (atau mulai_penjadwalan(jalankan_pertama=True))."
                    )
                    peringatan_tampil = True
            else:
                jalankan_jika_waktunya()
        except Exception:
            log.exception("Pemeriksaan jadwal gagal")
        _STOP.wait(detik_antar_cek)


def mulai_penjadwalan(interval_cek_menit=INTERVAL_CEK_MENIT, jalankan_pertama=False):
    """Mulai thread latar belakang yang memeriksa jadwal tiap interval_cek_menit menit.

    Aman dipanggil berulang (tidak membuat thread kedua). Bila aplikasi Flask
    dijalankan dengan debug=True, reloader membuat dua proses; kunci file
    mencegah pembaruan berjalan dobel.

    jalankan_pertama=False: bila belum pernah ada pembaruan, thread tidak
    langsung menjalankannya (hindari browser scraper terbuka saat server nyala).
    """
    global _THREAD
    with _THREAD_LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return _THREAD
        _STOP.clear()
        _THREAD = threading.Thread(
            target=_loop,
            args=(interval_cek_menit * 60, jalankan_pertama),
            name="scheduler-pembaruan",
            daemon=True,
        )
        _THREAD.start()
        log.info("Penjadwal dimulai: pembaruan tiap %d hari, cek tiap %d menit.",
                 INTERVAL_HARI, interval_cek_menit)
        return _THREAD


def hentikan_penjadwalan():
    _STOP.set()


# ---------------------------------------------------------------------------
# COMMAND LINE
# ---------------------------------------------------------------------------
def _tampilkan_status():
    state = _baca_state()
    if not state:
        print("Belum pernah dijalankan.")
        return
    terakhir = _parse_waktu(state.get("terakhir_dijalankan"))
    print(f"Terakhir berhasil : {state.get('terakhir_dijalankan', '-')}")
    print(f"Percobaan terakhir: {state.get('terakhir_percobaan', '-')} "
          f"({'berhasil' if state.get('sukses') else 'GAGAL'})")
    print(f"Ulasan baru       : {state.get('ulasan_baru', 0)}")
    print(f"Hasil terakhir    : {state.get('hasil_terakhir', '-')}")
    if terakhir:
        print(f"Jatuh tempo       : {(terakhir + timedelta(days=INTERVAL_HARI)).strftime(FORMAT_WAKTU)}")
    print(f"Sudah waktunya    : {'ya' if _sudah_waktunya() else 'belum'}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=f"Pembaruan data otomatis tiap {INTERVAL_HARI} hari "
                    "(scraping, preprocessing, analisis sentimen)."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--sekali", action="store_true", help="jalankan pembaruan sekarang (abaikan jadwal)")
    mode.add_argument("--jika-waktunya", action="store_true", help="jalankan hanya bila sudah jatuh tempo")
    mode.add_argument("--loop", action="store_true", help="terus berjalan dan memeriksa jadwal")
    mode.add_argument("--status", action="store_true", help="tampilkan status pembaruan terakhir")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.status:
        _tampilkan_status()
        return 0

    if args.sekali:
        berhasil, pesan = jalankan_pembaruan()
        print(("OK: " if berhasil else "GAGAL: ") + pesan)
        return 0 if berhasil else 1

    if args.jika_waktunya:
        hasil = jalankan_jika_waktunya()
        if hasil is None:
            print("Belum waktunya.")
            return 0
        berhasil, pesan = hasil
        print(("OK: " if berhasil else "GAGAL: ") + pesan)
        return 0 if berhasil else 1

    try:
        _loop(INTERVAL_CEK_MENIT * 60, jalankan_pertama=True)
    except KeyboardInterrupt:
        print("Dihentikan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
