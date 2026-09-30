import os
import pandas as pd
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import time
import re
from urllib.parse import quote



# KONFIGURASI MICROSOFT EDGE


options = Options()
options.add_argument("--start-maximized")

driver = webdriver.Edge(
    service=Service(EdgeChromiumDriverManager().install()),
    options=options
)

wait = WebDriverWait(driver, 15)



# NAMA PELABUHAN


nama_pelabuhan = "Pelabuhan Punggur"



# URL PENCARIAN


query = quote(nama_pelabuhan)

url = f"https://www.google.com/maps/search/?api=1&query={query}"



# BUKA GOOGLE MAPS


print("Membuka Google Maps...")

driver.get(url)

time.sleep(8)

print("Google Maps berhasil dibuka.")
print(f"Mencari: {nama_pelabuhan}")



# CEK URL


print("\nURL saat ini:")
print(driver.current_url)



# TAMPILKAN LINK HASIL


links = driver.find_elements(By.TAG_NAME, "a")



# MENCARI HASIL YANG SESUAI


target_name = "Terminal Ferry Telaga Punggur Batam"

target_url = None

for link in links:
    text = link.text.strip()
    href = link.get_attribute("href")

    if text == target_name and href and "/maps/place/" in href:
        target_url = href
        break



# MEMBUKA HALAMAN TEMPAT


if target_url:

    print("\nLokasi ditemukan!")
    print("Nama :", target_name)
    print("URL  :", target_url)

    driver.get(target_url)

    time.sleep(7)

    print("\nHalaman tempat berhasil dibuka.")


    
    # MENCARI TOMBOL ULASAN
    

    review_button = wait.until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                "//button[contains(@aria-label, 'Ulasan')]"
            )
        )
    )

    print("Tombol Ulasan ditemukan.")

    review_button.click()

    print("Tombol Ulasan berhasil diklik.")

    time.sleep(3)

    # print("\nMencari elemen yang memiliki teks ulasan...")

time.sleep(3)

print("\nMencari panel ulasan...")

panel = wait.until(
    EC.presence_of_element_located(
        (
            By.XPATH,
            "//div[@aria-label='Saring ulasan']/ancestor::div[contains(@class, 'm6QErb')]"
        )
    )
)

print("Panel ulasan ditemukan.")
print("CLASS:", panel.get_attribute("class"))

print("\nMelakukan scroll otomatis...")

ActionChains(driver).move_to_element(panel).click().perform()

for i in range(30):

    ActionChains(driver).send_keys(Keys.PAGE_DOWN).perform()

    time.sleep(2)

    print(f"Scroll otomatis ke-{i + 1}")

print("Scrolling selesai.")

print("\nMembuka teks review yang memiliki 'Lainnya'...")

review_elements = driver.find_elements(
    By.CSS_SELECTOR,
    "div.jftiEf"
)

for i, review in enumerate(review_elements):

    try:
        tombol_lainnya = review.find_elements(
            By.XPATH,
            ".//*[contains(text(), 'Lainnya')]"
        )

        if tombol_lainnya:
            driver.execute_script(
                "arguments[0].click();",
                tombol_lainnya[0]
            )

            time.sleep(0.5)

            print(f"Review ke-{i + 1}: Lainnya dibuka")

    except Exception:
        pass

print("Selesai membuka teks review.")


# MENYIAPKAN PENYIMPANAN DATA


data_review = []



# AMBIL SEMUA REVIEW


print("\nMengambil data review...")

review_elements = driver.find_elements(
    By.CSS_SELECTOR,
    "div.jftiEf"
)

print("Jumlah review ditemukan:", len(review_elements))



# PROSES SETIAP REVIEW


