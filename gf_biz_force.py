"""Google Flights business class search - force clicks to bypass MD overlays."""
import sys, os, re, time, json
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = "D:/claude/flights"

def search_route(page, origin, dest, date, label):
    print(f"\n{'='*60}")
    print(f"SEARCH: {label} — {origin}→{dest} {date} BUSINESS")
    print(f"{'='*60}")

    # Navigate to Google Flights
    page.goto("https://www.google.com/travel/flights", wait_until="networkidle", timeout=30000)
    time.sleep(3)

    # Dismiss consent/cookie banners
    for sel in ["button:has-text('Accept all')", "button:has-text('Reject all')", "button:has-text('I agree')"]:
        try:
            page.click(sel, force=True, timeout=2000)
            time.sleep(1)
        except:
            pass

    page.screenshot(path=f"{SCREENSHOT_DIR}/gf_force_{label}_01.png")

    # Step 1: Click "Round trip" dropdown and switch to One way using force + JS
    print("  Setting One Way...")
    try:
        # Use JavaScript to click — bypasses all overlay issues
        page.evaluate("""() => {
            // Find the trip type dropdown
            const spans = document.querySelectorAll('span');
            for (const s of spans) {
                if (s.textContent.trim() === 'Round trip') {
                    s.click();
                    break;
                }
            }
        }""")
        time.sleep(1)

        # Click "One way"
        page.evaluate("""() => {
            const items = document.querySelectorAll('li, [role="option"]');
            for (const item of items) {
                if (item.textContent.trim().includes('One way')) {
                    item.click();
                    break;
                }
            }
        }""")
        time.sleep(0.5)
        print("    One Way set via JS")
    except Exception as e:
        print(f"    One Way failed: {e}")

    # Step 2: Set Business class
    print("  Setting Business class...")
    try:
        page.evaluate("""() => {
            const spans = document.querySelectorAll('span');
            for (const s of spans) {
                if (s.textContent.trim() === 'Economy') {
                    s.click();
                    break;
                }
            }
        }""")
        time.sleep(1)

        page.evaluate("""() => {
            const items = document.querySelectorAll('li, [role="option"]');
            for (const item of items) {
                if (item.textContent.trim() === 'Business') {
                    item.click();
                    break;
                }
            }
        }""")
        time.sleep(0.5)
        print("    Business class set via JS")
    except Exception as e:
        print(f"    Business failed: {e}")

    page.screenshot(path=f"{SCREENSHOT_DIR}/gf_force_{label}_02_settings.png")

    # Step 3: Close any open dialog first
    try:
        page.keyboard.press("Escape")
        time.sleep(0.5)
    except:
        pass

    # Step 4: Set origin - find the origin input and type
    print(f"  Setting origin to {origin}...")
    try:
        # Click on the origin area
        page.evaluate("""(code) => {
            // Find "Where from?" placeholder div and click it
            const divs = document.querySelectorAll('[data-placeholder="Where from?"]');
            if (divs.length) { divs[0].click(); return; }
            // Or find the origin input by aria-label
            const inputs = document.querySelectorAll('input[aria-label*="Where from"]');
            if (inputs.length) { inputs[0].click(); return; }
            // Try clicking the first combobox input
            const combos = document.querySelectorAll('input[role="combobox"]');
            if (combos.length) { combos[0].focus(); combos[0].click(); }
        }""", origin)
        time.sleep(1)

        # Now find the active/focused input and type
        page.evaluate("""(code) => {
            const input = document.querySelector('input[aria-label*="Where from"], input[role="combobox"]:focus, input.II2One');
            if (input) {
                input.value = '';
                input.dispatchEvent(new Event('input', {bubbles: true}));
            }
        }""", origin)
        time.sleep(0.3)

        # Type the code using keyboard
        active_input = page.locator('input[aria-label*="Where from"], input.II2One').first
        try:
            active_input.fill(origin, force=True, timeout=3000)
        except:
            page.keyboard.type(origin, delay=100)
        time.sleep(2)

        # Click first suggestion
        page.evaluate("""() => {
            const options = document.querySelectorAll('ul[role="listbox"] li, [role="option"]');
            if (options.length) options[0].click();
        }""")
        time.sleep(1)
        print(f"    Origin set to {origin}")
    except Exception as e:
        print(f"    Origin error: {e}")

    # Step 5: Set destination
    print(f"  Setting destination to {dest}...")
    try:
        page.evaluate("""() => {
            const divs = document.querySelectorAll('[data-placeholder="Where to?"]');
            if (divs.length) { divs[0].click(); return; }
            const inputs = document.querySelectorAll('input[aria-label*="Where to"]');
            if (inputs.length) { inputs[0].click(); return; }
        }""")
        time.sleep(1)

        dest_input = page.locator('input[aria-label*="Where to"], input[placeholder*="Where to"]').first
        try:
            dest_input.fill(dest, force=True, timeout=3000)
        except:
            page.keyboard.type(dest, delay=100)
        time.sleep(2)

        page.evaluate("""() => {
            const options = document.querySelectorAll('ul[role="listbox"] li, [role="option"]');
            if (options.length) options[0].click();
        }""")
        time.sleep(1)
        print(f"    Destination set to {dest}")
    except Exception as e:
        print(f"    Dest error: {e}")

    page.screenshot(path=f"{SCREENSHOT_DIR}/gf_force_{label}_03_route.png")

    # Step 6: Set date
    print(f"  Setting date to {date}...")
    try:
        # Click the date field
        page.evaluate("""() => {
            const inputs = document.querySelectorAll('input[aria-label*="Departure"], input[placeholder*="Departure"]');
            if (inputs.length) { inputs[0].click(); return; }
            // Try clicking "Departure" text
            const spans = document.querySelectorAll('span, div');
            for (const s of spans) {
                if (s.textContent.trim() === 'Departure') { s.click(); break; }
            }
        }""")
        time.sleep(1)

        # Navigate calendar to correct month and click date
        year, month, day = date.split('-')
        month_names = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                       'July', 'August', 'September', 'October', 'November', 'December']
        target_month = f"{month_names[int(month)]} {year}"

        for _ in range(20):
            page_text = page.locator('body').text_content() or ''
            if target_month in page_text:
                break
            try:
                page.locator('button[aria-label="Next"]').first.click(force=True, timeout=1000)
            except:
                try:
                    page.evaluate("""() => {
                        const btns = document.querySelectorAll('button[aria-label*="Next"], button[aria-label*="next"]');
                        if (btns.length) btns[btns.length-1].click();
                    }""")
                except:
                    break
            time.sleep(0.3)

        # Click the target date
        day_int = int(day)
        page.evaluate(f"""() => {{
            const buttons = document.querySelectorAll('[role="button"], button');
            for (const b of buttons) {{
                const label = b.getAttribute('aria-label') || '';
                if (label.includes('{month_names[int(month)]} {day_int}') && label.includes('{year}')) {{
                    b.click();
                    return true;
                }}
            }}
            return false;
        }}""")
        time.sleep(0.5)

        # Click Done
        page.evaluate("""() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                if (b.textContent.trim() === 'Done') { b.click(); break; }
            }
        }""")
        time.sleep(0.5)
        print(f"    Date set to {date}")
    except Exception as e:
        print(f"    Date error: {e}")

    page.screenshot(path=f"{SCREENSHOT_DIR}/gf_force_{label}_04_ready.png")

    # Step 7: Click Search/Explore
    print("  Clicking Search...")
    try:
        page.evaluate("""() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                const text = b.textContent.trim();
                if (text === 'Search' || text === 'Explore') { b.click(); return; }
            }
        }""")
    except:
        page.keyboard.press("Enter")
    time.sleep(8)

    page.screenshot(path=f"{SCREENSHOT_DIR}/gf_force_{label}_05_results.png")

    # Step 8: Extract prices from ARIA labels
    print("  Extracting prices...")
    results = page.evaluate("""() => {
        const results = [];
        const els = document.querySelectorAll('[aria-label]');
        for (const el of els) {
            const label = el.getAttribute('aria-label');
            if (label && label.length > 30) {
                const priceMatch = label.match(/(\\d[\\d,]*)\\s*(?:US\\s*)?dollars?/i);
                if (priceMatch) {
                    const price = parseInt(priceMatch[1].replace(/,/g, ''));
                    if (price > 50) {
                        const airlineMatch = label.match(/flight with ([^.]+)/);
                        const stopsMatch = label.match(/(Nonstop|\\d+ stops?)/);
                        const durMatch = label.match(/(\\d+ hr\\s*(?:\\d+ min)?)/);
                        results.push({
                            price: price,
                            airline: airlineMatch ? airlineMatch[1].trim() : '?',
                            stops: stopsMatch ? stopsMatch[1] : '?',
                            duration: durMatch ? durMatch[1] : '?',
                            label: label.substring(0, 200)
                        });
                    }
                }
            }
        }
        return results;
    }""")

    if results:
        results.sort(key=lambda x: x['price'])
        print(f"  Found {len(results)} flights:")
        for r in results[:15]:
            print(f"    ${r['price']:>5} | {r['airline'][:45]} | {r['stops']} | {r['duration']}")
        cheap = [r for r in results if r['price'] < 1000]
        if cheap:
            print(f"\n  *** BUG FARE CANDIDATES (< $1000): {len(cheap)} ***")
            for r in cheap:
                print(f"    >>> ${r['price']} | {r['airline']} | {r['stops']}")
    else:
        print("  NO PRICES FOUND")
        # Check current URL
        url = page.url
        print(f"  URL: {url}")
        # Check if Business is actually selected
        page_text = page.locator('body').text_content() or ''
        if 'Business' in page_text:
            print("  'Business' visible on page")
        if 'Economy' in page_text:
            print("  'Economy' visible on page")

    # Full page screenshot
    try:
        page.screenshot(path=f"{SCREENSHOT_DIR}/gf_force_{label}_06_full.png", full_page=True)
    except:
        pass

    return results


