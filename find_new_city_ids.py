"""Find Freebase IDs for Xiamen, Tianjin, Fuzhou via Google Flights autocomplete."""
import sys, time, re, base64
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

CITIES_TO_FIND = ['Xiamen', 'Tianjin', 'Fuzhou']

def extract_dest_id(url):
    if 'tfs=' not in url:
        return None
    tfs = url.split('tfs=')[1].split('&')[0]
    pad = 4 - len(tfs) % 4
    if pad < 4: tfs += '=' * pad
    try:
        raw = base64.urlsafe_b64decode(tfs)
    except:
        return None
    text = raw.decode('utf-8', errors='replace')
    ids = re.findall(r'/m/[a-z0-9_]+', text)
    seen = []
    for mid in ids:
        if mid not in seen:
            seen.append(mid)
    # First ID = Taipei (origin), second = destination
    if len(seen) >= 2:
        return seen[1]
    return None

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport={'width': 1400, 'height': 900},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
        locale='en-US',
    )

    # First page: dismiss cookies
    page = ctx.new_page()
    page.goto('https://www.google.com/travel/flights?hl=en&gl=us&curr=USD', timeout=30000)
    page.wait_for_load_state('domcontentloaded')
    time.sleep(3)
    try:
        btn = page.get_by_role('button', name='Reject all')
        if btn.count() > 0: btn.first.click(); time.sleep(2)
    except: pass
    page.close()

    for city in CITIES_TO_FIND:
        page = ctx.new_page()
        page.goto('https://www.google.com/travel/flights?hl=en&gl=us&curr=USD', timeout=30000)
        page.wait_for_load_state('domcontentloaded')
        time.sleep(4)

        try:
            from_box = page.locator('[aria-label*="Where from"], [placeholder*="Where from"]')
            if from_box.count() > 0:
                from_box.first.click()
                time.sleep(0.5)
                page.keyboard.press('Control+a')
                page.keyboard.type('Taipei', delay=50)
                time.sleep(1.5)
                page.keyboard.press('ArrowDown')
                time.sleep(0.3)
                page.keyboard.press('Enter')
                time.sleep(1)
            else:
                for _ in range(3):
                    page.keyboard.press('Tab')
                    time.sleep(0.3)
                page.keyboard.type('Taipei', delay=50)
                time.sleep(1.5)
                page.keyboard.press('Enter')
                time.sleep(1)

            to_box = page.locator('[aria-label*="Where to"], [placeholder*="Where to"]')
            if to_box.count() > 0:
                to_box.first.click()
                time.sleep(0.5)
                page.keyboard.type(city, delay=50)
                time.sleep(2)
                page.keyboard.press('ArrowDown')
                time.sleep(0.3)
                page.keyboard.press('Enter')
                time.sleep(1)

            time.sleep(1)
            search_btn = page.locator('button:has-text("Search")')
            if search_btn.count() > 0:
                search_btn.first.click()
            else:
                page.keyboard.press('Enter')
            time.sleep(5)

            url = page.url
            dest_id = extract_dest_id(url)
            if dest_id:
                print(f"  '{city}': '{dest_id}',")
            else:
                title = page.title()
                print(f"  # {city}: no ID found (title: {title[:60]})")
                page.screenshot(path=f'D:/claude/flights/find_id_{city.replace(" ", "_")}.png')
        except Exception as e:
            print(f"  # {city}: error - {str(e)[:80]}")
        finally:
            page.close()

    browser.close()
