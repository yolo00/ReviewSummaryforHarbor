# run_scraper_manual.py
from modules.scraper import run_scraper

def log(msg):
    print(msg, flush=True)

total, msg = run_scraper(log)
print(f"\n=== HASIL: {total} ulasan — {msg} ===")