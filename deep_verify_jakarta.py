"""
Deep verification of Jakarta bug fares using Playwright.
1. Opens Google Flights Explore with proper consent handling
2. Loads Jakarta Business/Premium Economy to USA Explore pages
3. Parses destination prices from the Explore page
4. Clicks through to individual city results for booking links
5. Takes screenshots as evidence
"""
import sys
import os
import base64
import json
import re
import time
from datetime import datetime, timedelta

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

OUTPUT_DIR = 'D:/claude/flights'

# --- Protobuf helpers ---
def encode_varint(value):
    result = b''
    while value > 0x7f:
        result += bytes([(value & 0x7f) | 0x80])
        value >>= 7
    result += bytes([value])
    return result

def field_varint(num, val):
    return encode_varint((num << 3) | 0) + encode_varint(val)

def field_bytes(num, data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return encode_varint((num << 3) | 2) + encode_varint(len(data)) + data

JAKARTA_CITY_ID = '/m/044rv'
US_CITY_ID = '/m/09c7w0'

# Scanner bug fare prices to compare against
SCANNER_PRICES_BIZ = {
    'Houston': 839, 'Los Angeles': 889, 'New York': 893,
    'San Francisco': 897, 'Chicago': 893, 'Washington, D.C.': 861,
    'Las Vegas': 946, 'Boston': 861, 'Miami': 884,
    'Seattle': 894, 'San Diego': 898, 'Philadelphia': 903,
    'Atlanta': 884, 'Portland': 902, 'Tampa': 884,
    'Fort Lauderdale': 884, 'Baltimore': 861, 'Pittsburgh': 898,
    'Detroit': 884, 'Charlotte': 898,
}

SCANNER_PRICES_PE = {
    'Houston': 651, 'Los Angeles': 675, 'New York': 678,
    'Washington, D.C.': 675, 'Las Vegas': 678, 'Boston': 666,
    'Miami': 683, 'Seattle': 678, 'Philadelphia': 707,
    'Atlanta': 689, 'Portland': 685, 'Tampa': 712,
    'Fort Lauderdale': 683, 'Pittsburgh': 685, 'Charlotte': 685,
    'Detroit': 689,
}


def build_explore_url(origin_city_id, dest_city_id, date=None, cabin=3, currency='USD'):
    if not date:
        date = (datetime.now() + timedelta(days=120)).strftime('%Y-%m-%d')
    origin_msg = field_varint(1, 3) + field_bytes(2, origin_city_id)
    dest_msg = field_varint(1, 4) + field_bytes(2, dest_city_id)
    leg1 = field_bytes(2, date) + field_bytes(13, origin_msg) + field_bytes(14, dest_msg)
    leg2 = field_bytes(13, dest_msg) + field_bytes(14, origin_msg)
    pax_config = b'\x08\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01'
    field22 = field_varint(3, 1) + field_varint(4, 1)
    msg = (field_varint(1, 28) + field_varint(2, 3) +
           field_bytes(3, leg1) + field_bytes(3, leg2) +
           field_varint(8, 1) + field_varint(9, cabin) +
           field_varint(14, 2) + field_bytes(16, pax_config) +
           field_varint(19, 1) + field_bytes(22, field22))
    tfs = base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')
    return f'https://www.google.com/travel/explore?tfs={tfs}&tfu=GgA&hl=en&gl=hk&curr={currency}'


def handle_dialogs(page):
    """Dismiss Google cookie consent and browser upgrade dialogs."""
    print("  Checking for dialogs...")

    # Handle "Time for an upgrade" / "Proceed anyway"
    for sel in ['a:has-text("Proceed anyway")', 'button:has-text("Proceed anyway")', ':text("Proceed anyway")']:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=3000):
                el.click()
                print(f"    Clicked: {sel}")
                time.sleep(3)
                page.wait_for_load_state('networkidle', timeout=15000)
                time.sleep(3)
                break
        except Exception:
            pass

    # Handle cookie consent
    for sel in ['button:has-text("Accept all")', 'button:has-text("Reject all")',
                'button:has-text("I agree")', '[aria-label="Accept all"]']:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click()
                print(f"    Clicked consent: {sel}")
                time.sleep(3)
                return True
        except Exception:
            pass
    print("    No consent dialog found.")
    return False


