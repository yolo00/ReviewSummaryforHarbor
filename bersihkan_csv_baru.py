import pandas as pd
import os

CSV_PATH = os.path.join("data", "raw", "review_pelabuhan(fix).csv")

def clean_baru_bug():
    if not os.path.exists(CSV_PATH):
        print("File CSV tidak ditemukan.")
        return

    print("Membaca CSV...")
    df = pd.read_csv(CSV_PATH)
    
    # Hitung berapa baris yang terdampak
    mask = df['review'].astype(str).str.strip().str.upper().isin(["BARU", "NEW"])
    jumlah = mask.sum()
    
    if jumlah > 0:
        print(f"Menemukan {jumlah} baris dengan teks 'BARU' / 'NEW'. Memperbaiki...")
        df.loc[mask, 'review'] = "[Tanpa Teks]"
        df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
        print("✅ Selesai! Semua baris yang sebelumnya 'BARU' telah diubah menjadi '[Tanpa Teks]'.")
    else:
        print("Tidak ada baris yang terdampak. Data sudah bersih.")

if __name__ == "__main__":
    clean_baru_bug()