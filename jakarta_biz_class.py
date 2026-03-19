"""Search Jakarta to Europe/USA BUSINESS CLASS - verifying the bug fare."""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/claude/flights')

import json
import time
from datetime import datetime
from search_flights import FlightSearcher

# The scraper needs to support cabin class - check if it does
# Looking at search_flights.py, the search method builds a Google Flights URL
# We need to add cabin=business parameter

# Google Flights URL parameter for business class: tfs query includes "business"
# or we can use the natural language query approach

searcher = FlightSearcher(currency='USD')

# For business class, we'll modify the search query to include "business class"
# The scraper uses ?q= parameter with natural language

SEARCHES = [
    # Jakarta to Europe business class
    ('CGK', 'LHR', '2026-05-04', None, 'Jakarta-London Biz May4'),
    ('CGK', 'LHR', '2026-05-15', None, 'Jakarta-London Biz May15'),
    ('CGK', 'LHR', '2026-06-01', None, 'Jakarta-London Biz Jun1'),
    ('CGK', 'LHR', '2026-07-01', None, 'Jakarta-London Biz Jul1'),
    ('CGK', 'CDG', '2026-05-15', None, 'Jakarta-Paris Biz'),
    ('CGK', 'FCO', '2026-05-15', None, 'Jakarta-Rome Biz'),
    ('CGK', 'FRA', '2026-05-15', None, 'Jakarta-Frankfurt Biz'),
    ('CGK', 'ZRH', '2026-05-15', None, 'Jakarta-Zurich Biz'),
    # Jakarta to LAX business class (user asked about this!)
    ('CGK', 'LAX', '2026-05-15', None, 'Jakarta-LAX Biz May'),
    ('CGK', 'LAX', '2026-06-01', None, 'Jakarta-LAX Biz Jun'),
    ('CGK', 'LAX', '2026-09-01', None, 'Jakarta-LAX Biz Sep'),
    ('CGK', 'SFO', '2026-05-15', None, 'Jakarta-SFO Biz May'),
    ('CGK', 'SFO', '2026-09-01', None, 'Jakarta-SFO Biz Sep'),
    # RT versions
    ('CGK', 'LHR', '2026-05-15', '2026-06-15', 'Jakarta-London Biz RT'),
    ('CGK', 'FCO', '2026-05-15', '2026-06-15', 'Jakarta-Rome Biz RT'),
    ('CGK', 'LAX', '2026-05-15', '2026-06-15', 'Jakarta-LAX Biz RT'),
    ('CGK', 'CDG', '2026-06-01', '2026-06-29', 'Jakarta-Paris Biz RT Jun'),
]

all_results = []
n = 0

print("JAKARTA BUSINESS CLASS BUG FARE VERIFICATION")
print("=" * 80)

for origin, dest, dep, ret, label in SEARCHES:
    n += 1
    rt = f" RT {ret}" if ret else " OW"

    # Build business class query
    # Google Flights uses ?q= with natural language
    # We need to modify the query to include "business class"
    query_parts = [
        f"business class flights from {origin} to {dest}",
        f"departing {dep}",
    ]
    if ret:
        query_parts.append(f"returning {ret}")
    query = " ".join(query_parts)

    print(f"[{n}/{len(SEARCHES)}] {label}{rt}...", end=' ', flush=True)

    try:
        # Use the raw search with modified query for business class
        import urllib.parse
        import requests
        from bs4 import BeautifulSoup
        import re

        # Build Google Flights business class URL directly
        # tfs parameter approach: cabin=2 for business
        if ret:
            url = f"https://www.google.com/travel/flights?q={urllib.parse.quote(query)}&curr=USD"
        else:
            url = f"https://www.google.com/travel/flights?q={urllib.parse.quote(query)}&curr=USD"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }

        resp = requests.get(url, headers=headers, timeout=30)
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Parse ARIA labels for flight data
        flights = []
        for el in soup.find_all(attrs={"aria-label": True}):
            label_text = el.get("aria-label", "")
            # Look for price patterns
            price_match = re.search(r'\$(\d[\d,]*)', label_text)
            if price_match and ('from' in label_text.lower() or 'depart' in label_text.lower() or len(label_text) > 50):
                price = int(price_match.group(1).replace(',', ''))
                airline_match = re.search(r'(?:on|with)\s+([\w\s]+?)(?:\.|,|\s+from|\s+depart)', label_text)
                airline = airline_match.group(1).strip() if airline_match else '?'

                # Check for stops
                stops = 0
                if 'nonstop' in label_text.lower():
                    stops = 0
                elif '1 stop' in label_text.lower():
                    stops = 1
                elif '2 stop' in label_text.lower():
                    stops = 2

                flights.append({
                    'price': price,
                    'airline': airline,
                    'stops': stops,
                    'raw_label': label_text[:200],
                })

        # Also try the standard searcher (will be economy but useful for comparison)
        std_result = searcher.search(origin=origin, destination=dest, date=dep, return_date=ret)
        std_flights = std_result.get('flights', [])

        total_found = len(flights) + len(std_flights)
        print(f"{len(flights)} biz + {len(std_flights)} economy", flush=True)

        # Print business class finds
        for fl in flights[:5]:
            print(f"    BIZ ${fl['price']:>5}/pp | {fl['airline'][:35]} | {fl['stops']}stop")
            all_results.append({
                'origin': origin, 'destination': dest, 'route': f"{origin}-{dest}",
                'depart_date': dep, 'return_date': ret or '',
                'price_pp': fl['price'], 'airline': fl['airline'],
                'stops': fl['stops'], 'cabin': 'business',
                'label': label,
            })

        # Print cheapest economy for comparison
        for fl in std_flights[:2]:
            price = fl.get('price', 0)
            airline = fl.get('airline', '?')
            print(f"    ECO ${price:>5}/pp | {airline[:35]} | {fl.get('stops','')}stop")

    except Exception as e:
        print(f"ERROR: {e}", flush=True)

    time.sleep(1.5)

# Save and summarize
all_results.sort(key=lambda x: x['price_pp'])

with open('D:/claude/flights/jakarta_biz_results.json', 'w') as f:
    json.dump({'timestamp': datetime.now().isoformat(), 'results': all_results}, f, indent=2)

print("\n" + "=" * 80)
print("BUSINESS CLASS RESULTS (sorted by price):")
print("=" * 80)
for r in all_results[:25]:
    ow = ' OW' if not r.get('return_date') else ' RT'
    print(f"  ${r['price_pp']:>5}/pp | {r['route']:<8} | {r['airline'][:35]:<35} | {r['stops']}stop | {r['depart_date']}{ow}")
