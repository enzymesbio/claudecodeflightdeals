#!/usr/bin/env python3
"""
Chinese Airline Direct Site Crawler with CAPTCHA Solving
=========================================================

Scrapes flight prices directly from Chinese airline websites:
  1. Sichuan Airlines (sichuanair.com / global.sichuanair.com)
  2. China Southern Airlines (csair.com)
  3. China Eastern Airlines (ceair.com)

Each airline site has different anti-bot protections:
  - Sichuan Airlines: Image text CAPTCHAs, moderate anti-bot
  - China Southern: Slider CAPTCHAs, heavy JS rendering, session auth
  - China Eastern: Custom verification, geo-restrictions, JS rendering

Setup:
  pip install playwright playwright-stealth 2captcha-python
  python -m playwright install chromium
  set CAPTCHA_API_KEY=your_2captcha_key  (optional, for CAPTCHA solving)
  python airline_direct_crawler.py

=== AIRLINE ROUTE REFERENCE ===

Sichuan Airlines (3U):
  - TFU/CTU-LAX: 3U8695/3U8696, nonstop, 3x/week, Boeing 330
  - TFU-SYD: 3U3925/3U3926, via NKG
  - Hub: Chengdu (TFU/CTU)

China Southern (CZ):
  - CAN-LAX: CZ327/CZ328, nonstop daily, Boeing 777
  - CAN-SFO: CZ657/CZ658, nonstop
  - CAN-JFK: CZ399/CZ400, nonstop
  - Hub: Guangzhou (CAN)
  - CTU-LAX via CAN hub (CZ domestic + CZ327)

China Eastern (MU):
  - PVG-LAX: MU583/MU586, nonstop daily, Boeing 777
  - PVG-SFO: MU589/MU590, nonstop daily, Boeing 777
  - PVG-JFK: MU587/MU588, nonstop daily
  - Hub: Shanghai Pudong (PVG)
"""

import asyncio
import base64
import json
import logging
import os
import re
import sys
import io
import time
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
log = logging.getLogger("airline_direct_crawler")


# =============================================================================
# CONFIGURATION
# =============================================================================

CAPTCHA_API_KEY = os.environ.get("CAPTCHA_API_KEY", "")
CAPTCHA_SERVICE = os.environ.get("CAPTCHA_SERVICE", "capmonster")
CAPMONSTER_URL = os.environ.get("CAPMONSTER_URL", "https://api.capmonster.cloud")
TWOCAPTCHA_API_KEY = os.environ.get("TWOCAPTCHA_API_KEY", "")
PROXY_URL = os.environ.get("PROXY_URL", "")

ROUTES = [
    {"origin": "PVG", "dest": "LAX", "date": "2026-05-15"},
    {"origin": "PVG", "dest": "SFO", "date": "2026-05-15"},
    {"origin": "CAN", "dest": "LAX", "date": "2026-05-15"},
    {"origin": "TFU", "dest": "LAX", "date": "2026-05-15"},
    {"origin": "CTU", "dest": "LAX", "date": "2026-05-15"},
]

OUTPUT_FILE = "D:/claude/flights/airline_direct_results.json"


# =============================================================================
# CAPTCHA SOLVING - CapMonster Cloud (primary) + 2Captcha (fallback)
# =============================================================================

import urllib.request
import urllib.error


