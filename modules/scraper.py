import os
import re
import time
import platform
import tempfile
import hashlib
import gc
from collections import Counter
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
from selenium.common.exceptions import (
    StaleElementReferenceException,
    WebDriverException,
)

class FatalScrapeError(Exception):
    pass

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

CSV_PATH = os.path.join("data", "raw", "review_pelabuhan(fix).csv")
SCRAPED_AT_FORMAT = "%Y-%m-%d %H:%M:%S"

CSV_COLUMNS = [
    "lokasi", "pelabuhan", "nama_reviewer", "rating",
    "tanggal", "tanggal_estimasi", "review", "memiliki_foto", "scraped_at"
]

BULAN_ID = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "agu": 8, "agt": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12,
}

# ============ DETEKSI MEDIA ============
def detect_photo_indicator(review):
    try:
        if review.find_elements(By.CSS_SELECTOR, "button[data-photo-index]"):
            return "data-photo-index"
    except Exception:
        pass
    return None

# ============ KUNCI PEMBANDING ULASAN ============
TEKS_KOSONG = "[Tanpa Teks]"

def _kunci_ulasan(pelabuhan, rating, review):
    """Kunci pembanding ulasan: pelabuhan + jumlah bintang + isi ulasan.

    Isi ulasan dinormalisasi (spasi berlebih, huruf besar/kecil) agar beda format
    kecil tidak membuat ulasan yang sama dianggap baru. Nama reviewer dan tanggal
    sengaja TIDAK dipakai: nama tidak diambil lagi, dan label relatif Google Maps
    ("4 bulan lalu") berubah setiap scraping sehingga ulasan yang sama akan
    terlihat berbeda.
    """
    try:
        bintang = int(float(rating))
    except (TypeError, ValueError):
        bintang = None
    teks = "" if pd.isna(review) else re.sub(r"\s+", " ", str(review)).strip().casefold()
    pel = "" if pd.isna(pelabuhan) else str(pelabuhan).strip().casefold()
    return (pel, bintang, teks)

def _punya_teks(review):
    """Ulasan tanpa teks tidak bisa dibedakan lewat isinya, jadi tidak ikut pencocokan."""
    if pd.isna(review):
        return False
    return str(review).strip().casefold() not in ("", TEKS_KOSONG.casefold())

# ============ PARSING TANGGAL ============
def parse_relative_date(label, base_dt=None):
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
    for name, num in BULAN_ID.items():
        m = re.search(rf"(\d{{1,2}})\s+{name}\s+(\d{{4}})", text)
        if m:
            try:
                return datetime(int(m.group(2)), num, int(m.group(1))).date()
            except ValueError:
                pass
    if text in ("baru", "new", "barusan"):
        return base_dt.date()
    if text in ("kemarin", "yesterday"):
        return (base_dt - timedelta(days=1)).date()
    en_to_id = {
        "minute": "menit", "minutes": "menit", "hour": "jam", "hours": "jam",
        "day": "hari", "days": "hari", "week": "minggu", "weeks": "minggu",
        "month": "bulan", "months": "bulan", "year": "tahun", "years": "tahun",
    }
    for en, idw in en_to_id.items():
        text = re.sub(rf"\b{en}\b", idw, text)
    text = re.sub(r"\ba\b|\ban\b", "1", text).replace("yesterday", "kemarin").replace("ago", "lalu")
    text = re.sub(r"\bsehari\b", "1 hari", text).replace("seminggu", "1 minggu")
    text = text.replace("sebulan", "1 bulan").replace("setahun", "1 tahun")
    text = text.replace("sejam", "1 jam").replace("semenit", "1 menit")
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

def _is_date_line(line):
    l = str(line).strip().lower()
    if l in ("baru", "new", "kemarin", "yesterday"):
        return True
    if re.search(r"\d{1,2}\s+(januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember|jan|feb|mar|apr|jun|jul|agu|agt|sep|okt|nov|des)\s+\d{4}", l):
        return True
    if re.search(r"\d+\s+(minute|hour|day|week|month|year)s?\s+ago", l):
        return True
    keys = ("menit lalu", "jam lalu", "hari lalu", "minggu lalu", "bulan lalu", "tahun lalu",
            "hari yang lalu", "minggu yang lalu", "bulan yang lalu", "tahun yang lalu",
            "sehari", "seminggu", "sebulan", "setahun")
    return any(k in l for k in keys)

