"""
Google Flights Business Class Search via Playwright.
Uses the ?q= URL format which reliably loads search results.
"""
import os, sys, time, json, re

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = "D:/claude/flights"

SEARCHES = [
    {"origin": "CGK", "dest": "LHR", "date": "2026-05-04", "label": "CGK-LHR_May4"},
    {"origin": "CGK", "dest": "LAX", "date": "2026-05-04", "label": "CGK-LAX_May4"},
    {"origin": "CGK", "dest": "LAX", "date": "2026-05-08", "label": "CGK-LAX_May8"},
]


def ss(page, name):
    path = f"{SCREENSHOT_DIR}/gf_biz_{name}.png"
    page.screenshot(path=path)
    print(f"    Screenshot: {name}")


def handle_consent(page):
    try:
        body = page.evaluate("() => document.body.innerText.substring(0, 300)")
        if "Before you continue" in body:
            page.evaluate("""() => {
                const b = [...document.querySelectorAll('button')].find(b =>
                    b.textContent.includes('Reject all') || b.textContent.includes('Accept all'));
                if (b) b.click();
            }""")
            time.sleep(3)
            return True
    except:
        pass
    return False


def extract_flight_results(page):
    """Extract structured flight data from aria-labels and page content."""
    flights = []

    # Method 1: aria-labels on flight result items
    # These typically contain full flight info like:
    # "Departing flight on Monday, May 4. Leaves Jakarta at 7:30 PM, arrives at Los Angeles at 4:30 PM on Tuesday, May 5. Total travel time 35 hr. Garuda Indonesia, SWISS. 2 stops, SIN and ZRH. $521."
    for el in page.locator("[aria-label]").all():
        lbl = el.get_attribute("aria-label") or ""
        # Check if this is a flight result label
        if any(kw in lbl.lower() for kw in ["departing flight", "leaves", "arrives", "total travel time"]):
            price_match = re.findall(r'\$[\d,]+', lbl)
            price = price_match[0] if price_match else "N/A"
            price_val = int(price.replace("$", "").replace(",", "")) if price_match else 0
            flights.append({
                "price": price,
                "value": price_val,
                "details": lbl,
                "src": "aria-full"
            })

    # Method 2: Extract from visible flight rows
    # Get all text from flight result items
    page_text = page.evaluate("() => document.body.innerText")

    # Method 3: Simple price extraction from spans
    prices = []
    for sp in page.locator("span").all():
        text = (sp.text_content() or "").strip()
        if re.match(r'^\$[\d,]+$', text):
            val = int(text.replace("$", "").replace(",", ""))
            if 50 < val < 50000:
                # Get parent context
                ctx = sp.evaluate("e => { let p = e.closest('li, [data-resultid], [class]'); return p ? p.textContent.substring(0, 300) : ''; }")
                prices.append({"price": text, "value": val, "ctx": ctx, "src": "text"})

    return flights, prices


