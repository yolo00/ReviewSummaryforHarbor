import os
import re
import time
import platform
import tempfile
from datetime import datetime, timedelta
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PELABUHAN = {
    "Batam Centre": [
        {"nama": "Batam Center International Ferry Terminal", "url": "https://maps.app.goo.gl/xteioSuSkvQCAnCm9"},
        {"nama": "Batam Centre Point International Ferry Terminal", "url": "https://maps.app.goo.gl/RMB8k185hxGftNw47"}
    ],
    "Harbour Bay": [
        {"nama": "Pelabuhan Harbour Bay", "url": "https://maps.app.goo.gl/jtmmKUzjkRCVwtrJA"},
        {"nama": "Harbour Bay Ferry", "url": "https://maps.app.goo.gl/yUsvUuVVQghPGEmi9"},
        {"nama": "Harbour Bay", "url": "https://maps.app.goo.gl/WjXfrRvxBLMu3yQTA"}
    ],
    "Telaga Punggur": [
        {"nama": "Telaga Harbour Crossing Punggur", "url": "https://maps.app.goo.gl/j1bFczwQniiayxQP9"},
        {"nama": "Telaga Punggur", "url": "https://maps.app.goo.gl/2LiPQ5oCNb2cGLgU8"},
        {"nama": "PT ASDP Indonesia Ferry (Persero)", "url": "https://maps.app.goo.gl/QUiwjF6HMAMhHdgM9"},
        {"nama": "Pelabuhan Terminal Ferry Punggur", "url": "https://maps.app.goo.gl/xnuHKq6vWS666BNfA"},
        {"nama": "Telaga Punggur Ferry Terminal", "url": "https://maps.app.goo.gl/MDJ44zpRx9W4RsRy7"},
        {"nama": "Pelabuhan punggur", "url": "https://maps.app.goo.gl/PABS1c6jPK6fKi4y7"},
        {"nama": "Penyebrangan telaga punggur", "url": "https://maps.app.goo.gl/zV5mJCTomE4W76vK7"}
    ],
    "Nongsapura": [
        {"nama": "Pelabuhan internasional Nongsa Pura", "url": "https://maps.app.goo.gl/Y9ibAju4HgcyKTS49"},
        {"nama": "Nongsapura Ferry Terminal", "url": "https://maps.app.goo.gl/LBcbgBcnuswhMRxi7"},
        {"nama": "Batam Nongsapura Port", "url": "https://maps.app.goo.gl/HhstWNLmwUxvQMtZ7"}
    ],
    "Sekupang": [
        {"nama": "Sekupang Ferry Terminal", "url": "https://maps.app.goo.gl/4Zz1vwMkwBxQHeLx6"},
        {"nama": "Pelabuhan Domestik Sekupang", "url": "https://maps.app.goo.gl/PMhxf2b5oDa3Yngq6"},
        {"nama": "SEKUPANG INTERNATIONAL FERRY TERMINAL", "url": "https://maps.app.goo.gl/eWo1Gt5bzVNyf4qd9"},
        {"nama": "Sekupang", "url": "https://maps.app.goo.gl/iR5Sp6GVcVY9jYrF7"}
    ]
}

JUMLAH_SCROLL = 25
SCRAPED_AT_FORMAT = "%Y-%m-%d %H:%M:%S"

# Nama bulan Indonesia (untuk parse tanggal absolut kalau Google menampilkannya)
BULAN_ID = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "agu": 8, "agt": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12,
}

