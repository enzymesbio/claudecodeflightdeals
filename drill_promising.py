"""
Drill Promising Fares — Phase 2

For each promising one-way fare from oneway_results.json, tests:
  a) Round-trip duration variants: 7, 10, 14, 21, 28 days
  b) Open-jaw return to Shanghai (when origin ≠ Shanghai)
  c) Stopover nights (3+ nights) in hub city (ICN/NRT/HKG) for supported airlines

Usage:
    python drill_promising.py                    # drill top 20 from oneway_results.json
    python drill_promising.py --top 30           # drill top 30
    python drill_promising.py --origin beijing   # drill only Beijing fares
"""
import sys, os, json, re, base64, asyncio, argparse
from datetime import datetime, timedelta, timezone

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.async_api import async_playwright

BASE_DIR = 'D:/claude/flights'
SHANGHAI_TZ = timezone(timedelta(hours=8))
MAX_WORKERS = 3   # conservative to avoid blocks

RESULTS_FILE = os.path.join(BASE_DIR, 'drill_results.json')
ONEWAY_FILE  = os.path.join(BASE_DIR, 'oneway_results.json')

# Duration variants to test (days)
DURATION_VARIANTS = [7, 10, 14, 21, 28]

# Minimum stopover nights to test (and maximum)
STOPOVER_MIN_NIGHTS = 3
STOPOVER_MAX_NIGHTS = 5

# Shanghai Freebase ID (for open-jaw return)
SHANGHAI_CID = '/m/06wjf'

# Hub cities for stopover testing
HUB_CITIES = {
    'Seoul':       '/m/0hsqf',   # ICN — Korean Air, Asiana, Chinese airlines
    'Tokyo':       '/m/07dfk',   # NRT/HND — ANA, JAL
    'Hong Kong':   '/m/03h64',   # HKG — SIA, Cathay
}

# Airlines that commonly route through hubs and allow stopovers
STOPOVER_AIRLINES = [
    'Korean Air', 'Asiana', 'ANA', 'All Nippon', 'Japan Airlines', 'JAL',
    'Singapore Airlines', 'Air China', 'China Eastern', 'China Southern',
    'Hainan', 'Sichuan', 'Xiamen Air', 'Shenzhen Airlines', 'Cathay',
]

# US city Freebase IDs (needed for stopover leg builds)
US_DEST = {
    'Los Angeles': '/m/030qb3t', 'Houston': '/m/03l2n', 'New York': '/m/02_286',
    'San Francisco': '/m/0d6lp', 'Chicago': '/m/01_d4', 'Washington, D.C.': '/m/0rh6k',
    'Denver': '/m/02cl1', 'Las Vegas': '/m/0cv3w', 'Seattle': '/m/0d9jr',
    'Boston': '/m/01cx_', 'Atlanta': '/m/013yq',
    'Austin': '/m/0vzm', 'Nashville': '/m/05jbn', 'Minneapolis': '/m/0fpzwf',
    'Dallas': '/m/0f2rq',
    'Phoenix': '/m/0d35y', 'Baltimore': '/m/094jv', 'Philadelphia': '/m/0dclg',
    'Portland': '/m/02frhbc', 'Salt Lake City': '/m/0f2r6', 'San Diego': '/m/071vr',
    'Orlando': '/m/0ply0', 'Savannah': '/m/0lhn5',
}
US_CITY_ID = '/m/09c7w0'

ORIGINS = {
    'Jakarta': '/m/044rv', 'Kuala Lumpur': '/m/049d1', 'Bangkok': '/m/0fn2g',
    'Singapore': '/m/06t2t', 'Manila': '/m/0195pd', 'Ho Chi Minh City': '/m/0hn4h',
    'Hong Kong': '/m/03h64', 'Seoul': '/m/0hsqf', 'Tokyo': '/m/07dfk',
    'Shanghai': '/m/06wjf', 'Hangzhou': '/m/014vm4',
    'Ningbo': '/m/01l33l', 'Beijing': '/m/01914', 'Guangzhou': '/m/0393g',
    'Chengdu': '/m/016v46', 'Chongqing': '/m/017236', 'Shenzhen': '/m/0lbmv',
    'Nanjing': '/m/05gqy', 'Qingdao': '/m/01l3s0', 'Dalian': '/m/01l3k6', 'Wuhan': '/m/0l3cy',
    'Xiamen': '/m/0126c3', 'Tianjin': '/m/0df4y', 'Fuzhou': '/m/01jzm9',
}

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


def build_rt_url(origin_cid, dest_cid, depart, ret_date, return_to_cid=None):
    """Build round-trip Google Flights search URL. return_to_cid enables open-jaw."""
    o = _fv(1, 3) + _fb(2, origin_cid)
    d = _fv(1, 2) + _fb(2, dest_cid)
    ret_home = _fv(1, 3) + _fb(2, return_to_cid) if return_to_cid else o
    l1 = _fb(2, depart) + _fb(13, o) + _fb(14, d)
    l2 = _fb(2, ret_date) + _fb(13, d) + _fb(14, ret_home)
    msg = _fv(1, 27) + _fv(2, 2) + _fb(3, l1) + _fb(3, l2)
    tfs = base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')
    return f'https://www.google.com/travel/flights?tfs={tfs}&hl=en&gl=hk&curr=USD'


