import os
import re
import time
from datetime import datetime

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.microsoft import EdgeChromiumDriverManager


# =============================================================
# KONFIGURASI MICROSOFT EDGE
# =============================================================

options = Options()
options.add_argument("--start-maximized")

driver = webdriver.Edge(
    service=Service(EdgeChromiumDriverManager().install()),
    options=options
)

wait = WebDriverWait(driver, 15)


# =============================================================
# KONFIGURASI PELABUHAN
# key  = lokasi (kolom "lokasi" di CSV)
# nama = pelabuhan (kolom "pelabuhan" di CSV)
# url  = link Google Maps tempat tersebut
# =============================================================

PELABUHAN = {
    "Batam Centre": [
        {
            "nama": "Batam Center International Ferry Terminal",
            "url": "https://maps.app.goo.gl/xteioSuSkvQCAnCm9"
        },
        {
            "nama": "Batam Centre Point International Ferry Terminal",
            "url": "https://maps.app.goo.gl/RMB8k185hxGftNw47"
        }
    ],

    "Harbour Bay": [
        {"nama": "Pelabuhan Harbour Bay",
         "url": "https://maps.app.goo.gl/jtmmKUzjkRCVwtrJA"},
        {"nama": "Harbour Bay Ferry",
         "url": "https://maps.app.goo.gl/yUsvUuVVQghPGEmi9"},
        {"nama": "Harbour Bay",
         "url": "https://maps.app.goo.gl/WjXfrRvxBLMu3yQTA"},
    ],

    "Telaga Punggur": [
        {"nama": "Telaga Harbour Crossing Punggur",
         "url": "https://maps.app.goo.gl/j1bFczwQniiayxQP9"},
        {"nama": "Telaga Punggur",
         "url": "https://maps.app.goo.gl/2LiPQ5oCNb2cGLgU8"},
        {"nama": "PT ASDP Indonesia Ferry (Persero)",
         "url": "https://maps.app.goo.gl/QUiwjF6HMAMhHdgM9"},
        {"nama": "Pelabuhan Terminal Ferry Punggur",
         "url": "https://maps.app.goo.gl/xnuHKq6vWS666BNfA"},
        {"nama": "Telaga Punggur Ferry Terminal",
         "url": "https://maps.app.goo.gl/MDJ44zpRx9W4RsRy7"},
        {"nama": "Pelabuhan punggur",
         "url": "https://maps.app.goo.gl/PABS1c6jPK6fKi4y7"},
        {"nama": "Penyebrangan telaga punggur",
         "url": "https://maps.app.goo.gl/zV5mJCTomE4W76vK7"},
    ],

    "Nongsapura": [
        {"nama": "Pelabuhan internasional Nongsa Pura",
         "url": "https://maps.app.goo.gl/Y9ibAju4HgcyKTS49"},
        {"nama": "Nongsapura Ferry Terminal",
         "url": "https://maps.app.goo.gl/LBcbgBcnuswhMRxi7"},
        {"nama": "Batam Nongsapura Port",
         "url": "https://maps.app.goo.gl/HhstWNLmwUxvQMtZ7"},
    ],

    "Sekupang": [
        {"nama": "Sekupang Ferry Terminal",
         "url": "https://maps.app.goo.gl/4Zz1vwMkwBxQHeLx6"},
        {"nama": "Pelabuhan Domestik Sekupang",
         "url": "https://maps.app.goo.gl/PMhxf2b5oDa3Yngq6"},
        {"nama": "SEKUPANG INTERNATIONAL FERRY TERMINAL",
         "url": "https://maps.app.goo.gl/eWo1Gt5bzVNyf4qd9"},
        {"nama": "Sekupang",
         "url": "https://maps.app.goo.gl/iR5Sp6GVcVY9jYrF7"},
    ],
}

JUMLAH_SCROLL = 30
KATA_WAKTU = [
    "hari lalu", "minggu lalu", "bulan lalu", "tahun lalu",
    "hari yang lalu", "minggu yang lalu",
    "bulan yang lalu", "tahun yang lalu",
]

