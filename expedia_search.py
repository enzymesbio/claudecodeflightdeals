"""Search Expedia for Jakarta business class bug fare."""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/claude/flights')

import requests
import re
import json
import time

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# Expedia flight search URLs
# Expedia uses /Flights-search/ with parameters
searches = [
    # OW CGK-LAX Business
    {
        'label': 'CGK→LAX BIZ OW May 4',
        'url': 'https://www.expedia.com/Flights-search/CGK-LAX/20260504/?cabinclass=business&passengers=adults:1',
    },
    {
        'label': 'CGK→LAX BIZ OW May 8',
        'url': 'https://www.expedia.com/Flights-search/CGK-LAX/20260508/?cabinclass=business&passengers=adults:1',
    },
    {
        'label': 'CGK→LHR BIZ OW May 4',
        'url': 'https://www.expedia.com/Flights-search/CGK-LHR/20260504/?cabinclass=business&passengers=adults:1',
    },
    # RT CGK-LAX Business
    {
        'label': 'CGK→LAX BIZ RT May4-Jun15',
        'url': 'https://www.expedia.com/Flights-search/CGK-LAX/LAX-CGK/20260504-20260615/?cabinclass=business&passengers=adults:1',
    },
    # Also try Expedia.co.id (Indonesian)
    {
        'label': 'CGK→LAX BIZ OW May4 (ID)',
        'url': 'https://www.expedia.co.id/Flights-search/CGK-LAX/20260504/?cabinclass=business&passengers=adults:1',
    },
]

for s in searches:
    print(f"\n{'='*70}")
    print(f"{s['label']}")
    print(f"URL: {s['url']}")
    print(f"{'='*70}")
    try:
        resp = requests.get(s['url'], headers=headers, timeout=30, allow_redirects=True)
        print(f"Status: {resp.status_code}, Length: {len(resp.text)}, Final URL: {resp.url[:120]}")

        # Look for prices
        prices = re.findall(r'\$(\d[\d,]*)', resp.text)
        if prices:
            unique_prices = sorted(set(int(p.replace(',','')) for p in prices if 100 < int(p.replace(',','')) < 50000))
            print(f"Prices found: {unique_prices[:20]}")

        # Look for flight data in JSON
        json_matches = re.findall(r'"price":\s*\{[^}]*"amount":\s*([\d.]+)', resp.text)
        if json_matches:
            print(f"JSON prices: {json_matches[:20]}")

        # Look for any structured data
        offer_matches = re.findall(r'"totalPrice":\s*"?\$?([\d,]+)"?', resp.text)
        if offer_matches:
            print(f"Offer prices: {offer_matches[:20]}")

        # Check for business class confirmation
        if 'business' in resp.text.lower():
            biz_context = [m.start() for m in re.finditer(r'business', resp.text.lower())]
            print(f"'business' appears {len(biz_context)} times in response")

        # Save first response for inspection
        if 'May 4' in s['label'] and 'LAX' in s['label'] and '(ID)' not in s['label']:
            with open('D:/claude/flights/expedia_response.html', 'w', encoding='utf-8') as f:
                f.write(resp.text)
            print("(saved response to expedia_response.html)")

    except Exception as e:
        print(f"ERROR: {e}")

    time.sleep(2)

# Also try the Expedia API-style search
print(f"\n{'='*70}")
print("Trying Expedia API endpoint...")
print(f"{'='*70}")
api_url = "https://www.expedia.com/api/flight/search"
payload = {
    "legs": [
        {"origin": "CGK", "destination": "LAX", "departureDate": "2026-05-04"},
    ],
    "passengers": {"adults": 1},
    "cabinClass": "business",
    "nonstop": False,
}
try:
    resp = requests.post(api_url, json=payload, headers={
        **headers,
        'Content-Type': 'application/json',
    }, timeout=30)
    print(f"Status: {resp.status_code}, Length: {len(resp.text)}")
    if resp.status_code == 200:
        try:
            data = resp.json()
            print(f"Response keys: {list(data.keys())[:10]}")
        except:
            print(f"Not JSON. First 500 chars: {resp.text[:500]}")
    else:
        print(f"First 300 chars: {resp.text[:300]}")
except Exception as e:
    print(f"ERROR: {e}")

print("\n\nNOTE: Expedia likely requires JavaScript rendering.")
print("Try searching directly at:")
print("  https://www.expedia.com/Flights-search/CGK-LAX/20260504/?cabinclass=business")
print("  https://www.expedia.com/Flights-search/CGK-LHR/20260504/?cabinclass=business")
