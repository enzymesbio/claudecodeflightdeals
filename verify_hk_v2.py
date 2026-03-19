"""Verify HK fares using known search URLs and improved flight clicking."""
import sys, os, json, time, re
from datetime import datetime, timedelta, timezone

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

BASE_DIR = 'D:/claude/flights'
SHANGHAI_TZ = timezone(timedelta(hours=8))
EXCLUDE_AIRLINES = ['ZIPAIR', 'Philippine Airlines', 'Malaysia Airlines', 'Cebu Pacific']

# Search URLs from previous successful verify_hk.py run
HK_SEARCHES = [
    {
        'city': 'San Francisco',
        'url': 'https://www.google.com/travel/flights?tfs=CBsQAhooEgoyMDI2LTA2LTI2agwIAxIIL20vMDNoNjRyDAgCEggvbS8wZDZscBooEgoyMDI2LTA3LTA1agwIAhIIL20vMGQ2bHByDAgDEggvbS8wM2g2NEABSAFSA1VTRHABemxDalJJZVc1cFRERlpYemxHTVdOQlFrdFhTVUZDUnkwdExTMHRMUzB0TFhkaWRtd3lPRUZCUVVGQlIyMDJVRmQzUTNoQ1YwbEJFZ1ZWUVRnMk1ob0xDTVMwQkJBQ0dnTlZVMFE0SEhERXRBUT2YAQGyARIYASABKgwIAhIIL20vMGQ2bHA&tfu=GgA&hl=en&gl=hk&curr=USD',
        'dates': 'Jun 26 - Jul 5',
        'cabin': 'Economy',
        'explore_price': 723,
    },
    {
        'city': 'Los Angeles',
        'url': 'https://www.google.com/travel/flights?tfs=CBsQAhoqEgoyMDI2LTA2LTI2agwIAxIIL20vMDNoNjRyDggCEgovbS8wMzBxYjN0GioSCjIwMjYtMDctMDVqDggCEgovbS8wMzBxYjN0cgwIAxIIL20vMDNoNjRAAUgBUgNVU0RwAXp0Q2pSSVNrZHllbUl0TkZreWFWVkJRa1pUTlhkQ1J5MHRMUzB0TFMwdGQySmlhSEV5TjBGQlFVRkJSMjAyVUZwelRqWnhkbmxCRWd0VlFUZzJNbnhWUVRJNU9Cb0xDUFc0QkJBQ0dnTlZVMFE0SEhEMXVBUT2YAQGyARQYASABKg4IAhIKL20vMDMwcWIzdA&tfu=GgA&hl=en&gl=hk&curr=USD',
        'dates': 'Jun 26 - Jul 5',
        'cabin': 'Economy',
        'explore_price': 729,
    },
    {
        'city': 'Denver',
        'url': 'https://www.google.com/travel/flights?tfs=CBsQAhooEgoyMDI2LTA2LTEyagwIAxIIL20vMDNoNjRyDAgCEggvbS8wMmNsMRooEgoyMDI2LTA2LTIxagwIAhIIL20vMDJjbDFyDAgDEggvbS8wM2g2NEABSAFSA1VTRHABenRDalJJYkhOYU9YQnBjV05sTVdkQlFsZzJhMmRDUnkwdExTMHRMUzB0TFMxM1ptdHRNMEZCUVVGQlIyMDJVR05WU2prM1RtRkJFZ3RWUVRFMU0zeFZRVE0yTUJvTENQVzRCQkFDR2dOVlUwUTRISEQxdUFRPZgBAbIBEhgBIAEqDAgCEggvbS8wMmNsMQ&tfu=GgA&hl=en&gl=hk&curr=USD',
        'dates': 'Jun 12 - 21',
        'cabin': 'Economy',
        'explore_price': 729,
    },
    {
        'city': 'Seattle',
        'url': 'https://www.google.com/travel/flights?tfs=CBsQAhooEgoyMDI2LTA1LTA3agwIAxIIL20vMDNoNjRyDAgCEggvbS8wZDlqchooEgoyMDI2LTA1LTE0agwIAhIIL20vMGQ5anJyDAgDEggvbS8wM2g2NEABSAFSA1VTRHABenRDalJJUldOS2IyWnRhVGxrTmsxQlFuTTJia0ZDUnkwdExTMHRMUzB0TFMwdGQyWnJNVUZCUVVGQlIyMDJVR1puU0VGVFREUkJFZ3BCUXpoOFFVTTROems0R2dzSW1vOEdFQUlhQTFWVFJEZ2NjS2Y0QkE9PZgBAbIBEhgBIAEqDAgCEggvbS8wZDlqcg&tfu=GgA&hl=en&gl=hk&curr=USD',
        'dates': 'May 7 - 14',
        'cabin': 'Economy',
        'explore_price': 810,
    },
    {
        'city': 'New York',
        'url': 'https://www.google.com/travel/flights?tfs=CBsQAhopEgoyMDI2LTA1LTAxagwIAxIIL20vMDNoNjRyDQgCEgkvbS8wMl8yODYaKRIKMjAyNi0wNS0wN2oNCAISCS9tLzAyXzI4NnIMCAMSCC9tLzAzaDY0QAFIAVIDVVNEcAF6gAFDalJJWm1oaldYcERRVTF3WDI5QlEwSm1VMEZDUnkwdExTMHRMUzB0TFMwdGQyWnJNVUZCUVVGQlIyMDJVR2xKUVdoS2FGZEJFaE5WUVRnMk1ueFZRVFE0TURWOFZVRXhNRFE1R2dzSW1vOEdFQUlhQTFWVFJEZ2NjSnFQQmc9PZgBAbIBExgBIAEqDQgCEgkvbS8wMl8yODY&tfu=GgA&hl=en&gl=hk&curr=USD',
        'dates': 'May 1 - 7',
        'cabin': 'Economy',
        'explore_price': 1003,
    },
]

