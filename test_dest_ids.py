"""Test which US destination IDs work for Google Flights search."""
import sys, time, re, base64
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

def _varint(v):
    r = b''
    while v > 0x7f: r += bytes([(v & 0x7f) | 0x80]); v >>= 7
    r += bytes([v]); return r
def _fv(n, v): return _varint((n << 3) | 0) + _varint(v)
def _fb(n, d):
    if isinstance(d, str): d = d.encode('utf-8')
    return _varint((n << 3) | 2) + _varint(len(d)) + d

def build_url(ocid, dcid, dep, ret):
    o = _fv(1, 3) + _fb(2, ocid)
    d = _fv(1, 2) + _fb(2, dcid)
    l1 = _fb(2, dep) + _fb(13, o) + _fb(14, d)
    l2 = _fb(2, ret) + _fb(13, d) + _fb(14, o)
    msg = _fv(1, 27) + _fv(2, 2) + _fb(3, l1) + _fb(3, l2)
    tfs = base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')
    return f'https://www.google.com/travel/flights?tfs={tfs}&hl=en&gl=hk&curr=USD'

# Test all unique destinations from our fare list
US_DEST = {
    'Los Angeles': '/m/030qb3t', 'New York': '/m/02_286',
    'San Francisco': '/m/0d6lp', 'Seattle': '/m/0d9jr',
    'Phoenix': '/m/0dc_v', 'Las Vegas': '/m/0cv3w',
    'Houston': '/m/04lh6', 'Philadelphia': '/m/0k_q',
    'Portland': '/m/0fwwg', 'Salt Lake City': '/m/0f2nf',
    'Washington, D.C.': '/m/0rh6k', 'Baltimore': '/m/0k_p0',
    'Atlanta': '/m/013yq', 'Austin': '/m/0vzm',
    'Minneapolis': '/m/0fpzwf', 'Orlando': '/m/0fhp9',
    'Nashville': '/m/05jbn', 'San Diego': '/m/0d6lp',
    'Boston': '/m/01cx_', 'Denver': '/m/02cl1',
}

ORIGIN = '/m/0ftkx'  # Taipei
DEP = '2026-05-01'
RET = '2026-05-07'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport={'width': 1400, 'height': 900},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
        locale='en-US',
    )

    # Dismiss cookies on first page
    first = ctx.new_page()
    first.goto('https://www.google.com/travel/flights', timeout=20000)
    try:
        btn = first.get_by_role('button', name='Reject all')
        if btn.count() > 0: btn.first.click(); time.sleep(2)
    except: pass
    first.close()

    results = {}
    for dest_name, dcid in sorted(US_DEST.items()):
        url = build_url(ORIGIN, dcid, DEP, RET)
        page = ctx.new_page()
        try:
            page.goto(url, timeout=15000)
            page.wait_for_load_state('domcontentloaded')
            time.sleep(6)
            title = page.title()
            is_search = dest_name.split(',')[0].lower() in title.lower() or 'to' in title.lower()
            status = 'SEARCH' if is_search else 'EXPLORE'
            results[dest_name] = status
            print(f"  {dest_name:25s} {dcid:15s} → {status:8s} | {title[:60]}")
        except Exception as e:
            results[dest_name] = 'ERROR'
            print(f"  {dest_name:25s} {dcid:15s} → ERROR  | {str(e)[:60]}")
        finally:
            page.close()

    browser.close()

    print(f"\nSearch: {sum(1 for v in results.values() if v == 'SEARCH')}")
    print(f"Explore: {sum(1 for v in results.values() if v == 'EXPLORE')}")
    explore_dests = [k for k, v in results.items() if v == 'EXPLORE']
    if explore_dests:
        print(f"Explore destinations: {explore_dests}")
