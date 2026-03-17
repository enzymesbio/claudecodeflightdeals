#!/usr/bin/env python3
"""
ITA Matrix Scraper v3 - Full working scraper for Matrix v5 (Angular Material)
Uses Playwright (Chromium, headless) to search and extract flight/price data.

Proven to work:
- Page loads and renders fully
- Airport autocomplete works (type code -> click mat-option)
- Date range inputs accept M/D/YYYY format
- Search button enables and clicking triggers search
- Results page shows prices, airlines, times, durations, routes
- Uses USD currency for price consistency
"""

import json
import re
import time
import traceback
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

SCREENSHOT_DIR = Path("D:/claude/flights/ita_screenshots")
RESULTS_FILE = Path("D:/claude/flights/ita_matrix_results.json")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://matrix.itasoftware.com/search"

SEARCHES = [
    {
        "origin": "ICN",
        "destination": "LAX",
        "depart": "5/15/2026",
        "return": "6/15/2026",
        "label": "ICN-LAX",
    },
    {
        "origin": "CTU",
        "destination": "LAX",
        "depart": "5/15/2026",
        "return": "6/15/2026",
        "label": "CTU-LAX",
    },
    {
        "origin": "PVG",
        "destination": "SFO",
        "depart": "5/15/2026",
        "return": "6/15/2026",
        "label": "PVG-SFO",
    },
]

GOOGLE_COOKIES = [
    {"name": "CONSENT", "value": "YES+cb.20210720-07-p0.en+FX+410", "domain": ".google.com", "path": "/"},
    {"name": "CONSENT", "value": "YES+cb.20210720-07-p0.en+FX+410", "domain": ".itasoftware.com", "path": "/"},
]


def screenshot(page, name):
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"  [screenshot] {name}.png")
    return str(path)


def fill_airport(page, input_id, airport_code, label):
    """Fill an airport autocomplete field by typing the code and clicking the dropdown option."""
    print(f"  Filling {label}: {airport_code}")
    inp = page.locator(f"#{input_id}")
    inp.click()
    time.sleep(0.3)
    inp.fill("")
    inp.type(airport_code, delay=80)
    try:
        page.wait_for_selector("mat-option", timeout=5000)
        time.sleep(0.5)
        options = page.locator("mat-option")
        count = options.count()
        if count > 0:
            # For city codes like CTU, pick the airport (not city) option if available
            chosen = None
            for oi in range(count):
                text = options.nth(oi).inner_text()
                if f"({airport_code})" in text:
                    chosen = oi
                    break
            if chosen is None:
                chosen = 0
            option_text = options.nth(chosen).inner_text().replace("\n", " ")
            print(f"    Selected: '{option_text}'")
            options.nth(chosen).click()
            time.sleep(0.5)
            return True
    except PlaywrightTimeout:
        page.keyboard.press("Enter")
        time.sleep(0.5)
    return False


def fill_dates(page, depart_date, return_date):
    """Fill the date range inputs. Dates should be in M/D/YYYY format."""
    print(f"  Filling dates: {depart_date} - {return_date}")
    start_input = page.locator(".mat-start-date")
    end_input = page.locator(".mat-end-date")
    start_input.click()
    time.sleep(0.3)
    start_input.fill(depart_date)
    time.sleep(0.3)
    page.keyboard.press("Tab")
    time.sleep(0.3)
    end_input.fill(return_date)
    time.sleep(0.3)
    page.keyboard.press("Escape")
    time.sleep(0.3)
    return True


def set_currency_usd(page):
    """Set the search currency to USD."""
    print("  Setting currency to USD...")
    try:
        currency_input = page.locator("#mat-input-10")
        currency_input.click()
        time.sleep(0.3)
        currency_input.fill("")
        currency_input.type("USD", delay=80)
        time.sleep(1)
        # Click the USD option in autocomplete
        try:
            page.wait_for_selector("mat-option", timeout=3000)
            options = page.locator("mat-option")
            for i in range(options.count()):
                text = options.nth(i).inner_text()
                if "USD" in text:
                    options.nth(i).click()
                    print(f"    Selected: '{text.strip()}'")
                    time.sleep(0.5)
                    return True
        except PlaywrightTimeout:
            page.keyboard.press("Enter")
            time.sleep(0.3)
    except Exception as e:
        print(f"    Currency set error: {e}")
    return False


