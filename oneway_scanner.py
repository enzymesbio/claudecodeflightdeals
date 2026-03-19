"""
One-Way Outbound Scanner — Phase 1

Scans all origin cities to US using Google Flights Explore with one-way mode.
Finds cheapest one-way fares to identify the best outbound dates/origins.
Output saved to oneway_results.json for use by drill_promising.py.

Usage:
    python oneway_scanner.py                   # scan all origins, 3 date offsets
    python oneway_scanner.py --cities beijing,shanghai
    python oneway_scanner.py --date 2026-07-01
"""
import sys, os, argparse, base64, json, re, time
from datetime import datetime, timedelta, timezone

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
from money import parse_price_line
from entities import (
    ORIGINS, US_EXPLORE_ID, is_excluded_dest,
)

BASE_DIR = 'D:/claude/flights'
SHANGHAI_TZ = timezone(timedelta(hours=8))

# One-way budget: ≤ $700/pp (captures cheap/bug one-way fares; normal Economy OW is $600-900/pp)
ONEWAY_PP_BUDGET = 700
ONEWAY_FAMILY_BUDGET = int(ONEWAY_PP_BUDGET * 2.75)

RESULTS_FILE = os.path.join(BASE_DIR, 'oneway_results.json')

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

EXCLUDE_AIRLINES = ['ZIPAIR', 'Philippine Airlines', 'Malaysia Airlines', 'Cebu Pacific']

# ---------------------------------------------------------------------------
# Protobuf helpers
# ---------------------------------------------------------------------------
def _varint(v):
    r = b''
    while v > 0x7f: r += bytes([(v & 0x7f) | 0x80]); v >>= 7
    r += bytes([v]); return r

def _fv(n, v): return _varint((n << 3) | 0) + _varint(v)

def _fb(n, d):
    if isinstance(d, str): d = d.encode('utf-8')
    return _varint((n << 3) | 2) + _varint(len(d)) + d


def build_oneway_explore_tfs(origin_city_id, dest_city_id, date, cabin=1):
    """Build Explore TFS for one-way search (trip type 1 = one-way)."""
    origin_msg = _fv(1, 3) + _fb(2, origin_city_id)
    dest_msg   = _fv(1, 4) + _fb(2, dest_city_id)
    leg1 = _fb(2, date) + _fb(13, origin_msg) + _fb(14, dest_msg)

    pax_config = b'\x08\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01'
    field22 = _fv(3, 1) + _fv(4, 1)

    msg = (
        _fv(1, 28) +
        _fv(2, 1) +            # trip type 1 = one-way
        _fb(3, leg1) +
        _fv(8, 1) +
        _fv(9, cabin) +
        _fv(14, 2) +
        _fb(16, pax_config) +
        _fv(19, 1) +
        _fb(22, field22)
    )
    return base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')


def build_oneway_explore_url(origin_city_id, dest_city_id, date, cabin=1):
    tfs = build_oneway_explore_tfs(origin_city_id, dest_city_id, date, cabin)
    return (f'https://www.google.com/travel/explore'
            f'?tfs={tfs}&tfu=GgA&hl=en&gl=hk&curr=USD')


