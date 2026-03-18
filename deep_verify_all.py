"""Deep verify all fares under $2000 family — parallel with Playwright native clicks."""
import sys, os, json, time, re, base64, asyncio
from datetime import datetime, timedelta, timezone

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.async_api import async_playwright

BASE_DIR = 'D:/claude/flights'
SHANGHAI_TZ = timezone(timedelta(hours=8))
EXCLUDE_AIRLINES = ['ZIPAIR', 'Philippine Airlines', 'Malaysia Airlines', 'Cebu Pacific']
EXCLUDE_DESTS = ['Honolulu', 'Kauai', '1.5h drive from Washington', '1h drive from Miami', '1h drive from Washington']
FAMILY_BUDGET = 2000
PP_BUDGET = FAMILY_BUDGET / 2.75
MAX_WORKERS = 5

# --- Protobuf ---
def _varint(v):
    r = b''
    while v > 0x7f: r += bytes([(v & 0x7f) | 0x80]); v >>= 7
    r += bytes([v]); return r
def _fv(n, v): return _varint((n << 3) | 0) + _varint(v)
def _fb(n, d):
    if isinstance(d, str): d = d.encode('utf-8')
    return _varint((n << 3) | 2) + _varint(len(d)) + d

ORIGINS = {
    'Jakarta': '/m/044rv', 'Kuala Lumpur': '/m/049d1', 'Bangkok': '/m/0fn2g',
    'Singapore': '/m/06t2t', 'Manila': '/m/0195pd', 'Ho Chi Minh City': '/m/0hn4h',
    'Hong Kong': '/m/03h64', 'Seoul': '/m/0hsqf', 'Tokyo': '/m/07dfk',
    'Taipei': '/m/0ftkx', 'Shanghai': '/m/06wjf', 'Hangzhou': '/m/014vm4',
    'Ningbo': '/m/01l33l', 'Beijing': '/m/01914', 'Guangzhou': '/m/0393g',
    'Chengdu': '/m/016v46', 'Chongqing': '/m/017236', 'Shenzhen': '/m/0lbmv',
    'Nanjing': '/m/05gqy', 'Qingdao': '/m/01l3s0', 'Dalian': '/m/01l3k6', 'Wuhan': '/m/0l3cy',
}
US_DEST = {
    'Los Angeles': '/m/030qb3t', 'Houston': '/m/03l2n', 'New York': '/m/02_286',
    'San Francisco': '/m/0d6lp', 'Chicago': '/m/01_d4', 'Washington, D.C.': '/m/0rh6k',
    'Denver': '/m/02cl1', 'Las Vegas': '/m/0cv3w', 'Seattle': '/m/0d9jr',
    'Boston': '/m/01cx_', 'Atlanta': '/m/013yq',
    'Austin': '/m/0vzm', 'Nashville': '/m/05jbn', 'Minneapolis': '/m/0fpzwf',
    'Dallas': '/m/0f2rq',
    # IDs found via Google Flights autocomplete (v2):
    'Phoenix': '/m/0d35y', 'Baltimore': '/m/094jv', 'Philadelphia': '/m/0dclg',
    'Portland': '/m/02frhbc', 'Salt Lake City': '/m/0f2r6', 'San Diego': '/m/071vr',
    'Orlando': '/m/0ply0', 'Savannah': '/m/0lhn5',
}
US_CITY_ID = '/m/09c7w0'

def build_search_url(origin_cid, dest_cid, depart, ret_date):
    o = _fv(1, 3) + _fb(2, origin_cid)
    d = _fv(1, 2) + _fb(2, dest_cid)
    l1 = _fb(2, depart) + _fb(13, o) + _fb(14, d)
    l2 = _fb(2, ret_date) + _fb(13, d) + _fb(14, o)
    # Minimal TFS — matches working scanner format (no extra fields)
    msg = _fv(1, 27) + _fv(2, 2) + _fb(3, l1) + _fb(3, l2)
    tfs = base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')
    return f'https://www.google.com/travel/flights?tfs={tfs}&hl=en&gl=hk&curr=USD'

def parse_dates(s):
    if not s: return None, None
    s = s.replace('\u2009', ' ').replace('\u200a', ' ')
    parts = s.replace('\u2013', '-').replace('\u2014', '-').replace('–', '-').split('-')
    if len(parts) != 2: return None, None
    months = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
    try:
        sp = parts[0].strip().split(); sm, sd = months[sp[0]], int(sp[1])
        ep = parts[1].strip().split()
        if len(ep) == 1: em, ed = sm, int(ep[0])
        else: em, ed = months[ep[0]], int(ep[1])
        return f'2026-{sm:02d}-{sd:02d}', f'2026-{em:02d}-{ed:02d}'
    except: return None, None


