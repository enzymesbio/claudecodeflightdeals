"""Search for the Jakarta-Europe business class bug fare and positioning options."""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/claude/flights')

import json
import time
from datetime import datetime
from search_flights import FlightSearcher

searcher = FlightSearcher(currency='USD')

searches = []
all_results = []
n = 0

# === PART 1: Jakarta to Europe business class (verify the bug fare) ===
# The article shows Jakarta-London, but also mentions "European multi-cities"
EUROPE_BIZ = [
    # Jakarta to European cities - business class
    ('CGK', 'LHR', '2026-05-04', None, 'Jakarta-London (article exact)'),
    ('CGK', 'LHR', '2026-05-15', None, 'Jakarta-London May'),
    ('CGK', 'LHR', '2026-06-01', None, 'Jakarta-London Jun'),
    ('CGK', 'LHR', '2026-07-01', None, 'Jakarta-London Jul'),
    ('CGK', 'CDG', '2026-05-15', None, 'Jakarta-Paris'),
    ('CGK', 'FRA', '2026-05-15', None, 'Jakarta-Frankfurt'),
    ('CGK', 'ZRH', '2026-05-15', None, 'Jakarta-Zurich'),
    ('CGK', 'AMS', '2026-05-15', None, 'Jakarta-Amsterdam'),
    ('CGK', 'FCO', '2026-05-15', None, 'Jakarta-Rome'),
    # Round-trip options
    ('CGK', 'LHR', '2026-05-15', '2026-06-15', 'Jakarta-London RT'),
    ('CGK', 'CDG', '2026-05-15', '2026-06-15', 'Jakarta-Paris RT'),
    ('CGK', 'FRA', '2026-06-01', '2026-06-29', 'Jakarta-Frankfurt RT'),
]

# === PART 2: Positioning PVG/HKG to Jakarta ===
POSITIONING = [
    ('PVG', 'CGK', '2026-05-14', None, 'Shanghai-Jakarta positioning'),
    ('PVG', 'CGK', '2026-05-31', None, 'Shanghai-Jakarta positioning Jun'),
    ('HKG', 'CGK', '2026-05-14', None, 'HongKong-Jakarta positioning'),
    ('CAN', 'CGK', '2026-05-14', None, 'Guangzhou-Jakarta positioning'),
    ('HGH', 'CGK', '2026-05-14', None, 'Hangzhou-Jakarta positioning'),
]

# === PART 3: Direct China to Europe business class (comparison) ===
CHINA_EUROPE_BIZ = [
    ('PVG', 'LHR', '2026-05-15', '2026-06-15', 'Shanghai-London RT'),
    ('PVG', 'CDG', '2026-05-15', '2026-06-15', 'Shanghai-Paris RT'),
    ('PVG', 'FRA', '2026-05-15', '2026-06-15', 'Shanghai-Frankfurt RT'),
    ('PVG', 'LHR', '2026-09-01', '2026-09-29', 'Shanghai-London RT Sep'),
    ('HKG', 'LHR', '2026-05-15', '2026-06-15', 'HongKong-London RT'),
    ('HKG', 'CDG', '2026-05-15', '2026-06-15', 'HongKong-Paris RT'),
    ('CAN', 'LHR', '2026-05-15', '2026-06-15', 'Guangzhou-London RT'),
]

all_searches = EUROPE_BIZ + POSITIONING + CHINA_EUROPE_BIZ
total = len(all_searches)

print(f"Europe business class drill: {total} searches")
print("=" * 80)

for item in all_searches:
    origin, dest, dep, ret, note = item
    n += 1
    rt_str = f" RT {ret}" if ret else " OW"
    print(f"[{n}/{total}] {origin}-{dest} {dep}{rt_str} ({note})...", end=' ', flush=True)

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
            dur = fl.get('duration', '')

            # Print all results for bug fare searches, cheap ones for others
            if 'CGK' in (origin, dest) or price < 600:
                print(f"    ${price:>5}/pp | {airline[:40]} | {stops}stop | {dur}")

            all_results.append({
                'origin': origin,
                'destination': dest,
                'route': f"{origin}-{dest}",
                'note': note,
                'depart_date': dep,
                'return_date': ret or '',
                'price_pp': price,
                'price_3pax_est': round(price * 2.75),
                'airline': airline,
                'stops': stops,
                'duration': dur,
                'nonstop': stops == 0,
                'is_oneway': ret is None,
            })
    except Exception as e:
        print(f"ERROR: {e}", flush=True)

    time.sleep(1.5)

# Save
all_results.sort(key=lambda x: x['price_pp'])

with open('D:/claude/flights/europe_biz_results.json', 'w') as f:
    json.dump({'timestamp': datetime.now().isoformat(), 'searches': n, 'results': all_results}, f, indent=2)

# Summary
print("\n" + "=" * 80)
print("JAKARTA → EUROPE (bug fare verification):")
print("=" * 80)
jkt = [r for r in all_results if r['origin'] == 'CGK']
for r in jkt[:20]:
    ow = ' OW' if r['is_oneway'] else ' RT'
    print(f"  ${r['price_pp']:>5}/pp | {r['route']:<8} | {r['airline'][:35]:<35} | {r['stops']}stop | {r['depart_date']}{ow}")

print("\nPOSITIONING TO JAKARTA:")
pos = [r for r in all_results if r['destination'] == 'CGK']
for r in pos[:10]:
    print(f"  ${r['price_pp']:>5}/pp | {r['route']:<8} | {r['airline'][:35]:<35} | {r['stops']}stop")

print("\nDIRECT CHINA → EUROPE (comparison):")
direct = [r for r in all_results if r['origin'] in ('PVG','HKG','CAN') and r['destination'] in ('LHR','CDG','FRA')]
for r in direct[:15]:
    print(f"  ${r['price_pp']:>5}/pp | {r['route']:<8} | {r['airline'][:35]:<35} | {r['stops']}stop | {r['depart_date']}")

print("\nTRUE COST: PVG→Jakarta→Europe→(back):")
jkt_ow = [r for r in jkt if r['is_oneway']]
pos_ow = [r for r in pos if r['origin'] == 'PVG']
if jkt_ow and pos_ow:
    cheapest_pos = min(pos_ow, key=lambda x: x['price_pp'])
    cheapest_jkt = min(jkt_ow, key=lambda x: x['price_pp'])
    combo = cheapest_pos['price_pp'] + cheapest_jkt['price_pp']
    print(f"  Positioning PVG→CGK: ${cheapest_pos['price_pp']}/pp ({cheapest_pos['airline'][:25]})")
    print(f"  Bug fare CGK→Europe: ${cheapest_jkt['price_pp']}/pp ({cheapest_jkt['airline'][:25]})")
    print(f"  Combined one-way:    ${combo}/pp (~${round(combo*2.75)}/3pax)")
    print(f"  Note: This is ONE-WAY. Need return flight too!")
