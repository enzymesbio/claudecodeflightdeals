#!/usr/bin/env python3
"""
Trip.com (Ctrip International) Business Class Flight Search
============================================================
Searches for business class flights from Jakarta (CGK) to London (LHR) and Los Angeles (LAX).

Approach 1: Direct URL with Playwright - navigates to Trip.com flight search URLs
Approach 2: Trip.com API endpoint - POST to flightListSearch REST API

Searches:
  - CGK -> LHR  OW  May 4, 2026  Business
  - CGK -> LAX  OW  May 4, 2026  Business
  - CGK -> LAX  OW  May 8, 2026  Business
"""

import sys
import io
import os
import json
import time
import re
import traceback
from datetime import datetime

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

# ============================================================================
# CONFIGURATION
# ============================================================================

SEARCHES = [
    {
        "origin": "CGK",
        "dest": "LHR",
        "origin_city": "jakarta",
        "dest_city": "london",
        "date": "2026-05-04",
        "label": "CGK-LHR May4 Business OW",
    },
    {
        "origin": "CGK",
        "dest": "LAX",
        "origin_city": "jakarta",
        "dest_city": "los-angeles",
        "date": "2026-05-04",
        "label": "CGK-LAX May4 Business OW",
    },
    {
        "origin": "CGK",
        "dest": "LAX",
        "origin_city": "jakarta",
        "dest_city": "los-angeles",
        "date": "2026-05-08",
        "label": "CGK-LAX May8 Business OW",
    },
]

SCREENSHOT_DIR = "D:/claude/flights"
ALL_RESULTS = {}

# ============================================================================
# HELPERS
# ============================================================================

def build_url(search):
    """Build Trip.com flight search URL with business class cabin=c."""
    origin_city = search["origin_city"]
    dest_city = search["dest_city"]
    origin = search["origin"].lower()
    dest = search["dest"].lower()
    date = search["date"]
    # cabin=c for business class
    url = (
        f"https://www.trip.com/flights/{origin_city}-to-{dest_city}/"
        f"tickets-{origin}-{dest}?"
        f"dcity={origin}&acity={dest}&ddate={date}"
        f"&cabin=c&adult=1&searchtype=OW"
    )
    return url


def build_api_payload(search):
    """Build the JSON payload for Trip.com flightListSearch API."""
    return {
        "airportParams": [
            {
                "dcity": search["origin"],
                "dcityname": search["origin_city"].replace("-", " ").title(),
                "acity": search["dest"],
                "acityname": search["dest_city"].replace("-", " ").title(),
                "date": search["date"],
            }
        ],
        "classType": "C",  # C = Business class
        "flightWay": "S",  # S = one-way
        "hasBaby": False,
        "hasChild": False,
        "hasInfant": False,
        "searchIndex": 1,
        "airportParamType": 0,
        "token": "",
        "adult": 1,
        "child": 0,
        "infant": 0,
        "cabin": "C",
    }


def safe_screenshot(page, path, full_page=False):
    """Take a screenshot, handling errors gracefully."""
    try:
        page.screenshot(path=path, full_page=full_page, timeout=15000)
        print(f"  Screenshot saved: {path}")
    except Exception as e:
        print(f"  Screenshot failed ({path}): {e}")