def build_oneway_url(origin_cid, dest_cid, depart):
    """Build one-way Google Flights search URL."""
    o = _fv(1, 3) + _fb(2, origin_cid)
    d = _fv(1, 2) + _fb(2, dest_cid)
    l1 = _fb(2, depart) + _fb(13, o) + _fb(14, d)
    msg = _fv(1, 27) + _fv(2, 1) + _fb(3, l1)
    tfs = base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')
    return f'https://www.google.com/travel/flights?tfs={tfs}&hl=en&gl=hk&curr=USD'


# ---------------------------------------------------------------------------
# Price extraction
# ---------------------------------------------------------------------------
async def get_price_from_url(context, url, label=''):
    """Load a search URL and extract the 'from $X' price. Returns int or None."""
    page = await context.new_page()
    try:
        await page.goto(url, timeout=30000)
        await page.wait_for_load_state('domcontentloaded')
        await asyncio.sleep(10)
        text = (await page.inner_text('body'))[:4000]
        m = re.search(r'from \$([0-9,]+)', text)
        if m:
            return int(m.group(1).replace(',', ''))
        # Fallback: first $ amount in results area
        m2 = re.search(r'\$([0-9,]{3,})', text)
        if m2:
            return int(m2.group(1).replace(',', ''))
        return None
    except Exception as e:
        return None
    finally:
        await page.close()


