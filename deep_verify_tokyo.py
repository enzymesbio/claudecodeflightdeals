"""
Deep verification: Follow the full Google Flights flow to extract real booking links.

Routes verified:
1. Tokyo Business class -> USA (Honolulu, Los Angeles, San Francisco, Seattle)
2. Tokyo Economy -> Honolulu ($426 bug fare)
3. Seoul Economy -> Honolulu ($437 bug fare)
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

# ── Protobuf TFS URL builder ──────────────────────────────────────────
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

def _build_explore_url(origin_id, cabin=3, dest_id='/m/09c7w0'):
    """Build Google Flights Explore URL with protobuf TFS encoding."""
    date = (datetime.now() + timedelta(days=120)).strftime('%Y-%m-%d')
    origin_msg = _field_varint(1, 3) + _field_bytes(2, origin_id)
    dest_msg = _field_varint(1, 4) + _field_bytes(2, dest_id)
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

# ── Route definitions ──────────────────────────────────────────────────
ROUTES = [
    {
        'label': 'Tokyo Business -> USA',
        'origin_id': '/m/07dfk',
        'cabin': 3,
        'cabin_name': 'Business',
        'cities': ['Honolulu', 'Los Angeles', 'San Francisco', 'Seattle'],
    },
    {
        'label': 'Tokyo Economy -> Honolulu ($426 bug fare)',
        'origin_id': '/m/07dfk',
        'cabin': 1,
        'cabin_name': 'Economy',
        'cities': ['Honolulu'],
    },
    {
        'label': 'Seoul Economy -> Honolulu ($437 bug fare)',
        'origin_id': '/m/0hsqf',
        'cabin': 1,
        'cabin_name': 'Economy',
        'cities': ['Honolulu'],
    },
]


def screenshot(page, name):
    path = os.path.join(BASE_DIR, f'verify_{name}.png')
    page.screenshot(path=path, full_page=False)
    print(f'    [screenshot] {path}')
    return path


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
        const bookingCards = document.querySelectorAll('[class*="BVAVmf"], [class*="FKkPsb"], [class*="CEOyKe"]');
        for (const card of bookingCards) {
            const text = (card.innerText || '').trim();
            const link = card.querySelector('a[href]');
            if (text && link) {
                results.push({
                    text: text.substring(0, 150),
                    url: (link.href || '').substring(0, 500),
                    hasPrice: /\\$\\d/.test(text),
                    source: 'booking_card',
                });
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
            if (val > 50 && val < 50000 && !prices.includes(val)) {
                prices.push(val);
            }
        }
        return prices.sort((a, b) => a - b).slice(0, 20);
    }""")


