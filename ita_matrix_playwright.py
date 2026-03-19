"""Search ITA Matrix for Jakarta business class bug fare using Playwright."""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import re
import time

from playwright.sync_api import sync_playwright

searches = [
    ('CGK', 'LHR', '2026-05-04', None, 'CGK-LHR BIZ OW May4'),
    ('CGK', 'LAX', '2026-05-04', None, 'CGK-LAX BIZ OW May4'),
    ('CGK', 'LAX', '2026-05-08', None, 'CGK-LAX BIZ OW May8'),
    ('CGK', 'LHR', '2026-05-04', '2026-06-15', 'CGK-LHR BIZ RT May4'),
    ('CGK', 'LAX', '2026-05-04', '2026-06-15', 'CGK-LAX BIZ RT May4'),
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1400, 'height': 900},
        locale='en-US',
    )
    page = context.new_page()

    for origin, dest, dep, ret, label in searches:
        print(f"\n{'='*60}")
        print(f"{label} - BUSINESS CLASS")
        print(f"{'='*60}")

        try:
            # Load ITA Matrix
            page.goto('https://matrix.itasoftware.com/', wait_until='networkidle', timeout=60000)
            time.sleep(3)

            # Set to one-way or round trip
            if ret is None:
                # Click "One way" radio/option
                try:
                    page.click('text=One way', timeout=5000)
                    time.sleep(1)
                except:
                    try:
                        # Try the dropdown or radio button
                        ow_elements = page.query_selector_all('input[value="ONE_WAY"], label:has-text("One way")')
                        for el in ow_elements:
                            el.click()
                            break
                    except:
                        pass

            # Fill origin
            origin_input = page.query_selector('input[name="origin"], input[aria-label*="origin" i], input[aria-label*="from" i], #city0')
            if not origin_input:
                # Try finding by placeholder or position
                inputs = page.query_selector_all('input[type="text"]')
                print(f"  Found {len(inputs)} text inputs")
                if len(inputs) >= 2:
                    origin_input = inputs[0]

            if origin_input:
                origin_input.click()
                origin_input.fill('')
                origin_input.type(origin, delay=100)
                time.sleep(1)
                page.keyboard.press('Enter')
                time.sleep(0.5)
            else:
                print("  Could not find origin input")

            # Fill destination
            dest_input = page.query_selector('input[name="destination"], input[aria-label*="destination" i], input[aria-label*="to" i], #city1')
            if not dest_input:
                inputs = page.query_selector_all('input[type="text"]')
                if len(inputs) >= 2:
                    dest_input = inputs[1]

            if dest_input:
                dest_input.click()
                dest_input.fill('')
                dest_input.type(dest, delay=100)
                time.sleep(1)
                page.keyboard.press('Enter')
                time.sleep(0.5)

            # Fill departure date
            dep_input = page.query_selector('input[name="departureDate"], input[aria-label*="depart" i], #departure0')
            if not dep_input:
                inputs = page.query_selector_all('input[type="text"]')
                if len(inputs) >= 3:
                    dep_input = inputs[2]

            if dep_input:
                dep_input.click()
                dep_input.triple_click()
                dep_input.type(dep, delay=50)
                time.sleep(0.5)

            # Fill return date if RT
            if ret:
                ret_input = page.query_selector('input[name="returnDate"], input[aria-label*="return" i], #departure1')
                if not ret_input:
                    inputs = page.query_selector_all('input[type="text"]')
                    if len(inputs) >= 4:
                        ret_input = inputs[3]
                if ret_input:
                    ret_input.click()
                    ret_input.triple_click()
                    ret_input.type(ret, delay=50)
                    time.sleep(0.5)

            # Select Business class
            # ITA Matrix has a cabin class selector
            try:
                # Look for cabin class dropdown
                cabin_selector = page.query_selector('select[name="cabin"], select[aria-label*="cabin" i]')
                if cabin_selector:
                    cabin_selector.select_option(value='BUSINESS')
                    print("  Selected BUSINESS via dropdown")
                else:
                    # Try clicking a cabin class button/link
                    page.click('text=Business', timeout=3000)
                    print("  Clicked 'Business' text")
            except:
                try:
                    # Try the advanced options
                    page.click('text=Show advanced options', timeout=3000)
                    time.sleep(1)
                    cabin_selector = page.query_selector('select[name="cabin"]')
                    if cabin_selector:
                        cabin_selector.select_option(value='BUSINESS')
                        print("  Selected BUSINESS via advanced options")
                except:
                    print("  Could not find cabin class selector")

            # Take screenshot of the form
            page.screenshot(path=f'D:/claude/flights/ita_form_{label.replace(" ","_")}.png')

            # Click Search
            try:
                search_btn = page.query_selector('button:has-text("Search"), input[value="Search"]')
                if search_btn:
                    search_btn.click()
                else:
                    page.click('text=Search', timeout=5000)
                print("  Clicked Search, waiting for results...")
                time.sleep(15)  # ITA Matrix can be slow
            except Exception as e:
                print(f"  Could not click Search: {e}")

            # Wait for results
            try:
                page.wait_for_selector('text=USD', timeout=30000)
            except:
                pass

            time.sleep(3)

            # Screenshot results
            page.screenshot(path=f'D:/claude/flights/ita_results_{label.replace(" ","_")}.png')
            print(f"  Screenshot saved")

            # Extract text content for prices
            body_text = page.inner_text('body')

            # Find prices (USD amounts)
            price_matches = re.findall(r'USD\s*([\d,]+(?:\.\d{2})?)', body_text)
            if price_matches:
                prices = sorted(set(float(p.replace(',', '')) for p in price_matches))
                print(f"  Prices found: {['${:,.0f}'.format(p) for p in prices[:15]]}")
            else:
                # Try other price patterns
                price_matches = re.findall(r'\$([\d,]+(?:\.\d{2})?)', body_text)
                if price_matches:
                    prices = sorted(set(float(p.replace(',', '')) for p in price_matches if float(p.replace(',', '')) > 50))
                    print(f"  Prices found: {['${:,.0f}'.format(p) for p in prices[:15]]}")
                else:
                    print("  No prices found in page text")
                    # Print some page text for debugging
                    lines = [l.strip() for l in body_text.split('\n') if l.strip()]
                    print(f"  Page lines: {len(lines)}")
                    for line in lines[:30]:
                        if len(line) > 10:
                            print(f"    {line[:100]}")

        except Exception as e:
            print(f"  ERROR: {e}")

    browser.close()

print("\nDONE")