async def find_flight_li(page):
    """Find first flight li element using Playwright locator (native click compatible)."""
    lis = page.locator('li')
    count = await lis.count()
    for i in range(count):
        try:
            li = lis.nth(i)
            text = await li.inner_text(timeout=500)
            if re.search(r'\d{1,2}:\d{2}', text) and '$' in text and 30 < len(text) < 600:
                return li, text[:120]
        except:
            pass
    return None, None


async def verify_one(context, fare, idx, total, sem):
    """Verify a single fare with Playwright native clicks."""
    async with sem:
        origin = fare['origin_city']
        dest = fare['destination']
        price = fare['price_usd']
        cabin = fare.get('cabin', 'Economy')
        cabin_num = fare.get('cabin_num', 1)
        dates_raw = fare.get('dates', '').replace('\u2009', ' ').replace('\u2013', '-')
        tag = f"[{idx+1}/{total}]"

        result = {
            'origin': origin, 'city': dest, 'cabin': cabin,
            'explore_price': price, 'dates': dates_raw,
            'route': f"{origin} → {dest}",
            'status': 'UNKNOWN', 'booking_url': None, 'search_url': None,
            'airline': None, 'price': None, 'has_booking_page': False,
        }

        # Build search URL
        detail_url = fare.get('verification', {}).get('detail_url', '')
        if not detail_url or detail_url == 'none':
            depart, ret = parse_dates(dates_raw)
            ocid = ORIGINS.get(origin, '')
            dcid = US_DEST.get(dest, '')
            if not depart or not ret or not ocid:
                result['status'] = 'NO_URL'
                return result
            if not dcid: dcid = US_CITY_ID
            detail_url = build_search_url(ocid, dcid, depart, ret)
        result['search_url'] = detail_url

        page = await context.new_page()
        try:
            # Step 1: Load search
            await page.goto(detail_url, timeout=30000)
            await page.wait_for_load_state('domcontentloaded')
            # Dismiss cookies
            try:
                btn = page.get_by_role('button', name='Reject all')
                if await btn.count() > 0:
                    await btn.first.click()
                    await asyncio.sleep(2)
            except: pass
            # Wait for flight results to render (critical)
            await asyncio.sleep(12)

            # Get cheapest price
            text = await page.inner_text('body')
            text = text[:3000]
            m = re.search(r'from \$([0-9,]+)', text)
            if m: result['price'] = int(m.group(1).replace(',', ''))

            # Step 2: Click Cheapest tab
            try:
                tab = page.get_by_role('tab', name=re.compile(r'Cheapest'))
                if await tab.count() > 0:
                    await tab.first.click()
                    await asyncio.sleep(3)
            except: pass

            # Step 3: Click first departing flight (NATIVE CLICK)
            li, ftext = await find_flight_li(page)
            if not li:
                # Retry after more wait
                await asyncio.sleep(8)
                li, ftext = await find_flight_li(page)
            if not li:
                result['status'] = 'NO_FLIGHTS'
                result['booking_url'] = detail_url
                # Still try to get price from text
                txt = (await page.inner_text('body'))[:2000]
                m = re.search(r'from \$([0-9,]+)', txt)
                if m: result['price'] = int(m.group(1).replace(',', ''))
                print(f"  {tag} NO_FLIGHTS {origin}→{dest} (price: ${result.get('price','?')})")
                return result

            await li.click(timeout=5000)
            await asyncio.sleep(5)

            # Check URL — should have changed to /flights/search with return flights
            url2 = page.url
            if '/search' not in url2 and '/booking' not in url2:
                # Click didn't navigate, try once more
                await asyncio.sleep(3)
                url2 = page.url

            if '/booking' in url2:
                # Direct to booking (one-stop or some flows)
                result['booking_url'] = url2
                result['has_booking_page'] = True
                body2 = (await page.inner_text('body'))[:3000]
                bw = re.search(r'Book with\s+(.+?)(?:\n|Airline|$)', body2)
                if bw: result['airline'] = bw.group(1).strip()
                result['status'] = 'BOOKABLE' if 'Book with' in body2 else 'BOOKING_PAGE'
                if "can't find booking" in body2.lower(): result['status'] = 'GHOST'
                print(f"  {tag} BOOKABLE {origin}→{dest} ${result.get('price','?')} {result.get('airline','?')}")
                return result

            # Step 4: Click first return flight (NATIVE CLICK)
            await asyncio.sleep(2)
            li2, ftext2 = await find_flight_li(page)
            if li2:
                await li2.click(timeout=5000)
                await asyncio.sleep(5)

                url3 = page.url
                if '/booking' in url3:
                    result['booking_url'] = url3
                    result['has_booking_page'] = True
                    body3 = (await page.inner_text('body'))[:3000]
                    bw = re.search(r'Book with\s+(.+?)(?:\n|Airline|$)', body3)
                    if bw: result['airline'] = bw.group(1).strip()
                    bp = re.search(r'\$([0-9,]+)', body3)
                    if bp: result['price'] = int(bp.group(1).replace(',', ''))
                    result['status'] = 'BOOKABLE' if 'Book with' in body3 else 'BOOKING_PAGE'
                    if "can't find booking" in body3.lower(): result['status'] = 'GHOST'
                    print(f"  {tag} BOOKABLE {origin}→{dest} ${result.get('price','?')} {result.get('airline','?')}")
                    return result

            # Fallback: search confirmed
            result['status'] = 'SEARCH_CONFIRMED'
            result['booking_url'] = detail_url
            # Try to extract airline from page
            page_text = (await page.inner_text('body'))[:2000]
            for pat in [r'United\b', r'STARLUX', r'EVA Air', r'Cathay Pacific', r'Air Canada',
                        r'Korean Air', r'Asiana', r'ANA\b', r'Delta', r'American',
                        r'China Airlines', r'Singapore Airlines', r'China Eastern',
                        r'China Southern', r'Air China', r'Hainan', r'Thai',
                        r'Japan Airlines', r'Scoot', r'Jetstar', r'VietJet', r'Peach']:
                if re.search(pat, page_text):
                    result['airline'] = re.search(pat, page_text).group(0)
                    break
            print(f"  {tag} SEARCH {origin}→{dest} ${result.get('price','?')} {result.get('airline','?')}")

        except Exception as e:
            result['status'] = 'ERROR'
            result['booking_url'] = detail_url
            print(f"  {tag} ERROR {origin}→{dest}: {str(e)[:60]}")
        finally:
            await page.close()

        return result


