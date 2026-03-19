"""
Google Flights XHR/API Intercept Script
Uses Playwright to load Google Flights search URLs and intercept all network
requests/responses to capture flight data API calls (protobuf/JSON).
Handles Google's cookie consent dialog automatically.
"""

import sys
import os
import json
import time
import re
import hashlib
from datetime import datetime
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

# Output directory
OUT_DIR = Path("D:/claude/flights/gf_api_responses")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# URLs to search
urls = [
    ('CGK-LAX BIZ RT May8-Jun15',
     'https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA1LTA4agcIARIDQ0dLcgcIARIDTEFYGh4SCjIwMjYtMDYtMTVqBwgBEgNMQVhyBwgBEgNDR0tAAUgDcAGCAQsI____________AZgBAQ&curr=USD'),
    ('CGK-LHR BIZ OW May4',
     'https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA1LTA0agcIARIDQ0dLcgcIARIDTEhSQAFIA3ABggELCP___________wGYAQE&curr=USD'),
]

# Patterns that indicate flight/price data in URLs
FLIGHT_URL_PATTERNS = [
    r'travel/flights',
    r'TravelFrontend',
    r'batchexecute',
    r'_/Travel',
    r'flights/rpc',
    r'FlightSearch',
    r'proton',
]

# Patterns in response bodies that indicate flight data
FLIGHT_BODY_KEYWORDS = [
    b'price', b'Price', b'PRICE',
    b'flight', b'Flight', b'FLIGHT',
    b'offer', b'Offer', b'OFFER',
    b'itinerary', b'Itinerary',
    b'airline', b'Airline',
    b'CGK', b'LAX', b'LHR',
    b'Jakarta', b'Los Angeles', b'London', b'Heathrow',
    b'depart', b'Depart',
    b'arrival', b'Arrival',
    b'USD', b'usd',
    b'cabin', b'Cabin',
    b'business', b'Business',
    b'economy', b'Economy',
    b'duration', b'Duration',
    b'layover', b'Layover',
    b'stop', b'Stop',
    b'nonstop', b'Nonstop',
    b'booking', b'Booking',
    b'carrier', b'Carrier',
]

# URL patterns to skip entirely (static assets / tracking)
SKIP_URL_PATTERNS = [
    r'\.(png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|eot|css)(\?|$)',
    r'gstatic\.com.*\.(js|svg|woff|css)',
    r'googleusercontent\.com',
    r'youtube\.com',
    r'doubleclick\.net',
    r'googlesyndication',
    r'googleadservices',
    r'google-analytics',
    r'googletagmanager',
    r'fonts\.googleapis',
    r'play\.google\.com',
    r'accounts\.google',
    r'consent\.google',
    r'ogs\.google\.com',
    r'ssl\.gstatic\.com',
]


def sanitize_filename(name: str) -> str:
    return re.sub(r'[^\w\-.]', '_', name)[:100]


def should_skip_url(url: str) -> bool:
    for pattern in SKIP_URL_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    return False


def is_flight_related_url(url: str) -> bool:
    for pattern in FLIGHT_URL_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    return False


def body_has_flight_data(body: bytes) -> tuple[bool, list[str]]:
    found = []
    for kw in FLIGHT_BODY_KEYWORDS:
        if kw in body:
            found.append(kw.decode('utf-8', errors='replace'))
    return len(found) >= 3, found


def save_response(label: str, url: str, body: bytes, content_type: str,
                  status: int, keywords: list[str], index: int) -> str:
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    safe_label = sanitize_filename(label)

    ext = '.bin'
    if 'json' in content_type:
        ext = '.json'
    elif 'html' in content_type:
        ext = '.html'
    elif 'text/plain' in content_type:
        ext = '.txt'
    elif 'protobuf' in content_type or 'proto' in content_type:
        ext = '.pb'
    elif 'octet-stream' in content_type:
        ext = '.bin'

    filename = f"{safe_label}_{index:03d}_{url_hash}{ext}"
    filepath = OUT_DIR / filename
    filepath.write_bytes(body)

    meta = {
        'url': url,
        'content_type': content_type,
        'status': status,
        'body_size': len(body),
        'keywords_found': keywords,
        'saved_at': datetime.now().isoformat(),
        'filename': filename,
    }
    meta_path = OUT_DIR / f"{safe_label}_{index:03d}_{url_hash}_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding='utf-8')

    return str(filepath)


