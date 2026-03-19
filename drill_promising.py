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
from money import parse_money_usd
from entities import (
    ORIGINS as ENTITY_ORIGINS, ORIGINS_BY_CITY,
    HUB_AIRPORTS, HUB_KEYWORDS, HUB_CITIES_FREEBASE,
    US_EXPLORE_ID, get_origin_cid_by_city, get_dest_freebase_id,
)

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

# Shanghai / Hangzhou Freebase IDs (home base cities for feeder + open-jaw)
SHANGHAI_CID = ENTITY_ORIGINS['PVG']['google_id']   # '/m/06wjf'
HANGZHOU_CID = ENTITY_ORIGINS['HGH']['google_id']   # '/m/014vm4'

# Hub cities: city name → Freebase ID (derived from entities — no duplication)
HUB_CITIES = HUB_CITIES_FREEBASE

# Airlines that commonly route through hubs and allow stopovers
STOPOVER_AIRLINES = [
    'Korean Air', 'Asiana', 'ANA', 'All Nippon', 'Japan Airlines', 'JAL',
    'Singapore Airlines', 'Air China', 'China Eastern', 'China Southern',
    'Hainan', 'Sichuan', 'Xiamen Air', 'Shenzhen Airlines', 'Cathay',
]

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
    """Load a search URL and extract the cheapest flight price using money.py. Returns int or None."""
    page = await context.new_page()
    try:
        await page.goto(url, timeout=30000)
        await page.wait_for_load_state('domcontentloaded')
        try:
            btn = page.get_by_role('button', name='Reject all')
            if await btn.count() > 0:
                await btn.first.click()
                await asyncio.sleep(2)
        except: pass
        await asyncio.sleep(14)
        text = await page.inner_text('body')
        # Primary: "From $X" pattern shown in search page header (most reliable)
        price = parse_money_usd(text[:2000])
        if price and 50 <= price <= 15000:
            return round(price)
        # Secondary: click first result and re-check
        try:
            first_li = page.locator('li').first
            if await first_li.count() > 0:
                await first_li.click()
                await asyncio.sleep(4)
                text2 = (await page.inner_text('body'))[:5000]
                price2 = parse_money_usd(text2)
                if price2 and 50 <= price2 <= 15000:
                    return round(price2)
        except: pass
        return None
    except Exception:
        return None
    finally:
        await page.close()