async def main():
    with open(os.path.join(BASE_DIR, 'scanner_results.json'), encoding='utf-8') as f:
        data = json.load(f)

    fares = [d for d in data['destinations']
             if d['price_usd'] <= PP_BUDGET
             and d['destination'] not in EXCLUDE_DESTS
             and d['origin_city'] != 'Jakarta']
    fares.sort(key=lambda x: x['price_usd'])

    print('=' * 65)
    print(f"  DEEP VERIFY ALL — {MAX_WORKERS} workers, Playwright native clicks")
    print(f"  Time: {datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d %H:%M Shanghai')}")
    print(f"  Fares: {len(fares)} | Budget: ${FAMILY_BUDGET} family (${PP_BUDGET:.0f}/pp)")
    print('=' * 65)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1400, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
            locale='en-US',
        )

        sem = asyncio.Semaphore(MAX_WORKERS)
        tasks = [verify_one(context, f, i, len(fares), sem) for i, f in enumerate(fares)]
        results = await asyncio.gather(*tasks)

        await browser.close()

    results = [r for r in results if r]

    # Save
    output = {
        'verification_time': datetime.now(SHANGHAI_TZ).isoformat(),
        'budget': f'${FAMILY_BUDGET} family (${PP_BUDGET:.0f}/pp)',
        'total_verified': len(results),
        'excluded_airlines': EXCLUDE_AIRLINES,
        'results': results,
    }
    path = os.path.join(BASE_DIR, 'deep_verify_all_results.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Summary
    bookable = [r for r in results if r.get('has_booking_page')]
    confirmed = [r for r in results if r['status'] == 'SEARCH_CONFIRMED']
    ghosts = [r for r in results if r['status'] == 'GHOST']
    errors = [r for r in results if r['status'] in ('ERROR', 'NO_URL', 'NO_FLIGHTS')]
    print(f'\n{"=" * 65}')
    print(f'  BOOKING PAGES: {len(bookable)} | SEARCH: {len(confirmed)} | GHOST: {len(ghosts)} | ERR: {len(errors)}')
    print(f'{"=" * 65}')
    for r in sorted(results, key=lambda x: x.get('explore_price', 9999)):
        airline = (r.get('airline') or '?')[:18]
        p = r.get('price') or r.get('explore_price', 0)
        bk = 'BOOKING' if r.get('has_booking_page') else r['status'][:10]
        print(f"  {r['origin']:15s} → {r['city']:20s} | ${p:<6} | {airline:18s} | {bk}")
    print(f"\nSaved: {path}")


if __name__ == '__main__':
    asyncio.run(main())
