"""
Deep verification: Load Google Flights search pages for bug fares,
extract top 3 flight options with actual booking platform links.

Output: verification_results.json with booking URLs for each bug fare route.
"""
import sys
import os
import json
import re
import time
import base64
from datetime import datetime, timedelta

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

# --- Protobuf helpers (same as scanner) ---
def encode_varint(value):
    result = b''
    while value > 0x7f:
        result += bytes([(value & 0x7f) | 0x80])
        value >>= 7
    result += bytes([value])
    return result

def field_varint(num, val):
    return encode_varint((num << 3) | 0) + encode_varint(val)

def field_bytes(num, data):
    if isinstance(data, str): data = data.encode('utf-8')
    return encode_varint((num << 3) | 2) + encode_varint(len(data)) + data

# City IDs (verified via Wikidata)
CITY_IDS = {
    'Jakarta': '/m/044rv', 'Kuala Lumpur': '/m/049d1', 'Bangkok': '/m/0fn2g',
    'Singapore': '/m/06t2t', 'Manila': '/m/0195pd', 'Ho Chi Minh City': '/m/0hn4h',
    'Hong Kong': '/m/03h64', 'Taipei': '/m/0ftkx', 'Seoul': '/m/0hsqf',
    'Tokyo': '/m/07dfk', 'Shanghai': '/m/06wjf', 'Hangzhou': '/m/014vm4',
    'Ningbo': '/m/01l33l', 'Beijing': '/m/01914', 'Guangzhou': '/m/0393g',
    'Chengdu': '/m/016v46', 'Chongqing': '/m/017236', 'Shenzhen': '/m/0lbmv',
}
US_CITY_ID = '/m/09c7w0'

# US destination city IDs for building search URLs
US_DEST_IDS = {
    'Los Angeles': '/m/030qb3t', 'Houston': '/m/04lh6', 'New York': '/m/02_286',
    'San Francisco': '/m/0d6lp', 'Chicago': '/m/01_d4', 'Washington, D.C.': '/m/0rh6k',
    'Denver': '/m/02cl1', 'Las Vegas': '/m/0cv3w', 'Seattle': '/m/0d9jr',
    'Boston': '/m/01cx_', 'Miami': '/m/0f2v0', 'Atlanta': '/m/013yq',
    'Tampa': '/m/0hyxv', 'Dallas': '/m/0f2rq', 'Portland': '/m/0fwwg',
    'Philadelphia': '/m/0k_q', 'Orlando': '/m/0fhp9', 'Charlotte': '/m/0fttg',
    'San Diego': '/m/0d6lp', 'Baltimore': '/m/0k_p0', 'Pittsburgh': '/m/068p2',
    'Fort Lauderdale': '/m/0fvyg', 'Detroit': '/m/02dtg',
}

def build_explore_url(origin_city_id, date=None, cabin=3):
    if not date:
        date = (datetime.now() + timedelta(days=120)).strftime('%Y-%m-%d')
    origin_msg = field_varint(1, 3) + field_bytes(2, origin_city_id)
    dest_msg = field_varint(1, 4) + field_bytes(2, US_CITY_ID)
    leg1 = field_bytes(2, date) + field_bytes(13, origin_msg) + field_bytes(14, dest_msg)
    leg2 = field_bytes(13, dest_msg) + field_bytes(14, origin_msg)
    pax_config = b'\x08\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01'
    field22 = field_varint(3, 1) + field_varint(4, 1)
    msg = (field_varint(1, 28) + field_varint(2, 3) + field_bytes(3, leg1) +
           field_bytes(3, leg2) + field_varint(8, 1) + field_varint(9, cabin) +
           field_varint(14, 2) + field_bytes(16, pax_config) + field_varint(19, 1) +
           field_bytes(22, field22))
    tfs = base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')
    return f'https://www.google.com/travel/explore?tfs={tfs}&tfu=GgA&hl=en&gl=hk&curr=USD'