# ============ DRIVER ============
def init_driver():
    prefs = {
        "profile.managed_default_content_settings.images": 1,
        "profile.default_content_setting_values.notifications": 2,
    }
    if platform.system() == "Linux":
        options = ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(f"--user-data-dir={tempfile.mkdtemp()}")
        options.add_experimental_option("prefs", prefs)
        driver = webdriver.Chrome(options=options)
    else:
        options = EdgeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--disable-search-engine-choice-screen")
        scraper_dir = os.path.join(os.path.expanduser("~"), "EdgeScraperProfile")
        options.add_argument(f"--user-data-dir={scraper_dir}")
        options.add_experimental_option("prefs", prefs)
        driver = webdriver.Edge(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

# ============ CHIP SNAPSHOT & INSPECTION ============
CHIP_JS = """
const out = [];
const els = document.querySelectorAll("button, [role='radio'], [role='tab']");
els.forEach((el, i) => {
    if (el.closest('div.jftiEf')) return;
    const r = el.getBoundingClientRect();
    if (r.width < 30 || r.height < 18 || r.height > 70 || r.width > 500) return;
    if (el.getAttribute('role') === 'tab') return;
    const cs = getComputedStyle(el);
    out.push({
        i, tag: el.tagName, role: el.getAttribute('role'),
        checked: el.getAttribute('aria-checked'),
        pressed: el.getAttribute('aria-pressed'),
        selected: el.getAttribute('aria-selected'),
        label: el.getAttribute('aria-label'),
        text: (el.innerText || '').replace(/\\s+/g, ' ').trim(),
        bg: cs.backgroundColor, cls: el.className,
        x: r.left + r.width / 2, y: r.top + r.height / 2, area: r.width * r.height
    });
});
return out;
"""

def chip_snapshot(driver):
    try:
        return driver.execute_script(CHIP_JS) or []
    except Exception:
        return []

def dump_chips(driver, label=""):
    """Debug: print semua chip state untuk inspeksi."""
    print(f"\n{'='*70}")
    print(f"[DUMP CHIPS] {label}")
    print(f"{'='*70}")
    for c in chip_snapshot(driver):
        active_markers = []
        if c['checked'] == 'true': active_markers.append('checked')
        if c['pressed'] == 'true': active_markers.append('pressed')
        if c['selected'] == 'true': active_markers.append('selected')
        marker = f"← {'+'.join(active_markers)}" if active_markers else ""
        print(f"  [{c['i']:02d}] text={c['text']!r:40s} label={c['label']!r:20s} bg={c['bg']:20s} {marker}")
    print(f"{'='*70}\n")

def _find_semua(snap):
    """Cari chip 'Semua' — ambil elemen paling dalam (min area)."""
    cands = []
    for c in snap:
        text_lower = c['text'].lower()
        label_lower = (c['label'] or '').lower()
        # Match: text starts with "semua" atau "all", atau label exact
        if re.match(r"^(semua|all)\b", text_lower):
            cands.append(c)
        elif label_lower in ('semua', 'semua ulasan', 'all', 'all reviews'):
            cands.append(c)
    if not cands:
        return None
    # Ambil elemen paling dalam = area terkecil (button dalam wrapper)
    return min(cands, key=lambda c: c['area'])

def _is_on(c):
    """Cek apakah chip aktif (dari 3 attribute)."""
    return any(v == 'true' for v in (c['checked'], c['pressed'], c['selected']))

def _cdp_click(driver, x, y):
    """Klik via CDP — trusted OS-level event, paling reliable untuk React."""
    for t, extra in (
        ("mouseMoved", {}),
        ("mousePressed", {"button": "left", "clickCount": 1}),
        ("mouseReleased", {"button": "left", "clickCount": 1}),
    ):
        try:
            driver.execute_cdp_cmd("Input.dispatchMouseEvent",
                                   {"type": t, "x": x, "y": y, **extra})
            time.sleep(0.05)
        except Exception:
            pass

def reset_topic_filter(driver):
    """
    Reset filter chip ke 'Semua'.
    Return:
      - 'OK:cdp' / 'OK:js' → sukses
      - 'already-on-all' → sudah Semua
      - 'CHANGED-UNVERIFIED:<method>' → klik berhasil tapi state tidak bisa diverifikasi
      - 'semua-not-found' → tombol 'Semua' tidak ada di DOM
      - 'FAILED' → klik tidak berefek (perlu investigasi manual)
    """
    snap = chip_snapshot(driver)
    if not snap:
        return 'semua-not-found'
    
    semua = _find_semua(snap)
    if not semua:
        return 'semua-not-found'
    
    # Sudah aktif?
    if _is_on(semua):
        return 'already-on-all'
    
    # Snapshot BEFORE
    before_sig = [(c['text'], c['bg'], c['cls']) for c in snap]

    for method in ("cdp", "js"):
        # Re-locate element (bisa stale setelah scroll)
        try:
            el = driver.execute_script(
                "return document.querySelectorAll(\"button, [role='radio'], [role='tab']\")[arguments[0]];",
                semua['i'])
            if not el:
                return 'semua-not-found'
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.5)
        except Exception:
            return 'semua-not-found'
        
        # Re-snapshot untuk koordinat terbaru
        snap2 = chip_snapshot(driver)
        s2 = _find_semua(snap2)
        if not s2:
            return 'semua-not-found'
        
        # Klik
        if method == "cdp":
            _cdp_click(driver, s2['x'], s2['y'])
        else:
            try:
                driver.execute_script("arguments[0].click();", el)
            except Exception:
                pass
        
        time.sleep(3)
        
        # Verify
        snap3 = chip_snapshot(driver)
        s3 = _find_semua(snap3)
        
        # Cek 1: attribute-based
        if s3 and _is_on(s3):
            return f'OK:{method}'
        
        # Cek 2: tidak ada chip yang aktif (semua off) → kemungkinan "Semua" default
        any_active = any(_is_on(c) for c in snap3)
        if not any_active:
            return f'CHANGED-UNVERIFIED:{method}'
        
        # Cek 3: visual diff (background / class berubah)
        after_sig = [(c['text'], c['bg'], c['cls']) for c in snap3]
        if after_sig != before_sig:
            # Ada perubahan visual tapi attribute tidak akurat
            # Cek apakah chip topik lama masih aktif
            still_topic = []
            for c in snap3:
                if _is_on(c):
                    t = c['text'].lower()
                    if not (t.startswith('semua') or t.startswith('all')):
                        still_topic.append(c['text'])
            if not still_topic:
                return f'CHANGED-UNVERIFIED:{method}'
    
    return 'FAILED'

