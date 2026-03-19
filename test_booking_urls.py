"""Quick test if Trip.com and Expedia URL formats actually work."""
import sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

TESTS = [
    ('Trip.com', 'https://www.trip.com/flights/list/roundtrip-hkg-sfo-20260626-20260705/?cabin=Y&adult=1'),
    ('Expedia', 'https://www.expedia.com/Flights-search/HKG-SFO/2026-06-26/2026-07-05/?cabinclass=economy'),
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport={'width': 1400, 'height': 900},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
        locale='en-US',
    )

    for name, url in TESTS:
        print(f"\n{'='*50}")
        print(f"Testing {name}: {url}")
        page = ctx.new_page()
        try:
            page.goto(url, timeout=20000)
            page.wait_for_load_state('domcontentloaded')
            time.sleep(5)
            final_url = page.url
            title = page.title()
            text = page.inner_text('body')[:500]
            page.screenshot(path=f'D:/claude/flights/test_{name.replace(".", "_")}.png')
            print(f"  Final URL: {final_url[:120]}")
            print(f"  Title: {title}")
            print(f"  Body preview: {text[:200]}")
            has_results = '$' in text or 'price' in text.lower() or 'flight' in text.lower()
            has_captcha = 'captcha' in text.lower() or 'verify' in text.lower() or 'robot' in text.lower()
            print(f"  Has flight results: {has_results}")
            print(f"  Has CAPTCHA/block: {has_captcha}")
        except Exception as e:
            print(f"  ERROR: {e}")
        finally:
            page.close()

    browser.close()