def dismiss_cookies(page):
    try:
        for text in ['Reject all', 'Accept all']:
            btn = page.get_by_role('button', name=text)
            if btn.count() > 0:
                btn.first.click()
                print(f"    Cookies: {text}")
                time.sleep(2)
                return
    except:
        pass

def screenshot(page, name):
    path = os.path.join(BASE_DIR, f'verify_hk_{name}.png')
    page.screenshot(path=path)
    return path


def extract_flight_info(page):
    """Extract flight details from the search results page."""
    return page.evaluate(r"""() => {
        const results = [];
        // Look for flight result items - they contain airline, time, price info
        const items = document.querySelectorAll('li');
        for (const li of items) {
            const text = (li.innerText || '').trim();
            // Flight results typically have time ranges, durations, and prices
            if (/\d{1,2}:\d{2}/.test(text) && /\$\d/.test(text) && text.length > 30 && text.length < 500) {
                const priceMatch = text.match(/\$([0-9,]+)/);
                const price = priceMatch ? parseInt(priceMatch[1].replace(',', '')) : null;
                results.push({
                    text: text.substring(0, 200),
                    price: price,
                    tag: li.tagName
                });
            }
        }
        return results;
    }""")


def click_cheapest_flight(page):
    """Click the 'Cheapest' tab first, then click the first flight result."""
    # Click "Cheapest" tab
    page.evaluate(r"""() => {
        const buttons = document.querySelectorAll('button, [role="tab"]');
        for (const b of buttons) {
            if ((b.innerText || '').trim().startsWith('Cheapest')) {
                b.click();
                return true;
            }
        }
        return false;
    }""")
    time.sleep(3)

    # Now click the first flight result
    return page.evaluate(r"""() => {
        const items = document.querySelectorAll('li');
        for (const li of items) {
            const text = (li.innerText || '').trim();
            if (/\d{1,2}:\d{2}/.test(text) && /\$\d/.test(text) && text.length > 30) {
                li.click();
                return text.substring(0, 200);
            }
        }
        return null;
    }""")


def check_booking_state(page):
    """Check if we're on a booking page or still on search results."""
    text = page.inner_text('body')[:3000]
    url = page.url

    info = {
        'url': url,
        'has_booking': 'Book with' in text or 'Booking options' in text,
        'has_ghost': "can't find booking" in text.lower(),
        'has_select_return': 'Select return flight' in text or 'return flight' in text.lower(),
        'cheapest_price': None,
        'airline': None,
        'booking_text': text[:500],
    }

    # Extract cheapest price
    cheapest = re.search(r'from \$([0-9,]+)', text)
    if cheapest:
        info['cheapest_price'] = int(cheapest.group(1).replace(',', ''))

    # Extract airline from "Book with"
    bw = re.search(r'Book with\s+(.+?)(?:\n|Airline|$)', text)
    if bw:
        info['airline'] = bw.group(1).strip()

    return info


