"""
Deep verification: Follow the full Google Flights booking flow for Seoul fares to USA.

Flow:
1. Open Explore URL (Seoul Premium Economy / Business -> USA)
2. Click each city tab on the left panel (triggers fresh AJAX search)
3. Click "View flights" link -> opens flight search page
4. Click first outbound flight result
5. Select first return flight
6. Extract booking text from booking page
7. Screenshot each step
"""
import sys
import os
import json
import time
import re
from datetime import datetime, timedelta, timezone

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

BASE_DIR = 'D:/claude/flights'
SHANGHAI_TZ = timezone(timedelta(hours=8))

# Cities to verify for Premium Economy
PE_CITIES = ['Los Angeles', 'San Francisco', 'Seattle', 'Honolulu']

# Cities to verify for Business class (cheap bug fares)
BIZ_CITIES = [
    {'name': 'Seattle', 'expected_price': 2537},
    {'name': 'Honolulu', 'expected_price': 2132},
]

# Build Explore URL using protobuf TFS encoding
import base64

def _encode_varint(value):
    result = b''
    while value > 0x7f:
        result += bytes([(value & 0x7f) | 0x80])
        value >>= 7
    result += bytes([value])
    return result

def _field_varint(num, val):
    return _encode_varint((num << 3) | 0) + _encode_varint(val)

def _field_bytes(num, data):
    if isinstance(data, str): data = data.encode('utf-8')
    return _encode_varint((num << 3) | 2) + _encode_varint(len(data)) + data

def _build_explore_url(origin_id, cabin=2):
    """Build Google Flights Explore URL with protobuf TFS encoding."""
    date = (datetime.now() + timedelta(days=120)).strftime('%Y-%m-%d')
    origin_msg = _field_varint(1, 3) + _field_bytes(2, origin_id)
    dest_msg = _field_varint(1, 4) + _field_bytes(2, '/m/09c7w0')  # USA
    leg1 = _field_bytes(2, date) + _field_bytes(13, origin_msg) + _field_bytes(14, dest_msg)
    leg2 = _field_bytes(13, dest_msg) + _field_bytes(14, origin_msg)
    pax_config = b'\x08\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01'
    field22 = _field_varint(3, 1) + _field_varint(4, 1)
    msg = (_field_varint(1, 28) + _field_varint(2, 3) + _field_bytes(3, leg1) +
           _field_bytes(3, leg2) + _field_varint(8, 1) + _field_varint(9, cabin) +
           _field_varint(14, 2) + _field_bytes(16, pax_config) + _field_varint(19, 1) +
           _field_bytes(22, field22))
    tfs = base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')
    return f'https://www.google.com/travel/explore?tfs={tfs}&tfu=GgA&hl=en&gl=hk&curr=USD'

# Seoul = /m/0hsqf
EXPLORE_URL_PE = _build_explore_url('/m/0hsqf', cabin=2)    # Premium Economy
EXPLORE_URL_BIZ = _build_explore_url('/m/0hsqf', cabin=3)   # Business


def screenshot(page, name):
    path = os.path.join(BASE_DIR, f'verify_seoul_{name}.png')
    page.screenshot(path=path, full_page=False)
    print(f'    [screenshot] {path}')
    return path


def extract_booking_text(page):
    """Extract booking options text from the page."""
    return page.evaluate('''() => {
        const body = document.body.innerText;
        // Look for "Booking options" section
        const idx = body.indexOf('Booking options');
        if (idx >= 0) return body.substring(idx, idx + 500);
        // Look for "Book with" text
        const idx2 = body.indexOf('Book with');
        if (idx2 >= 0) return body.substring(idx2, idx2 + 500);
        // Look for "can't find"
        const idx3 = body.indexOf("can't find");
        if (idx3 >= 0) return body.substring(idx3 - 50, idx3 + 200);
        return 'NO BOOKING SECTION FOUND - Page text: ' + body.substring(body.length - 500);
    }''')