def extract_prices_from_page(page):
    """Try multiple selectors to extract flight prices from the DOM."""
    prices = []

    # Strategy 1: Look for common price selectors on Trip.com
    selectors_to_try = [
        # Trip.com common price selectors
        '[class*="price"]',
        '[class*="Price"]',
        '[class*="amount"]',
        '[class*="Amount"]',
        '[class*="fare"]',
        '[class*="Fare"]',
        '[class*="cost"]',
        '[class*="total"]',
        '[data-testid*="price"]',
        '.flight-price',
        '.ticket-price',
        '.o-price-flight',
        '.price-val',
        '.result-price',
        '.flight-item-price',
        '.price-text',
        '.currency',
    ]

    for sel in selectors_to_try:
        try:
            elements = page.query_selector_all(sel)
            for el in elements:
                text = el.inner_text().strip()
                if text and re.search(r'[\d,]+', text):
                    prices.append({"selector": sel, "text": text})
        except Exception:
            pass

    # Strategy 2: JavaScript extraction - look for price patterns in all text
    try:
        js_prices = page.evaluate("""() => {
            const results = [];
            // Look for elements containing currency symbols or price patterns
            const allText = document.body.innerText || '';
            // Find price-like patterns: $1,234 or USD 1,234 or 1,234 USD etc.
            const pricePatterns = allText.match(/(?:USD|US\\$|\\$|CNY|CN\\u00a5|\\u00a5|GBP|\\u00a3|IDR|Rp)\\s*[\\d,]+\\.?\\d*/gi) || [];
            const pricePatterns2 = allText.match(/[\\d,]+\\.?\\d*\\s*(?:USD|US\\$|CNY|GBP|IDR)/gi) || [];
            return { patterns1: pricePatterns.slice(0, 30), patterns2: pricePatterns2.slice(0, 30) };
        }""")
        if js_prices.get("patterns1"):
            for p in js_prices["patterns1"]:
                prices.append({"selector": "js_regex_1", "text": p})
        if js_prices.get("patterns2"):
            for p in js_prices["patterns2"]:
                prices.append({"selector": "js_regex_2", "text": p})
    except Exception as e:
        print(f"  JS price extraction error: {e}")

    # Strategy 3: Look for flight card/result containers
    try:
        flight_cards = page.evaluate("""() => {
            const results = [];
            // Look for flight list items
            const items = document.querySelectorAll(
                '[class*="flight-item"], [class*="FlightItem"], [class*="flight-card"], ' +
                '[class*="FlightCard"], [class*="result-item"], [class*="ResultItem"], ' +
                '[class*="flight-list"] > *, [class*="FlightList"] > *, ' +
                'li[class*="flight"], div[class*="itinerary"]'
            );
            items.forEach((item, idx) => {
                if (idx < 15) {
                    const text = item.innerText.replace(/\\n/g, ' | ').substring(0, 500);
                    results.push(text);
                }
            });
            return results;
        }""")
        if flight_cards:
            prices.append({"selector": "flight_cards", "text": json.dumps(flight_cards, ensure_ascii=False)})
    except Exception as e:
        print(f"  Flight card extraction error: {e}")

    return prices


def extract_api_response_data(response_data):
    """Parse the Trip.com API JSON response for flight details."""
    flights = []
    try:
        if isinstance(response_data, str):
            response_data = json.loads(response_data)

        # Try various response structures
        flight_list = (
            response_data.get("data", {}).get("flightItineraryList", [])
            or response_data.get("data", {}).get("routeList", [])
            or response_data.get("data", {}).get("flightList", [])
            or response_data.get("flightItineraryList", [])
            or response_data.get("routeList", [])
            or []
        )

        for idx, item in enumerate(flight_list[:20]):
            flight_info = {}

            # Extract price
            price_info = item.get("priceList", [{}])[0] if item.get("priceList") else {}
            if not price_info:
                price_info = item.get("price", {})
            flight_info["price"] = price_info.get("price", price_info.get("adultPrice", "N/A"))
            flight_info["currency"] = price_info.get("currency", price_info.get("currencyCode", ""))

            # Extract flight segments
            legs = item.get("flightSegments", item.get("legs", item.get("segmentList", [])))
            if legs:
                segs = []
                for leg in legs:
                    seg = {
                        "airline": leg.get("airlineName", leg.get("carrierName", "")),
                        "flight_no": leg.get("flightNo", leg.get("flightNumber", "")),
                        "depart": leg.get("departTime", leg.get("departureTime", "")),
                        "arrive": leg.get("arriveTime", leg.get("arrivalTime", "")),
                        "duration": leg.get("duration", ""),
                        "stops": leg.get("stopCount", leg.get("stops", 0)),
                        "cabin": leg.get("cabinClass", leg.get("cabin", "")),
                    }
                    segs.append(seg)
                flight_info["segments"] = segs

            flights.append(flight_info)

    except Exception as e:
        print(f"  API parse error: {e}")

    return flights


# ============================================================================
# APPROACH 1: Direct URL with Playwright
# ============================================================================