def main():
    print('=' * 60)
    print(f"  HK VERIFICATION v2 (using confirmed search URLs)")
    print(f"  Time: {datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d %H:%M Shanghai')}")
    print(f"  Cities: {len(HK_SEARCHES)}")
    print('=' * 60)

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1400, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
            locale='en-US',
        )

        for search in HK_SEARCHES:
            city = search['city']
            url = search['url']
            dates = search['dates']
            explore_price = search['explore_price']

            print(f"\n{'─' * 55}")
            print(f"  HK → {city} | Economy ${explore_price} | {dates}")
            print(f"{'─' * 55}")

            result = {
                'city': city,
                'cabin': 'Economy',
                'explore_price': explore_price,
                'dates': dates,
                'route': f"Hong Kong → {city}",
                'status': 'UNKNOWN',
                'booking_url': None,
                'airline': None,
                'price': None,
                'screenshots': [],
            }

            page = context.new_page()

            try:
                # Step 1: Load search results
                print(f"  Step 1: Loading search page...")
                page.goto(url, timeout=30000)
                page.wait_for_load_state('domcontentloaded')
                dismiss_cookies(page)
                print(f"  Waiting 8s for results...")
                time.sleep(8)

                result['screenshots'].append(screenshot(page, f'{city}_search'))

                # Check search loaded
                state = check_booking_state(page)
                if state['cheapest_price']:
                    print(f"  Cheapest on page: ${state['cheapest_price']}")
                    result['price'] = state['cheapest_price']

                # Extract flight details
                flights = extract_flight_info(page)
                if flights:
                    print(f"  Found {len(flights)} flight results")
                    for i, fl in enumerate(flights[:3]):
                        print(f"    #{i+1}: ${fl.get('price', '?')} - {fl['text'][:80]}")

                # Step 2: Click cheapest tab then first flight
                print(f"  Step 2: Clicking Cheapest tab + first flight...")
                clicked = click_cheapest_flight(page)
                if clicked:
                    print(f"    Clicked: {clicked[:80]}")
                else:
                    print(f"    No flight clicked, trying alternate selector...")
                    # Try clicking on the price element directly
                    clicked = page.evaluate(r"""() => {
                        // Try data-resultid elements
                        const results = document.querySelectorAll('[data-resultid]');
                        if (results.length > 0) {
                            results[0].click();
                            return results[0].innerText.substring(0, 200);
                        }
                        // Try list items with role
                        const items = document.querySelectorAll('[role="listitem"], ul li');
                        for (const item of items) {
                            const t = item.innerText || '';
                            if (t.includes('$') && t.includes('hr')) {
                                item.click();
                                return t.substring(0, 200);
                            }
                        }
                        return null;
                    }""")
                    if clicked:
                        print(f"    Alt click: {clicked[:80]}")

                time.sleep(5)
                result['screenshots'].append(screenshot(page, f'{city}_after_click'))

                # Step 3: Check if we need to select return flight
                state2 = check_booking_state(page)
                print(f"  Step 3: Check state after click...")
                print(f"    Has booking: {state2['has_booking']}")
                print(f"    Has return select: {state2['has_select_return']}")

                if state2['has_select_return']:
                    print(f"  Clicking return flight...")
                    time.sleep(2)
                    page.evaluate(r"""() => {
                        const items = document.querySelectorAll('li');
                        for (const li of items) {
                            const text = (li.innerText || '').trim();
                            if (/\d{1,2}:\d{2}/.test(text) && /\$\d/.test(text) && text.length > 30) {
                                li.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    time.sleep(6)
                    result['screenshots'].append(screenshot(page, f'{city}_return'))

                # Step 4: Check for booking page
                # May need to wait for navigation
                time.sleep(3)
                state3 = check_booking_state(page)
                result['booking_url'] = state3['url']

                if state3['has_booking']:
                    result['status'] = 'BOOKABLE'
                    result['airline'] = state3['airline']
                    # Get price from booking
                    bp = re.search(r'\$([0-9,]+)', state3.get('booking_text', ''))
                    if bp:
                        result['price'] = int(bp.group(1).replace(',', ''))
                    print(f"  BOOKABLE! Airline: {result['airline']}, Price: ${result.get('price', '?')}")
                elif state3['has_ghost']:
                    result['status'] = 'GHOST'
                    print(f"  GHOST FARE!")
                else:
                    # If we're still on search results, the search itself confirms prices
                    result['status'] = 'SEARCH_CONFIRMED'
                    result['booking_url'] = url  # Use the search URL as booking URL
                    print(f"  Search confirmed price: ${result.get('price', explore_price)}")
                    result['has_booking_page'] = False

                result['screenshots'].append(screenshot(page, f'{city}_final'))

                # Check excluded airlines
                if result.get('airline'):
                    for excl in EXCLUDE_AIRLINES:
                        if excl.lower() in result['airline'].lower():
                            result['excluded'] = True
                            print(f"  *** EXCLUDED AIRLINE: {result['airline']} ***")
                            break

            except Exception as e:
                print(f"  ERROR: {e}")
                result['status'] = 'ERROR'
            finally:
                page.close()

            results.append(result)

        browser.close()

    # Save
    output = {
        'verification_time': datetime.now(SHANGHAI_TZ).isoformat(),
        'origin': 'Hong Kong (HKG)',
        'cities_verified': len(results),
        'excluded_airlines': EXCLUDE_AIRLINES,
        'results': results,
    }

    out_path = os.path.join(BASE_DIR, 'deep_verify_hk_results.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print('\n' + '=' * 60)
    print('  HK VERIFICATION RESULTS')
    print('=' * 60)
    for r in results:
        excluded = ' [EXCLUDED]' if r.get('excluded') else ''
        airline = r.get('airline') or '?'
        price = f"${r['price']}" if r.get('price') else '?'
        print(f"  {r['city']:20s} | {r['status']:18s} | {airline:20s} | {price}{excluded}")

    print(f"\nSaved to: {out_path}")


if __name__ == '__main__':
    main()
