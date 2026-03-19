"""Verify Philippine Airlines deal from WeChat article.
Open-jaw: HKG-SFO/LAX via Manila, return LAX/SFO-PVG/PEK/HKG via Manila.
Also search from PVG directly since user is in Jiaxing."""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/claude/flights')

import json
import time
from datetime import datetime
from search_flights import FlightSearcher

searcher = FlightSearcher(currency='USD')

# The article's exact routes (open-jaw via multi-city)
# We'll search as one-way legs since Google Flights supports multi-city
# Also search round-trips for comparison

searches = []

# === EXACT ARTICLE ROUTES ===
# Open-jaw 1: HKG-SFO Sep 25, LAX-PVG Oct 4
# Open-jaw 2: HKG-LAX Sep 25, LAX-PEK Oct 5
# Open-jaw 3: HKG-SFO Sep 25, LAX-HKG Oct 4

# === ROUND-TRIP VARIANTS (what user can actually book) ===
# Philippine Airlines via Manila from various origins
RT_SEARCHES = [
    # HKG routes (article's origin)
    ('HKG', 'LAX', '2026-09-25', '2026-10-04'),
    ('HKG', 'LAX', '2026-09-25', '2026-10-05'),
    ('HKG', 'SFO', '2026-09-25', '2026-10-04'),
    ('HKG', 'SFO', '2026-09-25', '2026-10-05'),
    # Try other Sep dates
    ('HKG', 'LAX', '2026-09-15', '2026-10-01'),
    ('HKG', 'SFO', '2026-09-15', '2026-10-01'),
    ('HKG', 'LAX', '2026-09-01', '2026-09-29'),
    ('HKG', 'SFO', '2026-09-01', '2026-09-29'),

    # PVG routes (user's closest airport!)
    ('PVG', 'LAX', '2026-09-25', '2026-10-04'),
    ('PVG', 'LAX', '2026-09-25', '2026-10-05'),
    ('PVG', 'SFO', '2026-09-25', '2026-10-04'),
    ('PVG', 'SFO', '2026-09-25', '2026-10-05'),
    ('PVG', 'LAX', '2026-09-15', '2026-10-01'),
    ('PVG', 'SFO', '2026-09-15', '2026-10-01'),
    ('PVG', 'LAX', '2026-09-01', '2026-09-29'),
    ('PVG', 'SFO', '2026-09-01', '2026-09-29'),

    # Also try May-June for user's preferred dates
    ('HKG', 'LAX', '2026-05-15', '2026-06-12'),
    ('HKG', 'SFO', '2026-05-15', '2026-06-12'),
    ('PVG', 'LAX', '2026-05-15', '2026-06-12'),
    ('PVG', 'SFO', '2026-05-15', '2026-06-12'),
    ('HKG', 'LAX', '2026-06-01', '2026-06-29'),
    ('HKG', 'SFO', '2026-06-01', '2026-06-29'),
    ('PVG', 'LAX', '2026-06-01', '2026-06-29'),
    ('PVG', 'SFO', '2026-06-01', '2026-06-29'),

    # CAN (Guangzhou) - close to HKG
    ('CAN', 'LAX', '2026-09-25', '2026-10-04'),
    ('CAN', 'SFO', '2026-09-25', '2026-10-04'),

    # XMN (Xiamen) - Philippine Airlines has routes
    ('XMN', 'LAX', '2026-09-25', '2026-10-04'),
    ('XMN', 'SFO', '2026-09-25', '2026-10-04'),

    # PEK (Beijing)
    ('PEK', 'LAX', '2026-09-25', '2026-10-04'),
]

all_results = []
n = 0

print(f"Philippine Airlines deal verification: {len(RT_SEARCHES)} searches")
print("=" * 80)

for origin, dest, dep, ret in RT_SEARCHES:
    n += 1
    print(f"[{n}/{len(RT_SEARCHES)}] {origin}-{dest} {dep} RT {ret}...", end=' ', flush=True)

    try:
        result = searcher.search(origin=origin, destination=dest, date=dep, return_date=ret)
        flights = result.get('flights', [])
        print(f"{len(flights)} flights", flush=True)

        for fl in flights:
            price = fl.get('price', 0)
            if price == 0:
                continue
            airline = fl.get('airline', '?')
            stops = fl.get('stops', -1)

            # Highlight Philippine Airlines and cheap deals
            is_pr = 'philippine' in airline.lower() or 'cebu' in airline.lower()
            if is_pr or price < 800:
                tag = ' *** PHILIPPINE AIR ***' if is_pr else ''
                ns = ' NONSTOP' if stops == 0 else ''
                print(f"    ${price:>5}/pp | {airline[:40]} | {stops}stop{ns}{tag}")

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
                'is_philippine': 'philippine' in airline.lower(),
            })
    except Exception as e:
        print(f"ERROR: {e}", flush=True)

    time.sleep(1.5)

# Sort and save
all_results.sort(key=lambda x: x['price_pp'])

with open('D:/claude/flights/philippine_deal_results.json', 'w') as f:
    json.dump({'timestamp': datetime.now().isoformat(), 'source': 'WeChat article verification', 'searches': n, 'results': all_results}, f, indent=2)

# Summary
print("\n" + "=" * 80)
print("PHILIPPINE AIRLINES DEALS:")
print("=" * 80)
pr_results = [r for r in all_results if r['is_philippine']]
if pr_results:
    seen = set()
    for r in pr_results:
        key = (r['route'], r['price_pp'], r['depart_date'])
        if key in seen: continue
        seen.add(key)
        est = r['price_3pax_est']
        print(f"  ${r['price_pp']:>4}/pp (~${est:>5}/3pax) | {r['route']:<8} | {r['airline'][:35]} | {r['depart_date']} RT {r['return_date']}")
else:
    print("  No Philippine Airlines results found on Google Flights!")

print("\nALL CHEAP DEALS (under $800/pp):")
seen2 = set()
for r in all_results:
    if r['price_pp'] >= 800:
        break
    key = (r['route'], r['airline'], r['price_pp'])
    if key in seen2: continue
    seen2.add(key)
    est = r['price_3pax_est']
    pr_tag = ' [PR]' if r['is_philippine'] else ''
    print(f"  ${r['price_pp']:>4}/pp (~${est:>5}/3pax) | {r['route']:<8} | {r['airline'][:35]:<35} | {r['depart_date']} RT {r['return_date']}{pr_tag}")
