"""Search ITA Matrix for Jakarta business class bug fare."""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/claude/flights')

import requests
import json
import re
import time

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': 'https://matrix.itasoftware.com',
    'Referer': 'https://matrix.itasoftware.com/',
})

# ITA Matrix uses a JSON API
# First, get the page to establish session
print("Fetching ITA Matrix page...")
try:
    resp = session.get('https://matrix.itasoftware.com/', timeout=30)
    print(f"Status: {resp.status_code}, Length: {len(resp.text)}")
except Exception as e:
    print(f"ERROR: {e}")

# ITA Matrix API endpoint
api_url = 'https://matrix.itasoftware.com/search'

# The actual ITA Matrix uses a complex RPC API
# Let's try the known endpoint format
searches = [
    ('CGK', 'LAX', '2026-05-04', None, 'CGK-LAX OW May4'),
    ('CGK', 'LAX', '2026-05-08', None, 'CGK-LAX OW May8'),
    ('CGK', 'LHR', '2026-05-04', None, 'CGK-LHR OW May4'),
    ('CGK', 'LAX', '2026-05-04', '2026-06-15', 'CGK-LAX RT May4-Jun15'),
]

# ITA Matrix uses Google's QPX Express-like API internally
# The actual API format - let's try
for origin, dest, dep, ret, label in searches:
    print(f"\n{'='*60}")
    print(f"ITA Matrix: {label} BUSINESS CLASS")
    print(f"{'='*60}")

    slices = [{"origin": origin, "destination": dest, "date": dep}]
    if ret:
        slices.append({"origin": dest, "destination": origin, "date": ret})

    # Try the known ITA Matrix RPC format
    payload = {
        "method": "search",
        "params": {
            "slices": slices,
            "pax": {"adults": 1},
            "cabin": "BUSINESS",
            "currency": "USD",
            "sales_city": origin,
        }
    }

    try:
        resp = session.post(
            'https://matrix.itasoftware.com/api/search',
            json=payload,
            timeout=30
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            try:
                data = resp.json()
                print(f"Response: {json.dumps(data, indent=2)[:1000]}")
            except:
                print(f"Response: {resp.text[:500]}")
        else:
            print(f"Response: {resp.text[:300]}")
    except Exception as e:
        print(f"ERROR: {e}")

    time.sleep(1)

# Try the Google Flights proper TFS approach with Playwright
print(f"\n{'='*60}")
print("Attempting Playwright approach for Google Flights...")
print(f"{'='*60}")

try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
        )
        page = context.new_page()

        # Use the user's exact TFS URL format for business class
        urls = [
            ('CGK-LAX BIZ RT May8-Jun15',
             'https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA1LTA4agcIARIDQ0dLcgcIARIDTEFYGh4SCjIwMjYtMDYtMTVqBwgBEgNMQVhyBwgBEgNDR0tAAUgDcAGCAQsI____________AZgBAQ&curr=USD'),
            ('CGK-LAX BIZ OW May4',
             'https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA1LTA0agcIARIDQ0dLcgcIARIDTEFYQAFIA3ABggELCP___________wGYAQE&curr=USD'),
            ('CGK-LHR BIZ OW May4',
             'https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA1LTA0agcIARIDQ0dLcgcIARIDTEhSQAFIA3ABggELCP___________wGYAQE&curr=USD'),
        ]

        for label, url in urls:
            print(f"\n  {label}...")
            try:
                page.goto(url, wait_until='networkidle', timeout=60000)
                time.sleep(3)

                # Accept cookies if needed
                try:
                    page.click('button:has-text("Accept")', timeout=3000)
                    time.sleep(1)
                except:
                    pass

                # Get all text content
                content = page.content()

                # Extract prices from ARIA labels
                prices_found = []
                elements = page.query_selector_all('[aria-label]')
                for el in elements:
                    aria = el.get_attribute('aria-label') or ''
                    price_match = re.search(r'(\d[\d,]*)\s*(?:US\s*)?dollars?', aria)
                    if price_match and len(aria) > 30:
                        price = int(price_match.group(1).replace(',', ''))
                        if price > 50:
                            airline_match = re.search(r'flight with ([^.]+)', aria)
                            airline = airline_match.group(1) if airline_match else '?'
                            stops_match = re.search(r'(Nonstop|\d+ stops?)', aria)
                            stops = stops_match.group(1) if stops_match else '?'
                            dur_match = re.search(r'(\d+ hr\s*(?:\d+ min)?)', aria)
                            dur = dur_match.group(1) if dur_match else '?'
                            prices_found.append((price, airline, stops, dur))
                            if len(prices_found) <= 10:
                                print(f"    ${price:>5} | {airline[:40]} | {stops} | {dur}")

                if not prices_found:
                    print("    No prices found in ARIA labels")
                    # Try screenshot
                    page.screenshot(path=f'D:/claude/flights/gf_biz_{label.replace(" ","_")}.png')
                    print(f"    Screenshot saved")
                else:
                    print(f"    Total: {len(prices_found)} flights found")
                    prices_only = sorted([p[0] for p in prices_found])
                    print(f"    Price range: ${min(prices_only)} - ${max(prices_only)}")

            except Exception as e:
                print(f"    ERROR: {e}")

        browser.close()

except ImportError:
    print("Playwright not installed. Try: pip install playwright && playwright install chromium")
except Exception as e:
    print(f"Playwright error: {e}")

print("\nDONE")