# --- BARU: parser label relatif Google Maps → tanggal absolut ---
def parse_relative_date(label, base_dt=None):
    """Konversi label tanggal Google Maps (relatif) ke datetime.date.

    Contoh label: 'Baru', 'kemarin', '3 jam lalu', '2 minggu lalu',
                  '5 bulan lalu', '1 tahun lalu', 'a week ago', '2 days ago',
                  '12 Januari 2024'.
    Mengembalikan datetime.date atau None.
    """
    if not label:
        return None
    if base_dt is None:
        base_dt = datetime.now()

    text = str(label).strip().lower()
    text = re.sub(r"\bdiedit\b", "", text)
    text = re.sub(r"[()]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None

    # 1. Absolut: "12 Januari 2024" / "12 Jan 2024"
    for name, num in BULAN_ID.items():
        m = re.search(rf"(\d{{1,2}})\s+{name}\s+(\d{{4}})", text)
        if m:
            try:
                return datetime(int(m.group(2)), num, int(m.group(1))).date()
            except ValueError:
                pass

    # 2. "Baru" / "new" → hari ini
    if text in ("baru", "new", "barusan"):
        return base_dt.date()
    if text in ("kemarin", "yesterday"):
        return (base_dt - timedelta(days=1)).date()

    # 3. English → Indonesia
    en_to_id = {
        "minute": "menit", "minutes": "menit",
        "hour": "jam", "hours": "jam",
        "day": "hari", "days": "hari",
        "week": "minggu", "weeks": "minggu",
        "month": "bulan", "months": "bulan",
        "year": "tahun", "years": "tahun",
    }
    for en, idw in en_to_id.items():
        text = re.sub(rf"\b{en}\b", idw, text)
    text = re.sub(r"\ba\b|\ban\b", "1", text)
    text = re.sub(r"\byesterday\b", "kemarin", text)
    text = re.sub(r"\bago\b", "lalu", text)

    # 4. Bentuk "se-" tanpa angka
    text = re.sub(r"\bsehari\b", "1 hari", text)
    text = re.sub(r"\bseminggu\b", "1 minggu", text)
    text = re.sub(r"\bsebulan\b", "1 bulan", text)
    text = re.sub(r"\bsetahun\b", "1 tahun", text)
    text = re.sub(r"\bsejam\b", "1 jam", text)
    text = re.sub(r"\bsemenit\b", "1 menit", text)
    # "lebih dari setahun lalu" / "over a year ago"
    text = re.sub(r"\blebih dari\b", "", text).strip()

    m = re.search(r"(\d+)\s*(menit|jam|hari|minggu|bulan|tahun)", text)
    if not m:
        return None

    n = int(m.group(1))
    unit = m.group(2)
    if unit == "menit":  return (base_dt - timedelta(minutes=n)).date()
    if unit == "jam":    return (base_dt - timedelta(hours=n)).date()
    if unit == "hari":   return (base_dt - timedelta(days=n)).date()
    if unit == "minggu": return (base_dt - timedelta(weeks=n)).date()
    if unit == "bulan":  return (base_dt - timedelta(days=n * 30)).date()
    if unit == "tahun":  return (base_dt - timedelta(days=n * 365)).date()
    return None


# --- BARU: deteksi baris tanggal yang lebih tahan-banting ---
def _is_date_line(line):
    l = str(line).strip().lower()
    if l in ("baru", "new", "kemarin", "yesterday"):
        return True
    keys = (
        "menit lalu", "jam lalu", "hari lalu", "minggu lalu", "bulan lalu", "tahun lalu",
        "hari yang lalu", "minggu yang lalu", "bulan yang lalu", "tahun yang lalu",
        "sehari", "seminggu", "sebulan", "setahun",
    )
    return any(k in l for k in keys)


def init_driver():
    if platform.system() == "Linux":
        options = ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        options.add_argument(f"--user-data-dir={tempfile.mkdtemp()}")
        driver = webdriver.Chrome(options=options)
    else:
        options = EdgeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--disable-search-engine-choice-screen")
        scraper_profile_dir = os.path.join(os.path.expanduser("~"), "EdgeScraperProfile")
        options.add_argument(f"--user-data-dir={scraper_profile_dir}")
        driver = webdriver.Edge(options=options)

    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def bersihkan_review(teks):
    teks = re.sub(r"\b\d{1,2}:\d{2}\b", "", teks)
    teks = re.sub(r"[\ue000-\uf8ff]", "", teks)
    teks = re.sub(r"\+\d+(?:\s+\d+)?", "", teks)

    # --- FIX: hapus tombol UI Google Maps ---
    ui_patterns = [
        r"lihat terjemahan\s*\([^)]*\)",       # Lihat terjemahan (Indonesia)
        r"lihat terjemahan\b",                  # Lihat terjemahan
        r"lihat terjemahan lainnya\b",
        r"terjemahkan ulasan ini\b",
        r"see translation\s*\([^)]*\)",         # See translation (English)
        r"see translation\b",
        r"see original\s*\([^)]*\)",            # See original (Indonesian)
        r"see original\b",
        r"translated by google\b",
        r"diterjemahkan oleh google\b",
        r"\(translated by google\)",
        r"\(diterjemahkan oleh google\)",
        r"\(original\)",
        r"\(asli\)",
    ]
    for pat in ui_patterns:
        teks = re.sub(pat, " ", teks, flags=re.IGNORECASE)

    teks = re.sub(r"\blihat ulasan lainnya\b", "", teks, flags=re.IGNORECASE)
    teks = re.sub(r"\blainnya\b", "", teks, flags=re.IGNORECASE)
    teks = re.sub(r"^\s*BARU\s+", "", teks, flags=re.IGNORECASE)
    teks = teks.replace("…", "")
    teks = re.sub(r"\s+\d{1,2}\s*$", "", teks)
    return re.sub(r"\s+", " ", teks).strip()


def bersihkan_tanggal(teks_tanggal):
    if not teks_tanggal:
        return None
    teks = re.sub(r"diedit", "", teks_tanggal, flags=re.IGNORECASE)
    teks = re.sub(r"[()]", "", teks)
    return re.sub(r"\s+", " ", teks).strip()


def run_scraper(update_status_callback):
    driver = None
    data_review = []
    scraped_at_str = datetime.now().strftime(SCRAPED_AT_FORMAT)
    scraped_at_dt = datetime.strptime(scraped_at_str, SCRAPED_AT_FORMAT)

    try:
        update_status_callback("Membuat sesi browser...")
        driver = init_driver()
        wait = WebDriverWait(driver, 10)

        for lokasi, targets in PELABUHAN.items():
            for target in targets:
                update_status_callback(f"Membuka {target['nama']}...")
                driver.get(target["url"])
                time.sleep(5)

                try:
                    tutup_btns = driver.find_elements(
                        By.XPATH,
                        "//button[contains(., 'Setuju') or contains(., 'Tolak') or contains(., 'Lain kali') or contains(., 'Tutup')]"
                    )
                    for btn in tutup_btns:
                        if btn.is_displayed():
                            driver.execute_script("arguments[0].click();", btn)
                            time.sleep(1)
                except Exception:
                    pass

                try:
                    xpath_tab = (
                        "//button[@role='tab' "
                        "and (contains(@aria-label, 'Ulasan') or contains(., 'Ulasan')) "
                        "and not(contains(translate(@aria-label, 'TUIS', 'tuis'), 'tulis'))]"
                    )
                    tombol = wait.until(EC.presence_of_element_located((By.XPATH, xpath_tab)))
                    driver.execute_script("arguments[0].click();", tombol)
                    time.sleep(3)
                except Exception:
                    pass

                try:
                    btn_lihat_lainnya = driver.find_elements(By.XPATH, "//*[contains(text(), 'Lihat ulasan lainnya')]")
                    for btn in btn_lihat_lainnya:
                        if btn.is_displayed():
                            driver.execute_script("arguments[0].click();", btn)
                            time.sleep(3)
                            break
                except Exception:
                    pass

                try:
                    panel = wait.until(
                        EC.presence_of_element_located(
                            (By.XPATH, "//div[@aria-label='Saring ulasan']/ancestor::div[contains(@class, 'm6QErb')] | //div[contains(@class, 'm6QErb') and contains(@class, 'DshB1e')]")
                        )
                    )
                    ActionChains(driver).move_to_element(panel).click().perform()
                    for i in range(JUMLAH_SCROLL):
                        ActionChains(driver).send_keys(Keys.PAGE_DOWN).perform()
                        time.sleep(1.5)
                        update_status_callback(f"Scrolling {target['nama']} ({i+1}/{JUMLAH_SCROLL})")
                except Exception:
                    try:
                        panels = driver.find_elements(By.CSS_SELECTOR, "div.m6QErb")
                        for p in panels:
                            driver.execute_script("arguments[0].scrollTop += 1200;", p)
                        time.sleep(1.5)
                    except Exception:
                        continue

                review_elements = driver.find_elements(By.CSS_SELECTOR, "div.jftiEf")
                for r in review_elements:
                    try:
                        btn = r.find_elements(By.XPATH, ".//*[contains(text(), 'Lainnya')]")
                        if btn:
                            driver.execute_script("arguments[0].click();", btn[0])
                    except Exception:
                        pass

                review_elements = driver.find_elements(By.CSS_SELECTOR, "div.jftiEf")
                for review in review_elements:
                    try:
                        lines = [l.strip() for l in review.text.strip().split("\n") if l.strip()]

                        try:
                            nama = review.find_element(By.CSS_SELECTOR, ".d4r55").text.strip()
                        except Exception:
                            nama = lines[0] if lines else ""

                        try:
                            rating_text = review.find_element(By.CSS_SELECTOR, "span.kvMYJc").get_attribute("aria-label")
                            rating = int(rating_text.split()[0])
                        except Exception:
                            rating = None

                        tanggal_raw = None
                        for line in lines:
                            if _is_date_line(line):
                                tanggal_raw = line
                                break

                        tanggal = bersihkan_tanggal(tanggal_raw)

                        # --- BARU: estimasi tanggal absolut ---
                        tanggal_estimasi = None
                        if tanggal:
                            parsed = parse_relative_date(tanggal, scraped_at_dt)
                            if parsed:
                                tanggal_estimasi = parsed.isoformat()  # YYYY-MM-DD

                        teks_review = ""
                        if tanggal_raw and tanggal_raw in lines:
                            kandidat = lines[lines.index(tanggal_raw) + 1:]
                            kandidat = [x for x in kandidat if x not in ["Suka", "Bagikan", "Lainnya", "Lihat ulasan lainnya"]]
                            teks_review = bersihkan_review(" ".join(kandidat))

                        ada_foto = False
                        try:
                            foto_elements = review.find_elements(
                                By.CSS_SELECTOR,
                                "button.KT3P4, button[data-photo-index], div.T7L23e, button[aria-label*='foto'], button[aria-label*='photo']"
                            )
                            ada_foto = len(foto_elements) > 0
                        except Exception:
                            ada_foto = False

                        if teks_review:
                            data_review.append({
                                "lokasi": lokasi,
                                "pelabuhan": target["nama"],
                                "nama_reviewer": nama,
                                "rating": rating,
                                "tanggal": tanggal,                    # label asli
                                "tanggal_estimasi": tanggal_estimasi,  # BARU: ISO date
                                "review": teks_review,
                                "ada_foto": ada_foto,
                                "scraped_at": scraped_at_str,
                            })
                    except Exception:
                        pass

        if data_review:
            df = pd.DataFrame(data_review)
            df = df.drop_duplicates(subset=["lokasi", "nama_reviewer", "rating", "review"], keep="first")

            folder_raw = os.path.join("data", "raw")
            os.makedirs(folder_raw, exist_ok=True)
            path_file = os.path.join(folder_raw, "review_pelabuhan1.csv")

            try:
                df.to_csv(path_file, index=False, encoding="utf-8-sig")
                return len(df), "Selesai! Data berhasil disimpan."
            except PermissionError:
                return len(df), "Gagal menyimpan: Tutup dulu file 'review_pelabuhan1.csv' yang sedang terbuka di Excel!"

        return 0, "Gagal mengambil data."

    finally:
        if driver:
            driver.quit()