# Alternative: skip form, go directly to search URL with proper TFS
def search_via_url(page, origin, dest, date, label, return_date=None):
    """Use the TFS URL directly but with longer waits and scrolling."""
    import base64

    print(f"\n{'='*60}")
    print(f"URL SEARCH: {label} — {origin}→{dest} {date} BUSINESS")
    print(f"{'='*60}")

    def enc_varint(v):
        r = b''
        while v > 0x7f:
            r += bytes([(v & 0x7f) | 0x80])
            v >>= 7
        r += bytes([v])
        return r

    def fv(n, v):
        return enc_varint((n << 3) | 0) + enc_varint(v)

    def fb(n, d):
        if isinstance(d, str): d = d.encode()
        return enc_varint((n << 3) | 2) + enc_varint(len(d)) + d

    def build_leg(orig, dst, dt):
        o = fv(1, 1) + fb(2, orig)
        d = fv(1, 1) + fb(2, dst)
        return fb(2, dt) + fb(13, o) + fb(14, d)

    legs = fb(3, build_leg(origin, dest, date))
    trip_type = 1  # one-way
    if return_date:
        legs += fb(3, build_leg(dest, origin, return_date))
        trip_type = 2

    pax = b'\x08' + b'\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01'
    msg = (
        fv(1, 28) + fv(2, trip_type) + legs +
        fv(8, 1) +   # 1 adult
        fv(9, 3) +   # cabin: 3 = business
        fv(14, 1) +
        fb(16, pax) +
        fv(19, 1)
    )
    tfs = base64.urlsafe_b64encode(msg).rstrip(b'=').decode()
    url = f"https://www.google.com/travel/flights/search?tfs={tfs}&curr=USD&hl=en&gl=us"
    print(f"  URL: {url[:120]}...")

    page.goto(url, wait_until="networkidle", timeout=45000)
    time.sleep(5)

    # Dismiss consent
    for sel in ["button:has-text('Accept all')", "button:has-text('Reject all')"]:
        try:
            page.click(sel, force=True, timeout=2000)
            time.sleep(2)
        except:
            pass

    # Scroll and wait
    for _ in range(5):
        page.evaluate("window.scrollBy(0, 400)")
        time.sleep(1)
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(2)

    page.screenshot(path=f"{SCREENSHOT_DIR}/gf_url_{label}.png")

    # Extract via JS
    results = page.evaluate("""() => {
        const results = [];
        const els = document.querySelectorAll('[aria-label]');
        for (const el of els) {
            const label = el.getAttribute('aria-label');
            if (label && label.length > 30) {
                const priceMatch = label.match(/(\\d[\\d,]*)\\s*(?:US\\s*)?dollars?/i);
                if (priceMatch) {
                    const price = parseInt(priceMatch[1].replace(/,/g, ''));
                    if (price > 50) {
                        const airlineMatch = label.match(/flight with ([^.]+)/);
                        const stopsMatch = label.match(/(Nonstop|\\d+ stops?)/);
                        const durMatch = label.match(/(\\d+ hr\\s*(?:\\d+ min)?)/);
                        results.push({
                            price: price,
                            airline: airlineMatch ? airlineMatch[1].trim() : '?',
                            stops: stopsMatch ? stopsMatch[1] : '?',
                            duration: durMatch ? durMatch[1] : '?',
                        });
                    }
                }
            }
        }
        return results;
    }""")

    if results:
        results.sort(key=lambda x: x['price'])
        print(f"  Found {len(results)} flights:")
        for r in results[:15]:
            print(f"    ${r['price']:>5} | {r['airline'][:45]} | {r['stops']} | {r['duration']}")
    else:
        print("  NO PRICES from ARIA")
        # Check page state
        body = (page.locator('body').text_content() or '')[:300]
        print(f"  Body: {body[:200]}")
        # Check if "Business" shows on page
        if 'Business' in (page.locator('body').text_content() or ''):
            print("  'Business' confirmed on page")

    return results


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={'width': 1400, 'height': 900},
        locale='en-US',
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    )
    page = context.new_page()

    all_results = {}

    # Method 1: Form interaction with JS clicks
    for orig, dest, date, lbl in [
        ('CGK', 'LHR', '2026-05-04', 'CGK-LHR-May4'),
        ('CGK', 'LAX', '2026-05-04', 'CGK-LAX-May4'),
    ]:
        results = search_route(page, orig, dest, date, lbl)
        all_results[f'form_{lbl}'] = results

    # Method 2: Direct TFS URL
    for orig, dest, date, ret, lbl in [
        ('CGK', 'LHR', '2026-05-04', None, 'CGK-LHR-OW-May4'),
        ('CGK', 'LAX', '2026-05-04', None, 'CGK-LAX-OW-May4'),
        ('CGK', 'LAX', '2026-05-08', None, 'CGK-LAX-OW-May8'),
        ('CGK', 'LAX', '2026-05-04', '2026-06-15', 'CGK-LAX-RT-May4'),
    ]:
        results = search_via_url(page, orig, dest, date, lbl, ret)
        all_results[f'url_{lbl}'] = results

    browser.close()

# Save
with open(f'{SCREENSHOT_DIR}/gf_biz_final.json', 'w') as f:
    json.dump(all_results, f, indent=2, default=str)

print("\n" + "="*60)
print("DONE — screenshots saved to D:/claude/flights/gf_force_*.png and gf_url_*.png")