# ============ PANEL & SCROLL ============
def get_feed_panel(driver, max_wait=15):
    start = time.time()
    while time.time() - start < max_wait:
        try:
            result = driver.execute_script("""
                function isScrollable(el) {
                    if (!el || el === document.body) return false;
                    const style = window.getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    if (r.width < 100 || r.height < 100) return false;
                    if (style.overflowY !== 'auto' && style.overflowY !== 'scroll') return false;
                    return el.scrollHeight > el.clientHeight + 50;
                }
                if (document.querySelectorAll("div.jftiEf").length === 0) return null;
                const feeds = document.querySelectorAll("div[role='feed']");
                for (const feed of feeds) {
                    if (feed.querySelector("div.jftiEf") && isScrollable(feed)) return feed;
                }
                const firstCard = document.querySelector("div.jftiEf");
                if (firstCard) {
                    let el = firstCard.parentElement;
                    let depth = 0;
                    while (el && el !== document.body && depth < 30) {
                        if (isScrollable(el)) return el;
                        el = el.parentElement;
                        depth++;
                    }
                }
                return null;
            """)
            if result:
                return result
        except Exception:
            pass
        time.sleep(1)
    return None

def get_panel_cards(driver, panel):
    try:
        return panel.find_elements(By.CSS_SELECTOR, "div.jftiEf"), panel
    except StaleElementReferenceException:
        new_panel = get_feed_panel(driver, max_wait=10)
        if not new_panel:
            return [], None
        try:
            return new_panel.find_elements(By.CSS_SELECTOR, "div.jftiEf"), new_panel
        except Exception:
            return [], None
    except Exception:
        return [], None

def get_scroll_metrics(driver, panel):
    for attempt in range(3):
        try:
            metrics = driver.execute_script("""
                return { top: arguments[0].scrollTop, height: arguments[0].scrollHeight };
            """, panel)
            return metrics, panel
        except (StaleElementReferenceException, WebDriverException):
            time.sleep(1)
            panel = get_feed_panel(driver, max_wait=5)
            if panel is None:
                continue
    return None, None