def handle_consent(page):
    """Handle Google's cookie consent dialog if it appears."""
    print("  Checking for consent dialog...")
    try:
        # Check if we're on the consent page
        if 'consent.google' in page.url:
            print("  Consent page detected! Clicking 'Reject all'...")
            # Try multiple selectors for the reject/accept button
            selectors = [
                'button:has-text("Reject all")',
                'button:has-text("Accept all")',
                '[aria-label="Reject all"]',
                '[aria-label="Accept all"]',
                'form[action*="consent"] button:nth-of-type(1)',
                'button.VfPpkd-LgbsSe',
            ]
            for sel in selectors:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=2000):
                        print(f"    Found button: {sel}")
                        btn.click()
                        print("    Clicked consent button!")
                        # Wait for navigation after consent
                        page.wait_for_timeout(3000)
                        return True
                except Exception:
                    continue

            # Fallback: try clicking by coordinates or form submission
            print("  Trying fallback consent handling...")
            try:
                page.evaluate("""
                    var buttons = document.querySelectorAll('button');
                    for (var b of buttons) {
                        if (b.textContent.includes('Reject') || b.textContent.includes('Accept')) {
                            b.click();
                            break;
                        }
                    }
                """)
                page.wait_for_timeout(3000)
                return True
            except Exception as e:
                print(f"    Fallback failed: {e}")
        else:
            print("  No consent page detected, proceeding...")
    except Exception as e:
        print(f"  Consent handling error: {e}")
    return False