async def get_page_text(context, url, wait_secs=12):
    """Load a URL and return body text (for stopover city detection)."""
    page = await context.new_page()
    try:
        await page.goto(url, timeout=30000)
        await page.wait_for_load_state('domcontentloaded')
        try:
            btn = page.get_by_role('button', name='Reject all')
            if await btn.count() > 0:
                await btn.first.click()
                await asyncio.sleep(2)
        except: pass
        await asyncio.sleep(wait_secs)
        return await page.inner_text('body')
    except:
        return ''
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

        origin_cid = get_origin_cid_by_city(origin)
        dest_cid   = get_dest_freebase_id(dest)
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
            'stops': fare.get('stops', 0),
            'duration_results': {},
            'valid_duration_min': None,
            'valid_duration_max': None,
            'open_jaw_price': None,
            'open_jaw_url': None,
            'open_jaw_hangzhou_price': None,
            'open_jaw_hangzhou_url': None,
            'stopover': {},
            'stopover_return': None,
            'feeder': {},
            'actual_stopover_city': None,
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

        # --- 5b: Open-jaw returns (Shanghai and Hangzhou) ---
        ret_date_14 = (dt + timedelta(days=14)).strftime('%Y-%m-%d')
        if origin != 'Shanghai':
            oj_url = build_rt_url(origin_cid, dest_cid, depart, ret_date_14,
                                  return_to_cid=SHANGHAI_CID)
            oj_price = await get_price_from_url(context, oj_url, 'openjaw')
            if oj_price:
                result['open_jaw_price'] = oj_price
                result['open_jaw_url'] = oj_url
                print(f"      open-jaw→Shanghai: ${oj_price}/pp")
            await asyncio.sleep(1)
        if origin not in ('Shanghai', 'Hangzhou'):
            oj_hz_url = build_rt_url(origin_cid, dest_cid, depart, ret_date_14,
                                     return_to_cid=HANGZHOU_CID)
            oj_hz_price = await get_price_from_url(context, oj_hz_url, 'openjaw-hz')
            if oj_hz_price:
                result['open_jaw_hangzhou_price'] = oj_hz_price
                result['open_jaw_hangzhou_url'] = oj_hz_url
                print(f"      open-jaw→Hangzhou: ${oj_hz_price}/pp")
            await asyncio.sleep(1)

        # --- 5c: Non-stop → feeder; 1-stop → detect actual stopover city ---
        stops_raw = fare.get('stops', 0)
        if isinstance(stops_raw, str):
            s = stops_raw.lower()
            if 'nonstop' in s or 'non-stop' in s or s.strip() == '0':
                stops_val = 0
            else:
                m_s = re.search(r'(\d+)', s)
                stops_val = int(m_s.group(1)) if m_s else 1
        else:
            stops_val = int(stops_raw) if stops_raw else 0

        if stops_val == 0:
            # Non-stop: test feeder flights from Shanghai and Hangzhou to reach this origin
            if origin not in ('Shanghai', 'Hangzhou'):
                feeder_results = {}
                for home, home_cid in [('Shanghai', SHANGHAI_CID), ('Hangzhou', HANGZHOU_CID)]:
                    url = build_oneway_url(home_cid, origin_cid, depart)
                    price = await get_price_from_url(context, url, f'feeder-{home}')
                    if price:
                        feeder_results[home] = price
                        total_combo = price + pp_price
                        print(f"      feeder from {home}: ${price} + bug ${pp_price} = ${total_combo}/pp OW total")
                    await asyncio.sleep(1)
                if feeder_results:
                    result['feeder'] = feeder_results
        else:
            # Has stops: try to detect actual stopover city then test extended stay
            # Detect actual stopover for ALL 1-stop fares (not just top 5)
            actual_stop = None
            page_text = await get_page_text(context,
                            build_oneway_url(origin_cid, dest_cid, depart))
            # Use HUB_KEYWORDS from entities (IATA → keywords), map to city names
            for iata, keywords in HUB_KEYWORDS.items():
                city_name = HUB_AIRPORTS[iata]['city']
                if any(kw in page_text[:6000] for kw in keywords):
                    actual_stop = city_name
                    result['actual_stopover_city'] = city_name
                    print(f"      detected stopover: {city_name}")
                    break

            if actual_stop and actual_stop in HUB_CITIES and actual_stop != origin:
                hub_cid = HUB_CITIES[actual_stop]
                stopover_results = {}
                # Outbound: origin → hub → dest with 3-6 night extended stay at hub
                for nights in range(3, 7):  # min 3 nights as requested
                    hub_depart = (dt + timedelta(days=nights)).strftime('%Y-%m-%d')
                    p1 = await get_price_from_url(context,
                             build_oneway_url(origin_cid, hub_cid, depart), 'stop-leg1')
                    await asyncio.sleep(1)
                    p2 = await get_price_from_url(context,
                             build_oneway_url(hub_cid, dest_cid, hub_depart), 'stop-leg2')
                    await asyncio.sleep(1)
                    if p1 and p2:
                        stopover_results[f'{nights}n'] = {
                            'hub': actual_stop,
                            'leg1_price': p1,
                            'leg2_price': p2,
                            'total_outbound_pp': p1 + p2,
                        }
                        print(f"      outbound stopover {actual_stop} {nights}n: "
                              f"leg1=${p1} + leg2=${p2} = ${p1+p2}/pp")
                    else:
                        break  # prices stabilise — no need to test more nights
                if stopover_results:
                    result['stopover'] = stopover_results

                # Return stopover: dest → hub (2 nights) → origin
                ret_base = dt + timedelta(days=14)  # 14 days US stay
                ret_leg1_date = ret_base.strftime('%Y-%m-%d')
                ret_leg2_date = (ret_base + timedelta(days=2)).strftime('%Y-%m-%d')
                ret_p1 = await get_price_from_url(context,
                         build_oneway_url(dest_cid, hub_cid, ret_leg1_date), 'ret-leg1')
                await asyncio.sleep(1)
                ret_p2 = await get_price_from_url(context,
                         build_oneway_url(hub_cid, origin_cid, ret_leg2_date), 'ret-leg2')
                await asyncio.sleep(1)
                if ret_p1 and ret_p2:
                    result['stopover_return'] = {
                        'hub': actual_stop,
                        'leg1_price': ret_p1,
                        'leg2_price': ret_p2,
                        'total_return_pp': ret_p1 + ret_p2,
                    }
                    print(f"      return stopover {actual_stop} 2n: "
                          f"leg1=${ret_p1} + leg2=${ret_p2} = ${ret_p1+ret_p2}/pp")
            else:
                # Fallback: geography-based hub test
                airline = fare.get('airline', '')
                should_test_stopover = any(a.lower() in airline.lower() for a in STOPOVER_AIRLINES)
                if should_test_stopover or not airline:
                    origin_hub = None
                    chinese_cities = {'Shanghai', 'Beijing', 'Guangzhou', 'Chengdu', 'Chongqing',
                                       'Shenzhen', 'Nanjing', 'Hangzhou', 'Ningbo', 'Qingdao',
                                       'Dalian', 'Wuhan', 'Xiamen', 'Tianjin', 'Fuzhou'}
                    if origin in chinese_cities:
                        origin_hub = 'Seoul'
                    elif origin == 'Seoul':
                        origin_hub = 'Seoul'
                    elif origin == 'Tokyo':
                        origin_hub = 'Tokyo'
                    elif origin in ('Hong Kong', 'Singapore', 'Bangkok', 'Manila',
                                    'Kuala Lumpur', 'Ho Chi Minh City', 'Jakarta'):
                        origin_hub = 'Hong Kong'

                    if origin_hub and origin != origin_hub:
                        hub_cid = HUB_CITIES[origin_hub]
                        stopover_results = {}
                        for nights in range(STOPOVER_MIN_NIGHTS, STOPOVER_MAX_NIGHTS + 1):
                            hub_depart = (dt + timedelta(days=nights)).strftime('%Y-%m-%d')
                            p1 = await get_price_from_url(
                                context,
                                build_oneway_url(origin_cid, hub_cid, depart),
                                'stop-leg1'
                            )
                            await asyncio.sleep(1)
                            p2 = await get_price_from_url(
                                context,
                                build_oneway_url(hub_cid, dest_cid, hub_depart),
                                'stop-leg2'
                            )
                            await asyncio.sleep(1)
                            if p1 and p2:
                                total_pp_s = p1 + p2
                                stopover_results[f'{nights}n'] = {
                                    'hub': origin_hub,
                                    'leg1_price': p1,
                                    'leg2_price': p2,
                                    'total_outbound_pp': total_pp_s,
                                }
                                print(f"      stopover {origin_hub} {nights}n: "
                                      f"leg1=${p1} + leg2=${p2} = ${total_pp_s}/pp outbound")
                            else:
                                break
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
        oj = f" | ↩SH ${r['open_jaw_price']}" if r.get('open_jaw_price') else ''
        oj_hz = f" | ↩HZ ${r['open_jaw_hangzhou_price']}" if r.get('open_jaw_hangzhou_price') else ''
        feeder = r.get('feeder', {})
        feeder_str = (' | feeder: ' + ', '.join(f"{h}→${p}" for h, p in feeder.items())) if feeder else ''
        stop = ''
        if r.get('stopover'):
            best_stop = min(r['stopover'].items(), key=lambda x: x[1]['total_outbound_pp'])
            stop = f" | OB-stop {best_stop[1]['hub']} {best_stop[0]} ${best_stop[1]['total_outbound_pp']}"
        ret_stop = ''
        if r.get('stopover_return'):
            rs = r['stopover_return']
            ret_stop = f" | RT-stop {rs['hub']} 2n ${rs['total_return_pp']}"
        actual = f" | via {r['actual_stopover_city']}" if r.get('actual_stopover_city') else ''
        print(f"  {r['origin']:15s}→{r['dest']:20s} ${r['oneway_price']:>4}/pp | {dur_range}{oj}{oj_hz}{feeder_str}{stop}{ret_stop}{actual}")
    print(f"\nSaved: {RESULTS_FILE}")


if __name__ == '__main__':
    asyncio.run(main())
