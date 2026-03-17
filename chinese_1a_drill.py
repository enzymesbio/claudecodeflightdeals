"""Search Chinese airline hubs with 1 adult to find actual Chinese airline prices."""
import sys
sys.path.insert(0, 'D:/claude/flights')

import json
import time
from datetime import datetime
from search_flights import FlightSearcher

ROUTES = [
    ('CAN', 'LAX'), ('CAN', 'SFO'),
    ('PVG', 'LAX'), ('PVG', 'SFO'),
    ('CTU', 'LAX'), ('TFU', 'LAX'),
    ('PEK', 'LAX'), ('PEK', 'SFO'),
    ('XMN', 'LAX'), ('XMN', 'SFO'),
    ('HGH', 'LAX'),
    ('PEK', 'SEA'),  # Hainan Airlines
    # Also re-check the winning routes with 1A
    ('ICN', 'LAX'), ('ICN', 'SFO'),
    ('HKG', 'LAX'), ('HKG', 'SFO'),
]

DATES = [
    ('2026-05-15', '2026-06-12'),
    ('2026-05-22', '2026-06-19'),
    ('2026-06-01', '2026-06-29'),
    ('2026-09-01', '2026-09-29'),
    ('2026-09-15', '2026-10-13'),
]

def main():
    searcher = FlightSearcher(currency='USD')
    all_results = []
    total = len(ROUTES) * len(DATES)
    n = 0

    print(f"1-adult search: {total} searches across {len(ROUTES)} routes")

    for origin, dest in ROUTES:
        for dep, ret in DATES:
            n += 1
            print(f"[{n}/{total}] {origin}-{dest} {dep} RT {ret}...", end=' ', flush=True)

            try:
                result = searcher.search(
                    origin=origin, destination=dest,
                    date=dep, return_date=ret,
                )
                flights = result.get('flights', [])
                print(f"{len(flights)} flights", flush=True)

                for fl in flights:
                    price = fl.get('price', 0)
                    if price == 0:
                        continue
                    airline = fl.get('airline', '?')
                    stops = fl.get('stops', -1)
                    # Print interesting ones
                    if price < 1200 or any(kw in airline.lower() for kw in ['china', 'sichuan', 'hainan', 'xiamen', 'air china', 'premia']):
                        ns = ' NONSTOP' if stops == 0 else ''
                        print(f"    ${price:>5}/pp | {airline[:40]} | {stops}stop{ns}")

                    all_results.append({
                        'origin': origin,
                        'destination': dest,
                        'route': f"{origin}-{dest}",
                        'depart_date': dep,
                        'return_date': ret,
                        'price_pp': price,
                        'price_3pax_est': round(price * 2.75),
                        'airline': airline,
                        'stops': stops,
                        'duration': fl.get('duration', ''),
                        'nonstop': stops == 0,
                        'dep_time': fl.get('dep_time', ''),
                        'arr_time': fl.get('arr_time', ''),
                    })
            except Exception as e:
                print(f"ERROR: {e}", flush=True)

            time.sleep(1.5)

    all_results.sort(key=lambda x: x['price_pp'])

    with open('D:/claude/flights/chinese_1a_results.json', 'w') as f:
        json.dump({'timestamp': datetime.now().isoformat(), 'searches': n, 'results': all_results}, f, indent=2)

    # Summary
    print("\n" + "="*80)
    print(f"TOTAL: {len(all_results)} flights from {n} searches")
    print("="*80)

    chinese_kws = ['china southern', 'china eastern', 'air china', 'sichuan',
                   'hainan', 'xiamen', 'cathay']

    print("\nTOP 25 CHEAPEST (1 adult, est x2.75 for family):")
    seen = set()
    rank = 0
    for r in all_results:
        key = (r['route'], r['airline'], r['price_pp'])
        if key in seen: continue
        seen.add(key)
        rank += 1
        if rank > 25: break
        est = r['price_3pax_est']
        is_cn = any(kw in r['airline'].lower() for kw in chinese_kws)
        tag = ' [CN]' if is_cn else ''
        ns = ' NONSTOP' if r['nonstop'] else ''
        budget = ' << UNDER $2K!' if est < 2000 else ''
        print(f"  {rank:>2}. ${r['price_pp']:>4}/pp (~${est:>5}/3pax) | {r['route']:<8} | {r['airline'][:30]:<30} | {r['stops']}stop{ns} | {r['depart_date']}{tag}{budget}")

    print("\nCHINESE AIRLINES ONLY:")
    cn_results = [r for r in all_results if any(kw in r['airline'].lower() for kw in chinese_kws)]
    seen2 = set()
    for r in cn_results[:20]:
        key = (r['route'], r['airline'], r['price_pp'])
        if key in seen2: continue
        seen2.add(key)
        est = r['price_3pax_est']
        ns = ' NONSTOP' if r['nonstop'] else ''
        print(f"  ${r['price_pp']:>4}/pp (~${est:>5}/3pax) | {r['route']:<8} | {r['airline'][:35]:<35} | {r['depart_date']}{ns}")

if __name__ == '__main__':
    main()