def extract_booking_links(page):
    """Extract booking platform links from the final booking/flights page."""
    return page.evaluate("""() => {
        const results = [];
        const allLinks = document.querySelectorAll('a[href]');
        for (const a of allLinks) {
            const href = a.href || '';
            const text = (a.innerText || '').trim();
            if (text && text.length > 2 && text.length < 200) {
                const hasPrice = /\\$\\d/.test(text);
                const hasBook = /book|select|choose/i.test(text);
                const isBookingRedirect = /googleadservices|book|redirect|partner|flights\\/booking/i.test(href);
                if (hasPrice || hasBook || isBookingRedirect) {
                    results.push({
                        text: text.substring(0, 150),
                        url: href.substring(0, 500),
                        hasPrice: hasPrice,
                    });
                }
            }
        }
        return results;
    }""")


def extract_prices_from_page(page):
    """Extract all visible prices from the page."""
    return page.evaluate("""() => {
        const text = document.body.innerText;
        const prices = [];
        const matches = text.matchAll(/\\$(\\d[\\d,]*)/g);
        for (const m of matches) {
            const val = parseInt(m[1].replace(',', ''));
            if (val > 100 && val < 50000 && !prices.includes(val)) {
                prices.push(val);
            }
        }
        return prices.sort((a, b) => a - b).slice(0, 20);
    }""")


def find_view_flights_link(page):
    """Find the 'View flights' link after clicking a city tab."""
    return page.evaluate("""() => {
        const allEls = document.querySelectorAll('a, button, [role="link"]');
        for (const el of allEls) {
            const text = (el.innerText || '').trim().toLowerCase();
            if (text.includes('view flights') || text.includes('view flight')) {
                return {
                    text: el.innerText.trim(),
                    href: el.href || el.getAttribute('href') || '',
                    tag: el.tagName,
                };
            }
        }
        const links = document.querySelectorAll('a[href*="travel/flights"]');
        for (const a of links) {
            const text = (a.innerText || '').trim();
            if (text) {
                return {
                    text: text,
                    href: a.href,
                    tag: 'a',
                };
            }
        }
        return null;
    }""")


def click_first_flight(page):
    """Click the first flight result in the Best/Cheapest list."""
    try:
        rows = page.query_selector_all('li[class*="pIav2d"], ul.Rk10dc > li, [role="listitem"]')
        if not rows:
            rows = page.query_selector_all('div[class*="yR1fYc"], div[class*="nrcYhd"]')
        if rows:
            print(f'    Found {len(rows)} flight result rows')
            rows[0].click()
            return True
        else:
            print('    No flight result rows found')
            return False
    except Exception as e:
        print(f'    Error clicking flight: {e}')
        return False


