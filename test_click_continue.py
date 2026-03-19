"""Test clicking the Continue button on a Google Flights booking page to capture platform URL."""
import sys, time, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

# Use the Tokyo Business -> LA booking URL
BOOKING_URL = "https://www.google.com/travel/flights/booking?tfs=CBwQAhpKEgoyMDI2LTA3LTE2Ih4KA05SVBIKMjAyNi0wNy0xNhoDTEFYKgJaRzICMzRqDAgDEggvbS8wN2Rma3IOCAISCi9tLzAzMHFiM3QaShIKMjAyNi0wNy0yMiIeCgNMQVgSCjIwMjYtMDctMjIaA05SVCoCWkcyAjIzag4IAhIKL20vMDMwcWIzdHIMCAMSCC9tLzA3ZGZrQAFIA3ABggELCP___________wGYAQE&tfu=CmxDalJJVVU5WVFrOWZjRXhKY2tWQlFuVXRZM2RDUnkwdExTMHRMUzB0TFhkbWFHc3lNRUZCUVVGQlIyMDJURVZKVFVwTlZ6QkJFZ1JhUnpJekdnc0l4K29TRUFJYUExVlRSRGdjY01mcUVnPT0SAggAIgA&hl=en&gl=hk&curr=USD"

def dismiss_cookie_consent(page):
    """Click 'Reject all' or 'Accept all' on Google cookie consent."""
    try:
        # Wait for cookie dialog
        time.sleep(2)
        # Try to find and click "Reject all" first (less tracking)
        clicked = page.evaluate(r"""() => {
            const buttons = document.querySelectorAll('button, [role="button"]');
            for (const b of buttons) {
                const text = (b.innerText || '').trim().toLowerCase();
                if (text === 'reject all' || text === 'accept all') {
                    b.click();
                    return text;
                }
            }
            // Also check inside iframes
            const iframes = document.querySelectorAll('iframe');
            for (const iframe of iframes) {
                try {
                    const doc = iframe.contentDocument;
                    if (!doc) continue;
                    const btns = doc.querySelectorAll('button, [role="button"]');
                    for (const b of btns) {
                        const text = (b.innerText || '').trim().toLowerCase();
                        if (text === 'reject all' || text === 'accept all') {
                            b.click();
                            return text;
                        }
                    }
                } catch(e) {}
            }
            return null;
        }""")
        if clicked:
            print(f"  Cookie consent: clicked '{clicked}'")
            time.sleep(2)
        else:
            # Try Playwright's locator approach
            for text in ['Reject all', 'Accept all']:
                btn = page.get_by_role('button', name=text)
                if btn.count() > 0:
                    btn.first.click()
                    print(f"  Cookie consent: clicked '{text}' via locator")
                    time.sleep(2)
                    return
            print("  No cookie consent dialog found")
    except Exception as e:
        print(f"  Cookie consent error: {e}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={'width': 1400, 'height': 900},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
        locale='en-US',
    )
    page = context.new_page()

    print("Opening booking page...")
    page.goto(BOOKING_URL, timeout=30000)
    page.wait_for_load_state('networkidle', timeout=15000)
    time.sleep(2)

    # Handle cookie consent
    dismiss_cookie_consent(page)

    # Wait for actual page content to load
    page.wait_for_load_state('networkidle', timeout=15000)
    time.sleep(3)

    page.screenshot(path='D:/claude/flights/test_click_booking.png')
    print(f"Page title: {page.title()}")
    print(f"URL: {page.url[:120]}")

    # Check page content
    body_text = page.inner_text('body')[:500]
    print(f"Body text: {body_text[:300]}")

    # Find all elements with text "Continue"
    continue_els = page.evaluate(r"""() => {
        const results = [];
        const all = document.querySelectorAll('a, button, [role="button"], [role="link"]');
        for (const el of all) {
            const text = (el.innerText || el.textContent || '').trim();
            if (/^Continue$/i.test(text)) {
                results.push({
                    tag: el.tagName,
                    text: text,
                    href: el.href || '',
                    role: el.getAttribute('role') || '',
                    classes: el.className || '',
                    parentText: (el.parentElement?.parentElement?.innerText || '').substring(0, 200),
                });
            }
        }
        return results;
    }""")

    print(f"\nFound {len(continue_els)} Continue element(s):")
    for i, el in enumerate(continue_els):
        print(f"\n  [{i}] <{el['tag']}> role={el['role']}")
        print(f"      href: {el['href'][:200] if el['href'] else 'NONE'}")
        print(f"      classes: {el['classes'][:100]}")
        print(f"      parent text: {el['parentText'][:150]}")

    # Now try clicking
    if continue_els:
        print("\n\nClicking first Continue button...")
        try:
            with context.expect_page(timeout=10000) as new_page_info:
                page.evaluate(r"""() => {
                    const all = document.querySelectorAll('a, button, [role="button"], [role="link"]');
                    for (const el of all) {
                        if (/^Continue$/i.test((el.innerText || '').trim())) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""")
            new_tab = new_page_info.value
            new_tab.wait_for_load_state('domcontentloaded', timeout=15000)
            time.sleep(3)
            print(f"  NEW TAB URL: {new_tab.url}")
            new_tab.screenshot(path='D:/claude/flights/test_click_newtab.png')
            new_tab.close()
        except Exception as e:
            print(f"  No new tab: {e}")
            time.sleep(3)
            current = page.url
            if current != BOOKING_URL and 'consent' not in current:
                print(f"  PAGE REDIRECTED TO: {current}")
                page.screenshot(path='D:/claude/flights/test_click_redirect.png')
            else:
                print(f"  Page did NOT navigate.")
                page.screenshot(path='D:/claude/flights/test_click_nochange.png')
    else:
        print("\nNo Continue buttons found. Checking if booking content loaded...")
        # Look for "Book with" text
        book_with = page.evaluate(r"""() => {
            const body = document.body.innerText;
            const match = body.match(/Book with.+/g);
            return match || [];
        }""")
        print(f"'Book with' matches: {book_with}")

    browser.close()
    print("\nDone!")
