"""Test if a constructed URL works with sync Playwright."""
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

# Construct: Taipei -> Phoenix, May 1-7, Economy
o = _fv(1, 3) + _fb(2, '/m/0ftkx')
d = _fv(1, 2) + _fb(2, '/m/0dc_v')  # type 2 for search
l1 = _fb(2, '2026-05-01') + _fb(13, o) + _fb(14, d)
l2 = _fb(2, '2026-05-07') + _fb(13, d) + _fb(14, o)
px = b'\x08\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01'
f22 = _fv(3, 1) + _fv(4, 1)
msg = (_fv(1, 27) + _fv(2, 2) + _fb(3, l1) + _fb(3, l2) +
       _fv(8, 1) + _fv(9, 1) + _fv(14, 2) + _fb(16, px) + _fv(19, 1) + _fb(22, f22))
tfs = base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')
url = f'https://www.google.com/travel/flights?tfs={tfs}&tfu=GgA&hl=en&gl=hk&curr=USD'
print(f"URL: {url[:100]}...")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={'width': 1400, 'height': 900},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
        locale='en-US')
    page = ctx.new_page()
    page.goto(url, timeout=30000)
    page.wait_for_load_state('domcontentloaded')
    try:
        btn = page.get_by_role('button', name='Reject all')
        if btn.count() > 0: btn.first.click(); time.sleep(2)
    except: pass
    time.sleep(10)

    text = page.inner_text('body')[:2000]
    page.screenshot(path='D:/claude/flights/test_constructed_url.png')
    print(f"Page title: {page.title()}")
    print(f"Body (first 300): {text[:300]}")

    # Find flight lis
    lis = page.locator('li').all()
    flight_count = 0
    for li in lis:
        try:
            t = li.inner_text(timeout=500)
            if re.search(r'\d{1,2}:\d{2}', t) and '$' in t and len(t) > 30:
                flight_count += 1
                if flight_count <= 3:
                    print(f"  Flight li #{flight_count}: {t[:80]}")
        except: pass
    print(f"Total flight lis: {flight_count}")

    if flight_count > 0:
        print("\nAttempting click-through...")
        # Click cheapest tab
        try:
            tab = page.get_by_role('tab', name=re.compile(r'Cheapest'))
            if tab.count() > 0: tab.first.click(); time.sleep(3)
        except: pass

        # Click first flight
        for li in lis:
            try:
                t = li.inner_text(timeout=500)
                if re.search(r'\d{1,2}:\d{2}', t) and '$' in t and 30 < len(t) < 600:
                    print(f"  Clicking: {t[:60]}")
                    li.click(timeout=5000)
                    time.sleep(5)
                    print(f"  URL after depart: {page.url[:100]}")
                    break
            except: pass

        # Click return
        for li in page.locator('li').all():
            try:
                t = li.inner_text(timeout=500)
                if re.search(r'\d{1,2}:\d{2}', t) and '$' in t and 30 < len(t) < 600:
                    print(f"  Clicking return: {t[:60]}")
                    li.click(timeout=5000)
                    time.sleep(5)
                    print(f"  URL after return: {page.url[:120]}")
                    print(f"  Is booking: {'/booking' in page.url}")
                    if '/booking' in page.url:
                        bt = page.inner_text('body')[:1000]
                        bw = re.search(r'Book with\s+(.+?)(?:\n|Airline|$)', bt)
                        if bw: print(f"  Airline: {bw.group(1).strip()}")
                        page.screenshot(path='D:/claude/flights/test_constructed_booking.png')
                    break
            except: pass

    browser.close()
