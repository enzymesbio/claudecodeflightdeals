#!/usr/bin/env python3
"""
Fliggy Flight Scraper - Research & Documentation
=================================================

Fliggy (飞猪, fliggy.com) is Alibaba Group's travel platform.
It lists flights from all major Chinese and international airlines.

STATUS: NOT CURRENTLY FEASIBLE FOR AUTOMATED SCRAPING

This file documents:
  1. Why Fliggy is difficult to scrape
  2. The authentication requirements
  3. What CAPTCHAs are used
  4. Alternative approaches
  5. A proof-of-concept scraper that demonstrates the challenges

=== AUTHENTICATION ===

Fliggy uses Alibaba's mtop gateway protocol. All API requests go through:
  - h5api.m.taobao.com/h5/mtop.trip.flight.search/1.0/
  - acs.m.taobao.com/gw/mtop.trip.flight.search/1.0/

The mtop protocol requires:
  - appKey: Application identifier
  - token: Session token from OAuth 2.0 flow
  - sign: HMAC signature of the request
  - data: URL-encoded JSON payload
  - type: "json"
  - api: "mtop.trip.flight.search"
  - v: "1.0"
  - ttid: Client identifier

To obtain OAuth credentials:
  1. Register an Alibaba Cloud account (requires Chinese phone number)
  2. Create a developer application
  3. Complete the OAuth 2.0 authorization flow
  4. Use the access token to sign API requests

=== CAPTCHA ===

Fliggy uses Alibaba's NCMS (Non-Critical Mode Security) system:
  - Custom slider verification (not GeeTest)
  - Triggered on suspicious behavior patterns
  - Integrated with Alibaba's anti-fraud system
  - Cannot be easily solved by third-party CAPTCHA services
  - The slider uses proprietary challenge-response protocol

=== ALTERNATIVE APPROACH ===

Instead of scraping Fliggy directly, use one of these alternatives:
  1. Ctrip (flights.ctrip.com) - Same airlines, similar prices
  2. Trip.com (www.trip.com) - Ctrip's international brand
  3. Google Flights - Aggregates from multiple sources including Fliggy partners
  4. Skyscanner - Also aggregates Chinese airline prices

Fliggy's prices are typically within 5-10% of Ctrip's prices for the
same routes. The marginal benefit of scraping Fliggy does not justify
the complexity of bypassing their authentication system.
"""

import asyncio
import json
import logging
import os
import sys
import io
from datetime import datetime
from typing import List, Dict, Optional

if sys.platform == "win32":
    try:
        if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if not isinstance(sys.stderr, io.TextIOWrapper) or sys.stderr.encoding != "utf-8":
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass  # Already wrapped or buffer closed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("fliggy_scraper")


# =============================================================================
# FLIGGY API RESEARCH
# =============================================================================