# ---------------------------------------------------------------------------
# Page parsing (same format as bug_fare_scanner.py)
# ---------------------------------------------------------------------------
def parse_explore_results(body_text):
    """Parse Explore page text. Uses money.parse_price_line() for all price extraction."""
    lines = [l.strip() for l in body_text.split('\n') if l.strip()]
    results = []
    date_re  = re.compile(r'^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+')
    stops_re = re.compile(r'^(\d+)\s+stops?$|^Nonstop$', re.I)
    dur_re   = re.compile(r'^\d+\s*hr')

    i = 0
    while i < len(lines):
        line = lines[i]
        if not line or len(line) > 60 or line.startswith('http') or 'Google' in line:
            i += 1; continue

        # City candidate: next lines have date, stops, duration, price
        if (i + 4 < len(lines)
                and date_re.match(lines[i + 1])
                and (stops_re.match(lines[i + 2]) or stops_re.match(lines[i + 3]))
                and dur_re.match(lines[i + 3] if stops_re.match(lines[i + 2]) else lines[i + 2])):

            city = line
            dates = lines[i + 1]
            j = i + 2
            stops_str = lines[j]; j += 1
            dur_str   = lines[j]; j += 1
            price_str = lines[j] if j < len(lines) else ''

            price_usd = parse_price_line(price_str)

            if not is_excluded_dest(city) and price_usd is not None:
                stops = 0 if 'nonstop' in stops_str.lower() else int(re.search(r'\d+', stops_str).group(0))
                results.append({
                    'destination': city,
                    'dates': dates,
                    'stops': stops,
                    'duration': dur_str,
                    'price_usd': round(price_usd),
                    'price_raw': price_str,
                })
            i = j + 1
        else:
            i += 1

    return results


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------
def scan_origin(page, city_key, city_info, date, cabin=1, cookies_dismissed=False):
    """Scan one origin city for one-way fares. Returns list of fare dicts."""
    origin_cid = city_info['city_id']
    origin_name = city_info['name']
    url = build_oneway_explore_url(origin_cid, US_EXPLORE_ID, date, cabin)

    try:
        page.goto(url, timeout=30000)
        page.wait_for_load_state('domcontentloaded')

        if not cookies_dismissed:
            try:
                btn = page.get_by_role('button', name='Reject all')
                if btn.count() > 0:
                    btn.first.click()
                    time.sleep(2)
            except: pass

        time.sleep(12)  # wait for Explore to render

        body = page.inner_text('body')
        fares = parse_explore_results(body)

        results = []
        for f in fares:
            if f['price_usd'] > ONEWAY_PP_BUDGET:
                continue
            family_price = round(f['price_usd'] * 2.75)
            results.append({
                'origin_city': origin_name,
                'origin_code': city_info['code'],
                'destination': f['destination'],
                'cabin': 'Economy',
                'cabin_num': cabin,
                'price_usd': f['price_usd'],
                'family_price': family_price,
                'dates': f['dates'],
                'stops': f['stops'],
                'duration': f['duration'],
                'scan_date': date,
                'type': 'oneway',
            })
        return results
    except Exception as e:
        print(f"  ERROR {origin_name}: {str(e)[:60]}")
        return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cities', help='Comma-separated city keys to scan')
    parser.add_argument('--date', help='Single departure date YYYY-MM-DD')
    args = parser.parse_args()

    if args.cities:
        city_keys = [c.strip().lower() for c in args.cities.split(',')]
        cities = {k: v for k, v in ORIGIN_CITIES.items() if k in city_keys}
    else:
        cities = ORIGIN_CITIES

    # Scan 3 date windows: ~90, ~120, ~150 days out
    if args.date:
        scan_dates = [args.date]
    else:
        base = datetime.now()
        scan_dates = [
            (base + timedelta(days=90)).strftime('%Y-%m-%d'),
            (base + timedelta(days=120)).strftime('%Y-%m-%d'),
            (base + timedelta(days=150)).strftime('%Y-%m-%d'),
        ]

    print('=' * 65)
    print(f"  ONE-WAY SCANNER — {len(cities)} origins × {len(scan_dates)} dates")
    print(f"  Budget: ≤${ONEWAY_PP_BUDGET}/pp (family ${ONEWAY_FAMILY_BUDGET})")
    print(f"  Time: {datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d %H:%M Shanghai')}")
    print(f"  Dates: {', '.join(scan_dates)}")
    print('=' * 65)

    all_fares = []
    cookies_dismissed = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1400, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
            locale='en-US',
        )
        page = context.new_page()

        for date in scan_dates:
            print(f"\n--- Date window: {date} ---")
            for city_key, city_info in cities.items():
                fares = scan_origin(page, city_key, city_info, date,
                                    cabin=1, cookies_dismissed=cookies_dismissed)
                cookies_dismissed = True  # only dismiss once per browser session
                all_fares.extend(fares)
                count = len(fares)
                if count:
                    best = min(fares, key=lambda x: x['price_usd'])
                    print(f"  {city_info['name']:18s} → {count:2d} fares  "
                          f"(best: ${best['price_usd']}/pp → {best['destination']})")
                else:
                    print(f"  {city_info['name']:18s} → 0 fares")
                time.sleep(2)

        page.close()
        browser.close()

    # De-duplicate: keep cheapest per (origin, destination, dates)
    seen = {}
    for f in all_fares:
        key = (f['origin_city'], f['destination'])
        if key not in seen or f['price_usd'] < seen[key]['price_usd']:
            seen[key] = f
    deduped = sorted(seen.values(), key=lambda x: x['price_usd'])

    output = {
        'scan_time': datetime.now(SHANGHAI_TZ).isoformat(),
        'budget_pp': ONEWAY_PP_BUDGET,
        'budget_family': ONEWAY_FAMILY_BUDGET,
        'total_fares': len(deduped),
        'scan_dates': scan_dates,
        'fares': deduped,
    }
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f'\n{"=" * 65}')
    print(f'  TOTAL ONE-WAY FARES FOUND: {len(deduped)}')
    print(f'{"=" * 65}')
    for f in deduped[:30]:
        fam = f['family_price']
        print(f"  {f['origin_city']:15s} → {f['destination']:20s} | "
              f"${f['price_usd']:>4}/pp (${fam} fam) | {f['dates']}")
    if len(deduped) > 30:
        print(f"  ... and {len(deduped)-30} more")
    print(f"\nSaved: {RESULTS_FILE}")


if __name__ == '__main__':
    main()
