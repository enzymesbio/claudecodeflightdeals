"""Quick verification: same route economy vs business, check if results differ."""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/claude/flights')

from search_flights import FlightSearcher
import requests

searcher = FlightSearcher(currency='USD')

# Search same route with economy and business
route = ('CGK', 'LHR', '2026-05-04')

print("=== ECONOMY search ===")
eco = searcher.search(origin='CGK', destination='LHR', date='2026-05-04', cabin='economy')
print(f"Flights: {len(eco.get('flights',[]))}")
for f in eco.get('flights',[])[:8]:
    print(f"  ${f['price']:>5} | {f['airline'][:40]} | {f.get('stops','')}stop | {f.get('duration','')}")

print()
print("=== BUSINESS search ===")
biz = searcher.search(origin='CGK', destination='LHR', date='2026-05-04', cabin='business')
print(f"Flights: {len(biz.get('flights',[]))}")
for f in biz.get('flights',[])[:8]:
    print(f"  ${f['price']:>5} | {f['airline'][:40]} | {f.get('stops','')}stop | {f.get('duration','')}")

# Check the actual URLs being generated
print()
print("=== URL CHECK ===")
legs_eco = [{'origin': 'CGK', 'destination': 'LHR', 'date': '2026-05-04'}]
legs_biz = [{'origin': 'CGK', 'destination': 'LHR', 'date': '2026-05-04'}]
url_eco = searcher._build_search_url(legs_eco, cabin='economy')
url_biz = searcher._build_search_url(legs_biz, cabin='business')
print(f"Economy URL: {url_eco[:200]}")
print(f"Business URL: {url_biz[:200]}")

# Are results different?
eco_prices = sorted([f['price'] for f in eco.get('flights',[])])
biz_prices = sorted([f['price'] for f in biz.get('flights',[])])
print(f"\nEconomy prices: {eco_prices[:10]}")
print(f"Business prices: {biz_prices[:10]}")
print(f"Results are {'DIFFERENT' if eco_prices != biz_prices else 'SAME'}")

# If different, the business query IS working
if eco_prices != biz_prices:
    # Check if any biz prices are cheaper than cheapest eco (= bug fare)
    if biz_prices and eco_prices and min(biz_prices) < min(eco_prices):
        print(f"\n*** BUG FARE CONFIRMED: Business ${min(biz_prices)} < Economy ${min(eco_prices)} ***")
    else:
        print(f"\nBusiness min: ${min(biz_prices) if biz_prices else 'N/A'}, Economy min: ${min(eco_prices) if eco_prices else 'N/A'}")