def run_search(browser, cfg):
    label = cfg["label"]
    print(f"\n{'='*60}")
    print(f"SEARCH: {label} - {cfg['origin']} -> {cfg['dest']} on {cfg['date']}")
    print(f"{'='*60}")

    ctx = browser.new_context(
        viewport={"width": 1400, "height": 900},
        locale="en-US",
        timezone_id="America/New_York",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    page = ctx.new_page()

    try:
        # Handle consent first
        print("  Handling consent...")
        page.goto("https://www.google.com/travel/flights", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        handle_consent(page)
        time.sleep(1)

        # Use the ?q= URL format that works
        url = f"https://www.google.com/travel/flights?q={cfg['origin']}+to+{cfg['dest']}+{cfg['date']}+business+class+one+way&hl=en&gl=us&curr=USD"
        print(f"  Loading: {url}")
        page.goto(url, wait_until="networkidle", timeout=30000)
        time.sleep(3)
        handle_consent(page)

        # Wait for results to load
        print("  Waiting for flight results...")
        try:
            page.wait_for_selector("[aria-label*='Departing flight'], [aria-label*='departing flight'], [data-resultid]", timeout=20000)
            print("    Flight results detected")
        except:
            try:
                page.wait_for_selector("span:has-text('$')", timeout=10000)
            except:
                pass
        time.sleep(5)

        # Click "View more flights" to expand results
        try:
            view_more = page.locator("button:has-text('View more flights'), span:has-text('View more flights')").first
            view_more.click(force=True, timeout=5000)
            print("    Expanded 'View more flights'")
            time.sleep(3)
        except:
            pass

        # Scroll to load all
        for _ in range(6):
            page.evaluate("window.scrollBy(0, 600)")
            time.sleep(0.8)

        # Take screenshots
        ss(page, f"{label}_results")
        try:
            page.screenshot(path=f"{SCREENSHOT_DIR}/gf_biz_{label}_full.png", full_page=True)
            print(f"    Full-page screenshot saved")
        except:
            pass

        # Extract flight data
        print("  Extracting flight data...")
        flights, prices = extract_flight_results(page)

        final_url = page.url
        print(f"  URL: {final_url}")

        # Also check for price insights popup
        insights = page.evaluate("""() => {
            const text = document.body.innerText;
            const matches = text.match(/Travel on.*?\\$[\\d,]+/g) || [];
            const low = text.match(/Prices are currently low.*?\\$[\\d,]+.*?cheaper/g) || [];
            return { popup: matches, low: low };
        }""")
        if insights.get("popup"):
            print(f"\n  PRICE INSIGHTS POPUP: {insights['popup']}")
        if insights.get("low"):
            print(f"  LOW PRICE ALERT: {insights['low']}")

        # Print flight results
        if flights:
            # Filter to only those with prices
            with_price = [f for f in flights if f["value"] > 0]
            sorted_f = sorted(with_price, key=lambda x: x["value"])
            print(f"\n  DETAILED FLIGHT RESULTS: {len(with_price)} with prices (of {len(flights)} total)")
            for i, f in enumerate(sorted_f[:25]):
                print(f"\n    [{i+1}] {f['price']}")
                print(f"        {f['details'][:250]}")
        elif prices:
            sorted_p = sorted(prices, key=lambda x: x["value"])
            print(f"\n  PRICES: {len(prices)}")
            for i, p in enumerate(sorted_p[:30]):
                print(f"    [{i+1}] {p['price']}: {p['ctx'][:150]}")
        else:
            print("\n  NO RESULTS FOUND")
            vis = page.evaluate("() => document.body.innerText.substring(0, 2000)")
            print(f"  Page: {vis[:1000]}")

        # Combine for return
        all_prices = []
        for f in flights:
            all_prices.append({"price": f["price"], "value": f["value"], "src": f["src"], "ctx": f["details"][:300]})
        for p in prices:
            all_prices.append({"price": p["price"], "value": p["value"], "src": p["src"], "ctx": p["ctx"][:300]})

        # Bug fare candidates
        cheap = [p for p in all_prices if 0 < p["value"] < 1000]
        if cheap:
            print(f"\n  *** BUG FARE CANDIDATES (< $1000): {len(cheap)} ***")
            for p in cheap:
                print(f"    >>> {p['price']}: {p['ctx'][:200]}")

        return all_prices

    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        try:
            ss(page, f"{label}_error")
        except:
            pass
        return []
    finally:
        ctx.close()


def main():
    print("Google Flights Business Class Bug Fare Search")
    print("=" * 60)
    print("Target: CGK business class interline bug fares ($200-900)")
    print("Star Alliance routes: THAI+Austrian, SQ+SWISS/Lufthansa, GA+SWISS/LH")
    print()

    all_results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for cfg in SEARCHES:
            results = run_search(browser, cfg)
            all_results[cfg["label"]] = results
        browser.close()

    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    for label, results in all_results.items():
        print(f"\n{'='*40}")
        print(f"{label}")
        print(f"{'='*40}")
        if results:
            sp = sorted([r for r in results if r["value"] > 0], key=lambda x: x["value"])
            print(f"  Total results: {len(results)}")
            if sp:
                print(f"  Cheapest: {sp[0]['price']}")
                print(f"  Most expensive: {sp[-1]['price']}")

            # Show all under $1500
            affordable = [p for p in sp if p["value"] < 1500]
            if affordable:
                print(f"\n  Flights under $1500 ({len(affordable)}):")
                for p in affordable:
                    print(f"    {p['price']}: {p['ctx'][:150]}")

            # Bug fares
            bugs = [p for p in sp if p["value"] < 1000]
            if bugs:
                print(f"\n  *** BUG FARES (< $1000): {len(bugs)} ***")
                for p in bugs:
                    print(f"    >>> {p['price']}: {p['ctx'][:200]}")
        else:
            print("  No results")

    # Save
    with open(f"{SCREENSHOT_DIR}/gf_biz_results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved: {SCREENSHOT_DIR}/gf_biz_results.json")
    print("Screenshots saved to:", SCREENSHOT_DIR)


if __name__ == "__main__":
    main()
