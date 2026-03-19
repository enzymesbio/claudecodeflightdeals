"""Quick search: IAH→LAX domestic return + verify best RT dates."""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/claude/flights')

import time
from search_flights import FlightSearcher

searcher = FlightSearcher(currency='USD')

print("IAH → LAX (return domestic)")
print("=" * 60)
for d in ['2026-05-28', '2026-06-01', '2026-06-05', '2026-06-08', '2026-06-10', '2026-06-15']:
    print(f"  {d}...", end=' ', flush=True)
    try:
        r = searcher.search(origin='IAH', destination='LAX', date=d)
        flights = r.get('flights', [])
        print(f"{len(flights)} flights")
        for f in flights[:5]:
            p = f.get('price', 0)
            if p == 0: continue
            a = f.get('airline', '?')
            st = f.get('stops', -1)
            ns = ' NONSTOP' if st == 0 else ''
            print(f"    ${p:>5}/pp | {a[:35]} | {st}stop{ns} | {f.get('duration','')}")
    except Exception as e:
        print(f"ERROR: {e}")
    time.sleep(1.0)

# Also check if bug fare RT works for more date combos
print("\n" + "=" * 60)
print("CGK↔LAX RT BIZ - more date combos")
print("=" * 60)
combos = [
    ('2026-04-27', '2026-05-25'),
    ('2026-04-27', '2026-05-28'),
    ('2026-04-28', '2026-06-01'),
    ('2026-05-01', '2026-06-01'),
    ('2026-05-01', '2026-06-10'),
    ('2026-05-01', '2026-06-15'),
    ('2026-05-04', '2026-06-08'),
    ('2026-05-04', '2026-06-10'),
]
for dep, ret in combos:
    print(f"  CGK-LAX RT {dep} to {ret}...", end=' ', flush=True)
    try:
        r = searcher.search(origin='CGK', destination='LAX', date=dep, return_date=ret, cabin='business')
        flights = r.get('flights', [])
        print(f"{len(flights)} flights")
        for f in flights[:3]:
            p = f.get('price', 0)
            if p == 0: continue
            a = f.get('airline', '?')
            print(f"    ${p:>5}/pp | {a[:45]} | {f.get('stops','')}stop | {f.get('duration','')}")
    except Exception as e:
        print(f"ERROR: {e}")
    time.sleep(1.0)

print("\nDONE")