def safe_scroll(driver, panel):
    for attempt in range(2):
        try:
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", panel)
            return True, panel
        except StaleElementReferenceException:
            if attempt == 0:
                time.sleep(0.5)
                new_panel = get_feed_panel(driver, max_wait=5)
                if not new_panel:
                    return False, None
                panel = new_panel
            else:
                return False, None
        except WebDriverException:
            if attempt == 0:
                time.sleep(1)
                new_panel = get_feed_panel(driver, max_wait=5)
                if not new_panel:
                    return False, None
                panel = new_panel
            else:
                return False, None
    return False, None

# ============ CLEANING ============
def bersihkan_review(teks):
    if not teks:
        return ""
    clean_lines = []
    for line in str(teks).splitlines():
        line = line.strip()
        if not line:
            continue
        if line.upper() in ("BARU", "NEW"):
            continue
        if re.fullmatch(r"(Suka|Bagikan|Lainnya|More|Like|Share|Lihat ulasan lainnya|Terjemahkan|Translate)",
                        line, flags=re.IGNORECASE):
            continue
        clean_lines.append(line)
    teks = " ".join(clean_lines)
    ui_patterns = [
        r"lihat terjemahan(?:\s*\([^)]*\))?", r"lihat terjemahan lainnya",
        r"terjemahkan ulasan ini", r"see translation(?:\s*\([^)]*\))?",
        r"see original(?:\s*\([^)]*\))?", r"lihat versi asli(?:\s*\([^)]*\))?",
        r"view original(?:\s*\([^)]*\))?", r"translated by google",
        r"diterjemahkan oleh google", r"\(translated by google\)",
        r"\(diterjemahkan oleh google\)", r"\(original\)", r"\(asli\)",
    ]
    for pattern in ui_patterns:
        teks = re.sub(pattern, " ", teks, flags=re.IGNORECASE)
    teks = re.sub(r"[\ue000-\uf8ff]", "", teks)
    teks = re.sub(r"\+\d{1,3}[\s\d]{6,}", "", teks)
    teks = teks.replace("…", "").replace("・", " ").replace("·", " ").replace("•", " ")
    teks = re.sub(r"\s+", " ", teks).strip()
    if teks.upper() in ("BARU", "NEW"):
        return ""
    return teks

def bersihkan_tanggal(teks_tanggal):
    if not teks_tanggal:
        return None
    teks = re.sub(r"\bdiedit\b", "", teks_tanggal, flags=re.IGNORECASE)
    teks = re.sub(r"\bedited\b", "", teks, flags=re.IGNORECASE)
    teks = re.sub(r"[()]", "", teks)
    return re.sub(r"\s+", " ", teks).strip()

# ============ CSV ============
def ensure_csv_schema():
    if not os.path.exists(CSV_PATH):
        return True
    try:
        df = pd.read_csv(CSV_PATH)
        if set(CSV_COLUMNS).issubset(df.columns):
            return True
        print("🔧 Migrasi skema CSV...")
        for col in CSV_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
        df = df[CSV_COLUMNS]
        df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
        print(f"✅ CSV dimigrasi: {len(df)} baris.")
        return True
    except Exception as e:
        print(f"❌ Migrasi CSV gagal: {e}")
        return False

def save_batch(data_batch, retries=3):
    if not data_batch:
        return
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    df_new = pd.DataFrame(data_batch)
    for col in CSV_COLUMNS:
        if col not in df_new.columns:
            df_new[col] = ""
    df_new = df_new[CSV_COLUMNS]
    tulis_header = not os.path.exists(CSV_PATH)
    last_error = None
    for attempt in range(retries):
        try:
            df_new.to_csv(CSV_PATH, mode='a', header=tulis_header, index=False, encoding="utf-8")
            return
        except PermissionError as e:
            last_error = e
            print(f"⚠️ Simpan gagal ({attempt+1}/{retries}): Tutup file Excel!")
            time.sleep(2)
        except Exception as e:
            last_error = e
            print(f"⚠️ Simpan gagal ({attempt+1}/{retries}): {e}")
            time.sleep(2)
    raise FatalScrapeError(f"Gagal simpan CSV setelah {retries}x: {last_error}")

