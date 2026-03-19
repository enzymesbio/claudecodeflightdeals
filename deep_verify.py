"""
Deep verification: Follow the full Google Flights flow to extract real booking links.

Flow:
1. Open Explore URL (Jakarta Business -> USA)
2. Click each city tab on the left panel (triggers fresh AJAX search)
3. Click "View flights" link -> opens flight search page
4. Click first "Best" outbound flight
5. Select first return flight
6. Extract booking platform links + prices from booking page
7. Extract actual airline/OTA redirect URLs from "Continue" buttons
8. Screenshot each step

Flags:
  --rerun   Re-open existing Tokyo/Seoul booking pages to extract platform links
"""
import sys
import os
import json
import time
import re
import argparse
from datetime import datetime, timedelta, timezone

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

BASE_DIR = 'D:/claude/flights'
SHANGHAI_TZ = timezone(timedelta(hours=8))

# Bug fare cities to verify (top 5 cheapest from Jakarta scan)
VERIFY_CITIES = [
    'Houston', 'Los Angeles', 'Boston', 'Washington', 'New York',
]

# Build Explore URL for Jakarta Business to USA dynamically
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

def _build_explore_url(origin_id, cabin=3):
    date = (datetime.now() + timedelta(days=120)).strftime('%Y-%m-%d')
    origin_msg = _field_varint(1, 3) + _field_bytes(2, origin_id)
    dest_msg = _field_varint(1, 4) + _field_bytes(2, '/m/09c7w0')
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

# Jakarta Business class to USA
EXPLORE_URL = _build_explore_url('/m/044rv', cabin=3)
# Also verify Premium Economy
EXPLORE_URL_PREM = _build_explore_url('/m/044rv', cabin=2)


def screenshot(page, name):
    path = os.path.join(BASE_DIR, f'verify_{name}.png')
    page.screenshot(path=path, full_page=False)
    print(f'    [screenshot] {path}')
    return path


