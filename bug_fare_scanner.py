"""
Bug Fare Scanner - Monitors Google Flights Explore for anomalously cheap fares
from Asian cities to the United States across all cabin classes.

Uses Playwright to load Google Flights Explore pages with protobuf-encoded TFS URLs,
parses destination/price lists, and flags potential bug fares.

Usage:
    python bug_fare_scanner.py                           # Scan all cities, all cabins
    python bug_fare_scanner.py --cities jakarta,bangkok  # Specific cities
    python bug_fare_scanner.py --cabins 3,4              # Business + First only
    python bug_fare_scanner.py --date 2026-07-30         # Specific departure date
"""
import sys
import os
import argparse
import base64
import json
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
from money import parse_money_usd, parse_price_line

# ---------------------------------------------------------------------------
# Origin cities with Google Freebase city IDs (/m/xxxxx format)
# ---------------------------------------------------------------------------
ORIGIN_CITIES = {
    'jakarta':       {'code': 'CGK', 'city_id': '/m/044rv',  'name': 'Jakarta'},
    'bangkok':       {'code': 'BKK', 'city_id': '/m/0fn2g',  'name': 'Bangkok'},
    'singapore':     {'code': 'SIN', 'city_id': '/m/06t2t',  'name': 'Singapore'},
    'manila':        {'code': 'MNL', 'city_id': '/m/0195pd',  'name': 'Manila'},
    'kuala_lumpur':  {'code': 'KUL', 'city_id': '/m/049d1',  'name': 'Kuala Lumpur'},
    'ho_chi_minh':   {'code': 'SGN', 'city_id': '/m/0hn4h',  'name': 'Ho Chi Minh City'},
    'hong_kong':     {'code': 'HKG', 'city_id': '/m/03h64',  'name': 'Hong Kong'},
    'seoul':         {'code': 'ICN', 'city_id': '/m/0hsqf',  'name': 'Seoul'},
    'tokyo':         {'code': 'TYO', 'city_id': '/m/07dfk',  'name': 'Tokyo'},
    # Chinese cities
    'shanghai':      {'code': 'PVG', 'city_id': '/m/06wjf',  'name': 'Shanghai'},
    'hangzhou':      {'code': 'HGH', 'city_id': '/m/014vm4', 'name': 'Hangzhou'},
    'ningbo':        {'code': 'NGB', 'city_id': '/m/01l33l', 'name': 'Ningbo'},
    'qingdao':       {'code': 'TAO', 'city_id': '/m/01l3s0', 'name': 'Qingdao'},
    'dalian':        {'code': 'DLC', 'city_id': '/m/01l3k6', 'name': 'Dalian'},
    'beijing':       {'code': 'PEK', 'city_id': '/m/01914',  'name': 'Beijing'},
    'wuhan':         {'code': 'WUH', 'city_id': '/m/0l3cy',  'name': 'Wuhan'},
    'guangzhou':     {'code': 'CAN', 'city_id': '/m/0393g',  'name': 'Guangzhou'},
    'chongqing':     {'code': 'CKG', 'city_id': '/m/017236', 'name': 'Chongqing'},
    'chengdu':       {'code': 'CTU', 'city_id': '/m/016v46', 'name': 'Chengdu'},
    'shenzhen':      {'code': 'SZX', 'city_id': '/m/0lbmv',  'name': 'Shenzhen'},
    'nanjing':       {'code': 'NKG', 'city_id': '/m/05gqy',  'name': 'Nanjing'},
    'xiamen':        {'code': 'XMN', 'city_id': '/m/0126c3', 'name': 'Xiamen'},
    'tianjin':       {'code': 'TSN', 'city_id': '/m/0df4y',  'name': 'Tianjin'},
    'fuzhou':        {'code': 'FOC', 'city_id': '/m/01jzm9', 'name': 'Fuzhou'},
}

# United States destination city ID
US_CITY_ID = '/m/09c7w0'

# Destinations to exclude (Hawaii requires a connecting mainland US flight — not practical)
EXCLUDE_DESTINATIONS = {
    'Honolulu', 'Kauai', 'Maui', 'Hilo',
    '1.5h drive from Washington', '1h drive from Miami', '1h drive from Washington',
}

