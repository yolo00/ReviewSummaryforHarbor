"""
Debug script untuk menemukan selector foto ulasan Google Maps yang AKURAT.
Jalankan sekali, bandingkan dengan tampilan Google Maps manual.
"""
import os
import time
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import platform
import tempfile

DEBUG_URL = "https://maps.app.goo.gl/xteioSuSkvQCAnCm9"  # Batam Center
OUTPUT_FILE = "debug_photo_output.json"

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


def dump_card_html(driver, review):
    """Ambil SEMUA info elemen yang mungkin terkait foto dari 1 kartu ulasan."""
    try:
        return driver.execute_script("""
            const card = arguments[0];
            const result = {
                // 1. Tombol dengan data-photo-index
                photoIndexButtons: [...card.querySelectorAll('[data-photo-index]')].map(b => ({
                    index: b.getAttribute('data-photo-index'),
                    tag: b.tagName,
                    ariaLabel: b.getAttribute('aria-label'),
                    className: b.className,
                    rect: (() => {
                        const r = b.getBoundingClientRect();
                        return {w: Math.round(r.width), h: Math.round(r.height)};
                    })()
                })),

                // 2. Semua tombol (untuk cari button foto)
                allButtons: [...card.querySelectorAll('button')].map(b => ({
                    ariaLabel: b.getAttribute('aria-label'),
                    dataPhotoIndex: b.getAttribute('data-photo-index'),
                    className: b.className,
                    text: (b.innerText || '').trim().substring(0, 30)
                })),

                // 3. Semua img (untuk cari thumbnail foto ulasan)
                allImages: [...card.querySelectorAll('img')].map(img => {
                    const r = img.getBoundingClientRect();
                    return {
                        src: (img.getAttribute('src') || '').substring(0, 120),
                        className: img.className,
                        alt: img.getAttribute('alt'),
                        width: Math.round(r.width),
                        height: Math.round(r.height),
                        parentClass: (img.parentElement && img.parentElement.className) || ''
                    };
                }),

                // 4. Elemen dengan class yang MUNGKIN terkait foto
                photoLikeElements: [...card.querySelectorAll('[class*="photo"], [class*="Photo"], [class*="img"], [class*="Img"], [class*="image"], [class*="Image"]')].map(el => ({
                    tag: el.tagName,
                    className: el.className,
                    role: el.getAttribute('role'),
                    ariaLabel: el.getAttribute('aria-label'),
                    dataIndex: el.getAttribute('data-photo-index')
                })).slice(0, 20),

                // 5. Jumlah elemen total di kartu
                totalButtons: card.querySelectorAll('button').length,
                totalImages: card.querySelectorAll('img').length,
                totalLinks: card.querySelectorAll('a').length,
                cardHTMLSize: card.outerHTML.length
            };
            return result;
        """, review)
    except Exception as e:
        return {"error": str(e)}