def parse_results_text(text, search_label):
    """Parse the results page text into structured flight data."""
    flights = []

    # The results text has a repeating pattern:
    # price\tairline\tdepart_times\tarrive_times\tduration\tfrom_to\tstops\tadvisory
    lines = text.split("\n")

    # Find where results start (after the column headers)
    result_start = 0
    for i, line in enumerate(lines):
        if "Items per page:" in line:
            break
        # Prices start with currency symbols like $, Won, CNY, EUR
        if re.match(r'^[\$\u20A9\u00A5\u20AC][\d,]+', line.strip()) or re.match(r'^[A-Z]{3}\s*[\d,]+', line.strip()):
            result_start = i
            break

    # Parse flights from text blocks
    # Each flight is a block: price, airline, depart/return times, arrive/return times, durations, routes
    i = result_start
    while i < len(lines):
        line = lines[i].strip()

        # Match price patterns: $1,234 or Won1,234,000 etc.
        price_match = re.match(r'^([\$\u20A9\u00A5\u20AC][\d,]+(?:\.\d{2})?)', line)
        if not price_match and re.match(r'^[A-Z]{3}\s*[\d,]+', line):
            price_match = re.match(r'^([A-Z]{3}\s*[\d,]+(?:\.\d{2})?)', line)

        if price_match:
            price = price_match.group(1)

            # Collect the next several non-empty lines for this flight entry
            flight_lines = []
            j = i + 1
            while j < len(lines) and len(flight_lines) < 20:
                stripped = lines[j].strip()
                if stripped and not stripped.startswith("filter_alt"):
                    flight_lines.append(stripped)
                j += 1
                # Stop if we hit the next price
                if j < len(lines):
                    next_stripped = lines[j].strip() if j < len(lines) else ""
                    if re.match(r'^[\$\u20A9\u00A5\u20AC][\d,]+', next_stripped):
                        break
                    if re.match(r'^[A-Z]{3}\s*[\d,]+', next_stripped) and not re.match(r'^[A-Z]{3}\s+to\s+[A-Z]{3}', next_stripped):
                        break

            # Parse flight_lines
            if len(flight_lines) >= 4:
                airline = flight_lines[0] if flight_lines else "Unknown"

                # Extract times (patterns like "9:20 PM" or "10:00 AM")
                time_pattern = r'\d{1,2}:\d{2}\s*(?:AM|PM)'
                all_times = []
                for fl in flight_lines:
                    all_times.extend(re.findall(time_pattern, fl))

                # Extract durations
                duration_pattern = r'\d+h\s*\d+m'
                durations = []
                for fl in flight_lines:
                    durations.extend(re.findall(duration_pattern, fl))

                # Extract routes
                route_pattern = r'[A-Z]{3}\s+to\s+[A-Z]{3}'
                routes = []
                for fl in flight_lines:
                    routes.extend(re.findall(route_pattern, fl))

                # Extract stops info
                stops_text = ""
                for fl in flight_lines:
                    if re.match(r'^[A-Z]{3}$', fl) or "stop" in fl.lower():
                        stops_text = fl

                flight_entry = {
                    "price": price,
                    "airline": airline,
                    "outbound": {
                        "depart": all_times[0] if len(all_times) > 0 else "",
                        "arrive": all_times[2] if len(all_times) > 2 else (all_times[1] if len(all_times) > 1 else ""),
                        "duration": durations[0] if len(durations) > 0 else "",
                        "route": routes[0] if len(routes) > 0 else "",
                    },
                    "return": {
                        "depart": all_times[1] if len(all_times) > 1 else "",
                        "arrive": all_times[3] if len(all_times) > 3 else "",
                        "duration": durations[1] if len(durations) > 1 else "",
                        "route": routes[1] if len(routes) > 1 else "",
                    },
                    "stops": stops_text,
                }
                flights.append(flight_entry)

            i = j
        else:
            i += 1

    return flights