# Cabin class labels and normal price ranges (RT, in HKD roughly)
CABIN_INFO = {
    1: {'label': 'Economy',         'normal_min_usd': 800,   'normal_max_usd': 2000},
    2: {'label': 'Premium Economy', 'normal_min_usd': 1200,  'normal_max_usd': 3000},
    3: {'label': 'Business',        'normal_min_usd': 3000,  'normal_max_usd': 8000},
    4: {'label': 'First',           'normal_min_usd': 8000,  'normal_max_usd': 20000},
}

# Bug fare threshold: flag if price is below this fraction of normal_min (static fallback)
BUG_FARE_THRESHOLD = 0.60  # 60% of normal minimum

# Proof screenshots directory
PROOF_DIR = 'D:/claude/flights/proof'

RESULTS_FILE = 'D:/claude/flights/scanner_results.json'

# Regex for booking CTAs
BOOK_RE = re.compile(r'book|book with|select', re.I)
PRICE_NARROW_RE = re.compile(r'(?:US\$|\$)\s?\d[\d,]*(?:\.\d{1,2})?')


# ---------------------------------------------------------------------------
# Protobuf TFS encoding for Google Flights Explore URLs
# ---------------------------------------------------------------------------
def encode_varint(value):
    """Encode an integer as a protobuf varint."""
    result = b''
    while value > 0x7f:
        result += bytes([(value & 0x7f) | 0x80])
        value >>= 7
    result += bytes([value])
    return result


def field_varint(num, val):
    """Encode a varint field (wire type 0)."""
    return encode_varint((num << 3) | 0) + encode_varint(val)


def field_bytes(num, data):
    """Encode a length-delimited field (wire type 2)."""
    if isinstance(data, str):
        data = data.encode('utf-8')
    return encode_varint((num << 3) | 2) + encode_varint(len(data)) + data


def build_explore_tfs(origin_city_id, dest_city_id, date=None, cabin=3):
    """Build TFS parameter for Google Flights Explore URL.

    Args:
        origin_city_id: Google city ID like '/m/044rv' (Jakarta)
        dest_city_id:   Google city ID like '/m/09c7w0' (United States)
        date:           Departure date 'YYYY-MM-DD' or None for flexible
        cabin:          1=economy, 2=premium eco, 3=business, 4=first
    Returns:
        URL-safe base64 encoded TFS string
    """
    # Origin uses type=3 (city), dest uses type=4
    origin_msg = field_varint(1, 3) + field_bytes(2, origin_city_id)
    dest_msg = field_varint(1, 4) + field_bytes(2, dest_city_id)

    # Outbound leg
    if date:
        leg1 = field_bytes(2, date) + field_bytes(13, origin_msg) + field_bytes(14, dest_msg)
    else:
        leg1 = field_bytes(13, origin_msg) + field_bytes(14, dest_msg)

    # Return leg (no date = flexible return)
    leg2 = field_bytes(13, dest_msg) + field_bytes(14, origin_msg)

    # Passenger config sub-message
    pax_config = b'\x08\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01'

    # Field 22 sub-message
    field22 = field_varint(3, 1) + field_varint(4, 1)

    msg = (
        field_varint(1, 28) +
        field_varint(2, 3) +       # trip type 3 = explore round-trip
        field_bytes(3, leg1) +     # outbound leg
        field_bytes(3, leg2) +     # return leg
        field_varint(8, 1) +       # 1 adult
        field_varint(9, cabin) +   # cabin class
        field_varint(14, 2) +
        field_bytes(16, pax_config) +
        field_varint(19, 1) +
        field_bytes(22, field22)
    )

    return base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')


def build_explore_url(origin_city_id, dest_city_id, date=None, cabin=3, currency='USD'):
    """Build the full Google Flights Explore URL."""
    # A date is required for the Explore URL to work properly
    if not date:
        default_date = datetime.now() + timedelta(days=120)
        date = default_date.strftime('%Y-%m-%d')
    tfs = build_explore_tfs(origin_city_id, dest_city_id, date=date, cabin=cabin)
    url = (
        f'https://www.google.com/travel/explore'
        f'?tfs={tfs}'
        f'&tfu=GgA'
        f'&hl=en'
        f'&gl=hk'
        f'&curr={currency}'
    )
    return url