def verify_city(context, explore_page, city_name, cabin_label, explore_url):
    """Verify a single city by clicking through the full booking flow."""
    result = {
        'city': city_name,
        'cabin': cabin_label,
        'status': 'unknown',
        'explore_price': None,
        'search_price': None,
        'booking_text': None,
        'booking_links': [],
        'screenshots': [],
        'has_booking_page': False,
    }

    safe_name = city_name.replace(' ', '_')
    prefix = f'{cabin_label}_{safe_name}'

    try:
        # Step 1: Click city tab
        print(f'\n  Step 1: Click city tab for "{city_name}"...')
        city_clicked = False

        # Method 1: Text-based click
        try:
            city_el = explore_page.query_selector(f'text="{city_name}"')
            if not city_el:
                city_el = explore_page.query_selector(f'text=/{city_name}/i')
            if city_el:
                parent = city_el.evaluate_handle('el => el.closest("div[role], li, a, button") || el.parentElement')
                if parent:
                    parent.as_element().click()
                    city_clicked = True
                else:
                    city_el.click()
                    city_clicked = True
                print(f'    Clicked city tab via text selector')
        except Exception as e:
            print(f'    Method 1 failed: {e}')

        # Method 2: JS click
        if not city_clicked:
            try:
                clicked = explore_page.evaluate(f"""() => {{
                    const allEls = document.querySelectorAll('*');
                    for (const el of allEls) {{
                        if (el.children.length < 3 && el.innerText &&
                            el.innerText.includes('{city_name}') &&
                            /\\$\\d/.test(el.innerText)) {{
                            el.click();
                            return el.innerText.substring(0, 80);
                        }}
                    }}
                    return null;
                }}""")
                if clicked:
                    city_clicked = True
                    print(f'    Clicked via JS: {clicked}')
            except Exception as e:
                print(f'    Method 2 failed: {e}')

        if not city_clicked:
            result['status'] = 'click_failed'
            return result

        # Wait for AJAX
        print(f'  Waiting 5s for AJAX...')
        time.sleep(5)
        result['screenshots'].append(screenshot(explore_page, f'{prefix}_01_after_click'))

        # Extract explore price
        prices = extract_prices_from_page(explore_page)
        if prices:
            result['explore_price'] = prices[0]
            print(f'    Prices visible: {prices[:5]}')

        # Step 2: Find and click "View flights"
        print(f'  Step 2: Find "View flights" link...')
        vf_link = find_view_flights_link(explore_page)

        if not vf_link:
            print('    No "View flights" link found')
            result['status'] = 'no_view_flights'
            return result

        print(f'    Found: {vf_link["text"]} -> {vf_link["href"][:80]}')

        view_flights_url = vf_link.get('href', '')
        flights_page = None

        if view_flights_url and view_flights_url.startswith('http'):
            flights_page = context.new_page()
            flights_page.goto(view_flights_url, timeout=30000)
            print(f'  Waiting 10s for flight search to complete...')
            time.sleep(10)
        else:
            try:
                with context.expect_page() as new_page_info:
                    explore_page.evaluate("""() => {
                        const links = document.querySelectorAll('a');
                        for (const a of links) {
                            if (a.innerText.toLowerCase().includes('view flights')) {
                                a.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                flights_page = new_page_info.value
                flights_page.wait_for_load_state('domcontentloaded')
                print(f'  Waiting 10s for flight search to complete...')
                time.sleep(10)
            except Exception as e:
                print(f'    Error opening flights page: {e}')
                result['status'] = 'view_flights_error'
                return result

        result['screenshots'].append(screenshot(flights_page, f'{prefix}_02_flights'))

        # Extract prices from flights page
        flight_prices = extract_prices_from_page(flights_page)
        if flight_prices:
            result['search_price'] = flight_prices[0]
            print(f'    Flight page prices: {flight_prices[:5]}')

        # Step 3: Click first outbound flight
        print(f'  Step 3: Click first outbound flight...')
        if click_first_flight(flights_page):
            print(f'  Waiting 4s for return flights...')
            time.sleep(4)
            result['screenshots'].append(screenshot(flights_page, f'{prefix}_03_outbound'))

            # Step 4: Click first return flight
            print(f'  Step 4: Click first return flight...')
            click_first_flight(flights_page)
            print(f'  Waiting 5s for booking page...')
            time.sleep(5)

            result['screenshots'].append(screenshot(flights_page, f'{prefix}_04_after_return'))

            # Check if we reached booking page
            current_url = flights_page.url
            print(f'    Current URL: {current_url[:120]}')

            if 'booking' not in current_url:
                print(f'    Not on booking page yet, waiting 5 more seconds...')
                time.sleep(5)
                current_url = flights_page.url
                print(f'    URL now: {current_url[:120]}')

            result['booking_url'] = current_url
            result['has_booking_page'] = 'booking' in current_url

            # Wait 3 more seconds before extracting
            time.sleep(3)
            result['screenshots'].append(screenshot(flights_page, f'{prefix}_05_booking'))

            # Step 5: Extract booking text
            print(f'  Step 5: Extract booking options text...')
            booking_text = extract_booking_text(flights_page)
            result['booking_text'] = booking_text
            print(f'    Booking text: {booking_text[:200]}')

            # Extract booking links
            booking_links = extract_booking_links(flights_page)
            result['booking_links'] = booking_links
            print(f'    Found {len(booking_links)} booking links')
            for bl in booking_links[:8]:
                print(f'      {bl["text"][:80]}')

            # Extract final prices
            final_prices = extract_prices_from_page(flights_page)
            if final_prices:
                print(f'    Final prices: {final_prices[:8]}')
                result['final_prices'] = final_prices[:10]

        else:
            result['status'] = 'no_flight_rows'

        # Determine status
        if result.get('booking_text') and "can't find" in result['booking_text'].lower():
            result['status'] = 'NO_BOOKING_OPTIONS'
        elif result.get('booking_links'):
            has_price = any(bl.get('hasPrice') for bl in result['booking_links'])
            result['status'] = 'LIVE_WITH_BOOKING' if has_price else 'LIVE_NO_PRICE'
        elif result.get('has_booking_page'):
            result['status'] = 'BOOKING_PAGE_NO_LINKS'
        elif result.get('search_price'):
            result['status'] = 'LIVE_NO_BOOKING'
        else:
            result['status'] = 'UNCERTAIN'

        # Close flights page
        try:
            flights_page.close()
        except:
            pass

    except Exception as e:
        result['status'] = f'ERROR: {e}'
        print(f'    Error: {e}')
        import traceback
        traceback.print_exc()

    return result


def main():
    print(f"\n{'='*70}")
    print(f"  DEEP VERIFICATION: SEOUL CHEAP FARES TO USA")
    print(f"  Time: {datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d %H:%M Shanghai')}")
    print(f"  Origin: Seoul (ICN) /m/0hsqf")
    print(f"  Premium Economy cities: {PE_CITIES}")
    print(f"  Business class cities: {[c['name'] for c in BIZ_CITIES]}")
    print(f"{'='*70}")

    print(f"\n  PE Explore URL: {EXPLORE_URL_PE[:100]}...")
    print(f"  Biz Explore URL: {EXPLORE_URL_BIZ[:100]}...")

    all_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1400, 'height': 900},
            locale='en-US',
        )

        # ============================================
        # PART 1: Premium Economy verification
        # ============================================
        print(f"\n{'='*70}")
        print(f"  PART 1: Seoul PREMIUM ECONOMY to USA")
        print(f"{'='*70}")

        explore_page = context.new_page()
        explore_page.goto(EXPLORE_URL_PE, timeout=30000)
        time.sleep(5)

        # Accept cookies
        try:
            btn = explore_page.query_selector('button:has-text("Accept all")')
            if btn:
                btn.click()
                time.sleep(2)
        except:
            pass

        screenshot(explore_page, 'PE_00_explore')

        # Check initial prices
        init_prices = extract_prices_from_page(explore_page)
        print(f'  Initial prices on page: {init_prices[:10]}')

        for i, city in enumerate(PE_CITIES):
            print(f'\n{"="*60}')
            print(f'  [{i+1}/{len(PE_CITIES)}] PE: Seoul -> {city}')
            print(f'{"="*60}')

            result = verify_city(context, explore_page, city, 'PE', EXPLORE_URL_PE)
            all_results.append(result)

            print(f'  Result: [{result["status"]}]')
            print(f'    Explore price: ${result.get("explore_price", "?")}')
            print(f'    Search price: ${result.get("search_price", "?")}')
            print(f'    Has booking page: {result.get("has_booking_page")}')
            print(f'    Booking text excerpt: {(result.get("booking_text") or "N/A")[:100]}')

            time.sleep(2)

            # Navigate back for next city
            try:
                explore_page.goto(EXPLORE_URL_PE, timeout=30000)
                time.sleep(4)
            except:
                pass

        explore_page.close()

        # ============================================
        # PART 2: Business class verification
        # ============================================
        print(f"\n{'='*70}")
        print(f"  PART 2: Seoul BUSINESS CLASS to USA")
        print(f"  Seattle Business expected: $2,537")
        print(f"  Honolulu Business expected: $2,132")
        print(f"{'='*70}")

        explore_page2 = context.new_page()
        explore_page2.goto(EXPLORE_URL_BIZ, timeout=30000)
        time.sleep(5)

        # Accept cookies
        try:
            btn = explore_page2.query_selector('button:has-text("Accept all")')
            if btn:
                btn.click()
                time.sleep(2)
        except:
            pass

        screenshot(explore_page2, 'BIZ_00_explore')

        init_prices_biz = extract_prices_from_page(explore_page2)
        print(f'  Initial Business prices: {init_prices_biz[:10]}')

        for i, city_info in enumerate(BIZ_CITIES):
            city = city_info['name']
            expected = city_info['expected_price']
            print(f'\n{"="*60}')
            print(f'  [{i+1}/{len(BIZ_CITIES)}] BIZ: Seoul -> {city} (expected ${expected:,})')
            print(f'{"="*60}')

            result = verify_city(context, explore_page2, city, 'BIZ', EXPLORE_URL_BIZ)
            result['expected_price'] = expected
            all_results.append(result)

            print(f'  Result: [{result["status"]}]')
            print(f'    Expected: ${expected:,}')
            print(f'    Explore price: ${result.get("explore_price", "?")}')
            print(f'    Search price: ${result.get("search_price", "?")}')
            print(f'    Has booking page: {result.get("has_booking_page")}')
            print(f'    Booking text excerpt: {(result.get("booking_text") or "N/A")[:100]}')

            time.sleep(2)

            # Navigate back for next city
            if i < len(BIZ_CITIES) - 1:
                try:
                    explore_page2.goto(EXPLORE_URL_BIZ, timeout=30000)
                    time.sleep(4)
                except:
                    pass

        explore_page2.close()
        browser.close()

    # Save results
    output = {
        'verification_time': datetime.now(SHANGHAI_TZ).isoformat(),
        'origin': 'Seoul (ICN)',
        'pe_explore_url': EXPLORE_URL_PE,
        'biz_explore_url': EXPLORE_URL_BIZ,
        'total_cities_verified': len(all_results),
        'results': all_results,
    }

    out_path = os.path.join(BASE_DIR, 'deep_verify_seoul_results.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Summary
    print(f"\n{'='*70}")
    print(f"  DEEP VERIFICATION SUMMARY - SEOUL FARES")
    print(f"{'='*70}")

    pe_results = [r for r in all_results if r['cabin'] == 'PE']
    biz_results = [r for r in all_results if r['cabin'] == 'BIZ']

    print(f"\n  PREMIUM ECONOMY ({len(pe_results)} cities):")
    for r in pe_results:
        booking_preview = (r.get('booking_text') or 'N/A')[:80]
        print(f"    {r['city']:20s} [{r['status']:25s}] explore=${r.get('explore_price','?'):>6} search=${r.get('search_price','?'):>6}")
        print(f"      Booking: {booking_preview}")

    print(f"\n  BUSINESS CLASS ({len(biz_results)} cities):")
    for r in biz_results:
        booking_preview = (r.get('booking_text') or 'N/A')[:80]
        expected = r.get('expected_price', '?')
        print(f"    {r['city']:20s} [{r['status']:25s}] expected=${expected} explore=${r.get('explore_price','?'):>6} search=${r.get('search_price','?'):>6}")
        print(f"      Booking: {booking_preview}")

    # Check for real bookable fares
    live_fares = [r for r in all_results if 'LIVE' in r.get('status', '')]
    no_booking = [r for r in all_results if 'NO_BOOKING' in r.get('status', '')]
    errors = [r for r in all_results if 'ERROR' in r.get('status', '')]

    print(f"\n  TOTALS:")
    print(f"    Live/bookable: {len(live_fares)}")
    print(f"    No booking options: {len(no_booking)}")
    print(f"    Errors/other: {len(errors)}")

    print(f"\n  Results saved: {out_path}")
    print(f"  Screenshots: {BASE_DIR}/verify_seoul_*.png")


if __name__ == '__main__':
    main()
