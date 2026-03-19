"""Check April departure RT bug fare dates."""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/claude/flights')

import time
from search_flights import FlightSearcher

searcher = FlightSearcher(currency='USD')

print("CGK↔LAX RT BIZ - April departures")
print("=" * 60)
combos = [
    ('2026-04-13', '2026-05-15'),
    ('2026-04-14', '2026-05-15'),
    ('2026-04-15', '2026-05-18'),
    ('2026-04-16', '2026-05-18'),
    ('2026-04-17', '2026-05-20'),
    ('2026-04-18', '2026-05-20'),
    ('2026-04-19', '2026-05-22'),
    ('2026-04-20', '2026-05-25'),
    ('2026-04-21', '2026-05-25'),
    ('2026-04-22', '2026-05-25'),
    ('2026-04-23', '2026-05-28'),
    ('2026-04-24', '2026-05-28'),
    ('2026-04-25', '2026-06-01'),
    ('2026-04-26', '2026-06-01'),
    ('2026-04-27', '2026-06-01'),
    ('2026-04-28', '2026-06-01'),
    ('2026-04-29', '2026-06-01'),
    ('2026-04-30', '2026-06-01'),
]
for dep, ret in combos:
    print(f"  {dep} → {ret}...", end=' ', flush=True)
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
