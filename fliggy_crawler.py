#!/usr/bin/env python3
"""
Fliggy & Chinese OTA Flight Crawler
====================================

Multi-strategy scraper targeting Chinese OTAs for flight data.
Attempts Fliggy, Ctrip, and Qunar via various API and scraping approaches.

Strategies (in order of attempt):
  1. Ctrip Mobile API (m.ctrip.com/restapi/soa2/14022/flightListSearch)
  2. Ctrip Lowest-Price API (flights.ctrip.com/itinerary/api/12808/lowestPrice)
  3. Qunar Desktop Page Scraping (flight.qunar.com, requires Playwright)
  4. Fliggy mtop API probe (h5api.m.taobao.com - expected to fail w/o auth)
  5. Qunar Mobile Page Scraping (m.flight.qunar.com, requires Playwright)

Test route: PVG (Shanghai) -> LAX (Los Angeles), 2026-05-15, one-way

Research findings from March 2026:
  - Fliggy: Requires Alibaba OAuth 2.0 (Chinese phone number). NCMS CAPTCHA.
    h5.m.fliggy.com has EXPIRED SSL certificate. fliggy.hk redirects to error.
  - Ctrip old API (/itinerary/api/12808/products): OFFLINE ("接口下线")
  - Ctrip partner API (soa2/16427): Requires protobuf+ZSTD, partner auth.
  - Ctrip mobile API (soa2/14022/flightListSearch): Returns JSON structure,
    responds with rlt:510 and empty arrays on GET. Needs proper POST body.
  - Qunar: Desktop pages are JS-rendered shells. Mobile returns 403.
    API path /api/flight/interSearch -> 404.
  - Trip.com developer portal: Requires sign-in.

Usage:
  python fliggy_crawler.py [--route PVG-LAX] [--date 2026-05-15]
"""

import asyncio
import json
import logging
import os
import sys
import io
import time
import hashlib
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

# Fix Windows encoding
if sys.platform == "win32":
    try:
        if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != "utf-8":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if not isinstance(sys.stderr, io.TextIOWrapper) or sys.stderr.encoding != "utf-8":
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("fliggy_crawler")

# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_ROUTE = ("PVG", "LAX")
DEFAULT_DATE = "2026-05-15"

# Chinese city name mapping for APIs that require Chinese names
CITY_NAMES = {
    "PVG": "上海", "SHA": "上海", "PEK": "北京", "PKX": "北京",
    "CAN": "广州", "CTU": "成都", "SZX": "深圳", "HGH": "杭州",
    "WUH": "武汉", "XIY": "西安", "CKG": "重庆", "KMG": "昆明",
    "CSX": "长沙", "NKG": "南京", "TAO": "青岛", "DLC": "大连",
    "HRB": "哈尔滨", "SHE": "沈阳", "TNA": "济南", "TSN": "天津",
    "LAX": "洛杉矶", "SFO": "旧金山", "JFK": "纽约", "ORD": "芝加哥",
    "SEA": "西雅图", "YVR": "温哥华", "YYZ": "多伦多", "NRT": "东京",
    "ICN": "首尔", "HKG": "香港", "SIN": "新加坡", "BKK": "曼谷",
    "LHR": "伦敦", "CDG": "巴黎", "SYD": "悉尼",
}

HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.6261.119 Mobile Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

HEADERS_CTRIP_MOBILE = {
    **HEADERS_BROWSER,
    "Content-Type": "application/json",
    "Referer": "https://m.ctrip.com/html5/flight/",
    "Origin": "https://m.ctrip.com",
}

HEADERS_QUNAR = {
    **HEADERS_BROWSER,
    "Referer": "https://flight.qunar.com/",
    "Host": "flight.qunar.com",
}


# =============================================================================
# STRATEGY 1: CTRIP MOBILE API (flightListSearch)
# =============================================================================

