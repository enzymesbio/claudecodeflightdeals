"""URGENT booking search: Jiaxing → Jakarta → LAX (biz) → USA stay → Europe → home"""
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
    global all_results
    rt = f" RT {ret}" if ret else " OW"
    cab = ' BIZ' if cabin == 'business' else ''
    print(f"  {label or f'{origin}-{dest}'} {date}{rt}{cab}...", end=' ', flush=True)
    try:
        r = searcher.search(origin=origin, destination=dest, date=date, return_date=ret, cabin=cabin)
        flights = r.get('flights', [])
        print(f"{len(flights)} flights", flush=True)
        for f in flights[:5]:
            p = f.get('price', 0)
            if p == 0: continue
            a = f.get('airline', '?')
            st = f.get('stops', -1)
            d = f.get('duration', '')
            ns = ' NONSTOP' if st == 0 else ''
            print(f"    ${p:>5}/pp | {a[:40]} | {st}stop{ns} | {d}")
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
        time.sleep(1.2)

print("=" * 80)
print("STEP 1: Positioning HGH/PVG → Jakarta (after Apr 11)")
print("=" * 80)
# Check multiple April dates
for d in ['2026-04-12', '2026-04-13', '2026-04-14', '2026-04-15']:
    s('HGH', 'CGK', d, label=f'HGH-CGK {d}')
    s('PVG', 'CGK', d, label=f'PVG-CGK {d}')

print("\n" + "=" * 80)
print("STEP 2: Jakarta → LAX BUSINESS CLASS (bug fare)")
print("=" * 80)
# Check April and May dates
for d in ['2026-04-13', '2026-04-14', '2026-04-15', '2026-04-16',
          '2026-04-20', '2026-04-25', '2026-04-27',
          '2026-05-01', '2026-05-04', '2026-05-05', '2026-05-08',
          '2026-05-11', '2026-05-15']:
    s('CGK', 'LAX', d, cabin='business', label=f'CGK-LAX BIZ {d}')

print("\n" + "=" * 80)
print("STEP 2b: Jakarta → SFO BUSINESS CLASS")
print("=" * 80)
for d in ['2026-04-14', '2026-04-20', '2026-05-01', '2026-05-04', '2026-05-15']:
    s('CGK', 'SFO', d, cabin='business', label=f'CGK-SFO BIZ {d}')

print("\n" + "=" * 80)
print("STEP 3: LAX → Frankfurt (after USA stay, ~3-4 weeks later)")
print("=" * 80)
# If arrive LAX mid-April, depart to Europe mid-May
for d in ['2026-05-10', '2026-05-15', '2026-05-20', '2026-06-01']:
    s('LAX', 'FRA', d, cabin='economy', label=f'LAX-FRA ECO {d}')
    s('LAX', 'FRA', d, cabin='business', label=f'LAX-FRA BIZ {d}')

# Also check LAX to Munich (closer to some German destinations)
for d in ['2026-05-15', '2026-06-01']:
    s('LAX', 'MUC', d, cabin='economy', label=f'LAX-MUC ECO {d}')

print("\n" + "=" * 80)
print("STEP 4: Frankfurt/Munich → Shanghai (return home)")
print("=" * 80)
for d in ['2026-05-25', '2026-06-01', '2026-06-08', '2026-06-15']:
    s('FRA', 'PVG', d, cabin='economy', label=f'FRA-PVG ECO {d}')

for d in ['2026-06-01', '2026-06-15']:
    s('MUC', 'PVG', d, cabin='economy', label=f'MUC-PVG ECO {d}')

# Save
with open('D:/claude/flights/booking_plan_results.json', 'w') as f:
    json.dump({'timestamp': datetime.now().isoformat(), 'results': all_results}, f, indent=2)

print("\n" + "=" * 80)
print("DONE - results saved")
