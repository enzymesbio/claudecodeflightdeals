"""Deep verify HK cheap fares by going directly to Google Flights search page (skip Explore)."""
import sys, os, json, time, re, base64
from datetime import datetime, timedelta, timezone

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

BASE_DIR = 'D:/claude/flights'
SHANGHAI_TZ = timezone(timedelta(hours=8))
EXCLUDE_AIRLINES = ['ZIPAIR', 'Philippine Airlines', 'Malaysia Airlines', 'Cebu Pacific']
EXCLUDE_DESTS = ['Honolulu', 'Kauai']

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

def click_first_flight(page):
    """Click the first flight result."""
    return page.evaluate(r"""() => {
        const items = document.querySelectorAll('li');
        for (const li of items) {
            const text = li.innerText || '';
            if (text.includes('hr') && text.includes('min') && /\$\d/.test(text)) {
                li.click();
                return text.substring(0, 100);
            }
        }
        return null;
    }""")

def main():
    # Load HK fares from scanner results
    with open(os.path.join(BASE_DIR, 'scanner_results.json'), encoding='utf-8') as f:
        data = json.load(f)

    hk_fares = [d for d in data['destinations']
                if d['origin_city'] == 'Hong Kong'
                and d['destination'] not in EXCLUDE_DESTS
                and d['classification'] in ('CHEAP', 'BUG_FARE')]
    hk_fares.sort(key=lambda x: x['price_usd'])

    # Take top 5 cheapest
    targets = hk_fares[:5]

    print('=' * 60)
    print(f"  HK DIRECT VERIFICATION (skip Explore, use search URLs)")
    print(f"  Time: {datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d %H:%M Shanghai')}")
    print(f"  Fares to verify: {len(targets)}")
    print('=' * 60)

    for t in targets:
        dates = t.get('dates', '').replace('\u2009', ' ').replace('\u2013', '-')
        print(f"  ${t['price_usd']:>6.0f} | {t['destination']:20s} | {t['cabin']:15s} | {dates}")

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1400, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
            locale='en-US',
        )

        for fare in targets:
            dest = fare['destination']
            price = fare['price_usd']
            cabin = fare['cabin']
            dates = fare.get('dates', '').replace('\u2009', ' ').replace('\u2013', '-')
            detail_url = fare.get('verification', {}).get('detail_url', '')

            print(f"\n{'─' * 55}")
            print(f"  HK → {dest} | {cabin} ${price:.0f} | {dates}")
            print(f"{'─' * 55}")

            result = {
                'city': dest,
                'cabin': cabin,
                'explore_price': price,
                'dates': dates,
                'status': 'UNKNOWN',
                'booking_url': None,
                'airline': None,
                'price': None,
                'screenshots': [],
            }

            if not detail_url or detail_url == 'none':
                print(f"  No search URL available, skipping")
                result['status'] = 'NO_URL'
                results.append(result)
                continue

            page = context.new_page()
            print(f"  Opening search page...")
            print(f"  URL: {detail_url[:100]}...")

            try:
                page.goto(detail_url, timeout=30000)
                page.wait_for_load_state('domcontentloaded')
                dismiss_cookies(page)
                print(f"  Waiting 10s for search results...")
                time.sleep(10)

                result['screenshots'].append(screenshot(page, f'{dest}_01_search'))

                # Extract prices from page
                page_text = page.inner_text('body')[:2000]
                price_matches = re.findall(r'\$(\d{1,5}(?:,\d{3})*)', page_text)
                prices = sorted(set(int(p.replace(',', '')) for p in price_matches if int(p.replace(',', '')) > 50))
                if prices:
                    result['search_prices'] = prices[:8]
                    print(f"  Search prices: {prices[:5]}")

                # Step 2: Click first outbound flight
                print(f"  Clicking first outbound flight...")
                clicked = click_first_flight(page)
                if clicked:
                    print(f"    Clicked: {clicked[:80]}")
                time.sleep(4)
                result['screenshots'].append(screenshot(page, f'{dest}_02_outbound'))

                # Step 3: Click return flight
                print(f"  Waiting for return flights...")
                time.sleep(3)
                click_first_flight(page)
                time.sleep(5)
                result['screenshots'].append(screenshot(page, f'{dest}_03_return'))

                # Step 4: Check if booking page
                current_url = page.url
                if 'booking' not in current_url:
                    time.sleep(5)
                    current_url = page.url

                result['booking_url'] = current_url
                result['screenshots'].append(screenshot(page, f'{dest}_04_booking'))

                booking_text = page.inner_text('body')[:2000]

                if "can't find booking" in booking_text.lower():
                    result['status'] = 'GHOST'
                    print(f"  GHOST FARE!")
                elif 'Booking options' in booking_text or 'Book with' in booking_text:
                    result['status'] = 'BOOKABLE'
                    # Extract airline
                    bw = re.search(r'Book with\s+(.+?)(?:Airline|$)', booking_text, re.MULTILINE)
                    if bw:
                        result['airline'] = bw.group(1).strip()
                    # Extract price
                    bp = re.search(r'\$([0-9,]+)', booking_text)
                    if bp:
                        result['price'] = int(bp.group(1).replace(',', ''))
                    print(f"  BOOKABLE: {result['airline']} ${result.get('price', '?')}")

                    # Check if excluded airline
                    if result['airline']:
                        for excl in EXCLUDE_AIRLINES:
                            if excl.lower() in result['airline'].lower():
                                result['excluded'] = True
                                print(f"  *** EXCLUDED AIRLINE ***")
                                break
                else:
                    result['status'] = 'UNCLEAR'
                    print(f"  Status unclear. URL: {current_url[:100]}")

                print(f"  Booking URL: {current_url[:100]}")

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
        print(f"  {r['city']:20s} | {r['status']:12s} | {airline:20s} | {price}{excluded}")

    print(f"\nSaved to: {out_path}")


if __name__ == '__main__':
    main()