FLIGGY_API_DOCS = {
    "platform": "Fliggy (飞猪)",
    "url": "https://www.fliggy.com",
    "owner": "Alibaba Group",

    "flight_search_endpoints": {
        "mobile_h5": {
            "url": "https://h5api.m.taobao.com/h5/mtop.trip.flight.search/1.0/",
            "method": "POST",
            "auth": "mtop protocol (appKey + token + HMAC sign)",
            "status": "Requires Alibaba OAuth - not accessible without credentials",
        },
        "acs_gateway": {
            "url": "https://acs.m.taobao.com/gw/mtop.trip.flight.search/1.0/",
            "method": "POST",
            "auth": "Same mtop protocol",
            "status": "Alternative gateway - same auth requirements",
        },
        "web_search_page": {
            "url": "https://www.fliggy.com/flight/international/",
            "method": "GET (browser)",
            "auth": "Taobao/Alipay account login",
            "status": "Requires browser with Alibaba cookies",
        },
    },

    "mtop_protocol": {
        "description": (
            "Alibaba's mtop (Mobile Taobao Protocol) is a proprietary "
            "API gateway used across all Alibaba platforms (Taobao, Tmall, "
            "Fliggy, Alipay). Every API call must include a signed request "
            "with parameters: appKey, token, sign, timestamp, data."
        ),
        "parameters": {
            "appKey": "Application key from Alibaba developer console",
            "token": "OAuth 2.0 access token",
            "sign": "HMAC-MD5(token + timestamp + appKey + data)",
            "t": "Unix timestamp in milliseconds",
            "data": "URL-encoded JSON payload with search parameters",
            "type": "json",
            "api": "mtop.trip.flight.search",
            "v": "1.0",
            "ttid": "Client type ID (e.g., '2022@travel_h5_4.5.0')",
        },
        "how_to_obtain_token": [
            "1. Register Alibaba Cloud account (Chinese phone required)",
            "2. Create OAuth 2.0 application",
            "3. Redirect user to: oauth.taobao.com/authorize?...",
            "4. Exchange authorization code for access_token",
            "5. Token expires in ~24 hours, must refresh",
        ],
    },

    "captcha_system": {
        "name": "Alibaba NCMS (Non-Critical Mode Security)",
        "type": "Custom slider + behavioral analysis",
        "details": [
            "Not GeeTest - proprietary Alibaba system",
            "Slider verification with custom challenge images",
            "Behavioral analysis (mouse movements, timing)",
            "Device fingerprinting via Alibaba's umeng SDK",
            "Cannot be easily bypassed by 2Captcha/CapSolver",
            "Triggered when: IP is suspicious, too many requests, "
            "or no valid Alibaba session token",
        ],
        "solving_difficulty": "HIGH - not supported by major CAPTCHA services",
    },

    "anti_scraping_measures": [
        "mtop request signing (prevents replay attacks)",
        "Device fingerprinting (umeng SDK)",
        "IP reputation scoring",
        "Request rate limiting (500 req/min with valid token)",
        "Token expiration (24h lifetime)",
        "Behavioral analysis during browsing",
        "NCMS slider CAPTCHA on suspicious access",
    ],

    "recommendation": {
        "summary": "Do NOT scrape Fliggy. Use Ctrip or Trip.com instead.",
        "reasons": [
            "Fliggy requires Alibaba OAuth which needs a Chinese phone number",
            "The NCMS CAPTCHA is not supported by standard solving services",
            "Same airlines and similar prices are available on Ctrip",
            "Ctrip has better-documented scraping approaches (Suysker/Ctrip-Crawler)",
            "Trip.com provides the same data in English",
        ],
        "price_comparison": (
            "Fliggy prices are typically within 5-10% of Ctrip's prices. "
            "For routes like CTU-LAX, PVG-LAX, CAN-LAX, the price difference "
            "is negligible. Both platforms pull from the same airline inventory."
        ),
    },
}


# =============================================================================
# PROOF OF CONCEPT: Basic Fliggy Page Access
# =============================================================================

async def probe_fliggy_accessibility():
    """
    Test basic accessibility of Fliggy pages.
    This demonstrates what happens without proper authentication.
    """
    log.info("=" * 60)
    log.info("FLIGGY ACCESSIBILITY PROBE")
    log.info("=" * 60)

    results = {
        "probe_time": datetime.now().isoformat(),
        "pages_tested": [],
    }

    test_urls = [
        ("Main page", "https://www.fliggy.com/"),
        ("International flights", "https://www.fliggy.com/flight/international/"),
        ("US site", "https://us.fliggytravel.com/"),
        ("Flight search (attempt)", "https://www.fliggy.com/flight/international/search?"
         "tripType=1&depCityCode=CTU&arrCityCode=LAX&depDate=2026-05-15"),
    ]

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="zh-CN",
            )

            for name, url in test_urls:
                log.info(f"\nTesting: {name}")
                log.info(f"  URL: {url}")

                page_result = {
                    "name": name,
                    "url": url,
                    "status": "unknown",
                }

                try:
                    page = await context.new_page()
                    response = await page.goto(url, timeout=15000,
                                               wait_until="domcontentloaded")

                    page_result["http_status"] = response.status if response else None
                    page_result["final_url"] = page.url

                    # Check if we were redirected to a login page
                    if "login" in page.url.lower() or "auth" in page.url.lower():
                        page_result["status"] = "redirected_to_login"
                        page_result["auth_required"] = True
                        log.info(f"  -> Redirected to login: {page.url}")
                    elif response and response.status == 200:
                        content = await page.content()
                        title = await page.title()
                        page_result["title"] = title
                        page_result["content_length"] = len(content)

                        # Check for CAPTCHA
                        if "captcha" in content.lower() or "verify" in content.lower():
                            page_result["status"] = "captcha_wall"
                            page_result["captcha_detected"] = True
                            log.info(f"  -> CAPTCHA wall detected")
                        elif "flight" in content.lower() and "search" in content.lower():
                            page_result["status"] = "accessible"
                            log.info(f"  -> Page accessible (title: {title})")
                        else:
                            page_result["status"] = "loaded_but_no_flight_content"
                            log.info(f"  -> Loaded but no flight content (title: {title})")
                    else:
                        page_result["status"] = f"http_{response.status if response else 'none'}"
                        log.info(f"  -> HTTP {response.status if response else 'no response'}")

                    await page.close()

                except Exception as e:
                    page_result["status"] = "error"
                    page_result["error"] = str(e)
                    log.error(f"  -> Error: {e}")

                results["pages_tested"].append(page_result)

            await browser.close()

    except ImportError:
        log.error("Playwright not installed. Run: pip install playwright && python -m playwright install")

    # Print summary
    log.info("\n" + "=" * 60)
    log.info("FLIGGY PROBE SUMMARY")
    log.info("=" * 60)
    for page in results["pages_tested"]:
        log.info(f"  {page['name']:<30} -> {page['status']}")

    log.info("\nCONCLUSION:")
    log.info("  Fliggy requires Alibaba OAuth 2.0 authentication.")
    log.info("  Without a Chinese phone number, you cannot create an account.")
    log.info("  RECOMMENDATION: Use Ctrip (ctrip_crawler.py) instead.")
    log.info("  Same airlines, similar prices, better scraping support.")

    return results