def extract_flights_from_search_page(page, url, max_flights=3, wait_sec=8):
    """Load a Google Flights search URL and extract top flight options with booking links."""
    print(f"  Loading search page...")
    page.goto(url, timeout=30000)
    time.sleep(wait_sec)

    flights = []

    # Extract flight info from ARIA labels on result cards
    # Google Flights results have role="listitem" or data attributes
    # Each flight result contains: airline, times, duration, stops, price
    try:
        # Method 1: Extract from list items with price info
        # The results page has flight cards with structured data
        body_text = page.inner_text('body')

        # Find "Book with" or booking links by looking at all <a> tags
        booking_links = page.evaluate("""() => {
            const results = [];
            // Find all clickable flight result rows
            const rows = document.querySelectorAll('li[class*="pIav2d"], div[class*="yR1fYc"], ul[class*="Rk10dc"] > li');

            for (let i = 0; i < Math.min(rows.length, 10); i++) {
                const row = rows[i];
                const text = row.innerText;
                // Extract price from the row
                const priceMatch = text.match(/\\$(\\d[\\d,]*)/);
                // Extract airline
                const lines = text.split('\\n').filter(l => l.trim());
                results.push({
                    text: lines.slice(0, 6).join(' | '),
                    price: priceMatch ? priceMatch[0] : null,
                    hasBookLink: !!row.querySelector('a[href*="book"], a[href*="flights/booking"]')
                });
            }
            return results;
        }""")

        # Try to find and click the first few flight results to get booking links
        # Google Flights: clicking a result expands it with booking options
        flight_items = page.query_selector_all('li[class*="pIav2d"]')
        if not flight_items:
            flight_items = page.query_selector_all('ul.Rk10dc > li')

        print(f"  Found {len(flight_items)} flight result rows")

        for i, item in enumerate(flight_items[:max_flights]):
            flight_info = {'rank': i + 1}

            try:
                # Get text before clicking
                item_text = item.inner_text()
                lines = [l.strip() for l in item_text.split('\n') if l.strip()]

                # Parse basic info from text
                price_match = re.search(r'\$(\d[\d,]*)', item_text)
                flight_info['price'] = price_match.group(0) if price_match else None

                # Extract airline, duration, stops from lines
                for line in lines:
                    if re.match(r'\d+:\d+ [AP]M', line) or re.match(r'\d+:\d+$', line):
                        flight_info.setdefault('times', []).append(line)
                    elif 'hr' in line and 'min' in line:
                        flight_info['duration'] = line
                    elif re.match(r'^(Nonstop|\d+ stops?)$', line, re.I):
                        flight_info['stops'] = line
                    elif not price_match or line != price_match.group(0):
                        if 'airline' not in flight_info and len(line) > 2 and not line.startswith('$'):
                            flight_info['airline'] = line

                # Click to expand and find booking links
                try:
                    item.click()
                    time.sleep(3)

                    # Look for booking links in the expanded panel
                    book_links = page.evaluate("""() => {
                        const links = [];
                        // "Book with" links or booking buttons
                        const bookButtons = document.querySelectorAll(
                            'a[href*="flights/booking"], a[data-ved][href*="http"]'
                        );
                        for (const btn of bookButtons) {
                            const href = btn.href || btn.getAttribute('href');
                            const text = btn.innerText.trim();
                            if (href && text && (text.includes('Book') || text.includes('$') || text.includes('Select'))) {
                                links.push({url: href, text: text});
                            }
                        }

                        // Also look for the booking sidebar/panel
                        const bookingOptions = document.querySelectorAll(
                            'div[class*="BVAVmf"] a, div[class*="booking"] a, a[class*="booking"]'
                        );
                        for (const opt of bookingOptions) {
                            const href = opt.href || opt.getAttribute('href');
                            const text = opt.innerText.trim();
                            if (href && text) {
                                links.push({url: href, text: text});
                            }
                        }

                        // Generic: find all links that look like OTA/airline booking
                        const allLinks = document.querySelectorAll('a[href]');
                        for (const a of allLinks) {
                            const href = a.href;
                            const text = a.innerText.trim();
                            if (href && text && text.includes('$') &&
                                (href.includes('booking') || href.includes('redirect') ||
                                 href.includes('partner'))) {
                                links.push({url: href, text: text.substring(0, 80)});
                            }
                        }

                        return links.slice(0, 5);
                    }""")

                    flight_info['booking_links'] = book_links
                    print(f"    Flight {i+1}: {flight_info.get('airline','?')} {flight_info.get('price','?')} - {len(book_links)} booking links")

                except Exception as click_err:
                    print(f"    Flight {i+1}: click failed - {click_err}")

            except Exception as e:
                print(f"    Flight {i+1}: parse error - {e}")

            flights.append(flight_info)

        # Also extract ALL visible booking links from the page as a fallback
        all_page_links = page.evaluate("""() => {
            const links = [];
            const allA = document.querySelectorAll('a[href]');
            for (const a of allA) {
                const href = a.href;
                const text = a.innerText.trim();
                // Look for airline/OTA booking redirects
                if (href && (
                    href.includes('googleadservices') ||
                    href.includes('flights/booking') ||
                    href.includes('redirect') ||
                    (text.includes('$') && href.includes('http'))
                )) {
                    if (text.length > 0 && text.length < 100) {
                        links.push({url: href, text: text});
                    }
                }
            }
            return links.slice(0, 10);
        }""")

        return {
            'flights': flights,
            'page_booking_links': all_page_links,
            'total_results_found': len(flight_items),
        }

    except Exception as e:
        print(f"  Error extracting flights: {e}")
        return {'flights': [], 'page_booking_links': [], 'error': str(e)}