def parse_matrix_summary(text):
    """Parse the airline price matrix at the top of results."""
    matrix = {}
    lines = text.split("\n")

    # Look for the matrix section (between "All flights" / "Nonstops" / "1 stop" and the table headers)
    airlines = []
    in_matrix = False
    current_row = ""

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "All flights":
            in_matrix = True
            continue
        if in_matrix and stripped in ["Price", "Airline", "Depart"]:
            in_matrix = False
            break
        if in_matrix:
            # Airlines are listed before the price rows
            if stripped and not re.match(r'^[\$\u20A9\u00A5\u20AC\-]', stripped) and stripped not in [
                "Nonstops", "1 stop", "2 stops", "Hide matrix", "--", ""
            ] and not re.match(r'^\d', stripped):
                airlines.append(stripped)
            # Price rows start with category like "Nonstops", "1 stop"
            if stripped in ["Nonstops", "1 stop", "2 stops"]:
                current_row = stripped
                # The next lines contain prices for each airline
                prices_line = []
                for j in range(i + 1, min(i + len(airlines) + 2, len(lines))):
                    val = lines[j].strip()
                    if val and (re.match(r'^[\$\u20A9\u00A5\u20AC]', val) or val == "--"):
                        prices_line.append(val)
                    elif val in ["Nonstops", "1 stop", "2 stops", "Price", ""]:
                        break
                matrix[current_row] = dict(zip(airlines[:len(prices_line)], prices_line))

    return {"airlines": airlines, "matrix": matrix}


def get_all_pages(page, max_pages=3):
    """Get results from multiple pages by clicking the next button."""
    all_text = page.inner_text("body")

    for pg in range(1, max_pages):
        try:
            # Check if there's a next page button
            next_btn = page.locator("button[aria-label='Next page'], button:has(mat-icon:text('chevron_right'))").last
            if next_btn.is_visible() and not next_btn.is_disabled():
                print(f"    Loading page {pg + 1}...")
                next_btn.click()
                time.sleep(5)
                page_text = page.inner_text("body")
                all_text += "\n" + page_text
            else:
                break
        except Exception as e:
            print(f"    Page navigation error: {e}")
            break

    return all_text