for i, review in enumerate(review_elements):

    try:

        
        # Ambil semua teks dalam review
        

        lines = review.text.strip().split("\n")

        lines = [
            line.strip()
            for line in lines
            if line.strip()
        ]


        
        # NAMA REVIEWER
        

        try:

            nama_element = review.find_element(
                By.CSS_SELECTOR,
                ".d4r55"
            )

            nama = nama_element.text.strip()

        except:

            nama = lines[0] if lines else ""


        
        # RATING
        

        try:

            rating_element = review.find_element(
                By.CSS_SELECTOR,
                "span.kvMYJc"
            )

            rating_text = rating_element.get_attribute(
                "aria-label"
            )

            rating = int(rating_text.split()[0])

        except:

            rating = None


        
        # TANGGAL
        

        tanggal = None

        kata_waktu = [
            "hari lalu",
            "minggu lalu",
            "bulan lalu",
            "tahun lalu",
            "hari yang lalu",
            "minggu yang lalu",
            "bulan yang lalu",
            "tahun yang lalu"
        ]

        for line in lines:

            if any(
                kata in line.lower()
                for kata in kata_waktu
            ):

                tanggal = line
                break


        #        
        # TEKS REVIEW
        

        teks_review = ""

        if tanggal:

            index_tanggal = lines.index(tanggal)

            kandidat = lines[index_tanggal + 1:]


            
            # Hapus elemen UI Google Maps
            

            kandidat = [
                x for x in kandidat
                if x not in ["Suka", "Bagikan", "Lainnya"]
            ]

            teks_review = " ".join(kandidat).strip()


            
            # MEMBERSIHKAN NOISE REVIEW
            

            # Hapus timestamp seperti:
            # 0:05, 0:24, 0:06, 1:03
            teks_review = re.sub(
                r'\b\d{1,2}:\d{2}\b',
                '',
                teks_review
            )


            # Hapus simbol interaksi Google Maps
            teks_review = teks_review.replace("", "")
            teks_review = teks_review.replace("", "")


            # Hapus jumlah like/interaksi
            # Contoh:
            # +3
            # +11
            # +16
            # +2 1
            teks_review = re.sub(
                r'\+\d+(?:\s+\d+)?',
                '',
                teks_review
            )


            # Hapus "Lainnya" jika masih tersisa
            teks_review = re.sub(
                r'\bLainnya\b',
                '',
                teks_review,
                flags=re.IGNORECASE
            )


            # Hapus label "BARU" dari Google Maps
            # BARU hanya merupakan label UI,
            # bukan bagian dari isi review
            teks_review = re.sub(
                r'^\s*BARU\s+',
                '',
                teks_review,
                flags=re.IGNORECASE
            )


            # Hapus tanda ellipsis "…"
            teks_review = teks_review.replace("…", "")


            teks_review = re.sub(
            r'\s+\d{1,2}\s*$',
            '',
            teks_review)

            # Rapikan spasi
            teks_review = re.sub(
                r'\s+',
                ' ',
                teks_review
            ).strip()

        
        # TAMPILKAN HASIL
        

        print("\n" + "=" * 80)

        print(f"REVIEW KE-{i + 1}")

        print("Nama     :", nama)
        print("Rating   :", rating)
        print("Tanggal  :", tanggal)
        print("Ulasan   :", teks_review)


        
        # SIMPAN KE LIST
        

        data_review.append({

            "nama_pelabuhan": target_name,

            "nama_reviewer": nama,

            "rating": rating,

            "tanggal": tanggal,

            "review": teks_review

        })


    except Exception as e:

        print(
            f"Review ke-{i + 1} gagal diproses:",
            e
        )



# SIMPAN KE CSV

df = pd.DataFrame(data_review)

# Folder penyimpanan data raw
folder_raw = "data/raw"

# Membuat folder jika belum ada
os.makedirs(folder_raw, exist_ok=True)

# Nama file
nama_file = "review_telaga_punggur.csv"

# Path lengkap file
path_file = os.path.join(folder_raw, nama_file)

df.to_csv(
    path_file,
    index=False,
    encoding="utf-8-sig"
)



# INFORMASI HASIL


print("\n" + "=" * 80)

print("DATA BERHASIL DISIMPAN!")

print("Jumlah data :", len(df))

print("Nama file   :", nama_file)

print("=" * 80)

print("\nMencari teks review setelah scrolling...")

input("\nTekan Enter untuk keluar...")

driver.quit()