def extract_booking_section_text(page):
    """Extract the full text of the booking options section."""
    return page.evaluate("""() => {
        const body = document.body.innerText || '';

        // Try to find the booking options section
        // Look for text around "Booking options" or "Book with"
        const bookingIdx = body.indexOf('Booking options');
        const bookWithIdx = body.indexOf('Book with');
        const cantFindIdx = body.indexOf("can\\'t find booking");
        const cantFind2 = body.indexOf("can't find booking");
        const noBookIdx = body.indexOf("no booking options");

        let section = '';

        if (bookingIdx >= 0) {
            section = body.substring(bookingIdx, bookingIdx + 1500);
        } else if (bookWithIdx >= 0) {
            section = body.substring(Math.max(0, bookWithIdx - 200), bookWithIdx + 1500);
        } else if (cantFind2 >= 0) {
            section = body.substring(Math.max(0, cantFind2 - 200), cantFind2 + 500);
        } else if (cantFindIdx >= 0) {
            section = body.substring(Math.max(0, cantFindIdx - 200), cantFindIdx + 500);
        } else if (noBookIdx >= 0) {
            section = body.substring(Math.max(0, noBookIdx - 200), noBookIdx + 500);
        }

        // Trim to first 2000 chars
        return {
            booking_section: section.substring(0, 2000),
            has_cant_find: body.includes("can't find booking") || body.includes("can\\'t find booking"),
            has_book_with: body.includes("Book with"),
            has_booking_options: body.includes("Booking options"),
            full_page_length: body.length,
        };
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
    """Click the first flight result in the list."""
    try:
        rows = page.query_selector_all('li[class*="pIav2d"], ul.Rk10dc > li, [role="listitem"]')
        if not rows:
            rows = page.query_selector_all('div[class*="yR1fYc"], div[class*="nrcYhd"]')

        if rows:
            print(f'    Found {len(rows)} flight result rows')
            rows[0].click()
            return True
        else:
            print('    No flight result rows found, trying broader selectors...')
            # Try even broader search
            rows = page.query_selector_all('li')
            clickable = []
            for r in rows:
                text = r.inner_text()
                if '$' in text and ('hr' in text.lower() or 'stop' in text.lower() or 'nonstop' in text.lower()):
                    clickable.append(r)
            if clickable:
                print(f'    Found {len(clickable)} flight rows via broad search')
                clickable[0].click()
                return True
            print('    Still no flight rows found')
            return False
    except Exception as e:
        print(f'    Error clicking flight: {e}')
        return False


def verify_single_city(context, city_name, explore_page, route_label, prefix):
    """Verify a single city by clicking through the full booking flow."""
    safe_name = f"{prefix}_{city_name.replace(' ', '_')}"
    result = {
        'city': city_name,
        'route': route_label,
        'status': 'unknown',
        'explore_price': None,
        'search_price': None,
        'booking_reached': False,
        'booking_section_text': '',
        'has_cant_find_booking': None,
        'has_book_with_links': None,
        'booking_links': [],
        'screenshots': [],
    }

    try:
        # Step 1: Click the city tab
        print(f'\n  Step 1: Click city tab for "{city_name}"...')
        city_clicked = False

        # Method 1: Playwright text selector
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
                print(f'    Clicked city tab (method 1)')
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
        time.sleep(5)
        result['screenshots'].append(screenshot(explore_page, f'{safe_name}_02_after_click'))

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
            print(f'    Waiting 10s for flight search to complete...')
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
                print(f'    Waiting 10s for flight search to complete...')
                time.sleep(10)
            except Exception as e:
                print(f'    Error opening flights page: {e}')
                result['status'] = 'flights_page_error'
                return result

        result['screenshots'].append(screenshot(flights_page, f'{safe_name}_03_flights'))

        flight_prices = extract_prices_from_page(flights_page)
        if flight_prices:
            result['search_price'] = flight_prices[0]
            print(f'    Flight page prices: {flight_prices[:5]}')

        # Step 3: Click first outbound flight
        print(f'  Step 3: Click first outbound flight...')
        if click_first_flight(flights_page):
            print(f'    Waiting 4s for return flights...')
            time.sleep(4)
            result['screenshots'].append(screenshot(flights_page, f'{safe_name}_04_outbound'))

            # Step 4: Click first return flight
            print(f'  Step 4: Click first return flight...')
            click_first_flight(flights_page)
            print(f'    Waiting 5s for booking page...')
            time.sleep(5)

            result['screenshots'].append(screenshot(flights_page, f'{safe_name}_05_after_return'))

            # Step 5: Check booking page
            current_url = flights_page.url
            print(f'    Current URL: {current_url[:120]}')

            if 'booking' not in current_url:
                print(f'    Not on booking page yet, waiting 5s more...')
                time.sleep(5)
                current_url = flights_page.url
                print(f'    URL now: {current_url[:120]}')

            result['booking_url'] = current_url
            result['booking_reached'] = 'booking' in current_url

            # Wait 3s before extracting
            time.sleep(3)

            result['screenshots'].append(screenshot(flights_page, f'{safe_name}_06_booking'))

            # Extract booking section text
            booking_info = extract_booking_section_text(flights_page)
            result['booking_section_text'] = booking_info.get('booking_section', '')
            result['has_cant_find_booking'] = booking_info.get('has_cant_find', False)
            result['has_book_with_links'] = booking_info.get('has_book_with', False)
            result['has_booking_options_header'] = booking_info.get('has_booking_options', False)

            print(f'    Booking reached: {result["booking_reached"]}')
            print(f'    Has "can\'t find booking": {result["has_cant_find_booking"]}')
            print(f'    Has "Book with" links: {result["has_book_with_links"]}')
            if result['booking_section_text']:
                # Print first 500 chars of booking section
                section_preview = result['booking_section_text'][:500].replace('\n', ' | ')
                print(f'    Booking section: {section_preview}')

            # Extract booking links
            booking_links = extract_booking_links(flights_page)
            result['booking_links'] = booking_links
            print(f'    Found {len(booking_links)} booking links')
            for bl in booking_links[:8]:
                print(f'      {bl["text"][:80]}')

            # Final prices
            final_prices = extract_prices_from_page(flights_page)
            if final_prices:
                print(f'    Final prices: {final_prices[:8]}')
                result['final_prices'] = final_prices[:10]

            # Full page text extract for booking area
            full_page_text = flights_page.evaluate("""() => {
                return (document.body.innerText || '').substring(0, 10000);
            }""")
            # Search for booking-related keywords
            for keyword in ["can't find booking", "We can't find", "Book with", "Booking options", "no booking"]:
                if keyword.lower() in full_page_text.lower():
                    print(f'    ** Found keyword: "{keyword}" **')

        else:
            result['status'] = 'no_flights_found'

        # Determine status
        if result['has_cant_find_booking']:
            result['status'] = 'NO_BOOKING_OPTIONS'
        elif result['has_book_with_links'] and result['booking_links']:
            result['status'] = 'BOOKABLE'
        elif result['booking_reached'] and result['booking_links']:
            has_price = any(bl.get('hasPrice') for bl in result['booking_links'])
            result['status'] = 'BOOKABLE_WITH_PRICE' if has_price else 'BOOKABLE_NO_PRICE'
        elif result['booking_reached']:
            result['status'] = 'BOOKING_PAGE_NO_LINKS'
        elif result.get('search_price'):
            result['status'] = 'FLIGHTS_FOUND_NO_BOOKING'
        else:
            result['status'] = 'UNCERTAIN'

        # Close flights page
        try:
            if flights_page:
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
    print(f"  DEEP TOKYO BUG FARE VERIFICATION")
    print(f"  Time: {datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d %H:%M Shanghai')}")
    print(f"  Routes: {len(ROUTES)}")
    print(f"{'='*70}")

    all_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1400, 'height': 900},
            locale='en-US',
        )

        for route_idx, route in enumerate(ROUTES):
            label = route['label']
            origin_id = route['origin_id']
            cabin = route['cabin']
            cabin_name = route['cabin_name']
            cities = route['cities']

            explore_url = _build_explore_url(origin_id, cabin=cabin)

            print(f"\n{'='*70}")
            print(f"  ROUTE {route_idx+1}/{len(ROUTES)}: {label}")
            print(f"  Cabin: {cabin_name} (code={cabin})")
            print(f"  URL: {explore_url[:100]}...")
            print(f"  Cities: {cities}")
            print(f"{'='*70}")

            # Determine prefix for screenshots
            origin_short = 'TYO' if 'Tokyo' in label or origin_id == '/m/07dfk' else 'ICN'
            cabin_short = 'biz' if cabin == 3 else 'eco'
            prefix = f'{origin_short}_{cabin_short}'

            # Load Explore page
            print(f'\nStep 0: Loading Explore page for {label}...')
            explore_page = context.new_page()
            explore_page.goto(explore_url, timeout=30000)
            time.sleep(5)

            # Accept cookies
            try:
                btn = explore_page.query_selector('button:has-text("Accept all")')
                if btn:
                    btn.click()
                    time.sleep(2)
            except:
                pass

            screenshot(explore_page, f'{prefix}_01_explore')

            # Check initial prices
            init_prices = extract_prices_from_page(explore_page)
            print(f'  Initial prices on explore page: {init_prices[:10]}')

            # Verify each city for this route
            for ci, city in enumerate(cities):
                print(f'\n{"~"*60}')
                print(f'  [{ci+1}/{len(cities)}] {label} -> {city}')
                print(f'{"~"*60}')

                result = verify_single_city(context, city, explore_page, label, prefix)
                all_results.append(result)

                print(f'\n  RESULT: [{result["status"]}]')
                print(f'    Explore price: ${result.get("explore_price", "?")}')
                print(f'    Search price: ${result.get("search_price", "?")}')
                print(f'    Booking reached: {result.get("booking_reached", False)}')
                print(f'    Can\'t find booking: {result.get("has_cant_find_booking", "?")}')
                print(f'    Book with links: {result.get("has_book_with_links", "?")}')
                print(f'    Booking links count: {len(result.get("booking_links", []))}')

                # Navigate back for next city
                time.sleep(2)
                if ci < len(cities) - 1:
                    try:
                        explore_page.goto(explore_url, timeout=30000)
                        time.sleep(4)
                    except:
                        pass

            # Close explore page for this route
            try:
                explore_page.close()
            except:
                pass

        browser.close()

    # Save results
    output = {
        'verification_time': datetime.now(SHANGHAI_TZ).isoformat(),
        'routes_verified': len(ROUTES),
        'total_cities_checked': len(all_results),
        'results': all_results,
    }

    out_path = os.path.join(BASE_DIR, 'deep_verify_tokyo_results.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  VERIFICATION SUMMARY")
    print(f"{'='*70}")

    bookable = [r for r in all_results if 'BOOKABLE' in r.get('status', '')]
    no_booking = [r for r in all_results if r.get('status') == 'NO_BOOKING_OPTIONS']
    uncertain = [r for r in all_results if r.get('status') in ('UNCERTAIN', 'FLIGHTS_FOUND_NO_BOOKING', 'BOOKING_PAGE_NO_LINKS')]
    errors = [r for r in all_results if 'ERROR' in r.get('status', '') or r.get('status') in ('click_failed', 'no_view_flights', 'no_flights_found')]

    print(f"\n  BOOKABLE (real prices confirmed): {len(bookable)}")
    for r in bookable:
        print(f"    {r['route']} -> {r['city']}: ${r.get('search_price','?')}")
        for bl in r.get('booking_links', [])[:3]:
            print(f"      Link: {bl['text'][:80]}")

    print(f"\n  NO BOOKING OPTIONS (ghost/bug fare): {len(no_booking)}")
    for r in no_booking:
        print(f"    {r['route']} -> {r['city']}: ${r.get('search_price','?')}")
        if r.get('booking_section_text'):
            print(f"      Text: {r['booking_section_text'][:120]}")

    print(f"\n  UNCERTAIN: {len(uncertain)}")
    for r in uncertain:
        print(f"    {r['route']} -> {r['city']}: {r['status']} (${r.get('search_price','?')})")

    print(f"\n  ERRORS/FAILURES: {len(errors)}")
    for r in errors:
        print(f"    {r['route']} -> {r['city']}: {r['status']}")

    print(f"\n  Results saved: {out_path}")
    print(f"  Screenshots: {BASE_DIR}/verify_*.png")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