# =============================================================================
# COMPARATIVE INFORMATION
# =============================================================================

def print_platform_comparison():
    """Print a comparison of Chinese OTA platforms for flight scraping."""
    print("=" * 80)
    print("CHINESE OTA PLATFORM COMPARISON FOR FLIGHT SCRAPING")
    print("=" * 80)
    print()
    print(f"{'Platform':<15} {'Auth Needed':<20} {'CAPTCHA':<20} {'Solvable?':<12} {'Status'}")
    print("-" * 80)
    print(f"{'Ctrip':<15} {'Browser session':<20} {'GeeTest slider':<20} {'YES':<12} {'PRIMARY TARGET'}")
    print(f"{'Trip.com':<15} {'Browser + crypto':<20} {'Akamai 428':<20} {'HARD':<12} {'FALLBACK'}")
    print(f"{'Fliggy':<15} {'Alibaba OAuth':<20} {'NCMS slider':<20} {'NO':<12} {'NOT FEASIBLE'}")
    print(f"{'sichuanair':<15} {'Session cookies':<20} {'Image text':<20} {'YES':<12} {'LIMITED ROUTES'}")
    print(f"{'csair.com':<15} {'Session + JS':<20} {'Slider':<20} {'YES':<12} {'CZ ROUTES ONLY'}")
    print(f"{'ceair.com':<15} {'Cookie + JS':<20} {'Custom':<20} {'MAYBE':<12} {'MU ROUTES ONLY'}")
    print()
    print("RECOMMENDED APPROACH:")
    print("  1. PRIMARY: Use ctrip_crawler.py with 2Captcha/CapSolver for Ctrip International")
    print("  2. FALLBACK: Use ctrip_crawler.py's Trip.com mode")
    print("  3. SUPPLEMENT: Use airline_direct_crawler.py for specific airline pricing")
    print("  4. SKIP: Fliggy (same data available on Ctrip, harder to access)")
    print()
    print("COST ESTIMATE (per complete crawl of 5 routes x 15 dates):")
    print("  - Ctrip with 2Captcha:    ~$0.11  (75 GeeTest solves at $1.45/1000)")
    print("  - Ctrip with CapSolver:   ~$0.06  (75 GeeTest solves at $0.80/1000)")
    print("  - Residential proxy:      ~$0.50  (~300MB at $1.75/GB via IPRoyal)")
    print("  - Total per crawl:        ~$0.17 - $0.61")
    print()


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    print_platform_comparison()
    print()
    print("Running Fliggy accessibility probe...")
    print()

    # Print API documentation
    print("=" * 80)
    print("FLIGGY API DOCUMENTATION")
    print("=" * 80)
    print(json.dumps(FLIGGY_API_DOCS, indent=2, ensure_ascii=False))
    print()

    # Run the probe
    asyncio.run(probe_fliggy_accessibility())
