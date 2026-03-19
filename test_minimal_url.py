"""Test minimal TFS format (same as working scanner detail_urls)."""
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

def build_minimal_search_url(origin_cid, dest_cid, depart, ret_date):
    """Minimal TFS — matches working scanner format exactly."""
    origin_msg = _fv(1, 3) + _fb(2, origin_cid)
    dest_msg = _fv(1, 2) + _fb(2, dest_cid)
    leg1 = _fb(2, depart) + _fb(13, origin_msg) + _fb(14, dest_msg)
    leg2 = _fb(2, ret_date) + _fb(13, dest_msg) + _fb(14, origin_msg)
    msg = _fv(1, 27) + _fv(2, 2) + _fb(3, leg1) + _fb(3, leg2)
    tfs = base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')
    return f'https://www.google.com/travel/flights?tfs={tfs}&hl=en&gl=hk&curr=USD'

# Test 3 routes
TESTS = [
    ('Taipei', '/m/0ftkx', 'Phoenix', '/m/0dc_v', '2026-05-01', '2026-05-07'),
    ('Taipei', '/m/0ftkx', 'San Francisco', '/m/0d6lp', '2026-05-03', '2026-05-09'),
    ('Seoul', '/m/0hsqf', 'Los Angeles', '/m/030qb3t', '2026-09-11', '2026-09-17'),
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport={'width': 1400, 'height': 900},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
        locale='en-US',
    )

    for origin_name, ocid, dest_name, dcid, dep, ret in TESTS:
        url = build_minimal_search_url(ocid, dcid, dep, ret)
        print(f"\n{'='*60}")
        print(f"  {origin_name} → {dest_name} ({dep} to {ret})")
        print(f"  URL: {url[:100]}...")

        page = ctx.new_page()
        page.goto(url, timeout=30000)
        page.wait_for_load_state('domcontentloaded')
        try:
            btn = page.get_by_role('button', name='Reject all')
            if btn.count() > 0: btn.first.click(); time.sleep(2)
        except: pass
        time.sleep(10)

        title = page.title()
        text = page.inner_text('body')[:1000]
        print(f"  Title: {title}")

        # Check for flights
        has_search = 'departing flights' in text.lower() or 'results returned' in text.lower()
        has_explore = 'explore' in text.lower() and 'popular trips' in text.lower()
        price_match = re.search(r'from \$([0-9,]+)', text)
        print(f"  Is search page: {has_search}")
        print(f"  Is explore page: {has_explore}")
        if price_match:
            print(f"  Cheapest: ${price_match.group(1)}")

        # Count flight lis
        flight_count = 0
        for li in page.locator('li').all():
            try:
                t = li.inner_text(timeout=300)
                if re.search(r'\d{1,2}:\d{2}', t) and '$' in t and 30 < len(t) < 600:
                    flight_count += 1
            except: pass
        print(f"  Flight results: {flight_count}")

        safe_name = f"{origin_name}_{dest_name}".replace(' ', '_')
        page.screenshot(path=f'D:/claude/flights/test_min_{safe_name}.png')
        page.close()

    browser.close()
