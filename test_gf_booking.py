"""Test complete flow: search → click depart → click return → booking page."""
import sys, os, time, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

URL = 'https://www.google.com/travel/flights?tfs=CBsQAhooEgoyMDI2LTA2LTI2agwIAxIIL20vMDNoNjRyDAgCEggvbS8wZDZscBooEgoyMDI2LTA3LTA1agwIAhIIL20vMGQ2bHByDAgDEggvbS8wM2g2NEABSAFSA1VTRHABemxDalJJZVc1cFRERlpYemxHTVdOQlFrdFhTVUZDUnkwdExTMHRMUzB0TFhkaWRtd3lPRUZCUVVGQlIyMDJVRmQzUTNoQ1YwbEJFZ1ZWUVRnMk1ob0xDTVMwQkJBQ0dnTlZVMFE0SEhERXRBUT2YAQGyARIYASABKgwIAhIIL20vMGQ2bHA&tfu=GgA&hl=en&gl=hk&curr=USD'
BASE = 'D:/claude/flights'

def find_flight_li(page):
    """Find first flight result li using Playwright locator."""
    all_lis = page.locator('li').all()
    for li in all_lis:
        try:
            text = li.inner_text(timeout=500)
            if re.search(r'\d{1,2}:\d{2}', text) and '$' in text and 30 < len(text) < 600:
                return li, text[:120]
        except:
            pass
    return None, None

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport={'width': 1400, 'height': 900},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
        locale='en-US',
    )
    page = ctx.new_page()

    # Step 1: Load search
    print("Step 1: Loading search page...")
    page.goto(URL, timeout=30000)
    page.wait_for_load_state('networkidle', timeout=20000)
    try:
        btn = page.get_by_role('button', name='Reject all')
        if btn.count() > 0: btn.first.click(); time.sleep(2)
    except: pass
    time.sleep(5)
    print(f"  URL: {page.url[:80]}")

    # Step 2: Click Cheapest tab
    print("Step 2: Clicking Cheapest tab...")
    try:
        tab = page.get_by_role('tab', name=re.compile(r'Cheapest'))
        if tab.count() > 0:
            tab.first.click()
            time.sleep(3)
            print("  Cheapest tab clicked")
    except: pass

    # Step 3: Click first departing flight (Playwright native click)
    print("Step 3: Clicking first departing flight...")
    li, text = find_flight_li(page)
    if li:
        print(f"  Flight: {text[:80]}")
        li.click(timeout=5000)
        time.sleep(5)
        page.screenshot(path=f'{BASE}/test_booking_01_depart.png')
        print(f"  URL after depart click: {page.url[:100]}")
    else:
        print("  No flight found!")
        browser.close()
        exit()

    # Step 4: Check if we're on return flight selection
    body = page.inner_text('body')[:2000]
    print(f"  'Returning flights' in page: {'Returning flights' in body}")
    print(f"  'return' in page: {'return' in body.lower()}")

    # Step 5: Click first return flight
    print("Step 5: Clicking first return flight...")
    time.sleep(3)
    li2, text2 = find_flight_li(page)
    if li2:
        print(f"  Return flight: {text2[:80]}")
        li2.click(timeout=5000)
        time.sleep(5)
        page.screenshot(path=f'{BASE}/test_booking_02_return.png')
        print(f"  URL after return click: {page.url[:120]}")
    else:
        print("  No return flight found!")

    # Step 6: Check if we're on booking page
    final_url = page.url
    print(f"\nStep 6: Final state")
    print(f"  URL: {final_url[:150]}")
    print(f"  Is booking page: {'/booking' in final_url}")

    if '/booking' in final_url:
        body = page.inner_text('body')[:2000]
        print(f"  'Book with' in page: {'Book with' in body}")
        bw = re.search(r'Book with\s+(.+?)(?:\n|Airline|$)', body)
        if bw:
            print(f"  Airline: {bw.group(1).strip()}")
        bp = re.search(r'\$([0-9,]+)', body)
        if bp:
            print(f"  Price: ${bp.group(1)}")
        page.screenshot(path=f'{BASE}/test_booking_03_final.png')
        print(f"\n  BOOKING URL:\n  {final_url}")
    else:
        # Maybe need to wait more
        time.sleep(5)
        final_url = page.url
        print(f"  After extra wait URL: {final_url[:150]}")
        print(f"  Is booking: {'/booking' in final_url}")
        page.screenshot(path=f'{BASE}/test_booking_03_final.png')

    browser.close()
