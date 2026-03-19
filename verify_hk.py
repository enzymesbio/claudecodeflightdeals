"""Deep verify Hong Kong cheap fares to mainland US (exclude Honolulu)."""
import sys, os, json, time, re, base64
from datetime import datetime, timedelta, timezone

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

BASE_DIR = 'D:/claude/flights'
SHANGHAI_TZ = timezone(timedelta(hours=8))

# Excluded airlines
EXCLUDE_AIRLINES = ['ZIPAIR', 'Philippine Airlines', 'Malaysia Airlines', 'Cebu Pacific']

def _encode_varint(value):
    result = b''
    while value > 0x7f:
        result += bytes([(value & 0x7f) | 0x80])
        value >>= 7
    result += bytes([value])
    return result

def _field_varint(num, val):
    return _encode_varint((num << 3) | 0) + _encode_varint(val)

def _field_bytes(num, data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return _encode_varint((num << 3) | 2) + _encode_varint(len(data)) + data

def build_explore_url(origin_city_id, dest_city_id, date, cabin=1):
    origin_msg = _field_varint(1, 3) + _field_bytes(2, origin_city_id)
    dest_msg = _field_varint(1, 4) + _field_bytes(2, dest_city_id)
    leg1 = _field_bytes(2, date) + _field_bytes(13, origin_msg) + _field_bytes(14, dest_msg)
    leg2 = _field_bytes(13, dest_msg) + _field_bytes(14, origin_msg)
    pax_config = b'\x08\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01'
    field22 = _field_varint(3, 1) + _field_varint(4, 1)
    msg = (_field_varint(1, 28) + _field_varint(2, 3) + _field_bytes(3, leg1) +
           _field_bytes(3, leg2) + _field_varint(8, 1) + _field_varint(9, cabin) +
           _field_varint(14, 2) + _field_bytes(16, pax_config) + _field_varint(19, 1) +
           _field_bytes(22, field22))
    tfs = base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')
    return f'https://www.google.com/travel/explore?tfs={tfs}&tfu=GgA&hl=en&gl=hk&curr=USD'

def dismiss_cookie_consent(page):
    try:
        time.sleep(1)
        for text in ['Reject all', 'Accept all']:
            btn = page.get_by_role('button', name=text)
            if btn.count() > 0:
                btn.first.click()
                print(f"    Cookie consent: clicked '{text}'")
                time.sleep(2)
                return True
    except:
        pass
    return False

def screenshot(page, name):
    path = os.path.join(BASE_DIR, f'verify_hk_{name}.png')
    page.screenshot(path=path)
    return path

def verify_city(explore_page, context, city_name, cabin_label):
    """Click a city tab, View flights, select flights, reach booking page."""
    result = {
        'city': city_name,
        'cabin': cabin_label,
        'status': 'UNKNOWN',
        'screenshots': [],
        'booking_url': None,
        'airline': None,
        'price': None,
    }

    # Step 1: Click city tab
    print(f"  Step 1: Click '{city_name}' tab...")
    clicked = explore_page.evaluate(f"""() => {{
        const items = document.querySelectorAll('[role="tab"], [role="option"], [data-name]');
        for (const item of items) {{
            const text = (item.innerText || item.getAttribute('data-name') || '').trim();
            if (text.includes('{city_name}')) {{
                item.click();
                return true;
            }}
        }}
        // Try clicking on city name text
        const all = document.querySelectorAll('*');
        for (const el of all) {{
            if (el.children.length === 0 && (el.innerText || '').trim().includes('{city_name}')) {{
                el.click();
                return true;
            }}
        }}
        return false;
    }}""")
    if not clicked:
        print(f"    Could not find '{city_name}' tab")
        result['status'] = 'CITY_NOT_FOUND'
        return result

    time.sleep(4)
    result['screenshots'].append(screenshot(explore_page, f'{city_name}_01_click'))

    # Step 2: Find and click "View flights"
    print(f"  Step 2: Click 'View flights'...")
    time.sleep(2)

    # Extract "View flights" URL from DOM and open directly
    vf_url = explore_page.evaluate(r"""() => {
        // Try aria-label first (most reliable)
        const byLabel = document.querySelector('a[aria-label*="View flights"]');
        if (byLabel && byLabel.href) return byLabel.href;
        // Fallback: find by text content
        const links = document.querySelectorAll('a[href]');
        for (const a of links) {
            if ((a.textContent || '').includes('View flights')) return a.href;
        }
        return null;
    }""")
    if vf_url:
        print(f"    View flights URL: {vf_url[:100]}...")
        flights_page = context.new_page()
        flights_page.goto(vf_url, timeout=30000)
        flights_page.wait_for_load_state('domcontentloaded')
        dismiss_cookie_consent(flights_page)
        print(f"    Waiting 10s for fresh search...")
        time.sleep(10)
    else:
        print(f"    No 'View flights' link found in DOM")
        result['status'] = 'VIEW_FLIGHTS_FAILED'
        return result

    result['screenshots'].append(screenshot(flights_page, f'{city_name}_02_flights'))

    # Extract airline info from flights page
    flights_text = flights_page.inner_text('body')[:2000]

    # Step 3: Click first outbound flight
    print(f"  Step 3: Click first outbound flight...")
    clicked_flight = flights_page.evaluate(r"""() => {
        // Find flight result cards and click the first one
        const lists = document.querySelectorAll('ul[role="list"] li, [data-resultid]');
        for (const li of lists) {
            const text = li.innerText || '';
            if (text.includes('hr') && text.includes('$')) {
                li.click();
                return text.substring(0, 150);
            }
        }
        return null;
    }""")
    if clicked_flight:
        print(f"    Clicked: {clicked_flight[:80]}")
    time.sleep(4)
    result['screenshots'].append(screenshot(flights_page, f'{city_name}_03_outbound'))

    # Step 4: Click first return flight
    print(f"  Step 4: Click first return flight...")
    time.sleep(3)
    flights_page.evaluate(r"""() => {
        const lists = document.querySelectorAll('ul[role="list"] li, [data-resultid]');
        let found_selected = false;
        for (const li of lists) {
            const text = li.innerText || '';
            if (text.includes('hr') && text.includes('$')) {
                if (found_selected) {
                    li.click();
                    return text.substring(0, 150);
                }
                // Check if this one is already selected
                if (li.querySelector('[aria-selected="true"]') || li.classList.contains('selected')) {
                    found_selected = true;
                }
            }
        }
        // Fallback: just click the first clickable flight-like element
        for (const li of lists) {
            const text = li.innerText || '';
            if (text.includes('hr') && text.includes('$')) {
                li.click();
                return 'fallback: ' + text.substring(0, 100);
            }
        }
        return null;
    }""")
    time.sleep(5)
    result['screenshots'].append(screenshot(flights_page, f'{city_name}_04_return'))

    # Step 5: Check booking page
    current_url = flights_page.url
    print(f"    URL: {current_url[:120]}")

    if 'booking' not in current_url:
        time.sleep(5)
        current_url = flights_page.url

    result['booking_url'] = current_url
    result['screenshots'].append(screenshot(flights_page, f'{city_name}_05_booking'))

    # Extract booking info
    booking_text = flights_page.inner_text('body')[:2000]
    result['booking_text'] = booking_text[:500]

    # Check for ghost fare
    if "can't find booking" in booking_text.lower():
        result['status'] = 'GHOST'
        print(f"    GHOST FARE - can't find booking options")
        return result

    # Extract airline name
    bw_match = re.search(r'Book with\s+(.+?)(?:Airline|$)', booking_text, re.MULTILINE)
    if bw_match:
        result['airline'] = bw_match.group(1).strip()

    # Extract price
    price_match = re.search(r'\$([0-9,]+)', booking_text)
    if price_match:
        result['price'] = int(price_match.group(1).replace(',', ''))

    # Check for booking options
    if 'Booking options' in booking_text or 'Book with' in booking_text:
        result['status'] = 'BOOKABLE'
        print(f"    BOOKABLE: {result['airline']} ${result['price']}")
    else:
        result['status'] = 'UNKNOWN'
        print(f"    Status unclear")

    # Check if excluded airline
    if result['airline']:
        for excl in EXCLUDE_AIRLINES:
            if excl.lower() in result['airline'].lower():
                result['excluded'] = True
                print(f"    *** EXCLUDED AIRLINE: {result['airline']} ***")
                break

    return result


def main():
    HK_CITY_ID = '/m/03h64'
    US_CITY_ID = '/m/09c7w0'

    # Verify HK Economy fares (the cheap ones)
    # Use a date range that matches the scanner results (Jun-Jul 2026)
    explore_url_eco = build_explore_url(HK_CITY_ID, US_CITY_ID, '2026-06-25', cabin=1)

    # Top mainland US cities to check from HK (no Honolulu)
    cities_to_check = ['San Francisco', 'Los Angeles', 'Denver', 'Seattle', 'New York']

    print('=' * 60)
    print(f"  HONG KONG DEEP VERIFICATION")
    print(f"  Time: {datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d %H:%M Shanghai')}")
    print(f"  Cities: {', '.join(cities_to_check)}")
    print(f"  Cabin: Economy")
    print(f"  Excluded airlines: {', '.join(EXCLUDE_AIRLINES)}")
    print('=' * 60)

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1400, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
            locale='en-US',
        )

        for city in cities_to_check:
            print(f"\n{'─' * 50}")
            print(f"  Verifying: HK Economy → {city}")
            print(f"{'─' * 50}")

            explore_page = context.new_page()
            print(f"  Opening Explore page...")
            explore_page.goto(explore_url_eco, timeout=30000)
            explore_page.wait_for_load_state('networkidle', timeout=15000)
            dismiss_cookie_consent(explore_page)
            time.sleep(3)

            result = verify_city(explore_page, context, city, 'Economy')
            results.append(result)

            # Close all pages for clean slate
            for pg in context.pages:
                try:
                    pg.close()
                except:
                    pass

        browser.close()

    # Save results
    output = {
        'verification_time': datetime.now(SHANGHAI_TZ).isoformat(),
        'origin': 'Hong Kong (HKG)',
        'cabin': 'Economy',
        'cities_verified': len(results),
        'excluded_airlines': EXCLUDE_AIRLINES,
        'results': results,
    }

    out_path = os.path.join(BASE_DIR, 'deep_verify_hk_results.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Summary
    print('\n' + '=' * 60)
    print('  HK VERIFICATION RESULTS')
    print('=' * 60)
    for r in results:
        excluded = ' [EXCLUDED]' if r.get('excluded') else ''
        airline = r.get('airline') or '?'
        price = f"${r['price']}" if r.get('price') else '?'
        print(f"  {airline:20s} | {r['city']:20s} | {r['status']:12s} | {price}{excluded}")

    print(f"\nSaved to: {out_path}")


if __name__ == '__main__':
    main()
