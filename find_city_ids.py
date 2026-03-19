"""Find correct Google Flights city IDs by typing city names."""
import sys, time, re, base64
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

CITIES_TO_FIND = ['Phoenix', 'Baltimore', 'Philadelphia', 'Portland',
                   'Salt Lake City', 'San Diego', 'Orlando', 'Houston',
                   'Savannah', 'Charlotte', 'Tampa', 'Fort Lauderdale',
                   'Pittsburgh', 'New Orleans', 'Detroit', 'Miami']

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport={'width': 1400, 'height': 900},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
        locale='en-US',
    )

    for city in CITIES_TO_FIND:
        page = ctx.new_page()
        # Go to Google Flights
        page.goto('https://www.google.com/travel/flights?hl=en&gl=us&curr=USD', timeout=20000)
        page.wait_for_load_state('domcontentloaded')
        try:
            btn = page.get_by_role('button', name='Reject all')
            if btn.count() > 0: btn.first.click(); time.sleep(1)
        except: pass
        time.sleep(3)

        # Type origin
        try:
            # Click "Where from?" field and type Taipei
            from_input = page.locator('input[aria-label*="Where from"]').first
            from_input.click()
            time.sleep(0.5)
            from_input.fill('Taipei')
            time.sleep(1)
            # Select first suggestion
            page.keyboard.press('Enter')
            time.sleep(1)

            # Click "Where to?" and type the target city
            to_input = page.locator('input[aria-label*="Where to"]').first
            to_input.click()
            time.sleep(0.5)
            to_input.fill(city)
            time.sleep(2)
            # Select first suggestion
            page.keyboard.press('Enter')
            time.sleep(1)

            # Click search/explore
            page.keyboard.press('Enter')
            time.sleep(1)

            # Click "Search" button or "Explore" button
            search_btn = page.locator('button:has-text("Search"), button:has-text("Explore")')
            if search_btn.count() > 0:
                search_btn.first.click()
            time.sleep(5)

            # Extract city ID from URL
            url = page.url
            if 'tfs=' in url:
                tfs = url.split('tfs=')[1].split('&')[0]
                pad = 4 - len(tfs) % 4
                if pad < 4: tfs += '=' * pad
                raw = base64.urlsafe_b64decode(tfs)
                # Find field 14 (destination) in first leg
                pos = 0
                found = False
                while pos < len(raw) - 5:
                    if raw[pos] == 0x72:  # field 14
                        length = raw[pos+1]
                        sub = raw[pos+2:pos+2+length]
                        if len(sub) > 4 and sub[2] == 0x12:
                            id_len = sub[3]
                            city_id = sub[4:4+id_len].decode('utf-8', errors='replace')
                            print(f"  '{city}': '{city_id}',")
                            found = True
                        break
                    pos += 1
                if not found:
                    print(f"  # {city}: ID not found in URL")
            else:
                print(f"  # {city}: no tfs in URL")
        except Exception as e:
            print(f"  # {city}: error - {str(e)[:60]}")
        finally:
            page.close()

    browser.close()
