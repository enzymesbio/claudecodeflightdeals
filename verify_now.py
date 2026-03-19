"""Verify: are we actually getting business class prices or economy?"""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/claude/flights')

from search_flights import FlightSearcher
import time

searcher = FlightSearcher(currency='USD')

# Test Apr 21 RT - the "bug fare" date
print("=" * 70)
print("TEST 1: CGK→LAX Apr 21 RT May 25 - ECONOMY")
print("=" * 70)
r = searcher.search(origin='CGK', destination='LAX', date='2026-04-21', return_date='2026-05-25', cabin='economy')
for f in r.get('flights', [])[:8]:
    p = f.get('price', 0)
    if p == 0: continue
    print(f"  ECO ${p:>5}/pp | {f.get('airline','?')[:45]} | {f.get('stops','')}stop | {f.get('duration','')}")

time.sleep(1.5)

print("\n" + "=" * 70)
print("TEST 2: CGK→LAX Apr 21 RT May 25 - BUSINESS")
print("=" * 70)
r = searcher.search(origin='CGK', destination='LAX', date='2026-04-21', return_date='2026-05-25', cabin='business')
for f in r.get('flights', [])[:8]:
    p = f.get('price', 0)
    if p == 0: continue
    print(f"  BIZ ${p:>5}/pp | {f.get('airline','?')[:45]} | {f.get('stops','')}stop | {f.get('duration','')}")

time.sleep(1.5)

# Check the actual URL being generated
print("\n" + "=" * 70)
print("URL COMPARISON")
print("=" * 70)
legs = [{'origin': 'CGK', 'destination': 'LAX', 'date': '2026-04-21'}]
url_eco = searcher._build_search_url(legs, cabin='economy')
url_biz = searcher._build_search_url(legs, cabin='business')
print(f"ECO URL: {url_eco}")
print(f"BIZ URL: {url_biz}")

# Also test OW to compare
time.sleep(1.5)
print("\n" + "=" * 70)
print("TEST 3: CGK→LAX Apr 27 OW - ECONOMY")
print("=" * 70)
r = searcher.search(origin='CGK', destination='LAX', date='2026-04-27', cabin='economy')
for f in r.get('flights', [])[:5]:
    p = f.get('price', 0)
    if p == 0: continue
    print(f"  ECO ${p:>5}/pp | {f.get('airline','?')[:45]} | {f.get('stops','')}stop")

time.sleep(1.5)
print("\n" + "=" * 70)
print("TEST 4: CGK→LAX Apr 27 OW - BUSINESS")
print("=" * 70)
r = searcher.search(origin='CGK', destination='LAX', date='2026-04-27', cabin='business')
for f in r.get('flights', [])[:5]:
    p = f.get('price', 0)
    if p == 0: continue
    print(f"  BIZ ${p:>5}/pp | {f.get('airline','?')[:45]} | {f.get('stops','')}stop")

print("\nIf ECO and BIZ show SAME prices → scraper is NOT actually searching business class")
print("If BIZ shows DIFFERENT (possibly cheaper) prices → bug fare is real")