def extract_booking_links(page):
    """Extract booking platform links from the final booking/flights page."""
    return page.evaluate("""() => {
        const results = [];
        // Look for booking links - these typically have airline/OTA names and prices
        const allLinks = document.querySelectorAll('a[href]');
        for (const a of allLinks) {
            const href = a.href || '';
            const text = (a.innerText || '').trim();
            // Booking links typically contain price and platform name
            if (text && text.length > 2 && text.length < 200) {
                // Look for links with prices or "Book" text
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

        // Also look for the specific booking options panel
        // Google Flights shows "Book with [Platform]" buttons
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


def extract_platform_links(page, context):
    """Extract actual airline/OTA booking redirect URLs from the booking page.

    The Google Flights booking page shows entries like:
        Book with ZIPAIR Tokyo (Airline)
        $426
        [Continue] [View options]

    This function tries two approaches:
      (a) DOM inspection: find <a> tags near "Book with" text and extract hrefs
      (b) Click fallback: click each "Continue" button and capture the redirect URL

    Returns a list of dicts: [{"airline": "...", "price": "...", "url": "..."}]
    """
    # ── Approach (a): Extract from DOM ──────────────────────────────────────
    platform_links = page.evaluate(r"""() => {
        const results = [];

        // Strategy 1: Walk "Book with ..." text nodes and find nearby <a> tags.
        // Google Flights wraps each booking option in a container that has:
        //   - text "Book with <Airline>"
        //   - a price like "$426"
        //   - a "Continue" <a> link (often via Google redirect /travel/clk or similar)
        const body = document.body;
        const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, null);
        const bookWithNodes = [];
        while (walker.nextNode()) {
            const txt = walker.currentNode.textContent.trim();
            if (/^Book with\s/i.test(txt)) {
                bookWithNodes.push({node: walker.currentNode, text: txt});
            }
        }

        for (const {node, text} of bookWithNodes) {
            const airline = text.replace(/^Book with\s*/i, '').replace(/Airline$/i, '').trim();

            // Walk up to find the containing card (up to 8 levels)
            let container = node.parentElement;
            for (let i = 0; i < 8 && container && container !== body; i++) {
                // Check if this container has a "Continue" link
                const links = container.querySelectorAll('a[href]');
                let continueLink = null;
                let price = null;

                for (const a of links) {
                    const linkText = (a.innerText || '').trim();
                    if (/^Continue$/i.test(linkText) || /^Book$/i.test(linkText)) {
                        continueLink = a;
                    }
                }

                // Extract price from the container text
                const containerText = container.innerText || '';
                const priceMatch = containerText.match(/\$[\d,]+/);
                if (priceMatch) {
                    price = priceMatch[0];
                }

                if (continueLink) {
                    results.push({
                        airline: airline,
                        price: price || '',
                        url: continueLink.href || '',
                        method: 'dom_continue_link',
                    });
                    break;
                }

                container = container.parentElement;
            }

            // If we didn't find a Continue link, try finding any link in parent chain
            if (!results.find(r => r.airline === airline)) {
                let el = node.parentElement;
                for (let i = 0; i < 10 && el && el !== body; i++) {
                    const links = el.querySelectorAll('a[href]');
                    for (const a of links) {
                        const href = a.href || '';
                        const linkText = (a.innerText || '').trim();
                        // Skip Sign in, generic nav, etc.
                        if (/sign in|privacy|terms|about|help|feedback/i.test(linkText)) continue;
                        if (href && (href.includes('/travel/clk') ||
                                     href.includes('googleadservices') ||
                                     href.includes('flights/booking'))) {
                            const containerText = el.innerText || '';
                            const priceMatch = containerText.match(/\$[\d,]+/);
                            results.push({
                                airline: airline,
                                price: priceMatch ? priceMatch[0] : '',
                                url: href,
                                method: 'dom_nearby_link',
                            });
                            break;
                        }
                    }
                    if (results.find(r => r.airline === airline)) break;
                    el = el.parentElement;
                }
            }
        }

        // Strategy 2: Find all <a> tags whose ancestor text contains "Book with"
        if (results.length === 0) {
            const allAnchors = document.querySelectorAll('a[href]');
            for (const a of allAnchors) {
                const text = (a.innerText || '').trim();
                if (!/^Continue$/i.test(text)) continue;
                // Walk up to find "Book with" text
                let parent = a.parentElement;
                for (let i = 0; i < 8 && parent && parent !== body; i++) {
                    const pText = parent.innerText || '';
                    const bwMatch = pText.match(/Book with\s+(.+?)(?:Airline|$)/im);
                    if (bwMatch) {
                        const airline = bwMatch[1].trim();
                        const priceMatch = pText.match(/\$[\d,]+/);
                        results.push({
                            airline: airline,
                            price: priceMatch ? priceMatch[0] : '',
                            url: a.href || '',
                            method: 'dom_continue_ancestor',
                        });
                        break;
                    }
                    parent = parent.parentElement;
                }
            }
        }

        // Strategy 3: Look for clickable elements with data attributes
        // that might encode redirect URLs
        if (results.length === 0) {
            const clickables = document.querySelectorAll('[data-url], [data-href], [data-redirect]');
            for (const el of clickables) {
                const url = el.getAttribute('data-url') ||
                            el.getAttribute('data-href') ||
                            el.getAttribute('data-redirect') || '';
                if (url) {
                    const parentText = (el.closest('[class]') || el).innerText || '';
                    const bwMatch = parentText.match(/Book with\s+(.+?)(?:Airline|$)/im);
                    const priceMatch = parentText.match(/\$[\d,]+/);
                    results.push({
                        airline: bwMatch ? bwMatch[1].trim() : 'unknown',
                        price: priceMatch ? priceMatch[0] : '',
                        url: url,
                        method: 'dom_data_attr',
                    });
                }
            }
        }

        return results;
    }""")

    print(f'    [platform_links] DOM approach found {len(platform_links)} link(s)')
    for pl in platform_links:
        print(f'      {pl["airline"]}: {pl["price"]} -> {pl["url"][:100]}')

    # ── Approach (b): Click fallback ────────────────────────────────────────
    # If DOM approach yielded zero usable URLs (all empty or only page-internal),
    # try clicking each "Continue" button and capturing the navigation target.
    # Filter out non-booking URLs (CSS/static assets, Google sign-in, etc.)
    SKIP_DOMAINS = ['gstatic.com', 'accounts.google.com', 'google.com/_/mss']
    usable = [pl for pl in platform_links
              if pl.get('url') and '://' in pl.get('url', '')
              and not any(skip in pl.get('url', '') for skip in SKIP_DOMAINS)]
    if not usable:
        print('    [platform_links] DOM found no usable URLs, trying click approach...')
        platform_links = _extract_platform_links_by_click(page, context)

    return platform_links


def _extract_platform_links_by_click(page, context):
    """Fallback: click each 'Continue' button and capture the redirect URL."""
    results = []
    original_url = page.url

    # Count how many "Continue" buttons exist
    continue_count = page.evaluate(r"""() => {
        const anchors = document.querySelectorAll('a, button');
        let count = 0;
        for (const el of anchors) {
            if (/^Continue$/i.test((el.innerText || '').trim())) count++;
        }
        return count;
    }""")

    print(f'    [click_fallback] Found {continue_count} Continue button(s)')

    for idx in range(continue_count):
        try:
            # Re-find the idx-th Continue button (DOM may have changed)
            btn_info = page.evaluate(r"""(idx) => {
                const body = document.body;
                const anchors = document.querySelectorAll('a, button');
                let count = 0;
                for (const el of anchors) {
                    if (/^Continue$/i.test((el.innerText || '').trim())) {
                        if (count === idx) {
                            // Gather context: walk up to find airline + price
                            let airline = '';
                            let price = '';
                            let parent = el.parentElement;
                            for (let i = 0; i < 8 && parent && parent !== body; i++) {
                                const pText = parent.innerText || '';
                                if (!airline) {
                                    const bwMatch = pText.match(/Book with\s+(.+?)(?:Airline|$)/im);
                                    if (bwMatch) airline = bwMatch[1].trim();
                                }
                                if (!price) {
                                    const priceMatch = pText.match(/\$[\d,]+/);
                                    if (priceMatch) price = priceMatch[0];
                                }
                                if (airline && price) break;
                                parent = parent.parentElement;
                            }
                            return {airline, price, tag: el.tagName, hasHref: !!el.href};
                        }
                        count++;
                    }
                }
                return null;
            }""", idx)

            if not btn_info:
                continue

            print(f'      Clicking Continue #{idx}: {btn_info["airline"]} {btn_info["price"]}')

            # If the Continue button is an <a> with href, clicking may navigate
            # the page or open a new tab.  We handle both.
            redirect_url = None

            # Listen for popup (new tab)
            try:
                with context.expect_page(timeout=8000) as new_page_info:
                    # Click the idx-th Continue button
                    page.evaluate(r"""(idx) => {
                        const anchors = document.querySelectorAll('a, button');
                        let count = 0;
                        for (const el of anchors) {
                            if (/^Continue$/i.test((el.innerText || '').trim())) {
                                if (count === idx) { el.click(); return true; }
                                count++;
                            }
                        }
                        return false;
                    }""", idx)
                new_tab = new_page_info.value
                new_tab.wait_for_load_state('domcontentloaded', timeout=10000)
                time.sleep(2)
                redirect_url = new_tab.url
                print(f'      New tab URL: {redirect_url[:120]}')
                new_tab.close()
            except Exception:
                # No new tab opened; check if current page navigated
                time.sleep(3)
                current = page.url
                if current != original_url:
                    redirect_url = current
                    print(f'      Redirected to: {redirect_url[:120]}')
                    # Go back to the booking page for the next button
                    page.goto(original_url, timeout=30000)
                    time.sleep(5)

            if redirect_url:
                results.append({
                    'airline': btn_info.get('airline', ''),
                    'price': btn_info.get('price', ''),
                    'url': redirect_url,
                    'method': 'click_redirect',
                })

        except Exception as e:
            print(f'      Error on Continue #{idx}: {e}')

    return results


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


def get_city_tabs(page):
    """Get clickable city destination tabs from the Explore left panel."""
    return page.evaluate("""() => {
        const tabs = [];
        // City tabs are typically in a list on the left side
        // They contain city name and price
        const items = document.querySelectorAll(
            '[class*="UWmpq"], [class*="f4hh3d"], [role="listitem"], [data-city]'
        );
        for (let i = 0; i < items.length; i++) {
            const el = items[i];
            const text = (el.innerText || '').trim();
            if (text && /\\$\\d/.test(text)) {
                tabs.push({
                    index: i,
                    text: text.substring(0, 100),
                    selector: i,
                });
            }
        }

        // Fallback: look for any elements with city names and prices
        if (tabs.length === 0) {
            const allEls = document.querySelectorAll('div, li, span');
            for (let i = 0; i < allEls.length; i++) {
                const el = allEls[i];
                const text = (el.innerText || '').trim();
                const lines = text.split('\\n');
                // A city tab typically has: city name, price, dates, stops
                if (lines.length >= 2 && lines.length <= 6 && /\\$\\d/.test(text)) {
                    const priceMatch = text.match(/\\$(\\d[\\d,]*)/);
                    const price = priceMatch ? parseInt(priceMatch[1].replace(',','')) : 0;
                    if (price > 100 && price < 20000) {
                        tabs.push({
                            index: i,
                            text: text.replace(/\\n/g, ' | '),
                            price: price,
                            cityGuess: lines[0],
                        });
                    }
                }
            }
        }
        return tabs.slice(0, 30);
    }""")


def find_view_flights_link(page):
    """Find the 'View flights' link after clicking a city tab."""
    return page.evaluate("""() => {
        // Look for "View flights" text link
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
        // Also check for links with flights URL pattern
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
        # Look for flight result rows
        rows = page.query_selector_all('li[class*="pIav2d"], ul.Rk10dc > li, [role="listitem"]')
        if not rows:
            # Try broader selectors
            rows = page.query_selector_all('div[class*="yR1fYc"], div[class*="nrcYhd"]')

        if rows:
            print(f'    Found {len(rows)} flight result rows')
            # Click the first one
            rows[0].click()
            return True
        else:
            print('    No flight result rows found')
            return False
    except Exception as e:
        print(f'    Error clicking flight: {e}')
        return False


def verify_single_city(page, context, city_name, city_index, explore_page):
    """Verify a single city by clicking through the full flow."""
    result = {
        'city': city_name,
        'status': 'unknown',
        'explore_price': None,
        'search_price': None,
        'booking_links': [],
        'screenshots': [],
    }

    try:
        # Step 1: We're on the Explore page. Find and click the city tab.
        print(f'\n  Step 1: Click city tab for "{city_name}"...')

        # Try clicking by text content
        city_clicked = False

        # Method 1: Find element containing city name and click it
        try:
            # Use a text-based approach
            city_el = explore_page.query_selector(f'text="{city_name}"')
            if not city_el:
                # Try partial match
                city_el = explore_page.query_selector(f'text=/{city_name}/i')

            if city_el:
                # Get parent that's clickable
                parent = city_el.evaluate_handle('el => el.closest("div[role], li, a, button") || el.parentElement')
                if parent:
                    parent.as_element().click()
                    city_clicked = True
                else:
                    city_el.click()
                    city_clicked = True
                print(f'    Clicked city tab')
        except Exception as e:
            print(f'    Method 1 failed: {e}')

        if not city_clicked:
            # Method 2: Click via JavaScript
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

        # Wait for AJAX to load fresh results
        time.sleep(5)
        result['screenshots'].append(screenshot(explore_page, f'{city_name.replace(" ","_")}_02_after_click'))

        # Extract price shown after clicking
        prices = extract_prices_from_page(explore_page)
        if prices:
            result['explore_price'] = prices[0]
            print(f'    Prices visible: {prices[:5]}')

        # Step 2: Find and click "View flights" link
        print(f'  Step 2: Find "View flights" link...')
        vf_link = find_view_flights_link(explore_page)

        if not vf_link:
            print('    No "View flights" link found')
            result['status'] = 'no_view_flights'
            return result

        print(f'    Found: {vf_link["text"]} -> {vf_link["href"][:80]}')

        # Click "View flights" - it opens in new tab
        view_flights_url = vf_link.get('href', '')

        if view_flights_url and view_flights_url.startswith('http'):
            # Open in new page
            flights_page = context.new_page()
            flights_page.goto(view_flights_url, timeout=30000)
            time.sleep(10)  # Must wait 10s for real-time search to complete
        else:
            # Click the link and handle popup
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
            time.sleep(6)

        result['screenshots'].append(screenshot(flights_page, f'{city_name.replace(" ","_")}_03_flights'))

        # Extract prices from flights page
        flight_prices = extract_prices_from_page(flights_page)
        if flight_prices:
            result['search_price'] = flight_prices[0]
            print(f'    Flight page prices: {flight_prices[:5]}')

        # Step 3: Click first outbound flight (Best tab)
        print(f'  Step 3: Click first outbound flight...')
        if click_first_flight(flights_page):
            time.sleep(4)  # Wait for outbound selection to register
            result['screenshots'].append(screenshot(flights_page, f'{city_name.replace(" ","_")}_04_outbound'))

            # Step 4: Select return flight
            print(f'  Step 4: Waiting for return flights to load...')
            time.sleep(4)  # Wait for return flight options to appear

            page_text = flights_page.inner_text('body')
            result['screenshots'].append(screenshot(flights_page, f'{city_name.replace(" ","_")}_05_return_options'))

            # Click the first return flight
            print(f'  Step 4b: Clicking first return flight...')
            click_first_flight(flights_page)
            time.sleep(5)  # Wait for booking page to load

            result['screenshots'].append(screenshot(flights_page, f'{city_name.replace(" ","_")}_06_after_return'))

            # Step 5: Check if we reached the booking page
            current_url = flights_page.url
            print(f'    Current URL: {current_url[:120]}')

            # Wait a bit more if not on booking page yet
            if 'booking' not in current_url:
                print(f'    Not on booking page yet, waiting...')
                time.sleep(5)
                current_url = flights_page.url
                print(f'    URL now: {current_url[:120]}')

            result['booking_url'] = current_url
            result['screenshots'].append(screenshot(flights_page, f'{city_name.replace(" ","_")}_07_booking'))

            if 'booking' in current_url:
                print(f'  Step 5: ON BOOKING PAGE! Extracting links...')
            else:
                print(f'  Step 5: Extracting whatever links are on this page...')

            # Extract booking links
            booking_links = extract_booking_links(flights_page)
            result['booking_links'] = booking_links
            print(f'    Found {len(booking_links)} booking links')
            for bl in booking_links[:8]:
                print(f'      {bl["text"][:80]}')

            # Also get final prices
            final_prices = extract_prices_from_page(flights_page)
            if final_prices:
                print(f'    Final prices: {final_prices[:8]}')
                result['final_prices'] = final_prices[:10]

            # Extract ALL links on the page for debugging
            all_links = flights_page.evaluate("""() => {
                const results = [];
                const links = document.querySelectorAll('a[href]');
                for (const a of links) {
                    const text = (a.innerText || '').trim();
                    const href = a.href || '';
                    if (text && text.length > 3 && text.length < 200 &&
                        (href.includes('book') || href.includes('redirect') ||
                         href.includes('googleadservices') || /\\$\\d/.test(text))) {
                        results.push({text: text.substring(0,100), url: href.substring(0,300)});
                    }
                }
                return results;
            }""")
            if all_links:
                result['all_booking_links'] = all_links
                print(f'    Additional booking-related links: {len(all_links)}')
                for al in all_links[:5]:
                    print(f'      {al["text"][:80]}')

            # Step 6: Extract actual airline/OTA platform redirect URLs
            print(f'  Step 6: Extracting platform redirect URLs...')
            platform_links = extract_platform_links(flights_page, context)
            result['platform_links'] = platform_links
            print(f'    Platform links: {len(platform_links)}')

        # Determine status
        if result['booking_links']:
            # Check if any booking link has a price near the bug fare
            has_low_price = any(bl.get('hasPrice') for bl in result['booking_links'])
            result['status'] = 'LIVE_WITH_BOOKING' if has_low_price else 'LIVE_NO_PRICE'
        elif result.get('search_price'):
            result['status'] = 'LIVE_NO_BOOKING'
        else:
            result['status'] = 'UNCERTAIN'

        # Close the flights page
        try:
            flights_page.close()
        except:
            pass

    except Exception as e:
        result['status'] = f'ERROR: {e}'
        print(f'    Error: {e}')

    return result


def main():
    print(f"\n{'='*70}")
    print(f"  DEEP BUG FARE VERIFICATION")
    print(f"  Time: {datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d %H:%M Shanghai')}")
    print(f"  Target: Jakarta (CGK) Business -> USA")
    print(f"  Cities to verify: {len(VERIFY_CITIES)}")
    print(f"{'='*70}")

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1400, 'height': 900},
            locale='en-US',
        )

        # Step 0: Load Explore page
        print(f'\nStep 0: Loading Explore page...')
        explore_page = context.new_page()
        explore_page.goto(EXPLORE_URL, timeout=30000)
        time.sleep(5)

        # Accept cookies
        try:
            btn = explore_page.query_selector('button:has-text("Accept all")')
            if btn:
                btn.click()
                time.sleep(2)
        except:
            pass

        screenshot(explore_page, '01_explore_loaded')

        # Get initial city tabs
        tabs = get_city_tabs(explore_page)
        print(f'  Found {len(tabs)} city tabs')
        for t in tabs[:10]:
            print(f'    {t.get("cityGuess", t["text"][:40])} - ${t.get("price", "?")}')

        # Check initial page prices
        init_prices = extract_prices_from_page(explore_page)
        print(f'  Initial prices on page: {init_prices[:10]}')

        # Verify each city
        for i, city in enumerate(VERIFY_CITIES):
            print(f'\n{"─"*60}')
            print(f'  [{i+1}/{len(VERIFY_CITIES)}] Verifying: Jakarta -> {city}')
            print(f'{"─"*60}')

            result = verify_single_city(explore_page, context, city, i, explore_page)
            results.append(result)

            status_icon = {
                'LIVE_WITH_BOOKING': 'LIVE',
                'LIVE_NO_BOOKING': 'MAYBE',
                'LIVE_NO_PRICE': 'MAYBE',
                'click_failed': 'SKIP',
                'no_view_flights': 'NO VF',
                'UNCERTAIN': '???',
            }.get(result['status'], 'ERR')

            print(f'  Result: [{status_icon}] {result["status"]}')
            print(f'    Explore price: ${result.get("explore_price", "?")}')
            print(f'    Search price: ${result.get("search_price", "?")}')
            print(f'    Booking links: {len(result.get("booking_links", []))}')

            # Small delay between cities
            time.sleep(2)

            # Navigate back to explore page for next city
            try:
                explore_page.goto(EXPLORE_URL, timeout=30000)
                time.sleep(4)
            except:
                pass

        browser.close()

    # Save results
    output = {
        'verification_time': datetime.now(SHANGHAI_TZ).isoformat(),
        'origin': 'Jakarta (CGK)',
        'cabin': 'Business',
        'explore_url': EXPLORE_URL,
        'cities_verified': len(results),
        'results': results,
    }

    out_path = os.path.join(BASE_DIR, 'deep_verify_results.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Summary
    print(f"\n{'='*70}")
    print(f"  VERIFICATION SUMMARY")
    print(f"{'='*70}")
    live = [r for r in results if 'LIVE' in r.get('status', '')]
    dead = [r for r in results if r.get('status', '') in ('no_view_flights', 'click_failed')]
    errs = [r for r in results if 'ERROR' in r.get('status', '')]

    print(f"  Live (confirmed): {len(live)}")
    for r in live:
        print(f"    {r['city']}: ${r.get('explore_price','?')} -> {len(r.get('booking_links',[]))} booking links")

    print(f"  No booking found: {len(dead)}")
    for r in dead:
        print(f"    {r['city']}: {r['status']}")

    print(f"  Errors: {len(errs)}")
    print(f"\n  Results saved: {out_path}")
    print(f"  Screenshots: {BASE_DIR}/verify_*.png")


def rerun_for_platform_links():
    """Re-open existing Tokyo and Seoul booking pages to extract platform links.

    Reads deep_verify_tokyo_results.json and deep_verify_seoul_results.json,
    visits each booking_url, extracts platform links, and writes updated files.
    """
    result_files = [
        os.path.join(BASE_DIR, 'deep_verify_tokyo_results.json'),
        os.path.join(BASE_DIR, 'deep_verify_seoul_results.json'),
    ]

    print(f"\n{'='*70}")
    print(f"  RERUN: Extract platform links from existing booking pages")
    print(f"  Time: {datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d %H:%M Shanghai')}")
    print(f"{'='*70}")

    for fpath in result_files:
        if not os.path.exists(fpath):
            print(f'\n  [SKIP] {fpath} not found')
            continue

        print(f'\n  Loading {os.path.basename(fpath)}...')
        with open(fpath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        results = data.get('results', [])
        entries_with_booking = [r for r in results if r.get('booking_url')]
        print(f'  Found {len(entries_with_booking)} result(s) with booking_url')

        if not entries_with_booking:
            continue

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                           '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                viewport={'width': 1400, 'height': 900},
                locale='en-US',
            )

            for i, result in enumerate(results):
                booking_url = result.get('booking_url')
                if not booking_url:
                    print(f'\n  [{i+1}/{len(results)}] {result.get("city","?")} - no booking_url, skipping')
                    continue

                city = result.get('city', 'unknown')
                cabin = result.get('cabin', result.get('route', ''))
                print(f'\n  {"─"*55}')
                print(f'  [{i+1}/{len(results)}] {city} ({cabin})')
                print(f'  {"─"*55}')
                print(f'    Opening: {booking_url[:100]}...')

                try:
                    page = context.new_page()
                    page.goto(booking_url, timeout=30000)
                    time.sleep(8)  # Allow the booking page to fully render

                    # Dismiss cookie consent if prompted
                    try:
                        for consent_text in ['Reject all', 'Accept all']:
                            btn = page.get_by_role('button', name=consent_text)
                            if btn.count() > 0:
                                btn.first.click()
                                print(f'    Cookie consent: clicked "{consent_text}"')
                                time.sleep(2)
                                break
                    except Exception:
                        pass

                    # Screenshot the booking page
                    ss_name = f'rerun_{city.replace(" ","_")}_{i}_booking'
                    screenshot(page, ss_name)

                    # Extract platform links
                    print(f'    Extracting platform links...')
                    platform_links = extract_platform_links(page, context)
                    result['platform_links'] = platform_links
                    print(f'    Got {len(platform_links)} platform link(s)')

                    page.close()

                except Exception as e:
                    print(f'    Error: {e}')
                    result['platform_links'] = []

                time.sleep(2)

            browser.close()

        # Update the timestamp and save
        data['platform_links_updated'] = datetime.now(SHANGHAI_TZ).isoformat()
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f'\n  Updated: {fpath}')

    # Summary
    print(f"\n{'='*70}")
    print(f"  RERUN COMPLETE")
    print(f"{'='*70}")
    for fpath in result_files:
        if not os.path.exists(fpath):
            continue
        with open(fpath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for r in data.get('results', []):
            plinks = r.get('platform_links', [])
            city = r.get('city', '?')
            cabin = r.get('cabin', r.get('route', ''))
            if plinks:
                for pl in plinks:
                    print(f"  {city} ({cabin}): {pl['airline']} {pl['price']} -> {pl['url'][:80]}")
            else:
                print(f"  {city} ({cabin}): no platform links found")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Deep bug fare verification')
    parser.add_argument('--rerun', action='store_true',
                        help='Re-open existing Tokyo/Seoul booking pages to extract platform links')
    args = parser.parse_args()

    if args.rerun:
        rerun_for_platform_links()
    else:
        main()