def run_search(label: str, url: str, browser, context_to_reuse=None):
    """Run a single search URL and capture all API responses."""
    print(f"\n{'='*80}")
    print(f"SEARCH: {label}")
    print(f"URL: {url}")
    print(f"{'='*80}")

    safe_label = sanitize_filename(label)
    captured = []
    all_requests = []
    response_index = [0]

    if context_to_reuse:
        context = context_to_reuse
    else:
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='en-US',
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
            }
        )

    page = context.new_page()

    # ---- Response handler ----
    def on_response(response):
        resp_url = response.url
        status = response.status
        content_type = response.headers.get('content-type', '')

        all_requests.append({
            'url': resp_url[:300],
            'status': status,
            'content_type': content_type[:80],
            'resource_type': 'unknown',
        })

        # Skip static assets
        if should_skip_url(resp_url):
            return

        # Skip certain content types
        skip_types = ['image/', 'font/', 'text/css', 'video/', 'audio/']
        for st in skip_types:
            if st in content_type:
                return

        # Skip JS files (but not JSON or API responses)
        if ('javascript' in content_type and
            'batchexecute' not in resp_url and
            'TravelFrontend' not in resp_url and
            'travel' not in resp_url):
            return

        try:
            body = response.body()
        except Exception:
            return

        if not body or len(body) < 50:
            return

        url_match = is_flight_related_url(resp_url)
        body_match, keywords = body_has_flight_data(body)

        if url_match or body_match:
            idx = response_index[0]
            response_index[0] += 1

            saved_path = save_response(safe_label, resp_url, body, content_type,
                                       status, keywords, idx)
            entry = {
                'index': idx,
                'url': resp_url[:300],
                'status': status,
                'content_type': content_type,
                'body_size': len(body),
                'url_matched': url_match,
                'body_keywords': keywords[:10],
                'saved_to': saved_path,
            }
            captured.append(entry)
            print(f"  [CAPTURED #{idx}] {status} | {len(body):,} bytes | "
                  f"CT: {content_type[:50]} | URL: {url_match}")
            print(f"    {resp_url[:150]}")
            if keywords:
                print(f"    Keywords: {', '.join(keywords[:8])}")

    page.on("response", on_response)

    def on_request(request):
        if is_flight_related_url(request.url) and not should_skip_url(request.url):
            print(f"  [REQ] {request.method} {request.resource_type} -> {request.url[:150]}")

    page.on("request", on_request)

    # Navigate
    print(f"\nNavigating...")
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=60000)
        print(f"  Loaded: {page.url[:100]}")
    except Exception as e:
        print(f"  Navigation warning: {e}")

    # Handle consent dialog
    consent_handled = handle_consent(page)

    if consent_handled:
        print("  Consent handled, waiting for flight page to load...")
        try:
            page.wait_for_load_state('networkidle', timeout=30000)
        except Exception:
            pass
        page.wait_for_timeout(5000)

        # Check if we need to navigate again (consent may have redirected)
        current_url = page.url
        print(f"  Current URL after consent: {current_url[:100]}")

        if 'travel/flights' not in current_url:
            print("  Re-navigating to flights URL...")
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            print(f"  Re-navigated to: {page.url[:100]}")

    # Wait for network idle
    print("Waiting for network idle...")
    try:
        page.wait_for_load_state('networkidle', timeout=45000)
        print("  Network idle reached")
    except Exception as e:
        print(f"  Network idle timeout: {e}")

    # Extra wait for deferred API calls
    print("Waiting 10s for deferred API calls...")
    page.wait_for_timeout(10000)

    # Scroll to trigger lazy loading
    print("Scrolling to trigger lazy loading...")
    for i in range(6):
        page.evaluate(f"window.scrollBy(0, {600 * (i+1)})")
        page.wait_for_timeout(2000)

    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(2000)

    # Screenshot
    ss_path = f"D:/claude/flights/gf_api_responses/{safe_label}_screenshot.png"
    page.screenshot(path=ss_path, full_page=True)
    print(f"Screenshot: {ss_path}")

    # ---- Extract JS data ----
    print("\nExtracting JavaScript flight data...")
    js_extractions = {}

    js_checks = [
        ("WIZ_global_data", "window.WIZ_global_data"),
        ("AF_dataServiceRequests",
         """
         (function() {
             try {
                 if (window.AF_dataServiceRequests) {
                     return JSON.stringify(window.AF_dataServiceRequests).substring(0, 50000);
                 }
             } catch(e) {}
             return null;
         })()
         """),
        ("inline_scripts_with_data",
         """
         (function() {
             var scripts = document.querySelectorAll('script:not([src])');
             var found = [];
             for (var i = 0; i < scripts.length; i++) {
                 var text = scripts[i].textContent || '';
                 if (text.length > 200) {
                     var hasData = (
                         text.includes('AF_initDataCallback') ||
                         text.includes('CGK') || text.includes('LAX') || text.includes('LHR') ||
                         text.includes('price') || text.includes('Price') ||
                         text.includes('flight') || text.includes('Flight') ||
                         text.includes('itinerary') || text.includes('offer')
                     );
                     if (hasData) {
                         found.push({
                             index: i,
                             length: text.length,
                             snippet: text.substring(0, 2000)
                         });
                     }
                 }
             }
             return found;
         })()
         """),
        ("visible_flight_results",
         """
         (function() {
             var results = [];
             // Try common Google Flights result selectors
             var selectors = [
                 'li[class]', '[data-ved]', '[class*="result"]',
                 '[class*="flight"]', '[class*="price"]',
                 '[role="listitem"]', '.gws-flights-results__result-item',
                 '[class*="itinerary"]', 'ul li',
             ];
             var seen = new Set();
             for (var sel of selectors) {
                 var els = document.querySelectorAll(sel);
                 for (var i = 0; i < Math.min(els.length, 50); i++) {
                     var el = els[i];
                     var text = (el.innerText || '').trim();
                     if (text.length > 20 && text.length < 3000 && !seen.has(text)) {
                         if (text.match(/\\$[\\d,]+/) || text.includes('USD') ||
                             text.includes('hr') || text.includes('stop') ||
                             text.includes('min') || text.includes('nonstop')) {
                             seen.add(text);
                             results.push({
                                 selector: sel,
                                 tag: el.tagName,
                                 className: (el.className || '').toString().substring(0, 150),
                                 text: text.substring(0, 1000)
                             });
                         }
                     }
                 }
             }
             return results;
         })()
         """),
        ("page_title_and_text",
         """
         (function() {
             return {
                 title: document.title,
                 url: window.location.href,
                 bodyTextPreview: document.body.innerText.substring(0, 5000),
                 h1: Array.from(document.querySelectorAll('h1,h2,h3')).map(h => h.textContent).join(' | ')
             };
         })()
         """),
    ]

    for check_name, js_code in js_checks:
        try:
            result = page.evaluate(js_code)
            if result:
                js_extractions[check_name] = result
                if isinstance(result, list):
                    print(f"  JS [{check_name}]: {len(result)} items")
                elif isinstance(result, dict):
                    print(f"  JS [{check_name}]: dict with {len(result)} keys")
                else:
                    print(f"  JS [{check_name}]: {str(result)[:200]}")
        except Exception as e:
            err = str(e)[:100]
            if 'undefined' not in err.lower():
                print(f"  JS [{check_name}]: Error - {err}")

    # Save JS extractions
    if js_extractions:
        js_path = OUT_DIR / f"{safe_label}_js_extractions.json"
        try:
            js_path.write_text(
                json.dumps(js_extractions, indent=2, ensure_ascii=False, default=str),
                encoding='utf-8'
            )
            print(f"  Saved JS extractions: {js_path}")
        except Exception as e:
            print(f"  Error saving JS: {e}")

    # Extract ALL large inline scripts
    print("\nExtracting inline script data...")
    try:
        inline_scripts = page.evaluate("""
            (function() {
                var scripts = document.querySelectorAll('script:not([src])');
                var result = [];
                for (var i = 0; i < scripts.length; i++) {
                    var text = scripts[i].textContent || '';
                    if (text.length > 500) {
                        result.push({ index: i, length: text.length, content: text });
                    }
                }
                return result;
            })()
        """)
        if inline_scripts:
            print(f"  Found {len(inline_scripts)} large inline scripts")
            for si in inline_scripts:
                content = si.get('content', '')
                has_flight = any(kw in content for kw in
                    ['CGK', 'LAX', 'LHR', 'price', 'Price', 'flight', 'Flight',
                     'AF_initDataCallback', 'itinerary', 'offer', 'airline',
                     'Jakarta', 'business', 'Business', 'cabin', 'WIZ_global_data'])
                if has_flight:
                    idx = response_index[0]
                    response_index[0] += 1
                    sp = OUT_DIR / f"{safe_label}_inline_script_{idx:03d}.txt"
                    sp.write_text(content, encoding='utf-8')
                    print(f"    Saved script #{si['index']} ({si['length']:,} chars) -> {sp.name}")
    except Exception as e:
        print(f"  Error: {e}")

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY for {label}:")
    print(f"  Total responses: {len(all_requests)}")
    print(f"  Captured flight responses: {len(captured)}")
    for c in captured:
        print(f"    #{c['index']}: {c['body_size']:,}B | {c['content_type'][:40]}")
        print(f"      {c['url'][:120]}")
    print(f"{'='*60}")

    summary = {
        'label': label,
        'url': url,
        'total_requests': len(all_requests),
        'captured_count': len(captured),
        'captured': captured,
        'all_requests': all_requests,
        'timestamp': datetime.now().isoformat(),
    }
    summary_path = OUT_DIR / f"{safe_label}_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding='utf-8'
    )

    page.close()
    return captured, context


def main():
    print("Google Flights XHR/API Interceptor")
    print(f"Output: {OUT_DIR}")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"Searches: {len(urls)}")

    all_captured = {}
    shared_context = None

    with sync_playwright() as p:
        print("\nLaunching Chromium headless...")
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-web-security',
            ]
        )

        for i, (label, url) in enumerate(urls):
            try:
                captured, shared_context = run_search(
                    label, url, browser,
                    context_to_reuse=shared_context if i > 0 else None
                )
                all_captured[label] = captured
            except Exception as e:
                print(f"\nERROR: {label}: {e}")
                import traceback
                traceback.print_exc()
                shared_context = None  # Reset context on error

        browser.close()

    # Final report
    print(f"\n\n{'='*80}")
    print("FINAL REPORT")
    print(f"{'='*80}")
    total = 0
    for label, captured in all_captured.items():
        total += len(captured)
        print(f"  {label}: {len(captured)} responses")
    print(f"\n  TOTAL CAPTURED: {total}")
    print(f"  Output: {OUT_DIR}")
    print(f"\nAll saved files:")
    for f in sorted(OUT_DIR.iterdir()):
        print(f"  {f.name} ({f.stat().st_size:,} bytes)")


if __name__ == '__main__':
    main()