# ---------------------------------------------------------------------------
# Page parsing
# ---------------------------------------------------------------------------
def parse_explore_results(body_text, currency_symbol='HK$'):
    """Parse destination + price groups from Google Flights Explore page text.

    The Explore page inner_text() format:
        Los Angeles
        Jul 16 - 22
        2 stops
        32 hr 5 min
        HK$6,961
        New York
        ...

    Returns list of dicts with keys: city, dates, stops, duration, price_raw, price_numeric
    """
    lines = [l.strip() for l in body_text.split('\n') if l.strip()]
    results = []

    # Build a regex for the price line
    # Support HK$, US$, $, etc.
    price_re = re.compile(
        r'^(?:HK\$|US\$|\$|EUR|€|£|¥|MYR|SGD|THB|PHP|VND|TWD|KRW|JPY\s?)[\s]?(\d[\d,]*(?:\.\d+)?)$'
    )
    # Also match plain currency codes like "HK$6,961" or "$1,234"
    price_re2 = re.compile(r'^([A-Z]{2,3})?\$(\d[\d,]*(?:\.\d+)?)$')

    # Month names for date detection
    date_re = re.compile(
        r'^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+'
    )
    # Stops pattern
    stops_re = re.compile(r'^(?:Nonstop|\d+\s+stops?)$', re.IGNORECASE)
    # Duration pattern
    dur_re = re.compile(r'^\d+\s*hr', re.IGNORECASE)

    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip obviously non-city lines
        if price_re.match(line) or price_re2.match(line) or date_re.match(line) or stops_re.match(line) or dur_re.match(line):
            i += 1
            continue

        # Skip very short lines, special chars, or known non-city strings
        skip_prefixes = (
            'http', 'Explore', 'Where', 'Bags', 'Check', 'Carry', 'Price',
            'Filter', 'Sort', 'Google', 'Travel', 'Flights', 'More',
            'All filters', 'Stops', 'Airlines', 'Times', 'Duration',
            'Connecting', 'Emissions', 'Search', 'Sign in', 'Feedback',
            'About these', 'Learn more', 'View', 'Show', 'Hide', 'Close',
            'Round trip', 'One way', 'Multi-city', 'Passengers',
            'Tracked prices', 'Interests', 'Change', 'Showing', 'Based on',
        )
        if len(line) < 3 or any(line.startswith(p) for p in skip_prefixes):
            i += 1
            continue
        # Also skip lines that are clearly UI elements
        if line.lower() in ('bags', 'price', 'times', 'stops', 'duration',
                            'airlines', 'emissions', 'connecting airports',
                            'about these results', 'tracked prices',
                            'interests', 'popular destinations'):
            i += 1
            continue

        # Potential city name -- look ahead for the date/stops/duration/price pattern
        # We expect: city, date, stops, duration, price  (5 lines)
        # But some may be missing stops/duration, so be flexible
        candidate_city = line
        found_price = None
        found_dates = None
        found_stops = None
        found_duration = None

        # Look at the next 1-6 lines for the pattern
        for j in range(1, min(7, len(lines) - i)):
            check = lines[i + j]

            if date_re.match(check) and not found_dates:
                found_dates = check
            elif stops_re.match(check) and not found_stops:
                found_stops = check
            elif dur_re.match(check) and not found_duration:
                found_duration = check
            elif not found_price:
                pm = price_re.match(check)
                if pm:
                    found_price = pm.group(1).replace(',', '')
                    # We consumed up to this line
                    i = i + j + 1
                    break
                pm2 = price_re2.match(check)
                if pm2:
                    found_price = pm2.group(2).replace(',', '')
                    i = i + j + 1
                    break

        if found_price and found_dates:
            try:
                price_numeric = float(found_price)
            except ValueError:
                price_numeric = 0

            results.append({
                'city': candidate_city,
                'dates': found_dates,
                'stops': found_stops or '',
                'duration': found_duration or '',
                'price_raw': found_price,
                'price_numeric': price_numeric,
            })
        else:
            i += 1
            continue

    return results