# Waktu scraping (satu nilai untuk seluruh run)
SCRAPED_AT = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# =============================================================
# FUNGSI BANTU
# =============================================================

def cek_has_photo(review):
    """True jika review memiliki foto/video terlampir."""
    # Selector Google Maps bisa berubah, cek lewat DevTools jika selalu False
    return len(review.find_elements(By.CSS_SELECTOR, "button.Tya61d")) > 0


def cek_is_localguide(review, lines):
    """True jika reviewer berstatus Local Guide."""
    try:
        info = review.find_element(By.CSS_SELECTOR, "div.RfnDt").text
        return "local guide" in info.lower()
    except Exception:
        # Fallback: cek beberapa baris teks pertama di kartu review
        return "local guide" in " ".join(lines[:3]).lower()


def bersihkan_review(teks):
    # Hapus timestamp video seperti 0:05, 1:03
    teks = re.sub(r"\b\d{1,2}:\d{2}\b", "", teks)

    # Hapus ikon/glyph UI Google Maps (private use area)
    teks = re.sub(r"[\ue000-\uf8ff]", "", teks)

    # Hapus jumlah like/interaksi: +3, +11, +2 1
    teks = re.sub(r"\+\d+(?:\s+\d+)?", "", teks)

    # Hapus "Lainnya" yang tersisa
    teks = re.sub(r"\bLainnya\b", "", teks, flags=re.IGNORECASE)

    # Hapus label UI "BARU"
    teks = re.sub(r"^\s*BARU\s+", "", teks, flags=re.IGNORECASE)

    # Hapus ellipsis
    teks = teks.replace("…", "")

    # Hapus angka sisa di akhir
    teks = re.sub(r"\s+\d{1,2}\s*$", "", teks)

    # Rapikan spasi
    return re.sub(r"\s+", " ", teks).strip()


def buka_tab_ulasan():
    """
    Klik tab 'Ulasan' (bukan tombol 'Tulis/Buat ulasan' yang membuka login).
    Tab Ulasan berupa button dengan role='tab'; tombol tulis ulasan bukan tab.
    """
    huruf_kecil = (
        "translate(@aria-label, "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
    )

    xpath_tab = (
        "//button[@role='tab' "
        "and (contains(@aria-label, 'Ulasan') or contains(., 'Ulasan')) "
        f"and not(contains({huruf_kecil}, 'tulis')) "
        f"and not(contains({huruf_kecil}, 'buat')) "
        f"and not(contains({huruf_kecil}, 'write'))]"
    )

    tombol = wait.until(
        EC.element_to_be_clickable((By.XPATH, xpath_tab))
    )
    print("Tab Ulasan ditemukan:", tombol.get_attribute("aria-label"))

    url_sebelum = driver.current_url
    tombol.click()

    # Pengaman: jika tidak sengaja terlempar ke halaman login, kembali
    time.sleep(2)
    if "accounts.google.com" in driver.current_url:
        print("Terlempar ke halaman login, kembali ke halaman tempat.")
        driver.get(url_sebelum)
        raise RuntimeError("Tombol yang diklik membuka halaman login.")

    print("Tab Ulasan diklik.")