def _capmonster_create_task(task_payload: dict) -> Optional[int]:
    """Create a CAPTCHA solving task on CapMonster Cloud. Returns task ID."""
    req_body = json.dumps({
        "clientKey": CAPTCHA_API_KEY,
        **task_payload,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{CAPMONSTER_URL}/createTask",
        data=req_body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("errorId", 0) != 0:
            log.error(f"CapMonster createTask error: {data.get('errorCode')} - {data.get('errorDescription')}")
            return None
        task_id = data.get("taskId")
        log.info(f"CapMonster task created: {task_id}")
        return task_id
    except Exception as e:
        log.error(f"CapMonster createTask request failed: {e}")
        return None


def _capmonster_get_result(task_id: int, max_wait: int = 120) -> Optional[dict]:
    """Poll CapMonster Cloud for the task result."""
    req_body = json.dumps({
        "clientKey": CAPTCHA_API_KEY,
        "taskId": task_id,
    }).encode("utf-8")
    for _ in range(max_wait // 3):
        time.sleep(3)
        req = urllib.request.Request(
            f"{CAPMONSTER_URL}/getTaskResult",
            data=req_body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("errorId", 0) != 0:
                log.error(f"CapMonster getResult error: {data.get('errorCode')}")
                return None
            if data.get("status") == "ready":
                log.info("CapMonster task solved successfully")
                return data.get("solution", {})
            # still processing
        except Exception as e:
            log.error(f"CapMonster getResult request failed: {e}")
            return None
    log.error("CapMonster task timed out")
    return None


def get_captcha_solver():
    """Get a configured 2Captcha solver (used as fallback), or None."""
    key = TWOCAPTCHA_API_KEY or CAPTCHA_API_KEY
    if not key:
        return None
    try:
        from twocaptcha import TwoCaptcha
        solver = TwoCaptcha(key)
        log.info("2Captcha solver ready (fallback)")
        return solver
    except ImportError:
        log.warning("2captcha-python not installed: pip install 2captcha-python")
    return None


async def solve_image_captcha(image_base64: str) -> Optional[str]:
    """Solve an image CAPTCHA. Try CapMonster Cloud first, 2Captcha fallback."""
    # --- Primary: CapMonster Cloud ---
    if CAPTCHA_API_KEY and CAPTCHA_SERVICE == "capmonster":
        log.info("Attempting image CAPTCHA solve via CapMonster Cloud...")
        loop = asyncio.get_event_loop()
        task_id = await loop.run_in_executor(None, lambda: _capmonster_create_task({
            "task": {
                "type": "ImageToTextTask",
                "body": image_base64,
            }
        }))
        if task_id:
            solution = await loop.run_in_executor(None, lambda: _capmonster_get_result(task_id))
            if solution and solution.get("text"):
                text = solution["text"]
                log.info(f"CapMonster solved image CAPTCHA: {text}")
                return text
        log.warning("CapMonster image CAPTCHA failed, trying 2Captcha fallback...")

    # --- Fallback: 2Captcha ---
    solver = get_captcha_solver()
    if solver:
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: solver.normal(image_base64)
            )
            text = result.get("code", result) if isinstance(result, dict) else str(result)
            log.info(f"2Captcha solved image CAPTCHA: {text}")
            return text
        except Exception as e:
            log.error(f"2Captcha image CAPTCHA failed: {e}")

    return None


async def solve_geetest_captcha(gt: str, challenge: str, page_url: str,
                                 api_server: str = "api.geetest.com") -> Optional[dict]:
    """Solve a GeeTest CAPTCHA. Try CapMonster Cloud first, 2Captcha fallback."""
    # --- Primary: CapMonster Cloud ---
    if CAPTCHA_API_KEY and CAPTCHA_SERVICE == "capmonster":
        log.info("Attempting GeeTest solve via CapMonster Cloud...")
        loop = asyncio.get_event_loop()
        task_id = await loop.run_in_executor(None, lambda: _capmonster_create_task({
            "task": {
                "type": "GeeTestTaskProxyless",
                "websiteURL": page_url,
                "gt": gt,
                "challenge": challenge,
                "geetestApiServerSubdomain": api_server,
            }
        }))
        if task_id:
            solution = await loop.run_in_executor(None, lambda: _capmonster_get_result(task_id))
            if solution:
                log.info("CapMonster solved GeeTest CAPTCHA")
                return solution
        log.warning("CapMonster GeeTest failed, trying 2Captcha fallback...")

    # --- Fallback: 2Captcha ---
    solver = get_captcha_solver()
    if solver:
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: solver.geetest(gt=gt, challenge=challenge,
                                        url=page_url, apiServer=api_server)
            )
            text = result.get("code", result) if isinstance(result, dict) else result
            log.info(f"2Captcha solved GeeTest CAPTCHA")
            return text
        except Exception as e:
            log.error(f"2Captcha GeeTest failed: {e}")

    return None


# =============================================================================
# SICHUAN AIRLINES (3U) CRAWLER
# =============================================================================

class SichuanAirlinesCrawler:
    """
    Crawler for Sichuan Airlines (sichuanair.com).

    Site structure:
      - Chinese site: www.sichuanair.com
      - Global site: global.sichuanair.com
      - Booking page: global.sichuanair.com/en/booking

    CAPTCHA: Image text CAPTCHA on search page (occasionally)
    Anti-bot: Moderate - User-Agent + rate limiting
    Data format: Server-rendered HTML + AJAX price updates

    Key route: TFU/CTU-LAX nonstop (3U8695/3U8696), 3x/week on A330
    """

    SEARCH_URLS = {
        "global": "https://global.sichuanair.com",
        "chinese": "https://www.sichuanair.com",
        "booking": "https://global.sichuanair.com/en/booking",
    }

    async def search(self, origin: str, dest: str, date: str,
                     playwright) -> Dict:
        """Search Sichuan Airlines for a specific route."""
        result = {
            "airline": "Sichuan Airlines (3U)",
            "route": f"{origin}-{dest}",
            "date": date,
            "source": "sichuanair.com",
            "status": "unknown",
            "flights": [],
            "error": None,
        }

        log.info(f"[3U] Searching {origin}-{dest} on {date}")

        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            page = await context.new_page()

            try:
                from playwright_stealth import Stealth
                await Stealth().apply_stealth_async(page)
            except ImportError:
                pass

            # Intercept API responses
            api_data = []

            async def on_response(response):
                url = response.url
                if ("flight" in url.lower() or "search" in url.lower() or
                        "booking" in url.lower() or "price" in url.lower()):
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            body = await response.text()
                            data = json.loads(body)
                            api_data.append({"url": url, "data": data})
                    except Exception:
                        pass

            page.on("response", on_response)

            # Try the global booking page
            try:
                await page.goto(self.SEARCH_URLS["global"], timeout=20000,
                                wait_until="domcontentloaded")
                await asyncio.sleep(3)

                content = await page.content()
                title = await page.title()
                result["page_title"] = title
                result["page_accessible"] = True

                # Check for CAPTCHA
                captcha_el = await page.query_selector(
                    "[class*='captcha'], [class*='verify'], #captchaImg"
                )
                if captcha_el:
                    result["captcha_type"] = "image_text"
                    result["captcha_detected"] = True
                    log.warning("[3U] CAPTCHA detected")

                    # Attempt to solve via CapMonster (primary) / 2Captcha (fallback)
                    captcha_img = await page.query_selector("img[class*='captcha'], #captchaImg")
                    if captcha_img and CAPTCHA_API_KEY:
                        img_bytes = await captcha_img.screenshot()
                        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
                        captcha_text = await solve_image_captcha(img_b64)
                        if captcha_text:
                            input_el = await page.query_selector(
                                "input[name*='captcha'], input[name*='code'], "
                                "input[placeholder*='code']"
                            )
                            if input_el:
                                await input_el.fill(captcha_text)
                                log.info(f"[3U] CAPTCHA text entered: {captcha_text}")

                # Try to navigate to booking/search with our route
                search_url = (
                    f"{self.SEARCH_URLS['global']}/en/booking?"
                    f"tripType=OW&fromCity={origin}&toCity={dest}"
                    f"&fromDate={date}&adultCount=1&childCount=0"
                )
                await page.goto(search_url, timeout=20000, wait_until="domcontentloaded")
                await asyncio.sleep(5)

                # Try to extract flight data from the page
                flights = await self._extract_flights_from_page(page, origin, dest, date)
                if flights:
                    result["flights"] = flights
                    result["status"] = "success"
                    result["flight_count"] = len(flights)
                else:
                    result["status"] = "no_flights_found"
                    result["note"] = "Page loaded but no flight data extracted"

                # Check API interceptions
                if api_data:
                    result["api_interceptions"] = len(api_data)
                    for api_item in api_data:
                        flights_from_api = self._parse_api_response(api_item["data"])
                        if flights_from_api:
                            result["flights"].extend(flights_from_api)
                            result["status"] = "success"

            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)
                log.error(f"[3U] Error: {e}")

            await page.close()

        finally:
            await browser.close()

        return result

    async def _extract_flights_from_page(self, page, origin, dest, date) -> List[Dict]:
        """Extract flight information from the rendered page."""
        flights = []
        try:
            content = await page.content()

            # Look for Sichuan Airlines flight numbers
            fn_pattern = r'3U\d{4}'
            flight_numbers = re.findall(fn_pattern, content)

            if flight_numbers:
                for fn in set(flight_numbers):
                    flights.append({
                        "flight_number": fn,
                        "airline": "Sichuan Airlines",
                        "airline_code": "3U",
                        "route": f"{origin}-{dest}",
                        "date": date,
                        "source": "sichuanair.com (DOM)",
                        "price": None,  # Would need deeper parsing
                        "note": "Flight number found on page; price extraction requires CAPTCHA solving",
                    })

            # Try to get prices from structured elements
            price_elements = await page.query_selector_all(
                "[class*='price'], [class*='fare'], [class*='amount']"
            )
            for el in price_elements[:5]:
                text = await el.inner_text()
                price_match = re.search(r'[¥$]\s*(\d[\d,]+)', text)
                if price_match and flights:
                    flights[0]["price"] = int(price_match.group(1).replace(",", ""))

        except Exception as e:
            log.debug(f"[3U] DOM extraction error: {e}")

        return flights

    def _parse_api_response(self, data: dict) -> List[Dict]:
        """Parse any flight data from intercepted API responses."""
        flights = []
        # This would parse Sichuan Air's specific API format
        # Structure varies; this handles common patterns
        if isinstance(data, dict):
            for key in ["flights", "flightList", "data", "result"]:
                if key in data:
                    items = data[key]
                    if isinstance(items, list):
                        for item in items:
                            fn = item.get("flightNo") or item.get("flightNumber", "")
                            if fn:
                                flights.append({
                                    "flight_number": fn,
                                    "airline": "Sichuan Airlines",
                                    "price": item.get("price") or item.get("lowestPrice"),
                                    "source": "sichuanair.com (API)",
                                })
        return flights


# =============================================================================
# CHINA SOUTHERN (CZ) CRAWLER
# =============================================================================

class ChinaSouthernCrawler:
    """
    Crawler for China Southern Airlines (csair.com).

    Site structure:
      - Main: www.csair.com
      - US English: www.csair.com/en/
      - B2C booking: b2c.csair.com/B2C40/
      - Overseas booking: oversea.csair.com/tka/us/en/book/search
      - Mileage: b2c.csair.com/B2C40/modules/bookingnew/mileage/search.html

    Key API endpoints:
      - Search JS: B2C40/newTrips/static/main/scripts/search/searchInit.js
      - Search function: bussinessLogic.searchFlight()
      - IP locator: csair.com/iplocator/getIpInfo (public, responds)
      - NDC API: Level 4 certified, partner-only (not public)

    CAPTCHA: Slider CAPTCHA during booking flow
    Anti-bot: Session cookies, JS rendering, IP geo-checking
    NDC certification: Level 4 (highest in China) - IATA NDC 17.2

    Key routes to LAX:
      - CAN-LAX: CZ327/CZ328 (nonstop daily, Boeing 777, ~13h)
      - CTU-LAX: Via CAN hub (domestic CZ + CZ327)
    """

    URLS = {
        "main_en": "https://www.csair.com/en/",
        "b2c_search": "https://b2c.csair.com/B2C40/newTrips/static/main/page/search/index.html",
        "overseas": "https://oversea.csair.com/tka/us/en/book/search",
        "ip_locator": "https://www.csair.com/iplocator/getIpInfo",
    }

    async def search(self, origin: str, dest: str, date: str,
                     playwright) -> Dict:
        """Search China Southern for a specific route."""
        result = {
            "airline": "China Southern Airlines (CZ)",
            "route": f"{origin}-{dest}",
            "date": date,
            "source": "csair.com",
            "status": "unknown",
            "flights": [],
            "error": None,
            "api_info": {
                "ndc_level": "Level 4 (partner-only)",
                "b2c_search": self.URLS["b2c_search"],
                "search_js": "searchInit.js -> bussinessLogic.searchFlight()",
            },
        }

        log.info(f"[CZ] Searching {origin}-{dest} on {date}")

        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            page = await context.new_page()

            try:
                from playwright_stealth import Stealth
                await Stealth().apply_stealth_async(page)
            except ImportError:
                pass

            # Intercept API responses
            api_data = []
            async def on_response(response):
                url = response.url
                if any(kw in url.lower() for kw in ["flight", "search", "price", "avail"]):
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            body = await response.text()
                            data = json.loads(body)
                            api_data.append({"url": url, "data": data})
                    except Exception:
                        pass

            page.on("response", on_response)

            try:
                # First check IP locator (this endpoint is publicly accessible)
                ip_page = await context.new_page()
                try:
                    resp = await ip_page.goto(self.URLS["ip_locator"], timeout=10000)
                    if resp and resp.status == 200:
                        ip_text = await ip_page.inner_text("body")
                        try:
                            ip_data = json.loads(ip_text)
                            result["ip_locator"] = ip_data
                            log.info(f"[CZ] IP locator response: {ip_data}")
                        except json.JSONDecodeError:
                            pass
                except Exception:
                    pass
                await ip_page.close()

                # Navigate to the English booking site
                await page.goto(self.URLS["main_en"], timeout=25000,
                                wait_until="domcontentloaded")
                await asyncio.sleep(3)

                content = await page.content()
                title = await page.title()
                result["page_title"] = title
                result["page_accessible"] = True

                # Check for CAPTCHA
                captcha_el = await page.query_selector(
                    "[class*='captcha'], [class*='slider'], [class*='verify'], "
                    ".nc-container, #nc_1__"
                )
                if captcha_el:
                    result["captcha_type"] = "slider"
                    result["captcha_detected"] = True
                    log.warning("[CZ] Slider CAPTCHA detected")

                # Try to access the B2C search page
                b2c_url = (
                    f"{self.URLS['b2c_search']}?lang=en"
                    f"#/search?segtype=OW&fromcity={origin}&city1_code={origin}"
                    f"&tocity={dest}&city2_code={dest}"
                    f"&departuredate={date}&adultnum=1&childnum=0&infantnum=0"
                )

                await page.goto(b2c_url, timeout=25000, wait_until="domcontentloaded")
                await asyncio.sleep(5)

                # Check for flight content
                new_content = await page.content()
                has_flights = any(kw in new_content.lower() for kw in [
                    "cz327", "cz328", "cz657", "cz658",
                    "flight-list", "flight-item", "search-result",
                ])

                if has_flights:
                    flights = await self._extract_flights(page, origin, dest, date)
                    if flights:
                        result["flights"] = flights
                        result["status"] = "success"
                    else:
                        result["status"] = "page_has_flights_but_extraction_failed"
                else:
                    result["status"] = "no_flight_content"
                    result["note"] = (
                        "csair.com B2C system uses heavy JS rendering. "
                        "The search requires completing the full booking flow "
                        "in-browser including any CAPTCHA challenges."
                    )

                # Check API interceptions
                if api_data:
                    result["api_interceptions"] = len(api_data)
                    for api_item in api_data:
                        # Parse CZ-specific API format
                        data = api_item["data"]
                        if isinstance(data, dict):
                            fl = data.get("flightInfos") or data.get("flights") or []
                            for item in fl:
                                result["flights"].append({
                                    "flight_number": item.get("flightNo", ""),
                                    "airline": "China Southern",
                                    "price": item.get("lowestPrice"),
                                    "currency": item.get("currency", "CNY"),
                                    "source": "csair.com (API)",
                                })
                    if result["flights"]:
                        result["status"] = "success"

            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)
                log.error(f"[CZ] Error: {e}")

            await page.close()

        finally:
            await browser.close()

        return result

    async def _extract_flights(self, page, origin, dest, date) -> List[Dict]:
        """Extract flight data from rendered csair.com page."""
        flights = []
        try:
            content = await page.content()
            # Look for CZ flight numbers
            fn_pattern = r'CZ\d{3,4}'
            flight_numbers = re.findall(fn_pattern, content)
            for fn in set(flight_numbers):
                flights.append({
                    "flight_number": fn,
                    "airline": "China Southern",
                    "airline_code": "CZ",
                    "route": f"{origin}-{dest}",
                    "date": date,
                    "source": "csair.com (DOM)",
                })
        except Exception:
            pass
        return flights