def classify_fare(price_usd, cabin, baseline_median=None):
    """
    Classify fare using anomaly scoring against baseline when available,
    falling back to static cabin thresholds.
    Returns (label, ratio_to_normal).
    Labels: BUG_CANDIDATE, SALE_CANDIDATE, CHEAP, NORMAL, EXPENSIVE
    """
    if price_usd <= 0:
        return 'unknown', 0.0

    info = CABIN_INFO[cabin]
    static_min = info['normal_min_usd']

    if baseline_median and baseline_median > 0:
        ratio = price_usd / baseline_median
        if price_usd <= min(baseline_median * 0.55, static_min * 0.48):
            return 'BUG_CANDIDATE', ratio
        if price_usd <= baseline_median * 0.75:
            return 'SALE_CANDIDATE', ratio
        if price_usd < static_min:
            return 'CHEAP', ratio
        return 'NORMAL', ratio
    else:
        # Static fallback — no baseline data yet
        ratio = price_usd / static_min
        bug_threshold = static_min * BUG_FARE_THRESHOLD
        if price_usd < bug_threshold:
            return 'BUG_CANDIDATE', ratio
        if price_usd < static_min * 0.80:
            return 'SALE_CANDIDATE', ratio
        if price_usd < static_min:
            return 'CHEAP', ratio
        if price_usd <= info['normal_max_usd']:
            return 'NORMAL', ratio
        return 'EXPENSIVE', ratio


def cross_cabin_signals(econ_usd, prem_usd, biz_usd):
    """
    Detect cross-cabin price inversions — strong real bug fare signals.
    e.g. Business priced near/below Economy is almost always a pricing error.
    """
    signals = []
    if biz_usd and econ_usd and biz_usd <= econ_usd * 1.15:
        signals.append('BIZ_NEAR_ECON')
    if prem_usd and econ_usd and prem_usd < econ_usd:
        signals.append('PREM_BELOW_ECON')
    if biz_usd and prem_usd and biz_usd < prem_usd:
        signals.append('BIZ_BELOW_PREM')
    return signals


# ---------------------------------------------------------------------------
# Cookie consent handler
# ---------------------------------------------------------------------------
def handle_dialogs(page):
    """Dismiss Google's cookie consent dialog and browser upgrade warning if present."""
    print("  Checking for dialogs...")

    # Handle "Time for an upgrade" / "Proceed anyway" browser warning
    proceed_selectors = [
        'a:has-text("Proceed anyway")',
        'button:has-text("Proceed anyway")',
        ':text("Proceed anyway")',
    ]
    for sel in proceed_selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=3000):
                el.click()
                print(f"    Clicked: {sel}")
                time.sleep(3)
                # After clicking proceed, page may reload -- wait
                page.wait_for_load_state('networkidle', timeout=15000)
                time.sleep(3)
                break
        except Exception:
            pass

    # Handle cookie consent
    consent_selectors = [
        'button:has-text("Accept all")',
        'button:has-text("Reject all")',
        'button:has-text("I agree")',
        '[aria-label="Accept all"]',
        'button:has-text("Alle akzeptieren")',
        'button:has-text("Tout accepter")',
    ]
    for sel in consent_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click()
                print(f"    Clicked consent: {sel}")
                time.sleep(2)
                return True
        except Exception:
            pass
    print("    No consent dialog found (already accepted or not shown).")
    return False


# ---------------------------------------------------------------------------
# Semantic wait — replaces bare time.sleep() for Google Flights SPA
# ---------------------------------------------------------------------------
def wait_for_flight_ui(page, timeout=25000):
    """Wait for Google Flights UI to render useful content."""
    candidates = [
        lambda: page.get_by_text(re.compile(r'Best flights|Cheapest', re.I)).first,
        lambda: page.get_by_text(re.compile(r'(?:US\$|\$)\d', re.I)).first,
        lambda: page.locator('li').first,
    ]
    for getter in candidates:
        try:
            loc = getter()
            loc.wait_for(state='visible', timeout=timeout)
            return True
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# Partner link + price extraction (scoped, not body-wide)
# ---------------------------------------------------------------------------
def find_partner_links(page):
    """Find external booking links (non-Google) visible on the current page."""
    links = page.evaluate("""() => {
        const out = [];
        for (const a of document.querySelectorAll('a[href]')) {
            const txt = (a.innerText || a.textContent || '').trim();
            const href = a.href || '';
            if (!href || !/^https?:/i.test(href)) continue;
            try { if (/google\\./.test(new URL(href).hostname)) continue; }
            catch(e) { continue; }
            if (/book|book with|select|continue/i.test(txt)) {
                out.push({text: txt.substring(0, 100), href});
            }
        }
        return out;
    }""")
    seen = set()
    uniq = []
    for x in links:
        key = (x['text'], x['href'])
        if key not in seen:
            uniq.append(x)
            seen.add(key)
    return uniq


def capture_visible_prices(page):
    """Extract all visible price strings — scoped to first 20k chars of body."""
    text = page.inner_text('body')[:20000]
    return sorted(set(m.group(0) for m in PRICE_NARROW_RE.finditer(text)))[:20]


# ---------------------------------------------------------------------------
# Proof screenshot bundle
# ---------------------------------------------------------------------------
def capture_proof(page, route_key, out_dir):
    """
    Save full-page screenshot + tight book-button crop + meta JSON.
    Returns True if book button was found.
    """
    os.makedirs(out_dir, exist_ok=True)
    # Full page
    page.screenshot(path=os.path.join(out_dir, f'{route_key}_full.png'), full_page=True)
    # Tight crop of book button
    found_button = False
    for getter in [
        lambda: page.get_by_role('link', name=BOOK_RE).first,
        lambda: page.get_by_role('button', name=BOOK_RE).first,
        lambda: page.get_by_text(re.compile(r'book with', re.I)).first,
    ]:
        try:
            loc = getter()
            if loc.is_visible(timeout=3000):
                loc.scroll_into_view_if_needed(timeout=3000)
                loc.screenshot(path=os.path.join(out_dir, f'{route_key}_book_button.png'))
                found_button = True
                break
        except Exception:
            pass
    return found_button


# ---------------------------------------------------------------------------
# 4-state verification: MAP_ONLY → SEARCH_LOADED → BOOK_PANEL_VISIBLE → PARTNER_LINK_FOUND
# ---------------------------------------------------------------------------
def verify_exact_route(page, explore_url, dest_city, route_key, proof_dir=None):
    """
    Navigate from Explore map → click dest → search page → booking panel.
    Returns dict with status and evidence. Only BOOK_PANEL_VISIBLE+ is truly verified.
    """
    print(f"      Verifying: {dest_city} ({route_key})")

    # Go to Explore, click destination
    page.goto(explore_url, wait_until='domcontentloaded', timeout=45000)
    wait_for_flight_ui(page)

    try:
        city_el = page.get_by_text(dest_city, exact=False).first
        city_el.wait_for(state='visible', timeout=5000)
        city_el.click()
        time.sleep(2)
    except Exception as e:
        return {'status': 'MAP_ONLY', 'reason': f'dest_not_clickable: {e}', 'google_url': explore_url}

    # Find flights search link
    flight_links = page.evaluate("""() => {
        const links = [];
        document.querySelectorAll('a[href*="travel/flights"]').forEach(a => {
            links.push({href: a.href, text: (a.innerText || '').substring(0, 60)});
        });
        return links;
    }""")

    if not flight_links:
        return {'status': 'MAP_ONLY', 'reason': 'no_flight_links', 'google_url': page.url}

    # Navigate to search page
    search_url = flight_links[0]['href']
    page.goto(search_url, wait_until='domcontentloaded', timeout=45000)
    wait_for_flight_ui(page)

    # Click first result card
    try:
        cards = page.locator('li').filter(has_text=re.compile(r'nonstop|\d+ stop', re.I))
        if cards.count() == 0:
            cards = page.locator('li')
        if cards.count() > 0:
            cards.first.click(timeout=8000)
            time.sleep(3)
    except Exception:
        pass

    # Check for booking panel
    book_visible = False
    for getter in [
        lambda: page.get_by_role('link', name=BOOK_RE),
        lambda: page.get_by_role('button', name=BOOK_RE),
        lambda: page.get_by_text(re.compile(r'book with', re.I)),
    ]:
        try:
            loc = getter()
            if loc.count() > 0 and loc.first.is_visible():
                book_visible = True
                break
        except Exception:
            pass

    partner_links = find_partner_links(page)
    visible_prices = capture_visible_prices(page)

    result = {
        'status': 'SEARCH_LOADED',
        'google_booking_url': page.url,
        'visible_prices': visible_prices,
        'partner_links': partner_links[:5],
        'partner_domains': sorted({
            urlparse(x['href']).netloc.lower()
            for x in partner_links if x.get('href')
        }),
    }

    if book_visible:
        result['status'] = 'BOOK_PANEL_VISIBLE'
    if partner_links:
        result['status'] = 'PARTNER_LINK_FOUND'

    # Capture proof bundle
    if proof_dir:
        has_button = capture_proof(page, route_key, proof_dir)
        meta = {
            'route_key': route_key,
            'verified_at': datetime.utcnow().isoformat() + 'Z',
            'status': result['status'],
            'google_booking_url': result['google_booking_url'],
            'visible_prices': visible_prices,
            'partner_domains': result['partner_domains'],
            'book_button_screenshot': has_button,
        }
        with open(os.path.join(proof_dir, f'{route_key}_meta.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"      Status: {result['status']} | prices: {visible_prices[:3]} | "
          f"partners: {result['partner_domains'][:3]}")
    return result


# ---------------------------------------------------------------------------
# Main scanner
# ---------------------------------------------------------------------------
def run_scanner(cities_to_scan, cabins_to_scan, departure_date=None, output_file=None):
    """Run the bug fare scanner across specified cities and cabin classes."""

    scan_timestamp = datetime.now().isoformat()
    all_results = {
        'scan_timestamp': scan_timestamp,
        'scan_date': departure_date or 'flexible',
        'cities_scanned': [],
        'cabins_scanned': cabins_to_scan,
        'destinations': [],
        'bug_fares': [],
        'cheap_fares': [],
        'summary': {},
    }

    print("=" * 80)
    print(f"  BUG FARE SCANNER - Google Flights Explore")
    print(f"  Scan time:  {scan_timestamp}")
    print(f"  Cities:     {', '.join(c['name'] for c in cities_to_scan)}")
    print(f"  Cabins:     {', '.join(CABIN_INFO[c]['label'] for c in cabins_to_scan)}")
    print(f"  Date:       {departure_date or 'flexible (next 6 months)'}")
    print(f"  Dest:       United States")
    print("=" * 80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='en-HK',
            extra_http_headers={'Accept-Language': 'en-HK,en;q=0.9'},
        )
        page = ctx.new_page()

        # First load: accept cookie consent
        print("\nInitializing: loading Google Flights Explore...")
        first_url = build_explore_url(
            cities_to_scan[0]['city_id'], US_CITY_ID,
            date=departure_date, cabin=cabins_to_scan[0]
        )
        page.goto(first_url, wait_until='domcontentloaded', timeout=45000)
        wait_for_flight_ui(page)
        handle_dialogs(page)
        time.sleep(1)

        cookies_accepted = True
        total_scans = len(cities_to_scan) * len(cabins_to_scan)
        scan_num = 0

        for city_info in cities_to_scan:
            city_key = city_info['name']
            city_id = city_info['city_id']
            city_code = city_info['code']
            all_results['cities_scanned'].append(city_key)

            for cabin in cabins_to_scan:
                scan_num += 1
                cabin_label = CABIN_INFO[cabin]['label']

                print(f"\n{'─' * 70}")
                print(f"  [{scan_num}/{total_scans}] {city_key} ({city_code}) -> USA | {cabin_label}")
                print(f"{'─' * 70}")

                url = build_explore_url(city_id, US_CITY_ID, date=departure_date, cabin=cabin)
                print(f"  URL: {url[:120]}...")

                try:
                    page.goto(url, wait_until='domcontentloaded', timeout=45000)
                    wait_for_flight_ui(page)  # semantic wait — no bare sleep

                    # Get body text
                    body_text = page.inner_text('body')

                    # Currency is always USD since curr=USD in URL
                    page_currency = 'USD'

                    # Parse results
                    destinations = parse_explore_results(body_text)

                    if not destinations:
                        print("  No structured results parsed. Dumping price lines...")
                        for line in body_text.split('\n'):
                            line = line.strip()
                            if ('$' in line or 'HK$' in line) and len(line) < 50:
                                print(f"    >> {line}")
                        debug_path = f'D:/claude/flights/scanner_debug_{city_code}_{cabin}.txt'
                        with open(debug_path, 'w', encoding='utf-8') as df:
                            df.write(body_text)
                        print(f"  Debug text saved to {debug_path}")
                    else:
                        print(f"  Found {len(destinations)} destinations (currency: {page_currency}):")

                    for dest in destinations:
                        if dest['city'] in EXCLUDE_DESTINATIONS:
                            continue
                        # price_numeric is already USD (curr=USD in URL)
                        price_usd = float(dest['price_numeric'])
                        classification, ratio = classify_fare(price_usd, cabin)

                        marker = ''
                        if classification == 'BUG_CANDIDATE':
                            marker = ' *** BUG CANDIDATE ***'
                        elif classification == 'SALE_CANDIDATE':
                            marker = ' (sale!)'
                        elif classification == 'CHEAP':
                            marker = ' (cheap)'

                        print(f"    ${price_usd:>6,.0f} -> {dest['city']:<20} "
                              f"| {dest['dates']} | {dest['stops']}{marker}")

                        result_entry = {
                            'origin_city': city_key,
                            'origin_code': city_code,
                            'destination': dest['city'],
                            'cabin': cabin_label,
                            'cabin_num': cabin,
                            'price_usd': round(price_usd, 2),
                            'dates': dest['dates'],
                            'stops': dest['stops'],
                            'duration': dest['duration'],
                            'classification': classification,
                            'ratio': round(ratio, 3),
                            'scan_timestamp': scan_timestamp,
                            'verification': None,
                        }
                        all_results['destinations'].append(result_entry)

                        if classification in ('BUG_CANDIDATE',):
                            all_results['bug_fares'].append(result_entry)
                        elif classification in ('SALE_CANDIDATE', 'CHEAP'):
                            all_results['cheap_fares'].append(result_entry)

                    # Verify top bug candidates with 4-state verifier
                    bug_candidates_this_scan = [
                        d for d in destinations
                        if classify_fare(float(d.get('price_numeric', 0)), cabin)[0] == 'BUG_CANDIDATE'
                    ]

                    if bug_candidates_this_scan:
                        print(f"\n  >> {len(bug_candidates_this_scan)} bug candidate(s)! Running 4-state verification...")
                        for bf in bug_candidates_this_scan[:3]:
                            route_key = f"{city_code}_{bf['city'].replace(' ','_')}_{cabin_label}"
                            verification = verify_exact_route(
                                page, url, bf['city'], route_key, proof_dir=PROOF_DIR
                            )
                            status = verification.get('status', 'unknown')
                            print(f"      {bf['city']}: {status}")
                            if status in ('BOOK_PANEL_VISIBLE', 'PARTNER_LINK_FOUND'):
                                print(f"      *** CONFIRMED BOOKABLE *** partners: {verification.get('partner_domains')}")
                            # Update result entry
                            for entry in all_results['bug_fares']:
                                if (entry['destination'] == bf['city'] and
                                        entry['origin_code'] == city_code and
                                        entry['cabin_num'] == cabin):
                                    entry['verification'] = verification
                                    break

                except Exception as e:
                    print(f"  ERROR loading page: {e}")
                    try:
                        err_path = f'D:/claude/flights/scanner_error_{city_code}_{cabin}.png'
                        page.screenshot(path=err_path)
                        print(f"  Error screenshot: {err_path}")
                    except Exception:
                        pass

                # Rate limiting
                time.sleep(3)

        browser.close()

    # Build summary
    all_results['summary'] = {
        'total_destinations_found': len(all_results['destinations']),
        'total_bug_fares': len(all_results['bug_fares']),
        'total_cheap_fares': len(all_results['cheap_fares']),
        'bug_fare_details': [
            {
                'route': f"{bf['origin_code']} -> {bf['destination']}",
                'cabin': bf['cabin'],
                'price_usd': bf['price_usd'],
                'dates': bf['dates'],
                'verification_status': (bf.get('verification') or {}).get('status'),
                'partner_domains': (bf.get('verification') or {}).get('partner_domains', []),
            }
            for bf in all_results['bug_fares']
        ],
        'cheap_fare_details': [
            {
                'route': f"{cf['origin_code']} -> {cf['destination']}",
                'cabin': cf['cabin'],
                'price_usd': cf['price_usd'],
                'dates': cf['dates'],
            }
            for cf in all_results['cheap_fares']
        ],
    }

    # Save results
    out = output_file or RESULTS_FILE
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {out}")

    # Print summary
    print("\n" + "=" * 80)
    print("  SCAN COMPLETE - SUMMARY")
    print("=" * 80)
    print(f"  Total destinations found: {all_results['summary']['total_destinations_found']}")
    print(f"  Potential BUG FARES:      {all_results['summary']['total_bug_fares']}")
    print(f"  Cheap (below normal):     {all_results['summary']['total_cheap_fares']}")

    if all_results['bug_fares']:
        print(f"\n  {'='*60}")
        print(f"  *** BUG CANDIDATES DETECTED ***")
        print(f"  {'='*60}")
        for bf in all_results['bug_fares']:
            v = bf.get('verification') or {}
            vstatus = v.get('status', 'unverified')
            confirmed = '✓ CONFIRMED' if vstatus in ('BOOK_PANEL_VISIBLE', 'PARTNER_LINK_FOUND') else vstatus
            print(f"    {bf['origin_code']:>3} -> {bf['destination']:<20} | {bf['cabin']:<18} | "
                  f"${bf['price_usd']:>6,.0f} | {bf['dates']} | {confirmed}")
            if v.get('partner_domains'):
                print(f"         Partners: {', '.join(v['partner_domains'][:3])}")
            if v.get('google_booking_url'):
                print(f"         URL: {v['google_booking_url'][:100]}")

    if all_results['cheap_fares']:
        print(f"\n  Cheap fares (below normal range but not bug-fare level):")
        for cf in all_results['cheap_fares']:
            sym = 'HK$' if cf.get('price_currency') == 'HKD' else '$'
            print(f"    {cf['origin_code']:>3} -> {cf['destination']:<20} | {cf['cabin']:<18} | "
                  f"{sym}{cf['price_raw']:>8,.0f} (~US${cf['price_usd']:>6,.0f}) | {cf['dates']}")

    if not all_results['bug_fares'] and not all_results['cheap_fares']:
        print("\n  No anomalous fares detected in this scan. All prices within normal range.")

    return all_results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description='Bug Fare Scanner - Monitor Google Flights Explore for anomalously cheap fares'
    )
    parser.add_argument(
        '--cities', type=str, default=None,
        help='Comma-separated city names to scan (default: all). '
             'Options: jakarta,bangkok,singapore,manila,kuala_lumpur,ho_chi_minh,hong_kong,taipei,seoul,tokyo'
    )
    parser.add_argument(
        '--cabins', type=str, default='1,2,3,4',
        help='Comma-separated cabin class numbers (default: 1,2,3,4). '
             '1=economy, 2=premium economy, 3=business, 4=first'
    )
    parser.add_argument(
        '--date', type=str, default=None,
        help='Departure date YYYY-MM-DD (default: flexible/next 6 months)'
    )
    parser.add_argument(
        '--output', type=str, default=None,
        help='Output JSON file path (default: scanner_results.json)'
    )
    args = parser.parse_args()

    # Parse cities
    if args.cities:
        city_keys = [c.strip().lower().replace(' ', '_') for c in args.cities.split(',')]
        cities_to_scan = []
        for ck in city_keys:
            if ck in ORIGIN_CITIES:
                cities_to_scan.append(ORIGIN_CITIES[ck])
            else:
                print(f"Warning: unknown city '{ck}'. Available: {', '.join(ORIGIN_CITIES.keys())}")
        if not cities_to_scan:
            print("Error: no valid cities specified.")
            sys.exit(1)
    else:
        cities_to_scan = list(ORIGIN_CITIES.values())

    # Parse cabins
    cabins_to_scan = []
    for c in args.cabins.split(','):
        c = c.strip()
        if c.isdigit() and int(c) in CABIN_INFO:
            cabins_to_scan.append(int(c))
        else:
            print(f"Warning: invalid cabin '{c}'. Valid: 1,2,3,4")
    if not cabins_to_scan:
        print("Error: no valid cabin classes specified.")
        sys.exit(1)

    # Validate date
    if args.date:
        try:
            datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            print(f"Error: invalid date format '{args.date}'. Use YYYY-MM-DD.")
            sys.exit(1)

    # Partial runs (--cities or --cabins specified) write to a separate file
    # to avoid overwriting the full scan results.
    is_partial = bool(args.cities or (args.cabins and args.cabins != '1,2,3,4'))
    if args.output:
        output_file = args.output
    elif is_partial:
        tag = (args.cities or 'partial').replace(',', '_').replace(' ', '_')[:30]
        output_file = os.path.join(os.path.dirname(RESULTS_FILE), f'scanner_partial_{tag}.json')
        print(f"[Partial run] Results → {output_file}  (full results preserved)")
    else:
        output_file = RESULTS_FILE
    run_scanner(cities_to_scan, cabins_to_scan, departure_date=args.date, output_file=output_file)


if __name__ == '__main__':
    main()
