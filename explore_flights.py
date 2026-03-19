"""
Google Flights Explorer Scraper
Uses Playwright to load Explorer pages, screenshot them, and extract cheap fares.
Then drills down with search_flights.py for precise pricing.
"""
import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

# Freebase MIDs for our origins and destinations
MIDS = {
    'PVG': '/m/06wjf',   # Shanghai
    'HKG': '/m/03hrk',   # Hong Kong
    'NRT': '/m/0d5gx',   # Tokyo Narita
    'TYO': '/m/07dfk',   # Tokyo (city)
    'ICN': '/m/0hsqf',   # Seoul
    'USA': '/m/09c7w0',  # United States
    'LAX': '/m/030qb3t', # Los Angeles
    'SFO': '/m/0d6lp',   # San Francisco
    'SEA': '/m/0d9jr',   # Seattle
}


def build_explorer_url(origin_mid, dest_mid=None, currency='USD'):
    """Build a Google Flights Explorer URL.

    The TFS param is a base64-encoded protobuf. We'll build a simplified version
    that mimics what the Explorer page expects.
    """
    def encode_varint(value):
        result = b''
        while value > 0x7f:
            result += bytes([(value & 0x7f) | 0x80])
            value >>= 7
        result += bytes([value])
        return result

    def encode_varint_field(field_num, value):
        tag = (field_num << 3) | 0
        return encode_varint(tag) + encode_varint(value)

    def encode_bytes_field(field_num, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        tag = (field_num << 3) | 2
        return encode_varint(tag) + encode_varint(len(data)) + data

    # Build origin place
    origin_place = encode_varint_field(1, 2) + encode_bytes_field(2, origin_mid)

    # Build destination place (if specified, otherwise "anywhere")
    if dest_mid:
        dest_place = encode_varint_field(1, 4) + encode_bytes_field(2, dest_mid)
    else:
        dest_place = b''

    # Build the leg (outbound)
    leg1 = encode_bytes_field(5, origin_place)
    if dest_place:
        leg1 += encode_bytes_field(6, dest_place)

    # Build the return leg
    leg2 = b''
    if dest_place:
        leg2 = encode_bytes_field(5, dest_place) + encode_bytes_field(6, origin_place)
    else:
        leg2 = encode_bytes_field(5, b'') + encode_bytes_field(6, origin_place)

    # Main message
    msg = (
        encode_varint_field(1, 28) +
        encode_varint_field(2, 3) +  # explore mode
        encode_bytes_field(3, leg1) +
        encode_bytes_field(3, leg2) +
        encode_varint_field(8, 1) +  # 1 adult
        encode_varint_field(10, 1) +
        encode_varint_field(16, 2) +
        encode_bytes_field(17,
            encode_varint_field(3, 1) +
            encode_varint_field(4, 1)
        )
    )

    tfs = base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')

    url = (
        f'https://www.google.com/travel/explore'
        f'?tfs={tfs}'
        f'&tfu=GgA'
        f'&tcfs=UgRgAXgB'
        f'&curr={currency}'
    )
    return url


def run_explorer():
    from playwright.sync_api import sync_playwright

    output_dir = 'D:/claude/flights/explorer_results'
    os.makedirs(output_dir, exist_ok=True)

    # Origins to explore
    origins = [
        ('PVG', 'Shanghai'),
        ('TYO', 'Tokyo'),
        ('ICN', 'Seoul'),
        ('HKG', 'Hong Kong'),
    ]

    all_fares = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1400, 'height': 900},
            locale='en-US',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        )

        # Set consent cookies to bypass Google consent page
        context.add_cookies([
            {'name': 'CONSENT', 'value': 'YES+cb.20231008-14-p0.en+FX+999', 'domain': '.google.com', 'path': '/'},
            {'name': 'SOCS', 'value': 'CAISNQgDEitib3FfaWRlbnRpdHlmcm9udGVuZHVpc2VydmVyXzIwMjMxMDA5LjA5X3AwGgJlbiACGgYIgO6JqgY', 'domain': '.google.com', 'path': '/'},
        ])

        page = context.new_page()

        for origin_code, origin_name in origins:
            origin_mid = MIDS[origin_code]
            print(f'\n{"="*60}')
            print(f'Exploring: {origin_name} ({origin_code}) -> USA')
            print(f'{"="*60}')

            # Build Explorer URL: origin -> USA
            url = build_explorer_url(origin_mid, MIDS['USA'])
            print(f'  URL: {url[:100]}...')

            try:
                page.goto(url, wait_until='networkidle', timeout=30000)
                time.sleep(3)  # Let dynamic content load

                # Take screenshot
                screenshot_path = os.path.join(output_dir, f'explorer_{origin_code}_to_USA.png')
                page.screenshot(path=screenshot_path, full_page=False)
                print(f'  Screenshot saved: {screenshot_path}')

                # Try to extract fare data from the page
                # Look for price elements in the Explorer view
                html = page.content()

                # Parse prices from various patterns in Explorer
                fares_found = []

                # Pattern 1: City cards with prices (Explorer shows destination cards)
                # Look for aria-labels with price info
                price_labels = re.findall(r'aria-label="([^"]*\$\d[^"]*)"', html)
                for label in price_labels:
                    # Extract city and price
                    price_match = re.search(r'\$(\d[\d,]*)', label)
                    if price_match:
                        price = int(price_match.group(1).replace(',', ''))
                        fares_found.append({
                            'label': label[:200],
                            'price': price,
                        })

                # Pattern 2: Look for data attributes or structured content
                price_elements = re.findall(r'>\$(\d[\d,]*)<', html)
                for pe in price_elements:
                    price = int(pe.replace(',', ''))
                    if 50 < price < 5000:  # Reasonable flight price range
                        fares_found.append({
                            'label': 'price_element',
                            'price': price,
                        })

                # Pattern 3: JSON-LD or embedded data
                json_blocks = re.findall(r'data-fare="(\d+)"', html)
                for jb in json_blocks:
                    fares_found.append({
                        'label': 'data-fare',
                        'price': int(jb),
                    })

                # Pattern 4: Look for destination names near prices
                dest_price_pairs = re.findall(
                    r'(?:Los Angeles|San Francisco|New York|Seattle|Houston|Chicago|Miami|Las Vegas|San Diego|Portland|Denver|Phoenix|Dallas|Atlanta|Boston|Orlando|Tampa|Washington)'
                    r'[^$]{0,100}\$(\d[\d,]*)',
                    html
                )
                for dp in dest_price_pairs:
                    fares_found.append({
                        'label': 'city_price_pair',
                        'price': int(dp.replace(',', '')),
                    })

                # Also try to get text content from specific elements
                try:
                    # Get all visible text with prices
                    price_texts = page.query_selector_all('[class*="price"], [class*="fare"], [data-price]')
                    for elem in price_texts[:20]:
                        text = elem.inner_text()
                        pm = re.search(r'\$(\d[\d,]*)', text)
                        if pm:
                            fares_found.append({
                                'label': 'element_text: ' + text[:100],
                                'price': int(pm.group(1).replace(',', '')),
                            })
                except:
                    pass

                # Try getting all text on page to find prices
                try:
                    all_text = page.inner_text('body')
                    # Find lines with dollar amounts
                    for line in all_text.split('\n'):
                        line = line.strip()
                        if '$' in line and len(line) < 200:
                            pm = re.search(r'\$(\d[\d,]*)', line)
                            if pm:
                                price = int(pm.group(1).replace(',', ''))
                                if 100 < price < 5000:
                                    fares_found.append({
                                        'label': 'text: ' + line[:150],
                                        'price': price,
                                    })
                except:
                    pass

                # Deduplicate
                seen = set()
                unique_fares = []
                for f in fares_found:
                    key = (f['price'], f['label'][:50])
                    if key not in seen:
                        seen.add(key)
                        unique_fares.append(f)

                unique_fares.sort(key=lambda x: x['price'])

                all_fares[origin_code] = unique_fares

                print(f'  Found {len(unique_fares)} fare entries:')
                for f in unique_fares[:15]:
                    print(f'    ${f["price"]:,} - {f["label"][:100]}')

                if not unique_fares:
                    # Save HTML for debugging
                    html_path = os.path.join(output_dir, f'explorer_{origin_code}_raw.html')
                    with open(html_path, 'w', encoding='utf-8') as hf:
                        hf.write(html)
                    print(f'  No fares parsed - raw HTML saved to {html_path}')

                    # Also try getting page text
                    try:
                        text = page.inner_text('body')
                        text_path = os.path.join(output_dir, f'explorer_{origin_code}_text.txt')
                        with open(text_path, 'w', encoding='utf-8') as tf:
                            tf.write(text)
                        print(f'  Page text saved to {text_path}')
                        # Show first few lines with $
                        for line in text.split('\n')[:50]:
                            if '$' in line.strip():
                                print(f'    >> {line.strip()[:120]}')
                    except:
                        pass

            except Exception as e:
                print(f'  Error: {e}')
                # Take screenshot of whatever loaded
                try:
                    screenshot_path = os.path.join(output_dir, f'explorer_{origin_code}_error.png')
                    page.screenshot(path=screenshot_path)
                    print(f'  Error screenshot saved: {screenshot_path}')
                except:
                    pass

            time.sleep(2)

        # Also try a direct search URL (the one user shared style)
        print(f'\n{"="*60}')
        print('Trying user-style Explorer URL...')
        print(f'{"="*60}')

        # Use the user's URL format directly for PVG -> USA
        try:
            user_style_url = 'https://www.google.com/travel/explore?tfs=CBwQAxodagwIAhIIL20vMDZ3amZyDQgEEgkvbS8wOWM3dzAaHWoNCAQSCS9tLzA5Yzd3MHIMCAISCCptLzA2d2pmQAFIAXACggENCP___________wEQA5gBAQ&tfu=GgA&tcfs=UgRgAXgB&curr=USD'
            page.goto(user_style_url, wait_until='networkidle', timeout=30000)
            time.sleep(4)

            screenshot_path = os.path.join(output_dir, 'explorer_PVG_USA_direct.png')
            page.screenshot(path=screenshot_path, full_page=False)
            print(f'  Screenshot: {screenshot_path}')

            # Get all text
            text = page.inner_text('body')
            text_path = os.path.join(output_dir, 'explorer_PVG_USA_direct_text.txt')
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(text)

            # Find prices
            print('  Fares found in text:')
            for line in text.split('\n'):
                line = line.strip()
                if '$' in line and len(line) < 200 and len(line) > 2:
                    print(f'    {line[:120]}')
        except Exception as e:
            print(f'  Error: {e}')

        browser.close()

    # Save all fare data
    with open(os.path.join(output_dir, 'explorer_fares.json'), 'w') as f:
        json.dump(all_fares, f, indent=2)

    print(f'\nAll data saved to {output_dir}/')
    return all_fares


if __name__ == '__main__':
    fares = run_explorer()