def approach1_direct_url(pw_browser, search):
    """Navigate to Trip.com search URL and extract results."""
    label = search["label"].replace(" ", "_")
    url = build_url(search)
    print(f"\n{'='*70}")
    print(f"APPROACH 1 - Direct URL: {search['label']}")
    print(f"URL: {url}")
    print(f"{'='*70}")

    context = pw_browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1440, "height": 900},
        locale="en-US",
        timezone_id="Asia/Shanghai",
    )

    # Capture network responses that might contain flight data
    api_responses = []

    def handle_response(response):
        url_lower = response.url.lower()
        if any(kw in url_lower for kw in ["flightsearch", "flightlist", "flight/search",
                                            "batchsearch", "domesticflight", "intlflight",
                                            "restapi", "flightitinerary"]):
            try:
                body = response.json()
                api_responses.append({"url": response.url, "data": body})
                print(f"  [INTERCEPT] Captured API response from: {response.url[:120]}")
            except Exception:
                pass

    page = context.new_page()
    page.on("response", handle_response)

    try:
        # Navigate to the search URL
        print("  Navigating to Trip.com search page...")
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        print("  Page loaded (domcontentloaded). Waiting for network idle...")

        # Wait for network idle
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
            print("  Network idle reached.")
        except Exception:
            print("  Network idle timeout - continuing anyway.")

        # Extra wait for JS rendering
        print("  Waiting 12 seconds for dynamic content...")
        time.sleep(12)

        # Take screenshots
        safe_screenshot(page, f"{SCREENSHOT_DIR}/tripcom_url_{label}_viewport.png")
        safe_screenshot(page, f"{SCREENSHOT_DIR}/tripcom_url_{label}_full.png", full_page=True)

        # Check for CAPTCHA or blocking page
        page_text = page.inner_text("body")
        if any(kw in page_text.lower() for kw in ["captcha", "verify", "robot", "blocked",
                                                     "access denied", "security check"]):
            print("  WARNING: Possible CAPTCHA or anti-bot page detected!")

        # Try scrolling to trigger lazy loading
        print("  Scrolling to trigger lazy loading...")
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(1)

        # Wait a bit more after scrolling
        time.sleep(3)

        # Take post-scroll screenshot
        safe_screenshot(page, f"{SCREENSHOT_DIR}/tripcom_url_{label}_scrolled.png", full_page=True)

        # Extract prices from DOM
        print("  Extracting prices from DOM...")
        prices = extract_prices_from_page(page)

        # Get page title for debugging
        title = page.title()
        print(f"  Page title: {title}")

        # Get page content length
        content_len = len(page_text)
        print(f"  Page text length: {content_len} chars")

        # Show first 800 chars of page for debugging
        print(f"  Page text preview: {page_text[:800]}")

        result = {
            "approach": "direct_url",
            "search": search["label"],
            "url": url,
            "page_title": title,
            "content_length": content_len,
            "dom_prices": prices,
            "api_responses_captured": len(api_responses),
            "api_flights": [],
        }

        # Parse any intercepted API responses
        for resp in api_responses:
            flights = extract_api_response_data(resp["data"])
            if flights:
                result["api_flights"].extend(flights)
                print(f"  Extracted {len(flights)} flights from intercepted API response")

        # Print summary
        if prices:
            print(f"\n  DOM Prices found ({len(prices)}):")
            seen = set()
            for p in prices[:30]:
                key = p["text"][:100]
                if key not in seen:
                    seen.add(key)
                    print(f"    [{p['selector']}]: {p['text'][:200]}")
        else:
            print("  No prices found in DOM.")

        if result["api_flights"]:
            print(f"\n  API Flights found ({len(result['api_flights'])}):")
            for f in result["api_flights"][:10]:
                print(f"    Price: {f.get('price')} {f.get('currency')} | Segments: {f.get('segments', [])}")

        return result

    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        safe_screenshot(page, f"{SCREENSHOT_DIR}/tripcom_url_{label}_error.png")
        return {"approach": "direct_url", "search": search["label"], "error": str(e)}
    finally:
        context.close()


# ============================================================================
# APPROACH 2: Trip.com API endpoint
# ============================================================================