def parse_explore_results(body_text):
    """Parse destination + price from Explore page text."""
    lines = [l.strip() for l in body_text.split('\n') if l.strip()]
    results = []

    price_re = re.compile(r'^(?:HK\$|US\$|\$)[\s]?(\d[\d,]*(?:\.\d+)?)$')
    date_re = re.compile(r'^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+')
    stops_re = re.compile(r'^(?:Nonstop|\d+\s+stops?)$', re.IGNORECASE)
    dur_re = re.compile(r'^\d+\s*hr', re.IGNORECASE)

    skip_keywords = ['Explore', 'Where', 'Search', 'Google', 'Round trip', 'One way',
                     'Multi-city', 'Economy', 'Business', 'Premium', 'First', 'travelers',
                     'Departure', 'Return', 'Any dates', 'filters', 'interests',
                     'All', 'Popular', 'Beaches', 'Nature', 'Skiing', 'Cities',
                     'Map', 'List', 'hour', 'drive', 'Nonstop', 'stop']

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check if this is a potential city name
        if (price_re.match(line) or date_re.match(line) or
            stops_re.match(line) or dur_re.match(line) or
            len(line) < 3 or len(line) > 40 or
            any(kw.lower() == line.lower() for kw in skip_keywords)):
            i += 1
            continue

        # Potential city name -- look ahead for date, stops, duration, price
        city = line
        j = i + 1
        dates = stops = duration = price_str = None
        price_val = None

        while j < min(i + 8, len(lines)):
            nxt = lines[j]
            if date_re.match(nxt) and not dates:
                dates = nxt
            elif stops_re.match(nxt) and not stops:
                stops = nxt
            elif dur_re.match(nxt) and not duration:
                duration = nxt
            elif price_re.match(nxt) and not price_str:
                price_str = nxt
                m = price_re.match(nxt)
                price_val = float(m.group(1).replace(',', ''))
                break
            j += 1

        if price_val is not None:
            results.append({
                'city': city,
                'dates': dates or '',
                'stops': stops or '',
                'duration': duration or '',
                'price_str': price_str,
                'price_usd': price_val,
            })
            i = j + 1
        else:
            i += 1

    return results


def try_click_city_and_get_details(page, city_name, wait_secs=5):
    """Click on a city in the Explore results to get flight details."""
    details = {'flights': [], 'booking_links': [], 'view_flights_url': None}

    try:
        # Find and click the city name
        city_el = page.locator(f'text="{city_name}"').first
        if city_el.is_visible(timeout=3000):
            city_el.click()
            time.sleep(wait_secs)

            # Look for "View flights" link
            flight_links = page.evaluate("""() => {
                const links = [];
                document.querySelectorAll('a[href*="travel/flights"]').forEach(a => {
                    links.push({href: a.href, text: a.innerText.substring(0, 100)});
                });
                return links;
            }""")

            if flight_links:
                details['view_flights_url'] = flight_links[0]['href']

                # Navigate to flight details page
                page.goto(flight_links[0]['href'], wait_until='networkidle', timeout=30000)
                time.sleep(5)

                # Handle any new dialogs on the search results page
                handle_dialogs(page)
                time.sleep(2)

                body = page.inner_text('body')

                # Extract all prices visible
                prices = re.findall(r'\$[\d,]+', body)
                details['visible_prices'] = list(dict.fromkeys(prices))[:15]

                # Look for flight result rows
                flight_rows = page.evaluate("""() => {
                    const results = [];
                    const rows = document.querySelectorAll('li[class*="pIav2d"], ul.Rk10dc > li, div[data-resultid]');
                    for (let i = 0; i < Math.min(rows.length, 5); i++) {
                        const text = rows[i].innerText;
                        const lines = text.split('\\n').filter(l => l.trim()).slice(0, 8);
                        results.push(lines.join(' | '));
                    }
                    return results;
                }""")
                details['flights'] = flight_rows

                # Try clicking first flight to get booking options
                first_result = page.query_selector('li[class*="pIav2d"], div[data-resultid]')
                if first_result:
                    try:
                        first_result.click()
                        time.sleep(4)

                        # Extract booking options
                        booking = page.evaluate("""() => {
                            const results = [];
                            const allEls = document.querySelectorAll('a, button, div');
                            for (const el of allEls) {
                                const text = (el.innerText || '').trim();
                                if (text.length > 3 && text.length < 120 && text.includes('$')) {
                                    if (text.match(/Book|Select|Continue|Trip\.com|Expedia|Booking|Kiwi|CheapOair|Priceline|Kayak|airline/i)) {
                                        const href = el.href || el.getAttribute('href') || '';
                                        results.push({text: text, href: href.substring(0, 250)});
                                    }
                                }
                            }
                            return results.slice(0, 10);
                        }""")
                        details['booking_links'] = booking
                    except Exception:
                        pass

            return details
    except Exception as e:
        details['error'] = str(e)[:200]
    return details