# =============================================================================
# CHINA EASTERN (MU) CRAWLER
# =============================================================================

class ChinaEasternCrawler:
    """
    Crawler for China Eastern Airlines (ceair.com / us.ceair.com).

    Site structure:
      - US site: us.ceair.com/en/
      - Booking: us.ceair.com/en/booking-new.html
      - Flight results: us.ceair.com/en/flight-list.html
      - AU site: oa.ceair.com/au/en/

    Cookies needed: global_site_flag=en_US
    Environment: window.ENVIRONMENT = 'production'
    Analytics: PT Engine (cjs.ptengine.com), account: 71d4c6a5

    CAPTCHA: Custom verification system
    Anti-bot: Cookie-based auth, JS rendering, geo-restrictions
    Geo-restrictions: Password-gated for TW, PH, RU, KR, JP regions

    Key routes to US:
      - PVG-LAX: MU583/MU586 (nonstop daily, Boeing 777, ~12h)
      - PVG-SFO: MU589/MU590 (nonstop daily, Boeing 777, ~11h)
      - PVG-JFK: MU587/MU588 (nonstop daily)
    """

    URLS = {
        "us_main": "https://us.ceair.com/en/",
        "booking": "https://us.ceair.com/en/booking-new.html",
        "flight_list": "https://us.ceair.com/en/flight-list.html",
    }

    async def search(self, origin: str, dest: str, date: str,
                     playwright) -> Dict:
        """Search China Eastern for a specific route."""
        result = {
            "airline": "China Eastern Airlines (MU)",
            "route": f"{origin}-{dest}",
            "date": date,
            "source": "ceair.com",
            "status": "unknown",
            "flights": [],
            "error": None,
        }

        log.info(f"[MU] Searching {origin}-{dest} on {date}")

        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Cookie": "global_site_flag=en_US",
                },
            )
            page = await context.new_page()

            try:
                from playwright_stealth import Stealth
                await Stealth().apply_stealth_async(page)
            except ImportError:
                pass

            # Intercept API responses
            api_data = []
            async def on_response(response):
                url = response.url
                if any(kw in url.lower() for kw in ["flight", "search", "avail", "price"]):
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            body = await response.text()
                            data = json.loads(body)
                            api_data.append({"url": url, "data": data})
                    except Exception:
                        pass

            page.on("response", on_response)

            try:
                # Navigate to US booking page
                await page.goto(self.URLS["us_main"], timeout=25000,
                                wait_until="domcontentloaded")
                await asyncio.sleep(3)

                title = await page.title()
                result["page_title"] = title

                # Check for geo-restriction / password gate
                content = await page.content()
                if "password" in content.lower() and "region" in content.lower():
                    result["status"] = "geo_restricted"
                    result["error"] = "Page is password-gated for this region"
                    log.warning("[MU] Geo-restriction detected")
                    await page.close()
                    await browser.close()
                    return result

                result["page_accessible"] = True

                # Navigate to flight results page
                flight_list_url = (
                    f"{self.URLS['flight_list']}?"
                    f"oriCode={origin}&desCode={dest}"
                    f"&oriDate={date}&retDate="
                    f"&adtCount=1&chdCount=0&infCount=0"
                    f"&tripType=OW&directFlight=false"
                )

                await page.goto(flight_list_url, timeout=25000,
                                wait_until="domcontentloaded")
                await asyncio.sleep(5)

                # Check for CAPTCHA or verification
                verify_el = await page.query_selector(
                    "[class*='verify'], [class*='captcha'], [class*='security']"
                )
                if verify_el:
                    result["captcha_type"] = "custom_verification"
                    result["captcha_detected"] = True
                    log.warning("[MU] Verification challenge detected")

                # Try to extract flights
                flights = await self._extract_flights(page, origin, dest, date)
                if flights:
                    result["flights"] = flights
                    result["status"] = "success"
                else:
                    result["status"] = "no_flights_extracted"
                    result["note"] = (
                        "ceair.com uses heavy JS rendering. The flight-list.html page "
                        "may return 404 without proper JS execution or session cookies."
                    )

                # Check API interceptions
                if api_data:
                    result["api_interceptions"] = len(api_data)

            except Exception as e:
                result["status"] = "error"
                result["error"] = str(e)
                log.error(f"[MU] Error: {e}")

            await page.close()

        finally:
            await browser.close()

        return result

    async def _extract_flights(self, page, origin, dest, date) -> List[Dict]:
        """Extract flight data from rendered ceair.com page."""
        flights = []
        try:
            content = await page.content()
            # Look for MU flight numbers
            fn_pattern = r'MU\d{3,4}'
            flight_numbers = re.findall(fn_pattern, content)
            for fn in set(flight_numbers):
                flights.append({
                    "flight_number": fn,
                    "airline": "China Eastern",
                    "airline_code": "MU",
                    "route": f"{origin}-{dest}",
                    "date": date,
                    "source": "ceair.com (DOM)",
                })

            # Try price elements
            price_els = await page.query_selector_all("[class*='price'], [class*='fare']")
            for el in price_els[:5]:
                text = await el.inner_text()
                price_match = re.search(r'[¥$]\s*(\d[\d,]+)', text)
                if price_match and flights:
                    flights[0]["price"] = int(price_match.group(1).replace(",", ""))

        except Exception as e:
            log.debug(f"[MU] DOM extraction error: {e}")
        return flights


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================