def approach2_api(pw_browser, search):
    """Try the Trip.com REST API for flight search."""
    label = search["label"].replace(" ", "_")
    api_url = "https://www.trip.com/restapi/soa2/14021/flightListSearch"
    payload = build_api_payload(search)

    print(f"\n{'='*70}")
    print(f"APPROACH 2 - API: {search['label']}")
    print(f"Endpoint: {api_url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print(f"{'='*70}")

    context = pw_browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1440, "height": 900},
        locale="en-US",
    )
    page = context.new_page()

    try:
        # First visit Trip.com homepage to get cookies/session
        print("  Visiting Trip.com homepage for session cookies...")
        try:
            page.goto("https://www.trip.com/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            print("  Homepage loaded. Got session cookies.")
        except Exception as e:
            print(f"  Homepage load issue (continuing): {e}")

        # Now make the API call via page.evaluate (fetch from browser context)
        print("  Making API request via browser fetch...")
        api_result = page.evaluate("""async (payload) => {
            try {
                const resp = await fetch('https://www.trip.com/restapi/soa2/14021/flightListSearch', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                    },
                    body: JSON.stringify(payload),
                    credentials: 'include',
                });
                const status = resp.status;
                const text = await resp.text();
                return { status: status, body: text, ok: resp.ok };
            } catch(e) {
                return { error: e.message };
            }
        }""", payload)

        print(f"  API response status: {api_result.get('status', 'N/A')}")

        result = {
            "approach": "api",
            "search": search["label"],
            "api_url": api_url,
            "status": api_result.get("status"),
            "flights": [],
            "raw_response_preview": "",
        }

        if api_result.get("error"):
            print(f"  API fetch error: {api_result['error']}")
            result["error"] = api_result["error"]
        elif api_result.get("body"):
            body = api_result["body"]
            result["raw_response_preview"] = body[:2000]
            print(f"  Response body length: {len(body)} chars")
            print(f"  Response preview: {body[:500]}")

            # Try to parse as JSON
            try:
                data = json.loads(body)
                # Save full API response for analysis
                api_response_file = f"{SCREENSHOT_DIR}/tripcom_api_{label}.json"
                with open(api_response_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"  Full API response saved to: {api_response_file}")

                # Extract flights
                flights = extract_api_response_data(data)
                result["flights"] = flights
                if flights:
                    print(f"\n  API Flights found ({len(flights)}):")
                    for f_item in flights[:10]:
                        print(f"    Price: {f_item.get('price')} {f_item.get('currency')}")
                else:
                    print("  No flights parsed from API response.")

                # Check for error messages in the response
                if data.get("msg") or data.get("message"):
                    msg = data.get("msg") or data.get("message")
                    print(f"  API message: {msg}")
                    result["api_message"] = msg

                if data.get("code") or data.get("status"):
                    code = data.get("code") or data.get("status")
                    print(f"  API code: {code}")
                    result["api_code"] = code

            except json.JSONDecodeError:
                print(f"  Response is not valid JSON.")
                result["parse_error"] = "Not valid JSON"

        # Also try alternate API endpoints
        alt_endpoints = [
            "https://www.trip.com/restapi/soa2/14021/flightListSearch",
            "https://www.trip.com/restapi/soa2/16769/flightListSearch",
        ]

        for alt_url in alt_endpoints:
            if alt_url == api_url:
                continue
            print(f"\n  Trying alternate endpoint: {alt_url}")
            try:
                alt_result = page.evaluate("""async ([url, payload]) => {
                    try {
                        const resp = await fetch(url, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Accept': 'application/json',
                            },
                            body: JSON.stringify(payload),
                            credentials: 'include',
                        });
                        const text = await resp.text();
                        return { status: resp.status, body: text.substring(0, 3000) };
                    } catch(e) {
                        return { error: e.message };
                    }
                }""", [alt_url, payload])
                print(f"    Status: {alt_result.get('status', 'N/A')}")
                print(f"    Preview: {alt_result.get('body', '')[:300]}")
            except Exception as e:
                print(f"    Error: {e}")

        return result

    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        return {"approach": "api", "search": search["label"], "error": str(e)}
    finally:
        context.close()


# ============================================================================
# APPROACH 2b: Navigate to search URL and intercept the API call Trip.com makes
# ============================================================================

def approach2b_intercept(pw_browser, search):
    """Navigate to Trip.com with business class URL, intercept all XHR responses."""
    label = search["label"].replace(" ", "_")
    url = build_url(search)

    print(f"\n{'='*70}")
    print(f"APPROACH 2b - Intercept XHR: {search['label']}")
    print(f"URL: {url}")
    print(f"{'='*70}")

    context = pw_browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1440, "height": 900},
        locale="en-US",
        timezone_id="Asia/Shanghai",
    )

    api_responses = []
    all_xhr_urls = []

    def handle_response(response):
        url_str = response.url
        # Log all XHR-like responses
        if "restapi" in url_str or "soa2" in url_str or "flight" in url_str.lower():
            all_xhr_urls.append(url_str)
            try:
                ct = response.headers.get("content-type", "")
                if "json" in ct or "javascript" in ct:
                    body = response.json()
                    api_responses.append({
                        "url": url_str[:200],
                        "status": response.status,
                        "data": body,
                    })
                    print(f"  [XHR] {response.status} {url_str[:120]}")
            except Exception:
                pass

    page = context.new_page()
    page.on("response", handle_response)

    try:
        print("  Navigating with XHR interception...")
        page.goto(url, wait_until="domcontentloaded", timeout=45000)

        try:
            page.wait_for_load_state("networkidle", timeout=25000)
        except Exception:
            print("  Network idle timeout - continuing.")

        print("  Waiting 15 seconds for all XHR to complete...")
        time.sleep(15)

        # Take screenshot
        safe_screenshot(page, f"{SCREENSHOT_DIR}/tripcom_xhr_{label}_full.png", full_page=True)

        # Report what was intercepted
        print(f"\n  Total XHR URLs captured: {len(all_xhr_urls)}")
        for u in all_xhr_urls[:20]:
            print(f"    {u[:150]}")

        print(f"\n  JSON API responses captured: {len(api_responses)}")

        result = {
            "approach": "xhr_intercept",
            "search": search["label"],
            "xhr_count": len(all_xhr_urls),
            "api_responses_count": len(api_responses),
            "flights": [],
        }

        for resp in api_responses:
            # Save each response
            resp_data = resp.get("data", {})
            # Try to extract flights
            flights = extract_api_response_data(resp_data)
            if flights:
                result["flights"].extend(flights)

            # Also look for any price-related keys in the response
            resp_str = json.dumps(resp_data, ensure_ascii=False)[:5000]
            if any(kw in resp_str.lower() for kw in ["price", "fare", "amount", "itinerary"]):
                print(f"\n  Price-related response from: {resp['url'][:120]}")
                print(f"    Preview: {resp_str[:500]}")

                # Save the full response
                safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', label)
                api_file = f"{SCREENSHOT_DIR}/tripcom_xhr_data_{safe_name}_{len(result['flights'])}.json"
                try:
                    with open(api_file, "w", encoding="utf-8") as f:
                        json.dump(resp_data, f, ensure_ascii=False, indent=2)
                    print(f"    Saved to: {api_file}")
                except Exception:
                    pass

        if result["flights"]:
            print(f"\n  Total flights extracted: {len(result['flights'])}")
            for f_item in result["flights"][:10]:
                print(f"    Price: {f_item.get('price')} {f_item.get('currency')}")

        return result

    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        return {"approach": "xhr_intercept", "search": search["label"], "error": str(e)}
    finally:
        context.close()


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 70)
    print("Trip.com Business Class Flight Search")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    all_results = []

    with sync_playwright() as p:
        print("\nLaunching Chromium browser...")
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
            ],
        )

        for search in SEARCHES:
            print(f"\n\n{'#'*70}")
            print(f"# SEARCH: {search['label']}")
            print(f"{'#'*70}")

            # Approach 1: Direct URL
            r1 = approach1_direct_url(browser, search)
            all_results.append(r1)

            # Approach 2: API call
            r2 = approach2_api(browser, search)
            all_results.append(r2)

            # Approach 2b: XHR intercept
            r2b = approach2b_intercept(browser, search)
            all_results.append(r2b)

        browser.close()

    # ========================================================================
    # FINAL SUMMARY
    # ========================================================================
    print("\n\n" + "=" * 70)
    print("FINAL SUMMARY OF ALL RESULTS")
    print("=" * 70)

    for search in SEARCHES:
        label = search["label"]
        print(f"\n--- {label} ---")

        for r in all_results:
            if r.get("search") != label:
                continue

            approach = r.get("approach", "?")
            if r.get("error"):
                print(f"  [{approach}] ERROR: {r['error'][:200]}")
                continue

            # Report DOM prices
            dom_prices = r.get("dom_prices", [])
            if dom_prices:
                seen = set()
                unique_prices = []
                for p in dom_prices:
                    txt = p["text"][:150]
                    if txt not in seen:
                        seen.add(txt)
                        unique_prices.append(p)
                print(f"  [{approach}] DOM prices ({len(unique_prices)} unique):")
                for p in unique_prices[:15]:
                    print(f"    {p['text'][:200]}")

            # Report API flights
            api_flights = r.get("api_flights", []) or r.get("flights", [])
            if api_flights:
                print(f"  [{approach}] Flights from API ({len(api_flights)}):")
                for f_item in api_flights[:10]:
                    segs = f_item.get("segments", [])
                    seg_str = " -> ".join(
                        f"{s.get('airline','')} {s.get('flight_no','')}"
                        for s in segs
                    ) if segs else "N/A"
                    print(f"    {f_item.get('price','?')} {f_item.get('currency','')} | {seg_str}")

            # Report API messages
            if r.get("api_message"):
                print(f"  [{approach}] API message: {r['api_message']}")

            if not dom_prices and not api_flights and not r.get("api_message"):
                print(f"  [{approach}] No results found.")

    # Save all results to JSON
    output_file = f"{SCREENSHOT_DIR}/tripcom_search_results.json"
    # Make results serializable
    serializable = []
    for r in all_results:
        sr = {}
        for k, v in r.items():
            try:
                json.dumps(v)
                sr[k] = v
            except (TypeError, ValueError):
                sr[k] = str(v)
        serializable.append(sr)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    print(f"\nAll results saved to: {output_file}")


if __name__ == "__main__":
    main()
