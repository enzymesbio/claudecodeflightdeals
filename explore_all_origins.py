"""
Google Flights Explorer for all origins using Playwright interaction.
Instead of building protobuf URLs, we interact with the Explorer page directly.
"""
import json
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

output_dir = 'D:/claude/flights/explorer_results'
os.makedirs(output_dir, exist_ok=True)


def explore_origin(page, origin_name, origin_label):
    """Use Playwright to search Explorer for an origin city -> USA"""
    print(f'\n{"="*60}')
    print(f'Exploring: {origin_name} -> USA')
    print(f'{"="*60}')

    try:
        # Go to Explorer page
        page.goto('https://www.google.com/travel/explore', wait_until='networkidle', timeout=30000)
        time.sleep(2)

        # Clear and type origin
        origin_input = page.locator('input[placeholder="Where from?"], input[aria-label*="Where from"]').first
        origin_input.click()
        time.sleep(0.5)
        origin_input.fill('')
        time.sleep(0.3)
        origin_input.type(origin_name, delay=50)
        time.sleep(1.5)

        # Click first suggestion
        try:
            suggestion = page.locator('[role="option"], [data-value], li[class*="suggestion"]').first
            suggestion.click()
            time.sleep(1)
        except:
            page.keyboard.press('Enter')
            time.sleep(1)

        # Type destination: United States
        dest_input = page.locator('input[placeholder="Where to?"], input[aria-label*="Where to"]').first
        dest_input.click()
        time.sleep(0.5)
        dest_input.fill('')
        time.sleep(0.3)
        dest_input.type('United States', delay=50)
        time.sleep(1.5)

        try:
            suggestion = page.locator('[role="option"], [data-value], li[class*="suggestion"]').first
            suggestion.click()
            time.sleep(1)
        except:
            page.keyboard.press('Enter')
            time.sleep(1)

        # Wait for results
        time.sleep(4)

        # Screenshot
        screenshot_path = os.path.join(output_dir, f'explorer_{origin_label}_interactive.png')
        page.screenshot(path=screenshot_path, full_page=False)
        print(f'  Screenshot: {screenshot_path}')

        # Get page text
        text = page.inner_text('body')

        # Parse city + price + date pairs
        fares = []
        lines = text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Check if this is a city name followed by a date and price
            if line and not line.startswith('$') and len(line) > 2:
                # Look ahead for date and price
                date_line = lines[i+1].strip() if i+1 < len(lines) else ''
                price_line = lines[i+2].strip() if i+2 < len(lines) else ''

                # Check if date_line looks like a date range
                date_match = re.match(r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+\s*[–-]\s*(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+)?\d+)', date_line)
                price_match = re.match(r'\$(\d[\d,]*)', price_line)

                if date_match and price_match:
                    city = line
                    dates = date_match.group(1)
                    price = int(price_match.group(1).replace(',', ''))

                    # Get stops info if available
                    stops_line = lines[i+3].strip() if i+3 < len(lines) else ''
                    stops = stops_line if 'stop' in stops_line.lower() or 'nonstop' in stops_line.lower() else ''

                    fares.append({
                        'city': city,
                        'dates': dates,
                        'price_rt_pp': price,
                        'price_rt_3pax': int(price * 2.75),
                        'stops': stops,
                        'origin': origin_name,
                    })
                    i += 4
                    continue
            i += 1

        # Also try regex on full text for backup
        if not fares:
            # Pattern: City\nDate range\n$Price
            matches = re.findall(
                r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+National\s+Park)?)\n'
                r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+\s*[–-].*?)\n'
                r'\$(\d[\d,]*)',
                text
            )
            for city, dates, price in matches:
                fares.append({
                    'city': city,
                    'dates': dates.strip(),
                    'price_rt_pp': int(price.replace(',', '')),
                    'price_rt_3pax': int(int(price.replace(',', '')) * 2.75),
                    'origin': origin_name,
                })

        fares.sort(key=lambda x: x['price_rt_pp'])

        print(f'  Found {len(fares)} destination fares:')
        for f in fares[:15]:
            marker = ' ***' if f['price_rt_3pax'] < 2000 else ''
            print(f'    ${f["price_rt_pp"]:,}/pp RT (${f["price_rt_3pax"]:,}/3pax) -> {f["city"]} | {f["dates"]} {f.get("stops","")}{marker}')

        # Save text for debugging
        text_path = os.path.join(output_dir, f'explorer_{origin_label}_interactive_text.txt')
        with open(text_path, 'w', encoding='utf-8') as tf:
            tf.write(text)

        return fares

    except Exception as e:
        print(f'  Error: {e}')
        try:
            screenshot_path = os.path.join(output_dir, f'explorer_{origin_label}_error.png')
            page.screenshot(path=screenshot_path)
        except:
            pass
        return []


def main():
    origins = [
        ('Tokyo', 'TYO'),
        ('Seoul', 'ICN'),
        ('Hong Kong', 'HKG'),
        ('Shanghai', 'PVG'),
        ('Osaka', 'KIX'),
    ]

    all_fares = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1400, 'height': 900},
            locale='en-US',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        )
        context.add_cookies([
            {'name': 'CONSENT', 'value': 'YES+cb.20231008-14-p0.en+FX+999', 'domain': '.google.com', 'path': '/'},
            {'name': 'SOCS', 'value': 'CAISNQgDEitib3FfaWRlbnRpdHlmcm9udGVuZHVpc2VydmVyXzIwMjMxMDA5LjA5X3AwGgJlbiACGgYIgO6JqgY', 'domain': '.google.com', 'path': '/'},
        ])

        page = context.new_page()

        for origin_name, origin_label in origins:
            fares = explore_origin(page, origin_name, origin_label)
            if fares:
                all_fares[origin_label] = fares
            time.sleep(3)

        browser.close()

    # Save all results
    with open(os.path.join(output_dir, 'all_explorer_fares.json'), 'w') as f:
        json.dump(all_fares, f, indent=2)

    # Summary
    print('\n' + '=' * 70)
    print('EXPLORER SUMMARY: Cheapest RT fares to USA by origin')
    print('=' * 70)
    for origin, fares in all_fares.items():
        print(f'\n  From {origin}:')
        for f in fares[:5]:
            marker = ' *** UNDER $2K for 3! ***' if f['price_rt_3pax'] < 2000 else ''
            print(f'    ${f["price_rt_pp"]:,}/pp -> {f["city"]} ({f["dates"]}){marker}')

    print(f'\nAll data saved to {output_dir}/all_explorer_fares.json')


if __name__ == '__main__':
    main()
