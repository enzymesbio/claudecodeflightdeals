"""URGENT: Search Jakarta business class bug fare before it disappears."""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/claude/flights')

import json
import time
from datetime import datetime
from search_flights import FlightSearcher

searcher = FlightSearcher(currency='USD')

SEARCHES = [
    # The exact article route: Jakarta-London May 4 business class OW
    ('CGK', 'LHR', '2026-05-04', None),
    ('CGK', 'LHR', '2026-05-05', None),
    ('CGK', 'LHR', '2026-05-06', None),
    ('CGK', 'LHR', '2026-05-15', None),
    ('CGK', 'LHR', '2026-06-01', None),
    ('CGK', 'LHR', '2026-07-01', None),
    # Other European cities
    ('CGK', 'FCO', '2026-05-04', None),
    ('CGK', 'FCO', '2026-05-15', None),
    ('CGK', 'CDG', '2026-05-04', None),
    ('CGK', 'CDG', '2026-05-15', None),
    ('CGK', 'FRA', '2026-05-04', None),
    ('CGK', 'ZRH', '2026-05-04', None),
    ('CGK', 'AMS', '2026-05-04', None),
    # LAX too!
    ('CGK', 'LAX', '2026-05-04', None),
    ('CGK', 'LAX', '2026-05-15', None),
    ('CGK', 'LAX', '2026-06-01', None),
    ('CGK', 'SFO', '2026-05-15', None),
    # RT
    ('CGK', 'LHR', '2026-05-04', '2026-06-04'),
    ('CGK', 'FCO', '2026-05-04', '2026-06-04'),
    ('CGK', 'LAX', '2026-05-04', '2026-06-04'),
    ('CGK', 'CDG', '2026-05-15', '2026-06-15'),
]

all_results = []
n = 0

print("URGENT: Jakarta BUSINESS CLASS bug fare search")
print("=" * 80)

for origin, dest, dep, ret in SEARCHES:
    n += 1
    rt = f" RT {ret}" if ret else " OW"
    print(f"[{n}/{len(SEARCHES)}] BIZ {origin}-{dest} {dep}{rt}...", end=' ', flush=True)

    try:
        result = searcher.search(
            origin=origin, destination=dest,
            date=dep, return_date=ret,
            cabin='business',
        )
        flights = result.get('flights', [])
        print(f"{len(flights)} flights", flush=True)

        for fl in flights:
            price = fl.get('price', 0)
            if price == 0:
                continue
            airline = fl.get('airline', '?')
            stops = fl.get('stops', -1)
            dur = fl.get('duration', '')
            ns = ' NONSTOP' if stops == 0 else ''
            print(f"    ${price:>5}/pp | {airline[:40]} | {stops}stop{ns} | {dur}")

            all_results.append({
                'origin': origin, 'destination': dest,
                'route': f"{origin}-{dest}",
                'depart_date': dep, 'return_date': ret or '',
                'price_pp': price,
                'price_3pax': round(price * 2.75),
                'airline': airline, 'stops': stops,
                'duration': dur, 'cabin': 'business',
                'is_oneway': ret is None,
            })
    except Exception as e:
        print(f"ERROR: {e}", flush=True)

    time.sleep(1.0)  # faster, this is urgent

all_results.sort(key=lambda x: x['price_pp'])

with open('D:/claude/flights/jakarta_biz_verified.json', 'w') as f:
    json.dump({'timestamp': datetime.now().isoformat(), 'cabin': 'business', 'results': all_results}, f, indent=2)

print("\n" + "=" * 80)
print(f"BUSINESS CLASS RESULTS: {len(all_results)} flights found")
print("=" * 80)
if all_results:
    seen = set()
    for r in all_results[:30]:
        key = (r['route'], r['airline'], r['price_pp'])
        if key in seen: continue
        seen.add(key)
        ow = ' OW' if r['is_oneway'] else ' RT'
        print(f"  ${r['price_pp']:>5}/pp (${r['price_3pax']:>5}/3pax) | {r['route']:<8} | {r['airline'][:35]:<35} | {r['stops']}stop | {r['depart_date']}{ow}")
else:
    print("  NO BUSINESS CLASS RESULTS - query may not trigger biz class on Google Flights")
    print("  The bug fare may need to be searched directly on Google Flights UI or Expedia")
