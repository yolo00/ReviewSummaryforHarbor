"""Validasi ASPECT_KEYWORDS terhadap `final_text` hasil preprocessing.

Jalankan dari root project:
    python modules/validate_keywords.py --check-pipeline
    python modules/validate_keywords.py
    python modules/validate_keywords.py --csv "data/processed/review_processed(fix).csv"

Batasan penting:
- `--check-pipeline` hanya menguji tahap teks (clean -> slang -> stemming &
  stopword). TIDAK menguji deteksi bahasa dan translasi. Keyword berbahasa
  Inggris/Melayu bisa tidak cocok di sini walau di pipeline aslinya
  diterjemahkan dulu. Untuk keyword Indonesia, hasilnya cukup representatif.
- Audit coverage menghitung ulasan yang mengandung minimal satu keyword
  aspek. Persentase BUKAN proporsi ulasan yang membahas topik tersebut
  secara semantik; ia hanya mengukur cakupan pencocokan kata.
"""
import argparse
import os
import re

import pandas as pd

try:
    from modules.visualization import ASPECT_KEYWORDS
    from modules.preprocessing import TextPreprocessor
except ModuleNotFoundError:
    from visualization import ASPECT_KEYWORDS
    from preprocessing import TextPreprocessor

DEFAULT_CSV = os.path.join("data", "processed", "review_processed(fix).csv")


def _compile(patterns_dict):
    compiled = {}
    for aspect, kws in patterns_dict.items():
        sorted_kws = sorted(kws, key=len, reverse=True)
        alt = "|".join(re.escape(kw) for kw in sorted_kws)
        compiled[aspect] = re.compile(rf"\b(?:{alt})\b", re.IGNORECASE)
    return compiled


# ---------------------------------------------------------------------------
# Mode 1: --check-pipeline
# ---------------------------------------------------------------------------
def check_pipeline(keywords):
    """
    Tampilkan transformasi tiap keyword lewat TextPreprocessor.

    Batasan:
    - Hanya menguji clean_text, normalize_slang, remove_stopwords_and_stem.
    - Tidak menguji detect_and_filter_language dan translate_if_needed.
    - Untuk keyword ID, hasil cukup representatif.
    - Untuk keyword EN, hasil hanya menunjukkan bentuk setelah tahap teks;
      pipeline aslinya akan menerjemahkan dulu (via API), yang tidak
      direproduksi di sini.
    """
    pre = TextPreprocessor()

    print("\n🔬 Transformasi keyword melalui TextPreprocessor")
    print("   (tahap teks: clean → slang → stemming & stopword)")
    print("   Catatan: deteksi bahasa & translasi EN/MS TIDAK diuji di sini.\n")

    all_kws = sorted(set(k for kws in keywords.values() for k in kws))
    header = (
        f"{'Keyword asli':<28}"
        f"{'Setelah clean+slang':<30}"
        f"{'Setelah stemming':<24}"
        f"{'Status':<10}"
        f"{'Aspek'}"
    )
    print(header)
    print("-" * 130)

    aspek_of = {}
    for aspek, kws in keywords.items():
        for kw in kws:
            aspek_of.setdefault(kw, []).append(aspek)

    hilang = []
    berubah = []
    tetap = []

    for kw in all_kws:
        clean = pre.clean_text(kw)
        slang = pre.normalize_slang(clean)
        stemmed = pre.remove_stopwords_and_stem(slang)

        if not stemmed:
            status = "❌ kosong"
            hilang.append(kw)
        elif stemmed == kw.lower():
            status = "✓ tetap"
            tetap.append(kw)
        else:
            status = "↻ berubah"
            berubah.append(kw)

        aspek_str = ", ".join(aspek_of.get(kw, []))
        print(
            f"{kw:<28}"
            f"{slang or '-':<30}"
            f"{stemmed or '-':<24}"
            f"{status:<10}"
            f"{aspek_str}"
        )

    print("-" * 130)
    print(f"Ringkasan: ✓ tetap={len(tetap)}  ↻ berubah={len(berubah)}  "
          f"❌ kosong={len(hilang)}")

    if berubah:
        print("\n↻ Keyword berubah bentuk (sesuaikan ASPECT_KEYWORDS jika perlu):")
        for kw in berubah:
            clean = pre.clean_text(kw)
            slang = pre.normalize_slang(clean)
            stemmed = pre.remove_stopwords_and_stem(slang)
            print(f"   · '{kw}'  →  '{stemmed}'")

    if hilang:
        print("\n❌ Keyword menjadi kosong setelah preprocessing.")
        print("   Ini BISA disebabkan oleh beberapa hal, bukan hanya stopword:")
        print("   - terhapus saat cleaning (karakter non-alfabet)")
        print("   - ternormalisasi slang menjadi bentuk lain yang ikut terhapus")
        print("   - memang termasuk stopword Sastrawi/domain")
        print("   - tidak menghasilkan token setelah stemming")
        print("   Periksa penyebabnya SEBELUM menghapus dari ASPECT_KEYWORDS.")
        for kw in hilang:
            print(f"   · '{kw}'")


