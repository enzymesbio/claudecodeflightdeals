"""URGENT: Multi-city bug fare CGK→LAX, LAX→IAH, IAH→CGK business class."""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/claude/flights')

import json
import time
from datetime import datetime
from search_flights import FlightSearcher

searcher = FlightSearcher(currency='USD')
all_results = []

def s(origin, dest, date, ret=None, cabin='economy', label=''):
    rt = f" RT {ret}" if ret else " OW"
    cab = f' {cabin.upper()}' if cabin != 'economy' else ''
    print(f"  {label or f'{origin}-{dest}'} {date}{rt}{cab}...", end=' ', flush=True)
    try:
        r = searcher.search(origin=origin, destination=dest, date=date, return_date=ret, cabin=cabin)
        flights = r.get('flights', [])
        print(f"{len(flights)} flights", flush=True)
        for f in flights[:8]:
            p = f.get('price', 0)
            if p == 0: continue
            a = f.get('airline', '?')
            st = f.get('stops', -1)
            d = f.get('duration', '')
            ns = ' NONSTOP' if st == 0 else ''
            print(f"    ${p:>5}/pp | {a[:45]} | {st}stop{ns} | {d}")
            all_results.append({
                'origin': origin, 'dest': dest, 'date': date, 'return': ret,
                'price': p, 'airline': a, 'stops': st, 'duration': d,
                'cabin': cabin, 'label': label,
            })
        return flights
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        return []
    finally:
        time.sleep(1.0)

print("=" * 80)
print("LEG 1: CGK → LAX BUSINESS CLASS (bug fare dates)")
print("=" * 80)
for d in ['2026-04-27', '2026-04-28', '2026-04-29', '2026-04-30',
          '2026-05-01', '2026-05-02', '2026-05-03', '2026-05-04',
          '2026-05-05', '2026-05-08', '2026-05-10', '2026-05-15']:
    s('CGK', 'LAX', d, cabin='business', label=f'CGK-LAX BIZ {d}')

print("\n" + "=" * 80)
print("LEG 2: LAX → Houston (domestic, economy is fine)")
print("=" * 80)
# Check a few dates after potential LAX arrival
for d in ['2026-05-15', '2026-05-18', '2026-05-20', '2026-05-22', '2026-05-25']:
    s('LAX', 'IAH', d, cabin='economy', label=f'LAX-IAH ECO {d}')

print("\n" + "=" * 80)
print("LEG 3: Houston → CGK BUSINESS CLASS (return bug fare?)")
print("=" * 80)
for d in ['2026-05-25', '2026-05-28', '2026-06-01', '2026-06-05',
          '2026-06-08', '2026-06-10', '2026-06-15']:
    s('IAH', 'CGK', d, cabin='business', label=f'IAH-CGK BIZ {d}')

# Also try from Houston Hobby
print("\n" + "=" * 80)
print("LEG 3b: Houston → CGK via HOU BUSINESS")
print("=" * 80)
for d in ['2026-06-01', '2026-06-08', '2026-06-15']:
    s('HOU', 'CGK', d, cabin='business', label=f'HOU-CGK BIZ {d}')

# Also check RT from CGK (bug fare may only work OW from CGK)
print("\n" + "=" * 80)
print("ALT: CGK → LAX RT BUSINESS (bug fare RT?)")
print("=" * 80)
for dep, ret in [('2026-04-27', '2026-06-01'), ('2026-05-01', '2026-06-08'),
                  ('2026-05-04', '2026-06-15'), ('2026-05-08', '2026-06-08')]:
    s('CGK', 'LAX', dep, ret=ret, cabin='business', label=f'CGK-LAX BIZ RT {dep}-{ret}')

# Multi-city: CGK→LAX, then IAH→CGK
print("\n" + "=" * 80)
print("ALT: CGK→LAX + IAH→CGK MULTI-CITY BIZ (open jaw)")
print("=" * 80)
# The search_flights.py supports --multi, let's use it
for dep1, dep2 in [('2026-04-27', '2026-06-01'), ('2026-05-01', '2026-06-08'),
                    ('2026-05-04', '2026-06-15')]:
    label = f'MULTI CGK-LAX {dep1} + IAH-CGK {dep2}'
    print(f"  {label}...", end=' ', flush=True)
    try:
        legs = [
            {'origin': 'CGK', 'destination': 'LAX', 'date': dep1},
            {'origin': 'IAH', 'destination': 'CGK', 'date': dep2},
        ]
        url = searcher._build_search_url(legs, cabin='business')
        r = searcher._fetch_and_parse(url)
        flights = r.get('flights', [])
        print(f"{len(flights)} flights", flush=True)
        for f in flights[:5]:
            p = f.get('price', 0)
            if p == 0: continue
            a = f.get('airline', '?')
            st = f.get('stops', -1)
            d = f.get('duration', '')
            print(f"    ${p:>5}/pp | {a[:45]} | {st}stop | {d}")
            all_results.append({
                'origin': 'CGK', 'dest': 'LAX+IAH-CGK', 'date': dep1, 'return': dep2,
                'price': p, 'airline': a, 'stops': st, 'duration': d,
                'cabin': 'business', 'label': label,
            })
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
    time.sleep(1.0)

# Save
with open('D:/claude/flights/multicity_results.json', 'w') as f:
    json.dump({'timestamp': datetime.now().isoformat(), 'results': all_results}, f, indent=2)

print("\n" + "=" * 80)
print("SUMMARY - ALL RESULTS")
print("=" * 80)
# Group by leg
for leg_prefix in ['CGK-LAX BIZ', 'LAX-IAH', 'IAH-CGK', 'HOU-CGK', 'CGK-LAX BIZ RT', 'MULTI']:
    leg_results = [r for r in all_results if r['label'].startswith(leg_prefix)]
    if leg_results:
        leg_results.sort(key=lambda x: x['price'])
        print(f"\n  {leg_prefix}:")
        seen = set()
        for r in leg_results[:10]:
            key = (r['airline'], r['price'], r['date'])
            if key in seen: continue
            seen.add(key)
            print(f"    ${r['price']:>5}/pp | {r['airline'][:40]} | {r['stops']}stop | {r['date']} | {r['duration']}")

print("\nDONE")