def do_search(page, search, step_prefix):
    """Perform a complete search on ITA Matrix and extract flight data."""
    print(f"\n{'='*60}")
    print(f"SEARCH: {search['label']} ({search['origin']} -> {search['destination']})")
    print(f"  Dates: {search['depart']} - {search['return']}")
    print(f"{'='*60}")

    result = {
        "search": search,
        "success": False,
        "flights": [],
        "matrix_summary": {},
        "total_results": 0,
        "error": None,
    }

    try:
        # Step 1: Navigate
        print("  Step 1: Loading ITA Matrix...")
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#mat-input-0", timeout=15000)
        time.sleep(2)

        # Close welcome banner
        try:
            close_btn = page.locator("button:has(mat-icon:text('clear'))").first
            if close_btn.is_visible():
                close_btn.click()
                time.sleep(0.5)
        except:
            pass

        # Step 2: Set currency to USD
        set_currency_usd(page)
        time.sleep(0.5)

        # Step 3: Fill origin
        fill_airport(page, "mat-input-0", search["origin"], "Origin")
        time.sleep(0.5)

        # Step 4: Fill destination
        fill_airport(page, "mat-input-1", search["destination"], "Destination")
        time.sleep(0.5)

        # Step 5: Fill dates
        fill_dates(page, search["depart"], search["return"])
        time.sleep(0.5)

        screenshot(page, f"{step_prefix}_form")

        # Step 6: Click search
        search_btn = page.locator("button:has-text('Search')").last
        is_disabled = search_btn.is_disabled()
        print(f"  Search button disabled: {is_disabled}")

        if is_disabled:
            print("  ERROR: Search button is disabled. Form not fully valid.")
            result["error"] = "search_button_disabled"
            screenshot(page, f"{step_prefix}_disabled")
            return result

        print("  Clicking Search...")
        search_btn.click()

        # Step 7: Wait for results (the actual flight data, not just the results page header)
        print("  Waiting for results (up to 120s)...")
        max_wait = 120
        found_results = False
        for wait_i in range(max_wait // 5):
            time.sleep(5)
            try:
                body = page.inner_text("body")
                # The actual results contain "Items per page" at the bottom and price data
                # "Choose your flights" appears immediately but the spinner runs for 15-60s
                if "Items per page" in body:
                    print(f"    Results loaded after {(wait_i + 1) * 5}s!")
                    found_results = True
                    break
                if "Hide matrix" in body:
                    print(f"    Results loaded after {(wait_i + 1) * 5}s (matrix visible)!")
                    found_results = True
                    break
                if "No results found" in body or "no flights" in body.lower():
                    print(f"    No results found after {(wait_i + 1) * 5}s")
                    result["error"] = "no_results"
                    break
                print(f"    Waiting... ({(wait_i + 1) * 5}s)")
            except:
                pass

        # Take results screenshot
        screenshot(page, f"{step_prefix}_results")

        if not found_results:
            # One more try - maybe it loaded while we were checking
            time.sleep(5)
            body = page.inner_text("body")
            if "Choose your flights" in body:
                found_results = True
                screenshot(page, f"{step_prefix}_results_late")

        # Step 8: Extract data
        if found_results:
            print("  Extracting flight data...")
            # Get first page
            body_text = page.inner_text("body")

            # Parse total results count
            total_match = re.search(r'of\s+(\d+)', body_text)
            if total_match:
                result["total_results"] = int(total_match.group(1))
                print(f"    Total results: {result['total_results']}")

            # Parse matrix summary
            result["matrix_summary"] = parse_matrix_summary(body_text)
            if result["matrix_summary"]["airlines"]:
                print(f"    Airlines in matrix: {result['matrix_summary']['airlines']}")
                for stop_type, prices in result["matrix_summary"]["matrix"].items():
                    print(f"    {stop_type}: {prices}")

            # Get additional pages
            all_text = get_all_pages(page, max_pages=2)

            # Save full text
            with open(SCREENSHOT_DIR / f"{step_prefix}_all_text.txt", "w", encoding="utf-8") as f:
                f.write(all_text)

            # Parse flight entries
            result["flights"] = parse_results_text(all_text, search["label"])
            print(f"    Parsed {len(result['flights'])} flights")

            if result["flights"]:
                result["success"] = True
                # Show top 5
                for j, f in enumerate(result["flights"][:5]):
                    print(f"    [{j+1}] {f['price']} - {f['airline']} - "
                          f"Out: {f['outbound']['depart']}->{f['outbound']['arrive']} ({f['outbound']['duration']}) - "
                          f"Ret: {f['return']['depart']}->{f['return']['arrive']} ({f['return']['duration']})")
        else:
            print("  No results page detected")
            body_text = page.inner_text("body")
            result["error"] = f"no_results_page (text: {body_text[:200]})"

    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        result["error"] = str(e)
        try:
            screenshot(page, f"{step_prefix}_error")
        except:
            pass

    return result


def main():
    print("=" * 70)
    print("ITA Matrix Scraper v3 (with USD + data extraction)")
    print(f"Started at: {datetime.now().isoformat()}")
    print("=" * 70)

    all_results = {
        "timestamp": datetime.now().isoformat(),
        "version": 3,
        "searches": [],
    }

    with sync_playwright() as p:
        print("\nLaunching Chromium (headless)...")
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )

        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        context.add_cookies(GOOGLE_COOKIES)

        for i, search in enumerate(SEARCHES):
            page = context.new_page()
            result = do_search(page, search, f"v3_{search['label']}")
            all_results["searches"].append(result)
            page.close()
            time.sleep(2)

        browser.close()

    # Save results
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved to {RESULTS_FILE}")

    # Summary
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    for s in all_results["searches"]:
        label = s["search"]["label"]
        success = s["success"]
        n_flights = len(s["flights"])
        total = s["total_results"]
        error = s.get("error")
        print(f"\n  {label}: {'SUCCESS' if success else 'FAILED'}")
        print(f"    Flights extracted: {n_flights} / {total} total")
        if s["matrix_summary"].get("matrix"):
            for stop_type, prices in s["matrix_summary"]["matrix"].items():
                print(f"    Matrix {stop_type}: {prices}")
        if s["flights"]:
            cheapest = s["flights"][0]
            print(f"    Cheapest: {cheapest['price']} on {cheapest['airline']}")
        if error:
            print(f"    Error: {error}")

    print(f"\nScreenshots: {SCREENSHOT_DIR}")
    print(f"Results JSON: {RESULTS_FILE}")
    print(f"Finished at: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