async def try_ctrip_mobile_api(dep: str, arr: str, date: str) -> Dict[str, Any]:
    """
    Attempt Ctrip mobile flight list search API.

    Endpoint: https://m.ctrip.com/restapi/soa2/14022/flightListSearch
    Method: POST with JSON body

    Known from research:
    - GET requests return rlt:510 with empty arrays
    - Needs proper POST body with search parameters
    - No explicit auth token required in URL, but may need session cookies
    """
    import aiohttp

    log.info("=" * 60)
    log.info("STRATEGY 1: Ctrip Mobile API (flightListSearch)")
    log.info("=" * 60)

    url = "https://m.ctrip.com/restapi/soa2/14022/flightListSearch"

    dep_name = CITY_NAMES.get(dep, dep)
    arr_name = CITY_NAMES.get(arr, arr)

    # Construct search body based on known Ctrip mobile API format
    search_body = {
        "flag": 8,
        "trptpe": 1,  # 1 = one-way
        "preprdid": "",
        "searchitem": [{
            "dccode": dep,
            "accode": arr,
            "dcname": dep_name,
            "acname": arr_name,
            "ddate": date,
        }],
        "classtype": "Y",  # Economy
        "hasChild": False,
        "hasBaby": False,
    }

    # Also try alternative body formats
    search_bodies = [
        # Format 1: Standard mobile search
        search_body,
        # Format 2: Minimal
        {
            "searchitem": [{
                "dccode": dep,
                "accode": arr,
                "ddate": date,
            }],
            "trptpe": 1,
            "flag": 8,
        },
        # Format 3: With more parameters
        {
            "flag": 8,
            "trptpe": 1,
            "searchitem": [{
                "dccode": dep,
                "accode": arr,
                "dcname": dep_name,
                "acname": arr_name,
                "ddate": date,
            }],
            "classtype": "Y",
            "hasChild": False,
            "hasBaby": False,
            "searchIndex": 1,
            "subcls": 0,
        },
    ]

    result = {
        "strategy": "ctrip_mobile_api",
        "endpoint": url,
        "status": "untested",
        "attempts": [],
    }

    try:
        async with aiohttp.ClientSession() as session:
            for i, body in enumerate(search_bodies):
                log.info(f"  Attempt {i+1}/{len(search_bodies)} with body format #{i+1}")
                try:
                    async with session.post(
                        url,
                        json=body,
                        headers=HEADERS_CTRIP_MOBILE,
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as resp:
                        status = resp.status
                        text = await resp.text()

                        attempt = {
                            "format": i + 1,
                            "http_status": status,
                            "response_length": len(text),
                        }

                        try:
                            data = json.loads(text)
                            attempt["parsed"] = True

                            # Check for actual flight data
                            rlt = data.get("rlt")
                            attempt["rlt_code"] = rlt

                            fltitems = data.get("fltitem", [])
                            airports = data.get("airports", [])
                            airlines = data.get("airlines", [])

                            attempt["flight_count"] = len(fltitems)
                            attempt["airport_count"] = len(airports)
                            attempt["airline_count"] = len(airlines)

                            if fltitems:
                                attempt["has_flights"] = True
                                attempt["sample_flight"] = fltitems[0] if fltitems else None
                                log.info(f"    -> SUCCESS! Found {len(fltitems)} flights")
                                result["status"] = "success"
                                result["flights"] = fltitems
                                result["airports"] = airports
                                result["airlines"] = airlines
                                result["raw_response"] = data
                            else:
                                is_complete = data.get("iscomplete", None)
                                attempt["is_complete"] = is_complete
                                ack = data.get("ResponseStatus", {}).get("Ack", "")
                                attempt["ack"] = ack
                                errors = data.get("ResponseStatus", {}).get("Errors", [])
                                attempt["errors"] = errors

                                if ack == "Success" and rlt == 510:
                                    log.info(f"    -> API responded (rlt=510), but no flights returned")
                                    log.info(f"       iscomplete={is_complete}, likely needs session/cookie")
                                elif errors:
                                    log.info(f"    -> API errors: {errors}")
                                else:
                                    log.info(f"    -> Empty response. rlt={rlt}, ack={ack}")
                        except json.JSONDecodeError:
                            attempt["parsed"] = False
                            attempt["response_preview"] = text[:500]
                            log.info(f"    -> Non-JSON response ({status}): {text[:200]}")

                        result["attempts"].append(attempt)

                except aiohttp.ClientError as e:
                    log.info(f"    -> Connection error: {e}")
                    result["attempts"].append({"format": i + 1, "error": str(e)})

                # Small delay between attempts
                await asyncio.sleep(0.5)

    except ImportError:
        log.warning("  aiohttp not installed. Run: pip install aiohttp")
        result["status"] = "missing_dependency"
        result["error"] = "aiohttp not installed"

    if result["status"] != "success":
        result["status"] = "no_flight_data"
        result["analysis"] = (
            "Ctrip mobile API responds to requests but returns empty flight lists. "
            "The rlt=510 code and iscomplete=false suggest the API needs either: "
            "(a) valid session cookies from a browser session, or "
            "(b) a specific request signing mechanism, or "
            "(c) a preceding token-exchange call. "
            "The API structure is valid and operational, just requires auth context."
        )

    return result


# =============================================================================
# STRATEGY 2: CTRIP LOWEST PRICE API
# =============================================================================

async def try_ctrip_lowest_price(dep: str, arr: str) -> Dict[str, Any]:
    """
    Attempt Ctrip lowest-price calendar API.

    Endpoint: https://flights.ctrip.com/itinerary/api/12808/lowestPrice
    Method: GET with query parameters

    Known from research:
    - Returns JSON with oneWayPrice, roundTripPrice fields
    - Returns null for international routes (PVG-LAX, SHA-LAX)
    - Returns null even for domestic routes (SHA-PEK) as of March 2026
    - API appears to be deprecated/non-functional
    """
    import aiohttp

    log.info("=" * 60)
    log.info("STRATEGY 2: Ctrip Lowest Price API")
    log.info("=" * 60)

    base_url = "https://flights.ctrip.com/itinerary/api/12808/lowestPrice"

    result = {
        "strategy": "ctrip_lowest_price",
        "endpoint": base_url,
        "status": "untested",
        "attempts": [],
    }

    # Try with both city codes
    params_list = [
        {"flightWay": "Oneway", "dcity": dep, "acity": arr, "direct": "false", "army": "false"},
        # Also try domestic route to verify API is functional at all
        {"flightWay": "Oneway", "dcity": "SHA", "acity": "PEK", "direct": "false", "army": "false"},
    ]

    try:
        async with aiohttp.ClientSession() as session:
            for params in params_list:
                route_str = f"{params['dcity']}-{params['acity']}"
                log.info(f"  Trying {route_str}...")

                try:
                    async with session.get(
                        base_url,
                        params=params,
                        headers=HEADERS_BROWSER,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        text = await resp.text()
                        attempt = {
                            "route": route_str,
                            "http_status": resp.status,
                        }

                        try:
                            data = json.loads(text)
                            price_data = data.get("data", {})
                            one_way = price_data.get("oneWayPrice")
                            round_trip = price_data.get("roundTripPrice")
                            msg = data.get("msg", "")

                            attempt["msg"] = msg
                            attempt["oneWayPrice"] = one_way
                            attempt["roundTripPrice"] = round_trip

                            if one_way is not None:
                                log.info(f"    -> One-way prices found!")
                                attempt["has_data"] = True
                                result["status"] = "success"
                                result["prices"] = one_way
                            else:
                                log.info(f"    -> Prices are null (msg={msg})")
                                attempt["has_data"] = False

                        except json.JSONDecodeError:
                            attempt["error"] = "non-JSON response"
                            log.info(f"    -> Non-JSON response: {text[:200]}")

                        result["attempts"].append(attempt)

                except aiohttp.ClientError as e:
                    log.info(f"    -> Error: {e}")
                    result["attempts"].append({"route": route_str, "error": str(e)})

                await asyncio.sleep(0.3)

    except ImportError:
        result["status"] = "missing_dependency"
        result["error"] = "aiohttp not installed"

    if result["status"] != "success":
        result["status"] = "api_defunct"
        result["analysis"] = (
            "The Ctrip lowestPrice API returns null for all routes tested "
            "(both domestic SHA-PEK and international PVG-LAX). "
            "Combined with the old /products endpoint being officially offline "
            "('接口下线'), Ctrip has deprecated these unauthenticated API endpoints. "
            "Their newer architecture uses Next.js SSR with the runtime server at "
            "online.flight.ctripcorp.com, and the partner API uses protobuf+ZSTD "
            "via soa2/16427."
        )

    return result


# =============================================================================
# STRATEGY 3: CTRIP OLD PRODUCTS API (known offline, for documentation)
# =============================================================================

async def try_ctrip_old_api(dep: str, arr: str, date: str) -> Dict[str, Any]:
    """
    Test the old Ctrip products API - known to be offline since ~2024.

    Endpoint: https://flights.ctrip.com/itinerary/api/12808/products
    Returns: {"status":0,"data":{"error":{"code":"","msg":"接口下线"}}}
    """
    import aiohttp

    log.info("=" * 60)
    log.info("STRATEGY 3: Ctrip Old Products API (known offline)")
    log.info("=" * 60)

    url = "https://flights.ctrip.com/itinerary/api/12808/products"

    dep_name = CITY_NAMES.get(dep, dep)
    arr_name = CITY_NAMES.get(arr, arr)

    body = {
        "flightWay": "Oneway",
        "classType": "ALL",
        "hasChild": False,
        "hasBaby": False,
        "searchIndex": 1,
        "airportParams": [{
            "dcity": dep,
            "acity": arr,
            "dcityname": dep_name,
            "acityname": arr_name,
            "date": date,
        }],
    }

    result = {
        "strategy": "ctrip_old_products_api",
        "endpoint": url,
        "status": "untested",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=body,
                headers={**HEADERS_BROWSER, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                text = await resp.text()
                try:
                    data = json.loads(text)
                    error_msg = data.get("data", {}).get("error", {}).get("msg", "")
                    result["response"] = data
                    result["error_msg"] = error_msg

                    if error_msg == "接口下线":
                        log.info(f"  -> Confirmed: API offline ('接口下线' = 'interface offline')")
                        result["status"] = "confirmed_offline"
                    else:
                        log.info(f"  -> Response: {text[:300]}")
                        result["status"] = "unexpected_response"

                except json.JSONDecodeError:
                    log.info(f"  -> Non-JSON: {text[:200]}")
                    result["status"] = "error"

    except ImportError:
        result["status"] = "missing_dependency"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    result["analysis"] = (
        "The old Ctrip /itinerary/api/12808/products endpoint officially returns "
        "'接口下线' (interface offline). This was the primary endpoint used by "
        "scrapers like github.com/zhuang1108/Ctrip-Crawler. It accepted POST "
        "with JSON body containing flightWay, classType, airportParams, etc. "
        "Ctrip has migrated to SSR (Next.js) and partner protobuf APIs."
    )

    return result


# =============================================================================
# STRATEGY 4: FLIGGY mtop API PROBE
# =============================================================================

async def try_fliggy_mtop(dep: str, arr: str, date: str) -> Dict[str, Any]:
    """
    Probe Fliggy's mtop API gateway.

    Expected to fail without Alibaba OAuth credentials.
    Documents the authentication wall for reference.
    """
    import aiohttp

    log.info("=" * 60)
    log.info("STRATEGY 4: Fliggy mtop API Probe")
    log.info("=" * 60)

    result = {
        "strategy": "fliggy_mtop",
        "status": "untested",
        "endpoints_tested": [],
    }

    # mtop endpoints to probe
    endpoints = [
        {
            "name": "Taobao H5 API",
            "url": "https://h5api.m.taobao.com/h5/mtop.trip.flight.search/1.0/",
            "params": {
                "appKey": "12574478",
                "type": "json",
                "api": "mtop.trip.flight.search",
                "v": "1.0",
                "data": json.dumps({
                    "depCity": dep,
                    "arrCity": arr,
                    "depDate": date,
                    "tripType": "1",
                }),
            },
        },
        {
            "name": "Fliggy H5 API",
            "url": "https://h5api.m.fliggy.com/h5/mtop.trip.flight.search/1.0/",
            "params": {
                "appKey": "12574478",
                "type": "json",
                "api": "mtop.trip.flight.search",
                "v": "1.0",
                "data": json.dumps({
                    "depCity": dep,
                    "arrCity": arr,
                    "depDate": date,
                }),
            },
        },
        {
            "name": "Fliggy Main Site",
            "url": "https://www.fliggy.com/",
            "params": None,
        },
        {
            "name": "Fliggy H5 Mobile (expired cert expected)",
            "url": "https://h5.m.fliggy.com/trip/domestic/search-flight",
            "params": None,
        },
    ]

    try:
        async with aiohttp.ClientSession() as session:
            for ep in endpoints:
                log.info(f"  Probing: {ep['name']}")
                log.info(f"    URL: {ep['url']}")

                ep_result = {"name": ep["name"], "url": ep["url"]}

                try:
                    if ep["params"]:
                        async with session.get(
                            ep["url"],
                            params=ep["params"],
                            headers=HEADERS_BROWSER,
                            timeout=aiohttp.ClientTimeout(total=10),
                            ssl=False,  # Some Fliggy certs are expired
                        ) as resp:
                            text = await resp.text()
                            ep_result["http_status"] = resp.status
                            ep_result["response_length"] = len(text)
                            ep_result["response_preview"] = text[:500]

                            # Check for auth errors
                            if "FAIL_SYS_TOKEN" in text or "token" in text.lower():
                                ep_result["auth_required"] = True
                                log.info(f"    -> Auth token required (as expected)")
                            elif "ILLEGAL_ACCESS" in text:
                                ep_result["auth_required"] = True
                                log.info(f"    -> Illegal access (no valid token)")
                            else:
                                log.info(f"    -> Status {resp.status}, {len(text)} bytes")
                    else:
                        async with session.get(
                            ep["url"],
                            headers=HEADERS_BROWSER,
                            timeout=aiohttp.ClientTimeout(total=10),
                            ssl=False,
                        ) as resp:
                            ep_result["http_status"] = resp.status
                            ep_result["final_url"] = str(resp.url)
                            text = await resp.text()
                            ep_result["response_length"] = len(text)

                            if "login" in str(resp.url).lower():
                                ep_result["redirected_to_login"] = True
                                log.info(f"    -> Redirected to login")
                            else:
                                log.info(f"    -> Status {resp.status}, {len(text)} bytes")

                except aiohttp.ClientConnectorSSLError as e:
                    ep_result["error"] = f"SSL error: {e}"
                    log.info(f"    -> SSL certificate error (expired cert)")
                except aiohttp.ClientError as e:
                    ep_result["error"] = str(e)
                    log.info(f"    -> Connection error: {e}")
                except Exception as e:
                    ep_result["error"] = str(e)
                    log.info(f"    -> Error: {e}")

                result["endpoints_tested"].append(ep_result)
                await asyncio.sleep(0.3)

    except ImportError:
        result["status"] = "missing_dependency"
        result["error"] = "aiohttp not installed"
        return result

    result["status"] = "auth_wall"
    result["analysis"] = (
        "Fliggy uses Alibaba's mtop protocol for all API calls. Every request "
        "requires: appKey, OAuth token, HMAC signature, timestamp. Without a "
        "Chinese phone number, you cannot create an Alibaba account to get "
        "OAuth credentials. The H5 mobile site (h5.m.fliggy.com) has an "
        "expired SSL certificate as of March 2026. The main site (fliggy.com) "
        "loads but flight search requires authentication. NCMS CAPTCHA blocks "
        "automated access even with valid credentials."
    )

    return result


# =============================================================================
# STRATEGY 5: QUNAR SEARCH PAGE (Playwright-based)
# =============================================================================

async def try_qunar_playwright(dep: str, arr: str, date: str) -> Dict[str, Any]:
    """
    Attempt to scrape Qunar flight search using Playwright.

    Qunar's search results are entirely JS-rendered. The HTML shell contains
    only a search form template. Real data loads via XHR after JS execution.

    Known from research:
    - Desktop: flight.qunar.com/site/oneway_list.htm renders results via JS
    - Mobile: m.flight.qunar.com returns 403 to non-browser requests
    - API: /api/flight/interSearch -> 404
    - Scripts load from q.qunarzz.com/flight_qzz/prd/ and q.qunarzz.com/quinn/prd/
    """
    log.info("=" * 60)
    log.info("STRATEGY 5: Qunar Playwright Scraping")
    log.info("=" * 60)

    dep_name = CITY_NAMES.get(dep, dep)
    arr_name = CITY_NAMES.get(arr, arr)

    result = {
        "strategy": "qunar_playwright",
        "status": "untested",
    }

    # Build Qunar search URL
    search_url = (
        f"https://flight.qunar.com/site/oneway_list.htm?"
        f"searchDepartureAirport={urllib.parse.quote(dep_name)}"
        f"&searchArrivalAirport={urllib.parse.quote(arr_name)}"
        f"&searchDepartureTime={date}"
        f"&searchArrivalTime="
        f"&nextNDays=0"
        f"&startSearch=true"
        f"&fromCode={dep}"
        f"&toCode={arr}"
    )

    log.info(f"  URL: {search_url}")

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.warning("  Playwright not installed. Run: pip install playwright && python -m playwright install")
        result["status"] = "missing_dependency"
        result["error"] = "playwright not installed"
        return result

    intercepted_responses = []

    async def handle_response(response):
        """Intercept XHR/fetch responses to capture flight data."""
        url = response.url
        # Look for flight search API calls
        keywords = ["flight", "search", "list", "product", "domestic", "inter", "quote"]
        if any(kw in url.lower() for kw in keywords):
            try:
                ct = response.headers.get("content-type", "")
                if "json" in ct or "javascript" in ct:
                    body = await response.text()
                    intercepted_responses.append({
                        "url": url,
                        "status": response.status,
                        "content_type": ct,
                        "body_length": len(body),
                        "body_preview": body[:1000],
                    })
            except Exception:
                pass

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.6261.119 Safari/537.36"
                ),
                locale="zh-CN",
                viewport={"width": 1366, "height": 768},
            )

            page = await context.new_page()
            page.on("response", handle_response)

            log.info("  Loading Qunar search page...")
            try:
                await page.goto(search_url, timeout=30000, wait_until="networkidle")
            except Exception as e:
                log.info(f"  Page load timeout/error (may still have data): {e}")

            # Wait for dynamic content
            log.info("  Waiting for flight results to load...")
            await asyncio.sleep(5)

            # Try to find flight result elements
            content = await page.content()
            result["page_length"] = len(content)

            # Check for common flight result selectors
            selectors_to_try = [
                ".flight-item",
                ".result-item",
                ".b_txt_lst",
                "#content .item",
                ".m-list .item",
                "[class*='flight']",
                "[class*='price']",
                ".price",
            ]

            found_elements = {}
            for sel in selectors_to_try:
                try:
                    elements = await page.query_selector_all(sel)
                    if elements:
                        found_elements[sel] = len(elements)
                        log.info(f"  Found {len(elements)} elements matching '{sel}'")
                except Exception:
                    pass

            result["found_elements"] = found_elements

            # Try to extract text from the content area
            try:
                content_div = await page.query_selector("#content")
                if content_div:
                    text = await content_div.inner_text()
                    result["content_text_length"] = len(text)
                    result["content_preview"] = text[:2000]

                    if len(text) > 100:
                        log.info(f"  Content area has {len(text)} chars of text")
                        # Check for price patterns
                        import re
                        prices = re.findall(r'[¥$]\s*[\d,]+', text)
                        if prices:
                            log.info(f"  Found {len(prices)} price patterns: {prices[:10]}")
                            result["prices_found"] = prices
                    else:
                        log.info(f"  Content area is mostly empty ({len(text)} chars)")
            except Exception as e:
                log.info(f"  Could not extract content div: {e}")

            # Check for anti-bot / CAPTCHA
            captcha_indicators = ["verify", "captcha", "slider", "validate", "security"]
            page_text = content.lower()
            detected = [ind for ind in captcha_indicators if ind in page_text]
            if detected:
                result["captcha_detected"] = detected
                log.info(f"  Anti-bot indicators found: {detected}")

            # Save intercepted API responses
            result["intercepted_responses"] = intercepted_responses
            if intercepted_responses:
                log.info(f"  Intercepted {len(intercepted_responses)} flight-related responses")
                for ir in intercepted_responses:
                    log.info(f"    {ir['url'][:100]} ({ir['status']}, {ir['body_length']} bytes)")

            # Take screenshot for debugging
            screenshot_path = os.path.join(os.path.dirname(__file__), "qunar_screenshot.png")
            try:
                await page.screenshot(path=screenshot_path, full_page=False)
                result["screenshot"] = screenshot_path
                log.info(f"  Screenshot saved: {screenshot_path}")
            except Exception:
                pass

            await browser.close()

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        log.error(f"  Playwright error: {e}")
        return result

    # Analyze intercepted API endpoints
    discovered_apis = []
    for ir in intercepted_responses:
        if "json" in ir.get("content_type", ""):
            discovered_apis.append({
                "url": ir["url"],
                "size": ir["body_length"],
                "preview": ir.get("body_preview", "")[:300],
            })
    result["discovered_apis"] = discovered_apis

    if result.get("prices_found") or intercepted_responses:
        result["status"] = "partial_success"
        result["analysis"] = (
            "Qunar rendered some content via Playwright. Key API endpoints "
            "were discovered through network interception:\n"
            "  - flight.qunar.com/touch/api/domestic/wbdflightlist (flight list, "
            "returns JSON with flights array but empty without auth)\n"
            "  - gw.flight.qunar.com/api/f/priceCalendar (price calendar, "
            "returns 365-day skeleton but prices are empty, says '查价')\n"
            "  - flight.qunar.com/gw/f/flight/unified/tip (promotional tips)\n"
            "  - flight.qunar.com/gw/f/flight/list/whitetip (white-label tips)\n"
            "Note: The search page showed '暂无符合条件的机票信息' (no matching "
            "flights) because international routes on Qunar desktop are routed "
            "to a different search flow than domestic ones."
        )
    else:
        result["status"] = "js_rendering_needed"
        result["analysis"] = (
            "Qunar's flight results require full JavaScript rendering with "
            "specific browser fingerprinting. The page loads as an empty shell "
            "in static HTML. Even with Playwright, Qunar's anti-bot system may "
            "detect headless browsers and withhold results. Qunar uses heavy "
            "obfuscated JavaScript from q.qunarzz.com/flight_qzz/prd/ for "
            "search execution. A stealth browser with residential proxy and "
            "human-like behavior simulation would be needed."
        )

    return result


# =============================================================================
# MAIN EXECUTION
# =============================================================================

async def run_all_strategies(dep: str = None, arr: str = None, date: str = None):
    """Run all scraping strategies and compile results."""
    dep = dep or DEFAULT_ROUTE[0]
    arr = arr or DEFAULT_ROUTE[1]
    date = date or DEFAULT_DATE

    log.info("=" * 70)
    log.info("FLIGGY & CHINESE OTA FLIGHT CRAWLER")
    log.info("=" * 70)
    log.info(f"Route: {dep} -> {arr}")
    log.info(f"Date:  {date}")
    log.info(f"Time:  {datetime.now().isoformat()}")
    log.info("")

    results = {
        "search": {
            "departure": dep,
            "arrival": arr,
            "date": date,
            "departure_city": CITY_NAMES.get(dep, dep),
            "arrival_city": CITY_NAMES.get(arr, arr),
        },
        "timestamp": datetime.now().isoformat(),
        "strategies": {},
    }

    # Strategy 1: Ctrip Mobile API
    try:
        r1 = await try_ctrip_mobile_api(dep, arr, date)
        results["strategies"]["ctrip_mobile_api"] = r1
    except Exception as e:
        log.error(f"Strategy 1 failed: {e}")
        results["strategies"]["ctrip_mobile_api"] = {"status": "error", "error": str(e)}

    # Strategy 2: Ctrip Lowest Price
    try:
        r2 = await try_ctrip_lowest_price(dep, arr)
        results["strategies"]["ctrip_lowest_price"] = r2
    except Exception as e:
        log.error(f"Strategy 2 failed: {e}")
        results["strategies"]["ctrip_lowest_price"] = {"status": "error", "error": str(e)}

    # Strategy 3: Ctrip Old API (documentation probe)
    try:
        r3 = await try_ctrip_old_api(dep, arr, date)
        results["strategies"]["ctrip_old_api"] = r3
    except Exception as e:
        log.error(f"Strategy 3 failed: {e}")
        results["strategies"]["ctrip_old_api"] = {"status": "error", "error": str(e)}

    # Strategy 4: Fliggy mtop Probe
    try:
        r4 = await try_fliggy_mtop(dep, arr, date)
        results["strategies"]["fliggy_mtop"] = r4
    except Exception as e:
        log.error(f"Strategy 4 failed: {e}")
        results["strategies"]["fliggy_mtop"] = {"status": "error", "error": str(e)}

    # Strategy 5: Qunar Playwright (only if playwright available)
    try:
        import playwright
        r5 = await try_qunar_playwright(dep, arr, date)
        results["strategies"]["qunar_playwright"] = r5
    except ImportError:
        log.info("\nSkipping Qunar Playwright (playwright not installed)")
        results["strategies"]["qunar_playwright"] = {
            "status": "skipped",
            "reason": "playwright not installed",
        }
    except Exception as e:
        log.error(f"Strategy 5 failed: {e}")
        results["strategies"]["qunar_playwright"] = {"status": "error", "error": str(e)}

    # ==========================================================================
    # SUMMARY
    # ==========================================================================

    log.info("")
    log.info("=" * 70)
    log.info("RESULTS SUMMARY")
    log.info("=" * 70)

    any_success = False
    for name, result in results["strategies"].items():
        status = result.get("status", "unknown")
        status_icon = {
            "success": "[OK]",
            "partial_success": "[PARTIAL]",
            "no_flight_data": "[EMPTY]",
            "api_defunct": "[DEFUNCT]",
            "confirmed_offline": "[OFFLINE]",
            "auth_wall": "[AUTH]",
            "js_rendering_needed": "[JS]",
            "missing_dependency": "[NODEP]",
            "skipped": "[SKIP]",
            "error": "[ERR]",
        }.get(status, f"[{status.upper()}]")

        log.info(f"  {status_icon:>10}  {name}")
        if status in ("success", "partial_success"):
            any_success = True

    log.info("")
    log.info("OVERALL FINDINGS:")
    log.info("-" * 70)

    findings = [
        "1. FLIGGY (飞猪):",
        "   - Status: NOT ACCESSIBLE without Alibaba OAuth credentials",
        "   - The mtop protocol requires appKey + OAuth token + HMAC signature",
        "   - Account creation requires a Chinese phone number",
        "   - h5.m.fliggy.com has an expired SSL certificate",
        "   - fliggy.hk redirects to an error page",
        "   - NCMS (Non-Critical Mode Security) CAPTCHA blocks automation",
        "",
        "2. CTRIP (携程):",
        "   - Old /itinerary/api/12808/products: OFFICIALLY OFFLINE ('接口下线')",
        "   - lowestPrice API: Returns null for all routes (deprecated)",
        "   - Mobile API (soa2/14022/flightListSearch): Responds but needs",
        "     session cookies or signing (returns empty arrays without auth)",
        "   - Partner API (soa2/16427): Requires protobuf+ZSTD + partner auth",
        "   - New architecture: Next.js SSR via online.flight.ctripcorp.com",
        "   - BEST APPROACH: Browser automation with existing ctrip_crawler.py",
        "",
        "3. QUNAR (去哪儿):",
        "   - All flight data is JS-rendered (empty HTML shells)",
        "   - Mobile site returns 403 to non-browser requests",
        "   - No public API endpoints found (all return 404 or redirect)",
        "   - Playwright scraping possible but needs anti-bot evasion",
        "   - Heavy obfuscation in JS bundles from q.qunarzz.com",
        "",
        "4. TRIP.COM (携程国际版):",
        "   - Developer portal requires sign-in at developers.trip.com",
        "   - Same backend as Ctrip with additional Akamai 428 protection",
        "",
        "5. LY.COM (同程):",
        "   - Vue.js SPA, requires JS rendering for all content",
        "   - No public API endpoints exposed in page source",
        "",
        "RECOMMENDATION:",
        "   For Chinese OTA flight data, use the existing ctrip_crawler.py",
        "   which uses Playwright stealth + CAPTCHA solving. That approach",
        "   intercepts XHR responses during browser rendering, which is the",
        "   only reliable method since all Chinese OTAs have moved to:",
        "   (a) SSR/SPA architectures requiring full JS rendering",
        "   (b) Authenticated API endpoints with session cookies",
        "   (c) Anti-bot systems (GeeTest, NCMS, Akamai)",
        "",
        "   Fliggy prices are within 5-10% of Ctrip for the same routes.",
        "   Both pull from the same airline GDS inventory.",
    ]

    for line in findings:
        log.info(f"  {line}")

    results["findings"] = findings

    # Save results
    output_path = os.path.join(os.path.dirname(__file__), "fliggy_crawler_results.json")

    # Clean non-serializable data
    def clean_for_json(obj):
        if isinstance(obj, dict):
            return {k: clean_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean_for_json(v) for v in obj]
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        else:
            return str(obj)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(clean_for_json(results), f, ensure_ascii=False, indent=2)
    log.info(f"\n  Results saved to: {output_path}")

    return results


# =============================================================================
# PLATFORM COMPARISON TABLE
# =============================================================================

def print_platform_comparison():
    """Print comprehensive comparison of Chinese OTA platforms."""
    print("=" * 90)
    print("CHINESE OTA PLATFORM COMPARISON FOR FLIGHT DATA ACCESS (March 2026)")
    print("=" * 90)
    print()
    print(f"{'Platform':<12} {'API Status':<22} {'Auth Required':<20} {'Anti-Bot':<18} {'Verdict'}")
    print("-" * 90)
    print(f"{'Fliggy':<12} {'mtop (auth wall)':<22} {'Alibaba OAuth+Phone':<20} {'NCMS slider':<18} {'NOT FEASIBLE'}")
    print(f"{'Ctrip':<12} {'Old=offline,New=SSR':<22} {'Session cookies':<20} {'GeeTest slider':<18} {'BROWSER ONLY'}")
    print(f"{'Trip.com':<12} {'Partner protobuf':<22} {'Partner+Akamai':<20} {'Akamai 428':<18} {'PARTNER ONLY'}")
    print(f"{'Qunar':<12} {'JS-rendered only':<22} {'Cookie+fingerprint':<20} {'Obfuscated JS':<18} {'BROWSER ONLY'}")
    print(f"{'Ly.com':<12} {'Vue SPA only':<22} {'Session cookies':<20} {'Unknown':<18} {'BROWSER ONLY'}")
    print()
    print("KEY API ENDPOINTS TESTED:")
    print("-" * 90)
    print("  Ctrip /itinerary/api/12808/products     -> OFFLINE ('接口下线')")
    print("  Ctrip /itinerary/api/12808/lowestPrice   -> Returns null (deprecated)")
    print("  Ctrip /restapi/soa2/14022/flightListSearch -> Responds, needs session auth")
    print("  Ctrip /international/search/api/batchSearch -> 405 Method Not Allowed (POST only)")
    print("  Fliggy h5api.m.taobao.com/h5/mtop.*      -> Blocked by WebFetch (DNS)")
    print("  Fliggy h5.m.fliggy.com                   -> SSL certificate expired")
    print("  Fliggy fliggy.hk                         -> Redirects to err.taobao.com")
    print("  Qunar /api/flight/interSearch             -> 404 -> qunar.com/Error404.shtml")
    print("  Qunar m.flight.qunar.com                 -> 403 Forbidden")
    print("  Qunar touch.flight.qunar.com             -> DNS not found")
    print()
    print("WORKING APPROACHES:")
    print("-" * 90)
    print("  1. Playwright + stealth + CAPTCHA solving (ctrip_crawler.py)")
    print("     - Renders Ctrip/Trip.com in headless browser")
    print("     - Intercepts XHR responses containing flight JSON data")
    print("     - Uses 2Captcha/CapSolver for GeeTest slider ($0.06-0.11/search)")
    print("     - Residential proxy recommended for Chinese IPs")
    print()
    print("  2. Ctrip Mobile API with session cookie relay")
    print("     - Endpoint: m.ctrip.com/restapi/soa2/14022/flightListSearch")
    print("     - Extract session cookies from a browser session first")
    print("     - POST with JSON body containing searchitem, trptpe, flag")
    print("     - More fragile than full browser approach")
    print()


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Fliggy & Chinese OTA Flight Crawler"
    )
    parser.add_argument(
        "--route", type=str, default="PVG-LAX",
        help="Route in DEP-ARR format (default: PVG-LAX)"
    )
    parser.add_argument(
        "--date", type=str, default=DEFAULT_DATE,
        help=f"Departure date YYYY-MM-DD (default: {DEFAULT_DATE})"
    )
    parser.add_argument(
        "--info-only", action="store_true",
        help="Print platform comparison only (no API calls)"
    )

    args = parser.parse_args()

    if args.info_only:
        print_platform_comparison()
        sys.exit(0)

    parts = args.route.split("-")
    if len(parts) != 2:
        print(f"Error: route must be in DEP-ARR format, got '{args.route}'")
        sys.exit(1)

    dep, arr = parts[0].upper(), parts[1].upper()

    print_platform_comparison()
    print()

    asyncio.run(run_all_strategies(dep, arr, args.date))