def scrape_tempat(lokasi, nama_pelabuhan, url):
    """Scrape semua review dari satu link Google Maps. Return list of dict."""
    hasil = []

    driver.get(url)
    time.sleep(7)  # beri waktu short link redirect dan halaman termuat
    print("URL akhir:", driver.current_url)

    # --- Tab Ulasan ---
    buka_tab_ulasan()
    time.sleep(3)

    # --- Panel ulasan ---
    panel = wait.until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                "//div[@aria-label='Saring ulasan']"
                "/ancestor::div[contains(@class, 'm6QErb')]"
            )
        )
    )
    print("Panel ulasan ditemukan.")

    # --- Scroll otomatis ---
    ActionChains(driver).move_to_element(panel).click().perform()

    for i in range(JUMLAH_SCROLL):
        ActionChains(driver).send_keys(Keys.PAGE_DOWN).perform()
        time.sleep(2)
        print(f"Scroll ke-{i + 1}/{JUMLAH_SCROLL}", end="\r")
    print("\nScrolling selesai.")

    # --- Buka teks "Lainnya" ---
    review_elements = driver.find_elements(By.CSS_SELECTOR, "div.jftiEf")

    for review in review_elements:
        try:
            tombol = review.find_elements(
                By.XPATH, ".//*[contains(text(), 'Lainnya')]"
            )
            if tombol:
                driver.execute_script("arguments[0].click();", tombol[0])
                time.sleep(0.5)
        except Exception:
            pass

    # --- Ambil data review ---
    review_elements = driver.find_elements(By.CSS_SELECTOR, "div.jftiEf")
    print("Jumlah review ditemukan:", len(review_elements))

    for i, review in enumerate(review_elements):
        try:
            lines = [
                line.strip()
                for line in review.text.strip().split("\n")
                if line.strip()
            ]

            # Nama reviewer
            try:
                nama = review.find_element(By.CSS_SELECTOR, ".d4r55").text.strip()
            except Exception:
                nama = lines[0] if lines else ""

            # Rating
            try:
                rating_text = review.find_element(
                    By.CSS_SELECTOR, "span.kvMYJc"
                ).get_attribute("aria-label")
                rating = int(rating_text.split()[0])
            except Exception:
                rating = None

            # Tanggal
            tanggal = None
            for line in lines:
                if any(k in line.lower() for k in KATA_WAKTU):
                    tanggal = line
                    break

            # Teks review
            teks_review = ""
            if tanggal:
                kandidat = lines[lines.index(tanggal) + 1:]
                kandidat = [
                    x for x in kandidat
                    if x not in ["Suka", "Bagikan", "Lainnya"]
                ]
                teks_review = bersihkan_review(" ".join(kandidat))

            # Field tambahan
            has_photo = cek_has_photo(review)
            is_localguide = cek_is_localguide(review, lines)

            hasil.append({
                "lokasi": lokasi,
                "pelabuhan": nama_pelabuhan,
                "nama_reviewer": nama,
                "rating": rating,
                "tanggal": tanggal,
                "review": teks_review,
                "has_photo": has_photo,
                "is_localguide": is_localguide,
                "scraped_at": SCRAPED_AT,
            })

        except Exception as e:
            print(f"Review ke-{i + 1} gagal diproses:", e)

    return hasil


# =============================================================
# PROSES UTAMA
# =============================================================

data_review = []

for lokasi, targets in PELABUHAN.items():

    print("\n" + "=" * 60)
    print(f"LOKASI: {lokasi}")
    print("=" * 60)

    for target in targets:

        print(f"\nPelabuhan: {target['nama']}")
        print(f"URL      : {target['url']}")

        try:
            hasil = scrape_tempat(lokasi, target["nama"], target["url"])
            data_review.extend(hasil)
            print(f"-> {len(hasil)} review diambil.")
        except Exception as e:
            # Satu link gagal tidak menghentikan seluruh proses
            print(f"GAGAL memproses {target['nama']}: {e}")


# =============================================================
# SIMPAN KE CSV
# =============================================================

KOLOM = [
    "lokasi", "pelabuhan", "nama_reviewer", "rating", "tanggal",
    "review", "has_photo", "is_localguide", "scraped_at",
]

df = pd.DataFrame(data_review, columns=KOLOM)

# Beberapa link bisa mengarah ke tempat yang sama, buang review duplikat
jumlah_sebelum = len(df)
df = df.drop_duplicates(
    subset=["lokasi", "nama_reviewer", "rating", "review"],
    keep="first"
)
print(f"\nDuplikat dibuang: {jumlah_sebelum - len(df)}")

folder_raw = "data/raw"
os.makedirs(folder_raw, exist_ok=True)

nama_file = "review_pelabuhan.csv"
path_file = os.path.join(folder_raw, nama_file)

df.to_csv(path_file, index=False, encoding="utf-8-sig")

print("\n" + "=" * 80)
print("DATA BERHASIL DISIMPAN!")
print("Jumlah data :", len(df))
print("Nama file   :", path_file)
print("=" * 80)

input("\nTekan Enter untuk keluar...")
driver.quit()