def run_verification():
    all_results = {
        'timestamp': datetime.now().isoformat(),
        'business': {'explore_prices': [], 'city_details': {}},
        'premium_economy': {'explore_prices': [], 'city_details': {}},
    }

    print("=" * 70)
    print("  DEEP VERIFICATION - Jakarta Bug Fares to USA")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='en-HK',
            extra_http_headers={'Accept-Language': 'en-HK,en;q=0.9'},
        )
        page = ctx.new_page()

        # ============================================================
        # STEP 1: Initial load + consent
        # ============================================================
        print("\n[INIT] Loading Google Flights Explore to handle consent...")
        init_url = build_explore_url(JAKARTA_CITY_ID, US_CITY_ID, cabin=3)
        page.goto(init_url, wait_until='networkidle', timeout=45000)
        time.sleep(3)
        handle_dialogs(page)
        time.sleep(3)

        # Verify consent was handled -- check page content
        body = page.inner_text('body')
        if 'Before you continue' in body:
            print("  WARNING: Consent dialog still showing. Trying again...")
            handle_dialogs(page)
            time.sleep(3)
            # Try scrolling down to find and click the button
            page.evaluate("window.scrollBy(0, 300)")
            time.sleep(1)
            handle_dialogs(page)
            time.sleep(3)

        page.screenshot(path=f"{OUTPUT_DIR}/verify_init.png", full_page=False)

        # ============================================================
        # STEP 2: Business class Explore page
        # ============================================================
        print("\n" + "=" * 70)
        print("  BUSINESS CLASS - Jakarta to USA Explore")
        print("=" * 70)

        biz_url = build_explore_url(JAKARTA_CITY_ID, US_CITY_ID, cabin=3)
        print(f"  URL: {biz_url[:100]}...")
        page.goto(biz_url, wait_until='networkidle', timeout=45000)
        time.sleep(6)

        # Handle any dialogs again
        handle_dialogs(page)
        time.sleep(2)

        body = page.inner_text('body')
        page.screenshot(path=f"{OUTPUT_DIR}/verify_biz_explore.png", full_page=False)

        # Parse Explore results
        biz_results = parse_explore_results(body)
        print(f"\n  Destinations found: {len(biz_results)}")

        if not biz_results:
            # Debug: dump first few hundred lines
            print("\n  No results parsed. Page text excerpt:")
            for line in body.split('\n')[:50]:
                line = line.strip()
                if line and len(line) < 80:
                    print(f"    {line}")
        else:
            live_count = 0
            gone_count = 0
            changed_count = 0

            print(f"\n  {'Destination':<25s} {'Explore Price':>15s} {'Scanner Price':>15s} {'Status':>12s}")
            print("  " + "-" * 70)

            for dest in biz_results:
                city = dest['city']
                explore_price = dest['price_usd']
                scanner_price = SCANNER_PRICES_BIZ.get(city, None)

                if scanner_price:
                    if abs(explore_price - scanner_price) < 50:
                        status = 'STILL LIVE'
                        live_count += 1
                    elif explore_price < scanner_price * 1.5:
                        status = 'CHANGED'
                        changed_count += 1
                    else:
                        status = 'GONE'
                        gone_count += 1
                else:
                    status = 'NEW'

                scanner_str = f"${scanner_price}" if scanner_price else "N/A"
                print(f"  {city:<25s} ${explore_price:>13,.0f} {scanner_str:>15s} {status:>12s}")

                all_results['business']['explore_prices'].append({
                    'city': city,
                    'explore_price': explore_price,
                    'scanner_price': scanner_price,
                    'dates': dest['dates'],
                    'stops': dest['stops'],
                    'duration': dest['duration'],
                    'status': status,
                })

            print(f"\n  Summary: {live_count} STILL LIVE, {changed_count} CHANGED, {gone_count} GONE")

            # Click through to top cities for booking details
            top_cities = ['Houston', 'Los Angeles', 'Boston', 'New York', 'Miami']
            cities_to_check = [c for c in top_cities if c in [d['city'] for d in biz_results]]

            for city in cities_to_check[:3]:
                print(f"\n  >>> Clicking through to {city} for booking details...")
                # Re-navigate to explore page first
                page.goto(biz_url, wait_until='networkidle', timeout=45000)
                time.sleep(5)

                details = try_click_city_and_get_details(page, city)
                all_results['business']['city_details'][city] = details

                if details.get('view_flights_url'):
                    print(f"      View flights URL: {details['view_flights_url'][:100]}...")
                if details.get('visible_prices'):
                    print(f"      Prices on search page: {', '.join(details['visible_prices'][:8])}")
                if details.get('flights'):
                    print(f"      Flight options: {len(details['flights'])}")
                    for fl in details['flights'][:3]:
                        print(f"        {fl[:120]}")
                if details.get('booking_links'):
                    print(f"      Booking links found: {len(details['booking_links'])}")
                    for bl in details['booking_links']:
                        print(f"        {bl['text']}")

                # Screenshot
                fname = city.lower().replace(' ', '_').replace(',', '').replace('.', '')
                page.screenshot(path=f"{OUTPUT_DIR}/verify_biz_{fname}.png", full_page=False)
                print(f"      Screenshot: verify_biz_{fname}.png")

        # ============================================================
        # STEP 3: Premium Economy Explore page
        # ============================================================
        print("\n" + "=" * 70)
        print("  PREMIUM ECONOMY - Jakarta to USA Explore")
        print("=" * 70)

        pe_url = build_explore_url(JAKARTA_CITY_ID, US_CITY_ID, cabin=2)
        print(f"  URL: {pe_url[:100]}...")
        page.goto(pe_url, wait_until='networkidle', timeout=45000)
        time.sleep(6)

        body = page.inner_text('body')
        page.screenshot(path=f"{OUTPUT_DIR}/verify_pe_explore.png", full_page=False)

        pe_results = parse_explore_results(body)
        print(f"\n  Destinations found: {len(pe_results)}")

        if not pe_results:
            print("\n  No results parsed. Page text excerpt:")
            for line in body.split('\n')[:50]:
                line = line.strip()
                if line and len(line) < 80:
                    print(f"    {line}")
        else:
            live_count = 0
            gone_count = 0
            changed_count = 0

            print(f"\n  {'Destination':<25s} {'Explore Price':>15s} {'Scanner Price':>15s} {'Status':>12s}")
            print("  " + "-" * 70)

            for dest in pe_results:
                city = dest['city']
                explore_price = dest['price_usd']
                scanner_price = SCANNER_PRICES_PE.get(city, None)

                if scanner_price:
                    if abs(explore_price - scanner_price) < 50:
                        status = 'STILL LIVE'
                        live_count += 1
                    elif explore_price < scanner_price * 1.5:
                        status = 'CHANGED'
                        changed_count += 1
                    else:
                        status = 'GONE'
                        gone_count += 1
                else:
                    status = 'NEW/NORMAL'

                scanner_str = f"${scanner_price}" if scanner_price else "N/A"
                print(f"  {city:<25s} ${explore_price:>13,.0f} {scanner_str:>15s} {status:>12s}")

                all_results['premium_economy']['explore_prices'].append({
                    'city': city,
                    'explore_price': explore_price,
                    'scanner_price': scanner_price,
                    'dates': dest['dates'],
                    'status': status,
                })

            print(f"\n  Summary: {live_count} STILL LIVE, {changed_count} CHANGED, {gone_count} GONE")

            # Click through to Houston PE for details
            for city in ['Houston', 'Los Angeles', 'Boston']:
                if city in [d['city'] for d in pe_results]:
                    print(f"\n  >>> Clicking through to {city} PE for booking details...")
                    page.goto(pe_url, wait_until='networkidle', timeout=45000)
                    time.sleep(5)

                    details = try_click_city_and_get_details(page, city)
                    all_results['premium_economy']['city_details'][city] = details

                    if details.get('visible_prices'):
                        print(f"      Prices: {', '.join(details['visible_prices'][:8])}")
                    if details.get('flights'):
                        print(f"      Flights: {len(details['flights'])}")
                        for fl in details['flights'][:3]:
                            print(f"        {fl[:120]}")
                    if details.get('booking_links'):
                        print(f"      Booking links: {len(details['booking_links'])}")
                        for bl in details['booking_links']:
                            print(f"        {bl['text']}")

                    fname = city.lower().replace(' ', '_')
                    page.screenshot(path=f"{OUTPUT_DIR}/verify_pe_{fname}.png", full_page=False)
                    break  # Just do one for PE

        browser.close()

    # ============================================================
    # FINAL SUMMARY
    # ============================================================
    print("\n" + "=" * 70)
    print("  FINAL VERIFICATION SUMMARY")
    print("=" * 70)

    biz_live = [d for d in all_results['business']['explore_prices'] if d['status'] == 'STILL LIVE']
    biz_changed = [d for d in all_results['business']['explore_prices'] if d['status'] == 'CHANGED']
    biz_gone = [d for d in all_results['business']['explore_prices'] if d['status'] == 'GONE']

    pe_live = [d for d in all_results['premium_economy']['explore_prices'] if d['status'] == 'STILL LIVE']
    pe_changed = [d for d in all_results['premium_economy']['explore_prices'] if d['status'] == 'CHANGED']
    pe_gone = [d for d in all_results['premium_economy']['explore_prices'] if d['status'] == 'GONE']

    print(f"\n  BUSINESS CLASS:")
    print(f"    Still live at bug fare prices: {len(biz_live)}")
    if biz_live:
        for d in biz_live:
            print(f"      {d['city']}: ${d['explore_price']:.0f} (scanner: ${d['scanner_price']})")
    print(f"    Price changed (still cheap):   {len(biz_changed)}")
    if biz_changed:
        for d in biz_changed:
            print(f"      {d['city']}: ${d['explore_price']:.0f} (was: ${d['scanner_price']})")
    print(f"    Gone (back to normal):         {len(biz_gone)}")

    print(f"\n  PREMIUM ECONOMY:")
    print(f"    Still live at bug fare prices: {len(pe_live)}")
    if pe_live:
        for d in pe_live:
            print(f"      {d['city']}: ${d['explore_price']:.0f} (scanner: ${d['scanner_price']})")
    print(f"    Price changed (still cheap):   {len(pe_changed)}")
    print(f"    Gone (back to normal):         {len(pe_gone)}")

    # Save results
    output_file = f"{OUTPUT_DIR}/deep_verification_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n  Results saved to: {output_file}")

    return all_results


if __name__ == '__main__':
    run_verification()