# ---------------------------------------------------------------------------
# Drill single fare
# ---------------------------------------------------------------------------
async def drill_fare(context, fare, idx, total, sem):
    async with sem:
        origin = fare['origin_city']
        dest   = fare['destination']
        depart = fare.get('depart_date') or fare.get('scan_date', '')
        pp_price = fare['price_usd']
        tag = f"[{idx+1}/{total}]"

        if not depart:
            print(f"  {tag} SKIP {origin}→{dest}: no depart date")
            return None

        origin_cid = ORIGINS.get(origin)
        dest_cid   = US_DEST.get(dest, US_CITY_ID)
        if not origin_cid:
            print(f"  {tag} SKIP {origin}→{dest}: unknown origin ID")
            return None

        print(f"  {tag} Drilling {origin}→{dest} depart={depart} (${pp_price}/pp)")

        result = {
            'origin': origin,
            'dest': dest,
            'depart': depart,
            'oneway_price': pp_price,
            'airline': fare.get('airline', ''),
            'duration_results': {},
            'valid_duration_min': None,
            'valid_duration_max': None,
            'open_jaw_price': None,
            'open_jaw_url': None,
            'stopover': {},
        }

        dt = datetime.strptime(depart, '%Y-%m-%d')

        # --- 5a: Duration variants ---
        dur_tasks = {}
        for days in DURATION_VARIANTS:
            ret_date = (dt + timedelta(days=days)).strftime('%Y-%m-%d')
            url = build_rt_url(origin_cid, dest_cid, depart, ret_date)
            price = await get_price_from_url(context, url, f'{days}d')
            if price:
                result['duration_results'][f'{days}d'] = price
                dur_tasks[days] = price
                print(f"      {days}d: ${price}/pp")
            await asyncio.sleep(1)

        # Find valid duration window (prices within 20% of cheapest)
        if dur_tasks:
            min_price = min(dur_tasks.values())
            valid = [d for d, p in sorted(dur_tasks.items()) if p <= min_price * 1.20]
            if valid:
                result['valid_duration_min'] = min(valid)
                result['valid_duration_max'] = max(valid)

        # --- 5b: Open-jaw return to Shanghai ---
        if origin != 'Shanghai':
            ret_date_14 = (dt + timedelta(days=14)).strftime('%Y-%m-%d')
            oj_url = build_rt_url(origin_cid, dest_cid, depart, ret_date_14,
                                  return_to_cid=SHANGHAI_CID)
            oj_price = await get_price_from_url(context, oj_url, 'openjaw')
            if oj_price:
                result['open_jaw_price'] = oj_price
                result['open_jaw_url'] = oj_url
                print(f"      open-jaw→Shanghai: ${oj_price}/pp")
            await asyncio.sleep(1)

        # --- 5c: Stopover testing ---
        airline = fare.get('airline', '')
        should_test_stopover = any(a.lower() in airline.lower() for a in STOPOVER_AIRLINES)

        if should_test_stopover or not airline:
            # Determine hub based on origin geography
            origin_hub = None
            chinese_cities = {'Shanghai', 'Beijing', 'Guangzhou', 'Chengdu', 'Chongqing',
                               'Shenzhen', 'Nanjing', 'Hangzhou', 'Ningbo', 'Qingdao',
                               'Dalian', 'Wuhan', 'Xiamen', 'Tianjin', 'Fuzhou'}
            if origin in chinese_cities:
                # Chinese cities most commonly route through Seoul or Tokyo
                origin_hub = 'Seoul'  # test ICN first (Korean Air, Asiana common)
            elif origin in ('Seoul',):
                origin_hub = 'Seoul'
            elif origin in ('Tokyo',):
                origin_hub = 'Tokyo'
            elif origin in ('Hong Kong', 'Singapore', 'Bangkok', 'Manila',
                            'Kuala Lumpur', 'Ho Chi Minh City', 'Jakarta'):
                origin_hub = 'Hong Kong'

            if origin_hub and origin != origin_hub:
                hub_cid = HUB_CITIES[origin_hub]
                stopover_results = {}

                for nights in range(STOPOVER_MIN_NIGHTS, STOPOVER_MAX_NIGHTS + 1):
                    hub_depart = (dt + timedelta(days=nights)).strftime('%Y-%m-%d')
                    ret_date_stop = (dt + timedelta(days=nights + 14)).strftime('%Y-%m-%d')

                    # Leg 1: Origin → Hub (one-way)
                    p1 = await get_price_from_url(
                        context,
                        build_oneway_url(origin_cid, hub_cid, depart),
                        f'stop-leg1'
                    )
                    await asyncio.sleep(1)

                    # Leg 2: Hub → US (one-way, depart after stopover nights)
                    p2 = await get_price_from_url(
                        context,
                        build_oneway_url(hub_cid, dest_cid, hub_depart),
                        f'stop-leg2'
                    )
                    await asyncio.sleep(1)

                    if p1 and p2:
                        total_pp = p1 + p2
                        stopover_results[f'{nights}n'] = {
                            'hub': origin_hub,
                            'leg1_price': p1,
                            'leg2_price': p2,
                            'total_outbound_pp': total_pp,
                        }
                        print(f"      stopover {origin_hub} {nights}n: "
                              f"leg1=${p1} + leg2=${p2} = ${total_pp}/pp outbound")
                    else:
                        break  # if can't get price, stop testing more nights

                if stopover_results:
                    result['stopover'] = stopover_results

        return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--top', type=int, default=20, help='Drill top N fares')
    parser.add_argument('--origin', help='Filter by origin city name (partial match)')
    args = parser.parse_args()

    if not os.path.exists(ONEWAY_FILE):
        print(f"ERROR: {ONEWAY_FILE} not found. Run oneway_scanner.py first.")
        return

    with open(ONEWAY_FILE, encoding='utf-8') as f:
        data = json.load(f)

    fares = data['fares']

    if args.origin:
        fares = [f for f in fares if args.origin.lower() in f['origin_city'].lower()]

    fares = fares[:args.top]

    # Parse depart date from 'dates' field if 'depart_date' not set
    months = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,
              'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
    for f in fares:
        if not f.get('depart_date') and f.get('dates'):
            dates = f['dates'].replace('\u2009', ' ').replace('\u2013', '-')
            parts = re.split(r'[-–]', dates)
            try:
                sp = parts[0].strip().split()
                f['depart_date'] = f"2026-{months[sp[0]]:02d}-{int(sp[1]):02d}"
            except:
                f['depart_date'] = f.get('scan_date', '')

    print('=' * 65)
    print(f"  DRILL PROMISING FARES — {len(fares)} fares, {MAX_WORKERS} workers")
    print(f"  Durations: {DURATION_VARIANTS} days")
    print(f"  Stopover min nights: {STOPOVER_MIN_NIGHTS}")
    print(f"  Time: {datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d %H:%M Shanghai')}")
    print('=' * 65)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1400, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
            locale='en-US',
        )

        sem = asyncio.Semaphore(MAX_WORKERS)
        tasks = [drill_fare(context, f, i, len(fares), sem)
                 for i, f in enumerate(fares)]
        results = await asyncio.gather(*tasks)

        await browser.close()

    results = [r for r in results if r]

    output = {
        'drill_time': datetime.now(SHANGHAI_TZ).isoformat(),
        'total_drilled': len(results),
        'duration_variants_tested': DURATION_VARIANTS,
        'stopover_min_nights': STOPOVER_MIN_NIGHTS,
        'results': results,
    }
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f'\n{"=" * 65}')
    print(f'  DRILL COMPLETE: {len(results)} fares analyzed')
    print(f'{"=" * 65}')
    for r in results:
        dur_range = ''
        if r['valid_duration_min']:
            dur_range = f"stay {r['valid_duration_min']}-{r['valid_duration_max']}d"
        oj = f" | open-jaw ${r['open_jaw_price']}" if r.get('open_jaw_price') else ''
        stop = ''
        if r.get('stopover'):
            best_stop = min(r['stopover'].items(), key=lambda x: x[1]['total_outbound_pp'])
            stop = f" | stopover {best_stop[1]['hub']} {best_stop[0]} ${best_stop[1]['total_outbound_pp']}"
        print(f"  {r['origin']:15s}→{r['dest']:20s} ${r['oneway_price']:>4}/pp | {dur_range}{oj}{stop}")
    print(f"\nSaved: {RESULTS_FILE}")


if __name__ == '__main__':
    asyncio.run(main())