# ============ MAIN SCRAPER ============
def run_scraper(update_status_callback):
    driver = None
    scraped_at_str = datetime.now().strftime(SCRAPED_AT_FORMAT)
    scraped_at_dt = datetime.strptime(scraped_at_str, SCRAPED_AT_FORMAT)

    # Berapa kali tiap kunci (pelabuhan+bintang+isi) sudah ada di CSV. Tiap ulasan hasil
    # scraping 'memakai' satu kemunculan lama; yang tidak kebagian dianggap ulasan baru.
    sisa_lama = Counter()
    stats = {
        "new": 0, "duplicate": 0, "with_photos": 0,
        "failed_targets": [], "max_scroll_reached": [],
        "extraction_errors": 0, "tanpa_teks": 0,
    }

    def lapor(pesan):
        try:
            update_status_callback(pesan)
        except Exception:
            pass

    if not ensure_csv_schema():
        return False, "Gagal migrasi skema CSV."

    if os.path.exists(CSV_PATH):
        try:
            print(f"Memuat data lama dari {os.path.basename(CSV_PATH)}...")
            df_old = pd.read_csv(CSV_PATH)
            for pel, rt, teks in zip(df_old["pelabuhan"], df_old["rating"], df_old["review"]):
                if _punya_teks(teks):
                    sisa_lama[_kunci_ulasan(pel, rt, teks)] += 1
        except Exception as e:
            print(f"⚠️ Baca CSV lama: {e}")

    try:
        print("Membuat sesi browser...")
        driver = init_driver()
        wait = WebDriverWait(driver, 10)

        targets_processed = 0
        TARGETS_PER_RESTART = 2

        try:
            for lokasi, targets in PELABUHAN.items():
                for target in targets:
                    if targets_processed > 0 and targets_processed % TARGETS_PER_RESTART == 0:
                        print(f"🔄 Restart browser ({targets_processed} target selesai)...")
                        try:
                            try:
                                driver.quit()
                            except Exception:
                                pass
                            gc.collect()
                            time.sleep(2)
                            driver = init_driver()
                            wait = WebDriverWait(driver, 10)
                        except Exception as e:
                            print(f"⚠️ Restart gagal: {e}")
                            return False, f"Restart browser gagal: {e}"

                    seen_review_ids = set()
                    batch_data = []

                    try:
                        print(f"\n{'#'*70}")
                        print(f"# Membuka {target['nama']}")
                        print(f"{'#'*70}")
                        lapor(f"Mengambil ulasan: {target['nama']} ({stats['new']} ulasan baru)")
                        driver.get(target["url"])
                        time.sleep(5)

                        # Popup
                        try:
                            tutup = driver.find_elements(By.XPATH,
                                "//button[contains(., 'Setuju') or contains(., 'Tolak') or "
                                "contains(., 'Lain kali') or contains(., 'Tutup')]")
                            for btn in tutup:
                                if btn.is_displayed():
                                    driver.execute_script("arguments[0].click();", btn)
                                    time.sleep(1)
                        except Exception:
                            pass

                        # Tab Ulasan
                        review_tab = None
                        try:
                            review_tab = wait.until(EC.presence_of_element_located((
                                By.XPATH,
                                "//button[@role='tab'][normalize-space(.)='Ulasan' or normalize-space(.)='Reviews']"
                            )))
                        except Exception:
                            try:
                                review_tab = wait.until(EC.presence_of_element_located((
                                    By.XPATH,
                                    "//button[@role='tab'][@aria-label='Ulasan' or @aria-label='Reviews']"
                                )))
                            except Exception:
                                pass

                        if not review_tab:
                            raise Exception("Tab Ulasan tidak ditemukan.")

                        driver.execute_script("arguments[0].click();", review_tab)
                        time.sleep(3)

                        # Sort Terbaru
                        try:
                            print(f"Sort Terbaru: {target['nama']}...")
                            sort_btn = wait.until(EC.element_to_be_clickable((
                                By.XPATH,
                                "//button[@data-value='Sort' or contains(@aria-label, 'Urutkan') or "
                                "contains(@aria-label, 'Sort')] | "
                                "//div[@role='button'][contains(@aria-label, 'Urutkan') or contains(@aria-label, 'Sort')]"
                            )))
                            driver.execute_script("arguments[0].click();", sort_btn)
                            time.sleep(2)
                            newest = wait.until(EC.element_to_be_clickable((
                                By.XPATH,
                                "//div[@role='menuitemradio' and (contains(., 'Terbaru') or contains(., 'Newest'))] | "
                                "//div[@role='menuitemradio'][.//span[contains(text(), 'Terbaru') or contains(text(), 'Newest')]]"
                            )))
                            driver.execute_script("arguments[0].click();", newest)
                            time.sleep(4)
                        except Exception as e:
                            print(f"⚠️ Sort gagal: {e}")

                        # ============ RESET FILTER ============
                        print("\n" + "=" * 60)
                        print("🔄 RESET FILTER KE 'SEMUA'")
                        print("=" * 60)
                        
                        cards_before = len(driver.find_elements(By.CSS_SELECTOR, "div.jftiEf"))
                        print(f"📊 Kartu SEBELUM reset: {cards_before}")
                        
                        # DEBUG: dump chips dulu agar user bisa lihat state sebenarnya
                        dump_chips(driver, "SEBELUM reset")
                        
                        filter_result = reset_topic_filter(driver)
                        print(f"📋 Hasil reset attempt #1: {filter_result}")
                        
                        # Kalau FAILED, coba sekali lagi
                        if filter_result == 'FAILED':
                            print("⚠️ Attempt #1 FAILED, tunggu 3 detik + attempt #2...")
                            time.sleep(3)
                            filter_result = reset_topic_filter(driver)
                            print(f"📋 Hasil reset attempt #2: {filter_result}")
                        
                        # Snapshot setelah
                        dump_chips(driver, "SETELAH reset")
                        
                        # Keputusan
                        if filter_result.startswith('OK:') or filter_result == 'already-on-all' or filter_result.startswith('CHANGED-UNVERIFIED:'):
                            print(f"✅ Filter handling: {filter_result}")
                        elif filter_result == 'semua-not-found':
                            print("ℹ️ Chip 'Semua' tidak ditemukan — venue mungkin tidak punya filter topik")
                        else:
                            print(f"🚨 Filter reset FAILED — target akan di-skip")
                            raise Exception(f"Filter reset failed: {filter_result}")
                        
                        time.sleep(2)
                        cards_after = len(driver.find_elements(By.CSS_SELECTOR, "div.jftiEf"))
                        print(f"📊 Kartu SETELAH reset: {cards_after}")
                        
                        if cards_before > 0 and cards_before < 20 and cards_after <= cards_before:
                            print(f"⚠️ WARNING: Kartu tidak bertambah setelah reset")
                            print(f"    Kemungkinan filter masih aktif atau venue hanya punya {cards_after} ulasan")
                        
                        print("=" * 60 + "\n")

                        # Trigger lazy load
                        print("🔄 Memicu pemuatan awal daftar ulasan...")
                        try:
                            driver.execute_script("""
                                const target = document.elementFromPoint(
                                    window.innerWidth / 2,
                                    window.innerHeight / 2
                                );
                                if (target) {
                                    const wheelEvent = new WheelEvent('wheel', {
                                        deltaY: 800, deltaMode: 0, bubbles: true, cancelable: true
                                    });
                                    target.dispatchEvent(wheelEvent);
                                }
                                window.scrollBy(0, 500);
                                if (document.scrollingElement) {
                                    document.scrollingElement.scrollTop += 500;
                                }
                            """)
                            time.sleep(2)

                            if len(driver.find_elements(By.CSS_SELECTOR, "div.jftiEf")) == 0:
                                driver.execute_script("""
                                    const divs = document.querySelectorAll("div");
                                    for (const el of divs) {
                                        const style = window.getComputedStyle(el);
                                        const r = el.getBoundingClientRect();
                                        if ((style.overflowY === 'auto' || style.overflowY === 'scroll') &&
                                            r.width > 200 && r.height > 200 &&
                                            el.scrollHeight > el.clientHeight + 50) {
                                            el.scrollTop += 800;
                                        }
                                    }
                                """)
                                time.sleep(2)

                            cards_count = 0
                            for i in range(15):
                                cards_count = len(driver.find_elements(By.CSS_SELECTOR, "div.jftiEf"))
                                if cards_count > 0:
                                    print(f"✅ Trigger berhasil: {cards_count} kartu muncul")
                                    break
                                time.sleep(1)
                        except Exception as e:
                            print(f"⚠️ Trigger error: {e}")

                        # Panel
                        time.sleep(2)
                        panel = get_feed_panel(driver, max_wait=15)
                        if not panel:
                            print("⚠️ Panel belum muncul, recovery...")
                            try:
                                review_tab_retry = driver.find_element(By.XPATH,
                                    "//button[@role='tab'][normalize-space(.)='Ulasan' or normalize-space(.)='Reviews' "
                                    "or @aria-label='Ulasan' or @aria-label='Reviews']")
                                driver.execute_script("arguments[0].click();", review_tab_retry)
                                time.sleep(3)
                            except Exception:
                                pass
                            panel = get_feed_panel(driver, max_wait=15)

                        if not panel:
                            raise Exception("Panel scroll tidak ditemukan.")

                        # FIX: focus via JS, bukan ActionChains click (hindari klik chip)
                        try:
                            driver.execute_script("arguments[0].focus();", panel)
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollTop;", panel)
                            time.sleep(0.5)
                        except Exception:
                            pass

                        # ============ SCROLLING LOOP ============
                        scroll_count = 0
                        no_change_count = 0
                        spinner_count = 0
                        spinner_stuck = False
                        max_no_change = 10
                        max_scrolls = 2500
                        prev_count = 0
                        prev_scroll_top = 0
                        prev_scroll_height = 0

                        while no_change_count < max_no_change and scroll_count < max_scrolls:
                            if panel is None:
                                panel = get_feed_panel(driver, max_wait=10)
                                if not panel:
                                    time.sleep(2)
                                    panel = get_feed_panel(driver, max_wait=5)
                                    if not panel:
                                        raise Exception("Panel hilang total.")

                            scrolled, panel = safe_scroll(driver, panel)
                            if not scrolled:
                                time.sleep(2)
                                panel = get_feed_panel(driver, max_wait=10)
                                if not panel:
                                    raise Exception("Panel hilang saat scroll.")
                                scrolled, panel = safe_scroll(driver, panel)
                                if not scrolled:
                                    raise Exception("Scroll gagal setelah retry.")

                            time.sleep(2.5)

                            try:
                                if driver.find_elements(By.CSS_SELECTOR, "div.qjESne"):
                                    spinner_count += 1
                                    if spinner_count > 15:
                                        spinner_stuck = True
                                        break
                                    no_change_count = 0
                                    time.sleep(1)
                                    continue
                                else:
                                    spinner_count = 0
                            except WebDriverException:
                                pass

                            metrics, panel = get_scroll_metrics(driver, panel)
                            if metrics is None:
                                raise Exception("Panel tidak dapat dibaca setelah 3 percobaan.")
                            current_scroll_top = metrics["top"]
                            current_scroll_height = metrics["height"]

                            current_elements, panel = get_panel_cards(driver, panel)
                            if panel is None:
                                raise Exception("Panel hilang saat ambil cards.")
                            current_count = len(current_elements)
                            new_data_found = False

                            if scroll_count % 5 == 0:
                                lapor(f"{target['nama']}: scroll #{scroll_count}, {stats['new']} ulasan baru")
                                print(
                                    f"📊 Scroll #{scroll_count} | "
                                    f"scrollTop: {int(current_scroll_top)}/{int(current_scroll_height)} | "
                                    f"Cards: {current_count} | New: {stats['new']} | "
                                    f"Dup: {stats['duplicate']} | Media: {stats['with_photos']}"
                                )

                            for review in current_elements:
                                try:
                                    review_id = review.get_attribute("data-review-id")
                                    if not review_id:
                                        # cadangan: identitas dari isi kartu (nama, tanggal, teks), stabil antar scroll
                                        review_id = "txt:" + hashlib.md5(review.text.encode()).hexdigest()
                                    if review_id in seen_review_ids:
                                        continue

                                    try:
                                        more_btn = review.find_elements(By.XPATH,
                                            ".//*[contains(text(), 'Lainnya') or contains(text(), 'More')]")
                                        if more_btn and more_btn[0].is_displayed():
                                            driver.execute_script("arguments[0].click();", more_btn[0])
                                            time.sleep(0.2)
                                    except Exception:
                                        pass

                                    nama = ""  # nama reviewer tidak diambil lagi (kolom tetap ada, isinya kosong)
                                    rating_text = review.find_element(
                                        By.CSS_SELECTOR, "span.kvMYJc"
                                    ).get_attribute("aria-label")
                                    rating = int(rating_text.split()[0])
                                    lines = [l.strip() for l in review.text.strip().split("\n") if l.strip()]

                                    tanggal_raw = None
                                    for line in lines:
                                        if _is_date_line(line):
                                            tanggal_raw = line
                                            break

                                    tanggal = bersihkan_tanggal(tanggal_raw)
                                    tanggal_estimasi = None
                                    if tanggal:
                                        parsed = parse_relative_date(tanggal, scraped_at_dt)
                                        if parsed:
                                            tanggal_estimasi = parsed.isoformat()

                                    teks_review = ""
                                    if tanggal_raw and tanggal_raw in lines:
                                        kandidat = lines[lines.index(tanggal_raw) + 1:]
                                        teks_review = bersihkan_review("\n".join(kandidat))

                                    final_review_text = teks_review if teks_review else TEKS_KOSONG

                                    indicator = detect_photo_indicator(review)
                                    punya_media = indicator is not None

                                    if review_id:
                                        seen_review_ids.add(review_id)

                                    if not teks_review:
                                        # tanpa teks: tidak bisa dicocokkan dan dibuang saat preprocessing
                                        stats["tanpa_teks"] += 1
                                        continue

                                    review_key = _kunci_ulasan(target["nama"], rating, final_review_text)

                                    if sisa_lama[review_key] > 0:
                                        sisa_lama[review_key] -= 1
                                        stats["duplicate"] += 1
                                    else:
                                        new_data_found = True
                                        stats["new"] += 1
                                        if punya_media:
                                            stats["with_photos"] += 1

                                        batch_data.append({
                                            "lokasi": lokasi,
                                            "pelabuhan": target["nama"],
                                            "nama_reviewer": nama,
                                            "rating": rating,
                                            "tanggal": tanggal,
                                            "tanggal_estimasi": tanggal_estimasi,
                                            "review": final_review_text,
                                            "memiliki_foto": punya_media,
                                            "scraped_at": scraped_at_str,
                                        })

                                        if stats["new"] <= 10:
                                            preview = final_review_text[:40].replace("\n", " ")
                                            ind_info = f" [{indicator}]" if indicator else ""
                                            print(f"📸 {nama} | Media: {punya_media}{ind_info} | {preview}...")

                                        if len(batch_data) >= 50:
                                            save_batch(batch_data)
                                            batch_data.clear()

                                except FatalScrapeError:
                                    raise
                                except StaleElementReferenceException:
                                    stats["extraction_errors"] += 1
                                    continue
                                except Exception as e:
                                    stats["extraction_errors"] += 1
                                    if stats["extraction_errors"] <= 5:
                                        print(f"⚠️ Ekstrak err: {e}")
                                    continue

                            if current_count == prev_count and not new_data_found:
                                if current_scroll_top == prev_scroll_top and current_scroll_height == prev_scroll_height:
                                    no_change_count += 1
                                    try:
                                        driver.execute_script("arguments[0].scrollTop -= 800;", panel)
                                        time.sleep(1)
                                        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", panel)
                                    except StaleElementReferenceException:
                                        panel = None
                                    except Exception:
                                        pass
                                else:
                                    no_change_count = 0
                            else:
                                no_change_count = 0
                                prev_count = current_count

                            prev_scroll_top = current_scroll_top
                            prev_scroll_height = current_scroll_height
                            scroll_count += 1

                        if spinner_stuck:
                            raise Exception("Spinner macet.")
                        if scroll_count >= max_scrolls:
                            stats["max_scroll_reached"].append(target["nama"])

                    except FatalScrapeError:
                        raise
                    except Exception as e:
                        stats["failed_targets"].append(target["nama"])
                        print(f"❌ Target gagal: {target['nama']} - {e}")
                    finally:
                        if batch_data:
                            save_batch(batch_data)
                            batch_data.clear()
                        targets_processed += 1

        except FatalScrapeError as fse:
            print(f"🚨 FATAL: {fse}")
            return False, f"Fatal: {fse}"

        msg = f"Selesai. {stats['new']} baru ({stats['with_photos']} media), {stats['duplicate']} sudah ada."
        if stats["tanpa_teks"]:
            msg += f" {stats['tanpa_teks']} tanpa teks dilewati."
        if stats["extraction_errors"] > 0:
            msg += f" ({stats['extraction_errors']} err)"
        if stats["max_scroll_reached"]:
            msg += f" ⚠️ Max scroll: {len(stats['max_scroll_reached'])}."
        if stats["failed_targets"]:
            msg += f" ❌ Gagal: {len(stats['failed_targets'])}."
        msg += f"\n📁 Output: {CSV_PATH}"

        success = (
            not stats["failed_targets"]
            and not stats["max_scroll_reached"]
        )
        return success, msg

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass