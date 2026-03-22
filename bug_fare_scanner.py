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
from entities import (
    ORIGINS, ORIGINS_BY_CITY, DESTS_US_BY_CITY, US_EXPLORE_ID,
    is_excluded_dest, detect_stopover_iata, get_origin_google_id,
    get_dest_freebase_id,
)

# ---------------------------------------------------------------------------
# Origin cities — derived from entities.py (single source of truth)
# ---------------------------------------------------------------------------
ORIGIN_CITIES = {
    v['city'].lower().replace(' ', '_'): {
        'code': k,
        'city_id': v['google_id'],
        'name': v['city'],
    }
    for k, v in ORIGINS.items()
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

# Base directory — works on both Windows (D:/claude/flights) and Railway/Linux (/app)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Proof screenshots directory
PROOF_DIR = os.path.join(BASE_DIR, 'proof')
os.makedirs(PROOF_DIR, exist_ok=True)

# Family composition: 2 adults + 1 child (child ~2y7m old → age bucket 3)
CHILD_AGE = 3

RESULTS_FILE = os.path.join(BASE_DIR, 'scanner_results.json')

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
def parse_explore_results(body_text):
    """Parse destination + price groups from Google Flights Explore page text.

    Uses money.parse_price_line() for currency-agnostic, multi-format price parsing.

    The Explore page inner_text() format:
        Los Angeles
        Jul 16 - 22
        2 stops
        32 hr 5 min
        $1,234
        New York
        ...

    Returns list of dicts with keys: city, dates, stops, duration, price_raw, price_numeric
    price_numeric is always USD (money.py handles all currency conversions).
    """
    lines = [l.strip() for l in body_text.split('\n') if l.strip()]
    results = []

    date_re  = re.compile(r'^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+')
    stops_re = re.compile(r'^(?:Nonstop|\d+\s+stops?)$', re.IGNORECASE)
    dur_re   = re.compile(r'^\d+\s*hr', re.IGNORECASE)

    skip_prefixes = (
        'http', 'Explore', 'Where', 'Bags', 'Check', 'Carry', 'Price',
        'Filter', 'Sort', 'Google', 'Travel', 'Flights', 'More',
        'All filters', 'Stops', 'Airlines', 'Times', 'Duration',
        'Connecting', 'Emissions', 'Search', 'Sign in', 'Feedback',
        'About these', 'Learn more', 'View', 'Show', 'Hide', 'Close',
        'Round trip', 'One way', 'Multi-city', 'Passengers',
        'Tracked prices', 'Interests', 'Change', 'Showing', 'Based on',
    )
    skip_exact = {'bags', 'price', 'times', 'stops', 'duration', 'airlines',
                  'emissions', 'connecting airports', 'about these results',
                  'tracked prices', 'interests', 'popular destinations'}

    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip lines that are clearly non-city (price/date/stops/duration/UI)
        if (parse_price_line(line) or date_re.match(line) or
                stops_re.match(line) or dur_re.match(line)):
            i += 1
            continue
        if len(line) < 3 or any(line.startswith(p) for p in skip_prefixes):
            i += 1
            continue
        if line.lower() in skip_exact:
            i += 1
            continue

        # Potential city name — look ahead for date/stops/duration/price
        candidate_city = line
        found_price_usd = None
        found_dates = None
        found_stops = None
        found_duration = None

        for j in range(1, min(7, len(lines) - i)):
            check = lines[i + j]
            if date_re.match(check) and not found_dates:
                found_dates = check
            elif stops_re.match(check) and not found_stops:
                found_stops = check
            elif dur_re.match(check) and not found_duration:
                found_duration = check
            elif not found_price_usd:
                price_usd = parse_price_line(check)
                if price_usd:
                    found_price_usd = price_usd
                    i = i + j + 1
                    break

        if found_price_usd and found_dates:
            results.append({
                'city': candidate_city,
                'dates': found_dates,
                'stops': found_stops or '',
                'duration': found_duration or '',
                'price_raw': found_price_usd,    # USD float (converted by money.py)
                'price_numeric': found_price_usd,
            })
        else:
            i += 1

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
# Ghost-fare tracking (persistent across scan runs)
# ---------------------------------------------------------------------------
GHOST_FILE = os.path.join(BASE_DIR, 'ghost_fares.json')

def load_ghost_fares():
    """Load the ghost fare registry (route → failure count)."""
    try:
        with open(GHOST_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_ghost_fares(ghosts):
    with open(GHOST_FILE, 'w', encoding='utf-8') as f:
        json.dump(ghosts, f, indent=2, ensure_ascii=False)

def fare_hash(origin_code, dest_city, cabin_num, dates):
    """Stable hash for a fare — used to track ghost failures."""
    return f"{origin_code}:{dest_city}:{cabin_num}:{dates}"

def record_ghost_failure(ghosts, origin_code, dest_city, cabin_num, dates,
                         status='unknown', reason=''):
    """Record a verification failure. Stores structured data (count + last status/reason)."""
    key = fare_hash(origin_code, dest_city, cabin_num, dates)
    entry = ghosts.get(key)
    if entry is None:
        entry = {'count': 0, 'last_status': None, 'last_reason': '', 'last_seen': ''}
    elif isinstance(entry, int):
        # Migrate from old plain-int format
        entry = {'count': entry, 'last_status': None, 'last_reason': '', 'last_seen': ''}
    entry['count'] += 1
    entry['last_status'] = status
    entry['last_reason'] = reason
    entry['last_seen'] = datetime.utcnow().isoformat() + 'Z'
    ghosts[key] = entry
    return entry['count']


def is_likely_ghost(ghosts, origin_code, dest_city, cabin_num, dates, threshold=2):
    """
    Return True if this fare has failed meaningful verification ≥ threshold times.
    MAP_ONLY failures alone don't suppress — they may just be a UI load issue.
    """
    key = fare_hash(origin_code, dest_city, cabin_num, dates)
    entry = ghosts.get(key)
    if not entry:
        return False
    if isinstance(entry, int):
        return entry >= threshold
    count = entry.get('count', 0)
    # Don't suppress if the only recorded failures were MAP_ONLY (possible load issue)
    if entry.get('last_status') == 'MAP_ONLY' and count < threshold + 1:
        return False
    return count >= threshold


# ---------------------------------------------------------------------------
# Family verification (2 adults + 1 child) — real second-pass booking check
# ---------------------------------------------------------------------------
def estimate_family_price(pp_price_usd):
    """Estimate total family price (2A+1C). Child ~75% adult, so 2.75× adult."""
    return round(pp_price_usd * 2.75)


def build_family_search_url(origin_cid, dest_cid, depart_date, return_date,
                            cabin=3, child_age=CHILD_AGE):
    """
    Build Google Flights search URL for 2 adults + 1 child.
    child_age: actual child age in years (CHILD_AGE constant = 3, reflecting ~2y7m).
    TFS: field 8 = 2 adults, field 7 = child age (best-effort protobuf encoding).
    """
    o = field_varint(1, 3) + field_bytes(2, origin_cid)
    d = field_varint(1, 2) + field_bytes(2, dest_cid)
    l1 = field_bytes(2, depart_date) + field_bytes(13, o) + field_bytes(14, d)
    l2 = field_bytes(2, return_date) + field_bytes(13, d) + field_bytes(14, o)
    pax_config = b'\x08\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01'
    field22 = field_varint(3, 1) + field_varint(4, 1)
    msg = (
        field_varint(1, 27) +
        field_varint(2, 2) +         # round-trip
        field_bytes(3, l1) +
        field_bytes(3, l2) +
        field_varint(8, 2) +         # 2 adults
        field_varint(7, child_age) + # 1 child at actual age
        field_varint(9, cabin) +
        field_varint(14, 2) +
        field_bytes(16, pax_config) +
        field_varint(19, 1) +
        field_bytes(22, field22)
    )
    tfs = base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')
    return f'https://www.google.com/travel/flights?tfs={tfs}&hl=en&gl=hk&curr=USD'


def verify_family_booking(page_ctx, origin_cid, dest_cid, depart_date, return_date,
                          cabin, expected_pp_usd,
                          expected_dest='', expected_stops=-1, expected_date_text=''):
    """
    Second-pass verification: check if 2A+1C booking panel is available for exact itinerary.
    Uses route-aware card matching (dest + stops + date + price) to avoid wrong-card clicks.
    Returns dict with family_price_verified, family_booking_status, family_inventory_ok,
    family_reprice_delta_pct (vs 2.75× single-adult estimate).
    """
    url = build_family_search_url(origin_cid, dest_cid, depart_date, return_date, cabin)
    result = {
        'family_search_url': url,
        'family_price_verified': None,
        'family_booking_status': None,
        'family_inventory_ok': False,
        'family_reprice_delta_pct': None,
    }
    family_page = page_ctx.new_page()
    try:
        family_page.goto(url, wait_until='domcontentloaded', timeout=45000)
        wait_for_flight_ui(family_page)

        text = family_page.inner_text('body')[:3000]
        family_price = parse_price_line(text)
        result['family_price_verified'] = round(family_price) if family_price else None

        # Route-aware card click: pass all context so we don't confirm the wrong itinerary
        card, matched = find_matching_result_card(
            family_page, expected_pp_usd * 2.75,
            expected_dest=expected_dest,
            expected_stops=expected_stops,
            expected_date_text=expected_date_text,
        )
        if card:
            if not matched:
                print(f"      [family] no strong route match — skipping card click to avoid false confirm")
            else:
                card.click(timeout=8000)
                time.sleep(3)

        book_visible = False
        for getter in [
            lambda: family_page.get_by_role('link', name=BOOK_RE),
            lambda: family_page.get_by_role('button', name=BOOK_RE),
            lambda: family_page.get_by_text(re.compile(r'book with', re.I)),
        ]:
            try:
                loc = getter()
                if loc.count() > 0 and loc.first.is_visible():
                    book_visible = True
                    break
            except Exception:
                pass

        result['family_booking_status'] = 'BOOK_PANEL_VISIBLE' if book_visible else 'SEARCH_LOADED'
        result['family_inventory_ok'] = book_visible
        if family_price and expected_pp_usd > 0:
            expected_family = expected_pp_usd * 2.75
            result['family_reprice_delta_pct'] = round(
                (family_price / expected_family - 1) * 100, 1)
    except Exception as e:
        result['family_booking_status'] = f'ERROR: {str(e)[:60]}'
    finally:
        family_page.close()
    return result


# ---------------------------------------------------------------------------
# Result card matching — don't blindly click first result
# ---------------------------------------------------------------------------
def find_matching_result_card(page, expected_price_usd,
                              expected_dest='', expected_stops=-1,
                              expected_date_text='', tolerance=0.15):
    """
    Find the result card best matching dest, stops, outbound date month, and price.

    Scoring per candidate card (max 6 points):
      dest match    — 2 pts (card text contains expected_dest)
      stops match   — 1 pt  (nonstop/N stop count matches)
      date month    — 1 pt  (outbound month appears in card text)
      price match   — 2 pts (within ±tolerance of expected_price_usd)

    Falls back to first card if no strong match. Returns (locator, matched: bool).
    """
    cards = page.locator('li').filter(has_text=re.compile(r'nonstop|\d+ stop', re.I))
    if cards.count() == 0:
        cards = page.locator('li')
    count = cards.count()
    if count == 0:
        return None, False

    # Extract expected month abbreviation for date matching
    expected_month = ''
    if expected_date_text:
        m = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)',
                      expected_date_text, re.I)
        if m:
            expected_month = m.group(1).lower()

    candidates = []
    for idx in range(min(count, 8)):
        try:
            card = cards.nth(idx)
            text = card.inner_text(timeout=2000)
            text_lower = text.lower()

            dest_ok = not expected_dest or expected_dest.lower() in text_lower

            if expected_stops == 0:
                stops_ok = 'nonstop' in text_lower
            elif expected_stops > 0:
                stops_ok = f'{expected_stops} stop' in text_lower
            else:
                stops_ok = True

            date_ok = not expected_month or expected_month in text_lower

            price = parse_price_line(text)
            price_delta = float('inf')
            price_ok = False
            if price and expected_price_usd > 0:
                price_delta = abs(price - expected_price_usd) / expected_price_usd
                price_ok = price_delta <= tolerance

            score = ((2 if dest_ok else 0) + (1 if stops_ok else 0) +
                     (1 if date_ok else 0) + (2 if price_ok else 0))
            candidates.append((score, price_delta, idx, card))
        except Exception:
            pass

    if not candidates:
        return cards.first, False

    candidates.sort(key=lambda x: (-x[0], x[1]))
    best_score, _, _, best_card = candidates[0]
    matched = best_score >= 3  # dest+price, or stops+price+date, etc.
    return best_card, matched


# ---------------------------------------------------------------------------
# Partner link quality scoring (A/B/C/D)
# ---------------------------------------------------------------------------
def score_partner_links(page_ctx, partner_links, expected_dest='', expected_price_usd=0):
    """
    Visit each partner link and assess booking quality using strict itinerary matching.

    Grade A: destination visible + price near expected + book CTA — confirmed same itinerary
    Grade B: destination visible + (price or CTA) — likely correct itinerary
    Grade C: generic booking signals (CTA or route words) but no destination confirmation
    Grade D: no meaningful booking signal or error

    Only A/B grades are used to confirm PARTNER_LINK_FOUND status.
    Returns partner_links list with 'grade' added.
    """
    if not partner_links:
        return []
    scored = []
    for link in partner_links[:2]:   # max 2 to keep runtime bounded
        href = link.get('href', '')
        if not href:
            scored.append({**link, 'grade': 'D'})
            continue
        pg = page_ctx.new_page()
        try:
            pg.goto(href, wait_until='domcontentloaded', timeout=20000)
            time.sleep(4)
            text = pg.inner_text('body')[:5000]
            text_lower = text.lower()

            # Destination name check — key itinerary identity signal
            dest_seen = bool(expected_dest and expected_dest.lower() in text_lower)

            # Price check — within 25% of expected per-person price
            found_price = parse_price_line(text[:3000])
            has_price = found_price is not None
            price_near = (has_price and expected_price_usd > 0
                          and abs(found_price - expected_price_usd) / expected_price_usd <= 0.25)

            cta_words = ['book now', 'buy now', 'checkout', 'confirm booking',
                         'continue to book', 'select fare', 'reserve']
            has_cta = any(w in text_lower for w in cta_words)
            route_words = ['departure', 'arrival', 'itinerary', 'outbound flight', 'passenger']
            has_route = any(w in text_lower for w in route_words)

            # Strict grading: destination presence is required for A/B
            if dest_seen and price_near and has_cta:
                grade = 'A'
            elif dest_seen and (has_cta or has_price):
                grade = 'B'
            elif has_cta or has_route:
                grade = 'C'
            else:
                grade = 'D'
            scored.append({**link, 'grade': grade})
        except Exception:
            scored.append({**link, 'grade': 'D'})
        finally:
            pg.close()
    # Append unscored links without opening new pages
    for link in partner_links[2:]:
        scored.append({**link, 'grade': '?'})
    return scored


# ---------------------------------------------------------------------------
# 4-state verification: MAP_ONLY → SEARCH_LOADED → BOOK_PANEL_VISIBLE → PARTNER_LINK_FOUND
# ---------------------------------------------------------------------------
def _extract_return_date(date_text, base_date_iso, fallback_days=14):
    """
    Try to extract a return date from a fare date-range string.

    Handles formats:
      - "Jul 4 – Jul 18"  → '2026-07-18'
      - "Jul 4 – 18"      → '2026-07-18'
      - "Jul 4"           → base_date_iso + fallback_days (synthetic)

    Adjusts year automatically when date range crosses Dec/Jan.
    """
    # "Month Day – Month Day"
    m = re.search(
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+'
        r'\s*[–\-]\s*'
        r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+)',
        date_text, re.I)
    if m:
        try:
            base_dt = datetime.strptime(base_date_iso, '%Y-%m-%d')
            ret_dt = datetime.strptime(f"{m.group(1)} {base_dt.year}", '%b %d %Y')
            if ret_dt < base_dt:
                ret_dt = ret_dt.replace(year=base_dt.year + 1)
            return ret_dt.strftime('%Y-%m-%d')
        except Exception:
            pass

    # "Month Day – Day" (same month)
    m2 = re.search(
        r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))\s+\d+\s*[–\-]\s*(\d+)',
        date_text, re.I)
    if m2:
        try:
            base_dt = datetime.strptime(base_date_iso, '%Y-%m-%d')
            ret_dt = datetime.strptime(f"{m2.group(1)} {m2.group(2)} {base_dt.year}",
                                       '%b %d %Y')
            if ret_dt < base_dt:
                ret_dt = ret_dt.replace(year=base_dt.year + 1)
            return ret_dt.strftime('%Y-%m-%d')
        except Exception:
            pass

    # Fallback: synthetic default
    try:
        base_dt = datetime.strptime(base_date_iso, '%Y-%m-%d')
        return (base_dt + timedelta(days=fallback_days)).strftime('%Y-%m-%d')
    except Exception:
        return None


def verify_exact_route(page, explore_url, dest_city, route_key,
                       expected_price_usd=0, expected_stops=-1,
                       expected_date_text='', origin_cid=None, dest_cid=None,
                       depart_date=None, return_date=None, cabin=3, proof_dir=None):
    """
    Navigate from Explore map → click dest → search page → booking panel.
    When BOOK_PANEL_VISIBLE: also runs partner link scoring and 2A+1C family check.
    return_date: actual return date if known; derived from expected_date_text range
    if parseable; falls back to depart_date+14 otherwise.
    Returns dict with status, evidence, partner grades, and family verification.
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

    # Click the result card that best matches dest + stops + date + price
    try:
        card, matched = find_matching_result_card(
            page, expected_price_usd,
            expected_dest=dest_city,
            expected_stops=expected_stops,
            expected_date_text=expected_date_text,
        )
        if card:
            if not matched:
                print(f"      [warn] no strong route match — skipping click to avoid false confirm")
            else:
                card.click(timeout=8000)
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
    # Don't auto-set PARTNER_LINK_FOUND yet — grade first; only A/B earns it

    # Partner link quality scoring — gates PARTNER_LINK_FOUND on A/B grade
    if partner_links:
        try:
            scored = score_partner_links(
                page.context, partner_links,
                expected_dest=dest_city,
                expected_price_usd=expected_price_usd,
            )
            result['partner_links'] = scored[:5]
            result['partner_grades'] = {
                s['href']: s['grade'] for s in scored if s.get('href')
            }
            grades = [s.get('grade', 'D') for s in scored[:2]]
            print(f"      Partner grades: {grades}")
            best = min(grades, key=lambda g: 'ABCD?'.index(g) if g in 'ABCD?' else 99,
                       default='D')
            if best in ('A', 'B'):
                result['status'] = 'PARTNER_LINK_FOUND'  # earned: same itinerary confirmed
            elif best == 'C' and result['status'] == 'SEARCH_LOADED':
                result['status'] = 'BOOK_PANEL_VISIBLE'  # C = booking page but not confirmed
        except Exception as _e:
            print(f"      Partner scoring error: {_e}")

    # Family booking verification (2A+1C) — full route context, actual child age
    if (result['status'] in ('BOOK_PANEL_VISIBLE', 'PARTNER_LINK_FOUND')
            and origin_cid and dest_cid and depart_date):
        try:
            # Use passed return_date if provided; otherwise parse from date range string
            # (e.g., "Jul 4 – Jul 18") or fall back to depart + 14 days
            _ret = (return_date
                    or _extract_return_date(expected_date_text, depart_date, fallback_days=14))
            ret_date = _ret or (
                (datetime.strptime(depart_date, '%Y-%m-%d') + timedelta(days=14))
                .strftime('%Y-%m-%d'))
            fam = verify_family_booking(
                page.context, origin_cid, dest_cid,
                depart_date, ret_date, cabin, expected_price_usd,
                expected_dest=dest_city,
                expected_stops=expected_stops,
                expected_date_text=expected_date_text,
            )
            result['family'] = fam
            print(f"      Family 2A+1C: {fam.get('family_booking_status')} "
                  f"price={fam.get('family_price_verified')} "
                  f"Δ={fam.get('family_reprice_delta_pct')}%")
        except Exception as _e:
            print(f"      Family verification error: {_e}")

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
    ghosts = load_ghost_fares()

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
            cities_to_scan[0]['city_id'], US_EXPLORE_ID,
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

                url = build_explore_url(city_id, US_EXPLORE_ID, date=departure_date, cabin=cabin)
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
                        debug_path = os.path.join(BASE_DIR, f'scanner_debug_{city_code}_{cabin}.txt')
                        with open(debug_path, 'w', encoding='utf-8') as df:
                            df.write(body_text)
                        print(f"  Debug text saved to {debug_path}")
                    else:
                        print(f"  Found {len(destinations)} destinations (currency: {page_currency}):")

                    for dest in destinations:
                        if is_excluded_dest(dest['city']):
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

                        family_price = estimate_family_price(price_usd)
                        _ghost_entry = ghosts.get(
                            fare_hash(city_code, dest['city'], cabin, dest['dates']))
                        # Support both old int format and new structured dict format
                        if isinstance(_ghost_entry, dict):
                            ghost_count = _ghost_entry.get('count', 0)
                        else:
                            ghost_count = _ghost_entry or 0

                        result_entry = {
                            'origin_city': city_key,
                            'origin_code': city_code,
                            'destination': dest['city'],
                            'cabin': cabin_label,
                            'cabin_num': cabin,
                            'price_usd': round(price_usd, 2),
                            'family_price_est': family_price,
                            'dates': dest['dates'],
                            'stops': dest['stops'],
                            'duration': dest['duration'],
                            'classification': classification,
                            'ratio': round(ratio, 3),
                            'ghost_failures': ghost_count,
                            'is_ghost': ghost_count >= 2,
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
                            # Skip known ghosts
                            if is_likely_ghost(ghosts, city_code, bf['city'], cabin, bf.get('dates','')):
                                print(f"      SKIP (ghost ×{ghosts.get(fare_hash(city_code, bf['city'], cabin, bf.get('dates','')),0)}): {bf['city']}")
                                continue

                            route_key = f"{city_code}_{bf['city'].replace(' ','_')}_{cabin_label}"
                            pp_price = float(bf.get('price_numeric', 0))
                            print(f"      Family est: ${estimate_family_price(pp_price)} (2A+1C)")

                            # Parse stop count for route-aware card matching
                            _s = bf.get('stops', '').lower()
                            if 'nonstop' in _s:
                                _bf_stops = 0
                            else:
                                _sm = re.search(r'(\d+)', _s)
                                _bf_stops = int(_sm.group(1)) if _sm else -1
                            verification = verify_exact_route(
                                page, url, bf['city'], route_key,
                                expected_price_usd=pp_price,
                                expected_stops=_bf_stops,
                                expected_date_text=bf.get('dates', ''),
                                origin_cid=city_id,
                                dest_cid=get_dest_freebase_id(bf['city']),
                                depart_date=departure_date,
                                cabin=cabin,
                                proof_dir=PROOF_DIR,
                            )
                            status = verification.get('status', 'unknown')
                            print(f"      {bf['city']}: {status}")

                            if status in ('BOOK_PANEL_VISIBLE', 'PARTNER_LINK_FOUND'):
                                print(f"      *** CONFIRMED BOOKABLE *** partners: {verification.get('partner_domains')}")
                            else:
                                # Record ghost failure with status + reason for smarter suppression
                                count = record_ghost_failure(
                                    ghosts, city_code, bf['city'], cabin, bf.get('dates', ''),
                                    status=status, reason=verification.get('reason', ''))
                                print(f"      Ghost failure #{count} ({status}) recorded")

                            # Update result entry
                            for entry in all_results['bug_fares']:
                                if (entry['destination'] == bf['city'] and
                                        entry['origin_code'] == city_code and
                                        entry['cabin_num'] == cabin):
                                    entry['verification'] = verification
                                    break

                    save_ghost_fares(ghosts)  # persist after each city scan

                except Exception as e:
                    print(f"  ERROR loading page: {e}")
                    try:
                        err_path = os.path.join(BASE_DIR, f'scanner_error_{city_code}_{cabin}.png')
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
            print(f"    {cf['origin_code']:>3} -> {cf['destination']:<20} | {cf['cabin']:<18} | "
                  f"${cf['price_usd']:>6,.0f} | {cf['dates']}")

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