# ---------------------------------------------------------------------------
# Mode 2: audit coverage pada dataset
# ---------------------------------------------------------------------------
def audit(csv_path, keywords):
    if not os.path.exists(csv_path):
        print(f"❌ File tidak ditemukan: {csv_path}")
        return

    df = pd.read_csv(csv_path)
    if "final_text" not in df.columns:
        print(f"❌ Kolom 'final_text' tidak ada di {csv_path}")
        return

    texts = df["final_text"].dropna().astype(str).tolist()
    total = len(texts)
    if total == 0:
        print("❌ Tidak ada teks valid.")
        return

    patterns = _compile(keywords)

    print(f"📋 Audit ASPECT_KEYWORDS terhadap {total} ulasan")
    print(f"📄 File: {csv_path}")
    print("   Catatan: persentase = cakupan pencocokan kata (minimal satu")
    print("   keyword aspek muncul), BUKAN proporsi ulasan yang secara")
    print("   semantik membahas topik tersebut.\n")

    header = (
        f"{'Aspek':<18}"
        f"{'Hit':>6}"
        f"{'%':>8}"
        f"{'KW OK':>8}"
        f"{'KW miss':>9}   "
        f"Keyword tidak muncul"
    )
    print(header)
    print("-" * 130)

    ringkasan = []
    for aspect, kws in keywords.items():
        pat = patterns[aspect]
        hits = 0
        kw_seen = set()
        examples = []
        for t in texts:
            if pat.search(t):
                hits += 1
                if len(examples) < 3:
                    examples.append(t)
            for kw in kws:
                if kw in kw_seen:
                    continue
                if re.search(rf"\b{re.escape(kw)}\b", t, re.IGNORECASE):
                    kw_seen.add(kw)

        pct = hits / total * 100
        kw_ok = len(kw_seen)
        kw_total = len(kws)
        kw_miss = kw_total - kw_ok
        missing = [kw for kw in kws if kw not in kw_seen]
        missing_str = ", ".join(missing[:8])
        if len(missing) > 8:
            missing_str += f" ... (+{len(missing) - 8})"

        print(
            f"{aspect:<18}"
            f"{hits:>6}"
            f"{pct:>7.1f}%"
            f"{kw_ok:>8}"
            f"{kw_miss:>9}   "
            f"{missing_str}"
        )

        ringkasan.append({
            "aspek": aspect,
            "hit": hits,
            "pct": pct,
            "kw_ok": kw_ok,
            "kw_total": kw_total,
        })

        if examples:
            print("    Contoh ulasan:")
            for ex in examples:
                ex_short = ex if len(ex) <= 120 else ex[:117] + "…"
                print(f"      · {ex_short}")

    print("-" * 130)
    total_kw = sum(r["kw_total"] for r in ringkasan)
    total_ok = sum(r["kw_ok"] for r in ringkasan)
    print(f"Ringkasan: total keyword {total_kw}, muncul {total_ok} "
          f"({total_ok / total_kw * 100:.1f}%).")

    aspek_lemah = [r["aspek"] for r in ringkasan if r["kw_ok"] < r["kw_total"] * 0.5]
    if aspek_lemah:
        print("Aspek dengan <50% keyword muncul (perlu evaluasi): "
              + ", ".join(aspek_lemah))

    print("\nLangkah selanjutnya:")
    print("  1. Untuk keyword yang TIDAK muncul, cek --check-pipeline untuk")
    print("     melihat apakah Sastrawi mengubah bentuknya.")
    print("  2. Untuk keyword YANG muncul, periksa contoh ulasan di atas")
    print("     apakah konteksnya relevan dengan aspek.")
    print("  3. Jangan mengubah ASPECT_KEYWORDS sebelum kedua pemeriksaan ini.")


def main():
    parser = argparse.ArgumentParser(
        description="Validasi ASPECT_KEYWORDS terhadap hasil preprocessing."
    )
    parser.add_argument(
        "--csv", default=DEFAULT_CSV,
        help=f"Path CSV hasil preprocessing (default: {DEFAULT_CSV}).",
    )
    parser.add_argument(
        "--check-pipeline", action="store_true",
        help="Tampilkan transformasi keyword lewat TextPreprocessor "
             "(tanpa membaca CSV).",
    )
    args = parser.parse_args()

    if args.check_pipeline:
        check_pipeline(ASPECT_KEYWORDS)
        return

    audit(args.csv, ASPECT_KEYWORDS)


if __name__ == "__main__":
    main()