"""Test different click approaches to reach Google Flights booking page."""
import sys, os, time, re, asyncio
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

# HK→SFO search URL (known to work, shows $723 United)
URL = 'https://www.google.com/travel/flights?tfs=CBsQAhooEgoyMDI2LTA2LTI2agwIAxIIL20vMDNoNjRyDAgCEggvbS8wZDZscBooEgoyMDI2LTA3LTA1agwIAhIIL20vMGQ2bHByDAgDEggvbS8wM2g2NEABSAFSA1VTRHABemxDalJJZVc1cFRERlpYemxHTVdOQlFrdFhTVUZDUnkwdExTMHRMUzB0TFhkaWRtd3lPRUZCUVVGQlIyMDJVRmQzUTNoQ1YwbEJFZ1ZWUVRnMk1ob0xDTVMwQkJBQ0dnTlZVMFE0SEhERXRBUT2YAQGyARIYASABKgwIAhIIL20vMGQ2bHA&tfu=GgA&hl=en&gl=hk&curr=USD'

BASE = 'D:/claude/flights'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport={'width': 1400, 'height': 900},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
        locale='en-US',
    )
    page = ctx.new_page()

    # Listen for new pages (in case clicking opens new tab)
    new_pages = []
    ctx.on('page', lambda p: new_pages.append(p))

    page.goto(URL, timeout=30000)
    page.wait_for_load_state('networkidle', timeout=20000)

    # Dismiss cookies
    try:
        btn = page.get_by_role('button', name='Reject all')
        if btn.count() > 0:
            btn.first.click()
            time.sleep(2)
    except: pass

    time.sleep(5)
    page.screenshot(path=f'{BASE}/test_click_01_loaded.png')
    print("Page loaded. URL:", page.url[:100])

    # First click "Cheapest" tab using Playwright locator
    print("\n--- Clicking Cheapest tab ---")
    try:
        cheapest = page.get_by_role('tab', name=re.compile(r'Cheapest'))
        if cheapest.count() > 0:
            cheapest.first.click()
            print("  Clicked Cheapest tab via role=tab")
        else:
            # Try button
            cheapest = page.locator('button:has-text("Cheapest")')
            if cheapest.count() > 0:
                cheapest.first.click()
                print("  Clicked Cheapest via button:has-text")
    except Exception as e:
        print(f"  Cheapest tab error: {e}")
    time.sleep(3)

    # Method 1: Find flight li items and try Playwright native click
    print("\n--- Method 1: Playwright locator click on li ---")
    flight_lis = page.locator('li').all()
    target_li = None
    for li in flight_lis:
        try:
            text = li.inner_text(timeout=1000)
            if 'hr' in text and '$' in text and len(text) > 30 and len(text) < 600:
                target_li = li
                print(f"  Found flight li: {text[:80]}")
                break
        except: pass

    if target_li:
        print("  Clicking with Playwright native click...")
        try:
            target_li.click(timeout=5000)
            print("  Click succeeded!")
            time.sleep(3)
            page.screenshot(path=f'{BASE}/test_click_02_after_li.png')
        except Exception as e:
            print(f"  Click failed: {e}")

    # Check for "Select flight" button
    print("\n--- Checking for 'Select flight' button ---")
    page_text = page.inner_text('body')[:5000]
    if 'Select flight' in page_text:
        print("  'Select flight' button IS visible!")
        sel_btn = page.get_by_role('button', name='Select flight')
        if sel_btn.count() > 0:
            print(f"  Found {sel_btn.count()} 'Select flight' button(s)")
            sel_btn.first.click()
            print("  Clicked 'Select flight'!")
            time.sleep(5)
            page.screenshot(path=f'{BASE}/test_click_03_after_select.png')
            print(f"  URL after select: {page.url[:120]}")
    else:
        print("  No 'Select flight' in page text")
        # Check what IS visible after click
        print(f"  Page text sample: {page_text[500:1000]}")

    # Method 2: Try clicking price element directly
    print("\n--- Method 2: Click on price span ---")
    price_spans = page.locator('span:has-text("$723")').all()
    print(f"  Found {len(price_spans)} spans with '$723'")
    if price_spans:
        try:
            price_spans[0].click(timeout=5000)
            print("  Clicked price span!")
            time.sleep(3)
            page.screenshot(path=f'{BASE}/test_click_04_price.png')
        except Exception as e:
            print(f"  Price click error: {e}")

    # Method 3: Try the expand chevron
    print("\n--- Method 3: Click expand/chevron button ---")
    chevrons = page.locator('[aria-label*="more"], [aria-label*="expand"], [aria-label*="detail"]').all()
    print(f"  Found {len(chevrons)} expand buttons")
    if chevrons:
        try:
            chevrons[0].click(timeout=5000)
            time.sleep(3)
            page.screenshot(path=f'{BASE}/test_click_05_expand.png')
        except Exception as e:
            print(f"  Expand click error: {e}")

    # Method 4: Try data-resultid elements
    print("\n--- Method 4: data-resultid elements ---")
    results = page.locator('[data-resultid]').all()
    print(f"  Found {len(results)} [data-resultid] elements")

    # Method 5: Check DOM for flight info
    print("\n--- Method 5: Extract flight data from DOM ---")
    flight_data = page.evaluate(r"""() => {
        // Look for any data attributes or structured data
        const items = document.querySelectorAll('li');
        const flights = [];
        for (const li of items) {
            const text = (li.innerText || '').trim();
            if (/\d{1,2}:\d{2}/.test(text) && /\$\d/.test(text) && text.length > 30) {
                const attrs = {};
                for (const attr of li.attributes) {
                    attrs[attr.name] = attr.value;
                }
                // Check data on parent and grandparent
                const parentAttrs = {};
                if (li.parentElement) {
                    for (const attr of li.parentElement.attributes) {
                        parentAttrs[attr.name] = attr.value;
                    }
                }
                flights.push({
                    text: text.substring(0, 150),
                    attrs: attrs,
                    parentAttrs: parentAttrs,
                    className: li.className,
                    role: li.getAttribute('role'),
                    tagName: li.tagName,
                    childCount: li.children.length,
                    firstChildTag: li.children[0]?.tagName,
                });
                if (flights.length >= 3) break;
            }
        }
        return flights;
    }""")
    for fd in flight_data:
        print(f"  Flight: {fd['text'][:80]}")
        print(f"    attrs: {fd['attrs']}")
        print(f"    parent attrs: {fd['parentAttrs']}")
        print(f"    class: {fd['className'][:80]}")
        print(f"    role: {fd['role']}, children: {fd['childCount']}")

    # Final state
    print(f"\nFinal URL: {page.url[:120]}")
    print(f"New pages opened: {len(new_pages)}")

    browser.close()