async def run_all_airline_searches():
    """Run searches across all three airline sites."""
    log.info("=" * 70)
    log.info("CHINESE AIRLINE DIRECT SITE CRAWLER")
    log.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"CAPTCHA key: {'set' if CAPTCHA_API_KEY else 'NOT SET'}")
    log.info("=" * 70)

    all_results = {
        "crawl_time": datetime.now().isoformat(),
        "config": {
            "captcha_service": CAPTCHA_SERVICE,
            "captcha_key_set": bool(CAPTCHA_API_KEY),
            "proxy_set": bool(PROXY_URL),
        },
        "sichuan_airlines": [],
        "china_southern": [],
        "china_eastern": [],
        "summary": {},
    }

    from playwright.async_api import async_playwright

    async with async_playwright() as p:

        # --- Sichuan Airlines ---
        log.info("\n--- SICHUAN AIRLINES (3U) ---")
        log.info("Known nonstop: TFU/CTU-LAX (3U8695/3U8696), 3x/week")
        sichuan = SichuanAirlinesCrawler()
        for route in ROUTES:
            if route["origin"] in ("CTU", "TFU") and route["dest"] == "LAX":
                result = await sichuan.search(route["origin"], route["dest"],
                                              route["date"], p)
                all_results["sichuan_airlines"].append(result)
                log.info(f"  {result['route']} {result['date']}: {result['status']}")
                if result.get("flights"):
                    for f in result["flights"][:3]:
                        log.info(f"    {f.get('flight_number', 'N/A')} - "
                                 f"{f.get('price', 'N/A')}")
                await asyncio.sleep(3)

        # --- China Southern ---
        log.info("\n--- CHINA SOUTHERN (CZ) ---")
        log.info("Known nonstop: CAN-LAX (CZ327/CZ328), daily")
        csouthern = ChinaSouthernCrawler()
        for route in ROUTES:
            if route["dest"] == "LAX" and route["origin"] in ("CAN", "CTU"):
                result = await csouthern.search(route["origin"], route["dest"],
                                                route["date"], p)
                all_results["china_southern"].append(result)
                log.info(f"  {result['route']} {result['date']}: {result['status']}")
                await asyncio.sleep(3)

        # --- China Eastern ---
        log.info("\n--- CHINA EASTERN (MU) ---")
        log.info("Known nonstop: PVG-LAX (MU583), PVG-SFO (MU589), daily")
        ceastern = ChinaEasternCrawler()
        for route in ROUTES:
            if route["origin"] == "PVG":
                result = await ceastern.search(route["origin"], route["dest"],
                                               route["date"], p)
                all_results["china_eastern"].append(result)
                log.info(f"  {result['route']} {result['date']}: {result['status']}")
                await asyncio.sleep(3)

    # Summary
    total_flights = 0
    for key in ["sichuan_airlines", "china_southern", "china_eastern"]:
        for result in all_results[key]:
            total_flights += len(result.get("flights", []))

    all_results["summary"] = {
        "total_searches": (
            len(all_results["sichuan_airlines"]) +
            len(all_results["china_southern"]) +
            len(all_results["china_eastern"])
        ),
        "total_flights_found": total_flights,
        "airlines_searched": ["Sichuan Airlines (3U)", "China Southern (CZ)", "China Eastern (MU)"],
        "captcha_info": {
            "sichuan_air": "Image text CAPTCHA (solvable via 2Captcha image recognition)",
            "china_southern": "Slider CAPTCHA (solvable via 2Captcha slider/coordinates)",
            "china_eastern": "Custom verification (partially solvable)",
        },
        "note": (
            "Airline direct sites require browser automation with CAPTCHA solving. "
            "For best results, use a Chinese residential proxy and set CAPTCHA_API_KEY. "
            "The Ctrip crawler (ctrip_crawler.py) is often more effective since it "
            "aggregates all airlines in one search."
        ),
    }

    # Save
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    log.info(f"\nResults saved to: {OUTPUT_FILE}")

    # Print summary
    log.info("\n" + "=" * 70)
    log.info("SUMMARY")
    log.info("=" * 70)
    log.info(f"Total searches: {all_results['summary']['total_searches']}")
    log.info(f"Flights found: {all_results['summary']['total_flights_found']}")
    for key in ["sichuan_airlines", "china_southern", "china_eastern"]:
        statuses = [r["status"] for r in all_results[key]]
        log.info(f"  {key}: {statuses}")

    return all_results


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    print("Chinese Airline Direct Site Crawler")
    print("=" * 60)
    print()
    print("Airlines: Sichuan (3U), China Southern (CZ), China Eastern (MU)")
    print()

    if not CAPTCHA_API_KEY:
        print("NOTE: CAPTCHA_API_KEY not set. The crawler may encounter CAPTCHAs")
        print("that it cannot solve automatically.")
        print()
        print("To set up CAPTCHA solving:")
        print("  1. Primary: CapMonster Cloud (https://api.capmonster.cloud)")
        print("     set CAPTCHA_API_KEY=your_capmonster_key")
        print("     set CAPTCHA_SERVICE=capmonster")
        print("  2. Fallback: 2Captcha (https://2captcha.com)")
        print("     set TWOCAPTCHA_API_KEY=your_2captcha_key")
        print("  3. Re-run this script")
        print()
    else:
        print(f"CAPTCHA service: {CAPTCHA_SERVICE} (primary)")
        print(f"CapMonster URL: {CAPMONSTER_URL}")
        print(f"2Captcha fallback: {'configured' if TWOCAPTCHA_API_KEY else 'not set'}")
        print()

    asyncio.run(run_all_airline_searches())