def main():
    print("=" * 70)
    print("DEBUG FOTO — Google Maps Review")
    print("=" * 70)
    print(f"URL: {DEBUG_URL}")
    print(f"Output: {OUTPUT_FILE}")
    print()

    driver = init_driver()
    wait = WebDriverWait(driver, 10)
    results = []

    try:
        print("Membuka URL...")
        driver.get(DEBUG_URL)
        time.sleep(5)

        # Popup
        try:
            btns = driver.find_elements(By.XPATH, "//button[contains(., 'Setuju') or contains(., 'Tolak') or contains(., 'Tutup')]")
            for btn in btns:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(1)
        except Exception:
            pass

        # Buka tab ulasan
        print("Membuka tab ulasan...")
        xpath_tab = ("//button[@role='tab' and "
                     "(contains(@aria-label, 'Ulasan') or contains(., 'Ulasan')) and "
                     "not(contains(translate(@aria-label, 'TUIS', 'tuis'), 'tulis'))]")
        try:
            tab = wait.until(EC.presence_of_element_located((By.XPATH, xpath_tab)))
            driver.execute_script("arguments[0].click();", tab)
            time.sleep(3)
        except Exception:
            print("⚠️ Tab ulasan tidak ditemukan.")

        # Cari panel scroll
        print("Mencari panel scroll...")
        panel = None
        try:
            panel = driver.find_element(By.CSS_SELECTOR, "div[role='feed']")
        except Exception:
            try:
                card = driver.find_element(By.CSS_SELECTOR, "div.jftiEf")
                panel = driver.execute_script("""
                    var el = arguments[0];
                    while (el && el !== document.body) {
                        var s = window.getComputedStyle(el);
                        if (s.overflowY === 'auto' || s.overflowY === 'scroll') return el;
                        el = el.parentElement;
                    }
                    return null;
                """, card)
            except Exception:
                pass

        if not panel:
            print("❌ Panel scroll tidak ditemukan.")
            return

        # Scroll beberapa kali untuk load ~30 ulasan
        print("Scroll 8 kali untuk load ~30 ulasan...")
        for i in range(8):
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", panel)
            time.sleep(2)
            count = len(driver.find_elements(By.CSS_SELECTOR, "div.jftiEf"))
            print(f"  Scroll {i+1}: {count} kartu")

        # Ambil 30 ulasan pertama untuk di-dump
        cards = driver.find_elements(By.CSS_SELECTOR, "div.jftiEf")
        print(f"\nTotal kartu ter-load: {len(cards)}")
        print("Dump 30 kartu pertama...\n")

        for i, review in enumerate(cards[:30]):
            try:
                # Nama reviewer
                try:
                    nama = review.find_element(By.CSS_SELECTOR, ".d4r55").text.strip()
                except Exception:
                    nama = "???"

                # Preview teks
                try:
                    lines = [l.strip() for l in review.text.split("\n") if l.strip()]
                    preview = " | ".join(lines[:3])[:80]
                except Exception:
                    preview = "???"

                # Dump semua info foto
                dump = dump_card_html(driver, review)

                results.append({
                    "index": i + 1,
                    "nama": nama,
                    "preview": preview,
                    "dump": dump
                })

                # Print ringkas
                if "error" in dump:
                    print(f"[{i+1:02d}] {nama[:25]:25s} → ERROR: {dump['error']}")
                else:
                    n_photo_idx = len(dump["photoIndexButtons"])
                    n_imgs = len(dump["allImages"])
                    n_btns = len(dump["allButtons"])
                    print(f"[{i+1:02d}] {nama[:25]:25s} | photoIndex:{n_photo_idx} | imgs:{n_imgs} | btns:{n_btns}")

            except Exception as e:
                print(f"[{i+1:02d}] ERROR: {e}")
                results.append({"index": i + 1, "error": str(e)})

        # Simpan ke JSON
        output = {
            "url": DEBUG_URL,
            "timestamp": datetime.now().isoformat(),
            "total_cards": len(cards),
            "dumped_cards": results
        }
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"\n✅ Output saved to: {OUTPUT_FILE}")
        print(f"   Ukuran file: {os.path.getsize(OUTPUT_FILE) / 1024:.1f} KB")

        # Print ringkasan pola
        print("\n" + "=" * 70)
        print("RINGKASAN POLA")
        print("=" * 70)

        with_photo_idx = sum(1 for r in results if r.get("dump", {}).get("photoIndexButtons"))
        with_images = sum(1 for r in results if len(r.get("dump", {}).get("allImages", [])) > 1)
        print(f"Kartu dengan data-photo-index : {with_photo_idx} / {len(results)}")
        print(f"Kartu dengan >1 img            : {with_images} / {len(results)}")

        # Analisis img yang mungkin foto ulasan
        print("\nAnalisis img src (top patterns):")
        src_patterns = {}
        for r in results:
            for img in r.get("dump", {}).get("allImages", []):
                src = img.get("src", "")
                if "googleusercontent" in src or "ggpht" in src:
                    cls = img.get("className", "")
                    key = f"class={cls[:40]} | size={img.get('width')}x{img.get('height')}"
                    src_patterns[key] = src_patterns.get(key, 0) + 1

        for pattern, count in sorted(src_patterns.items(), key=lambda x: -x[1])[:10]:
            print(f"  {count:3d}x  {pattern}")

        print("\n" + "=" * 70)
        print("LANGKAH SELANJUTNYA:")
        print("=" * 70)
        print("1. Buka Google Maps manual, cek 5-10 ulasan dari 30 di atas")
        print("2. Kategorikan: mana yang PUNYA FOTO, mana yang TIDAK")
        print("3. Buka file debug_photo_output.json")
        print("4. Bandingkan: kartu yang punya foto → apa yang BEDA dari yang tidak?")
        print("5. Kirim ke saya:")
        print("   - Nama 3-5 reviewer yang PUNYA foto")
        print("   - Nama 3-5 reviewer yang TIDAK punya foto")
        print("   - Isi 'dump' (allButtons + allImages) dari masing-masing")
        print("=" * 70)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()