def verify_bug_fares(results_files, output_file='verification_results.json', max_verify=20):
    """Load bug fares from scan results and verify each with booking links."""

    # Merge results from all scan files
    all_bug_fares = []
    for rf in results_files:
        if not os.path.exists(rf):
            continue
        with open(rf, encoding='utf-8') as f:
            data = json.load(f)
        for d in data.get('destinations', []):
            if d.get('classification') == 'BUG_FARE' and d.get('price_usd', 99999) * 2.75 <= 3000:
                all_bug_fares.append(d)

    # Sort by price (cheapest first)
    all_bug_fares.sort(key=lambda x: x.get('price_usd', 99999))

    # Deduplicate by origin+destination+cabin
    seen = set()
    unique_fares = []
    for f in all_bug_fares:
        key = (f['origin_city'], f['destination'], f['cabin_num'])
        if key not in seen:
            seen.add(key)
            unique_fares.append(f)
    unique_fares = unique_fares[:max_verify]

    print(f"\n{'='*70}")
    print(f"  DEEP VERIFICATION - Extracting booking links")
    print(f"  Bug fares to verify: {len(unique_fares)}")
    print(f"{'='*70}\n")

    verified = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 900},
            locale='en-US',
        )
        page = context.new_page()

        # Accept cookies on first page
        page.goto('https://www.google.com/travel/flights?hl=en&gl=hk&curr=USD', timeout=30000)
        time.sleep(2)
        try:
            accept_btn = page.query_selector('button:has-text("Accept all")')
            if accept_btn:
                accept_btn.click()
                time.sleep(1)
        except:
            pass

        for idx, fare in enumerate(unique_fares):
            origin = fare['origin_city']
            dest = fare['destination']
            cabin = fare['cabin_num']
            price = fare['price_usd']
            dates = fare.get('dates', '')

            print(f"\n[{idx+1}/{len(unique_fares)}] {origin} -> {dest} | {fare['cabin']} | ${price:.0f}")

            # Use the scanner's verified detail URL if available
            detail_url = fare.get('verification', {}).get('detail_url', '')

            if not detail_url:
                # Build an Explore URL — user will need to click through
                origin_id = CITY_IDS.get(origin, '')
                if origin_id:
                    # Parse departure date from dates string
                    depart = None
                    if dates:
                        dates_clean = dates.replace('\u2009', ' ').replace('\u2013', '-')
                        parts = dates_clean.split('-')
                        if len(parts) == 2:
                            months = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
                            try:
                                sp = parts[0].strip().split()
                                depart = f"2026-{months[sp[0]]:02d}-{int(sp[1]):02d}"
                            except:
                                pass
                    detail_url = build_explore_url(origin_id, date=depart, cabin=cabin)
                    print(f"  No search URL — using Explore URL")

            if not detail_url:
                print(f"  SKIP — no URL available")
                continue

            # Load and extract
            result = extract_flights_from_search_page(page, detail_url, max_flights=3)

            verified.append({
                'origin_city': origin,
                'origin_code': fare.get('origin_code', ''),
                'destination': dest,
                'cabin': fare['cabin'],
                'cabin_num': cabin,
                'scanner_price_usd': price,
                'dates': dates,
                'search_url': detail_url,
                'verification': result,
                'verified_at': datetime.now().isoformat(),
            })

        browser.close()

    # Save
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'verification_timestamp': datetime.now().isoformat(),
            'total_verified': len(verified),
            'results': verified,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*70}")
    print(f"  VERIFICATION COMPLETE")
    print(f"  Verified: {len(verified)} fares")
    print(f"  Results: {output_file}")
    print(f"{'='*70}")

    return verified


if __name__ == '__main__':
    import glob

    # Find all scan result files
    scan_files = glob.glob('D:/claude/flights/scan_group*.json')
    scan_files.append('D:/claude/flights/scanner_results.json')
    scan_files = [f for f in scan_files if os.path.exists(f)]

    print(f"Scan files found: {scan_files}")
    verify_bug_fares(scan_files)
