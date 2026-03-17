#!/usr/bin/env python3
"""
Qunar.com (去哪儿) International Flight Crawler
=================================================

A Playwright-based scraper for Qunar international flight search with
stealth mode and CAPTCHA solving support.

Architecture (informed by GitHub projects):
  - fankcoder/findtrip: Scrapy + Selenium + PhantomJS approach
  - blueboy888/Qunar: Revealed anti-bot measures (AES encryption, price
    obfuscation, cookie validation, UADATA tokens)
  - windhw/qunar: API endpoint discovery (longwell, groupdata.jsp, etc.)

Key findings from research:
  - Qunar uses React client-side rendering at flight.qunar.com
  - Flight data is loaded via XHR to /twell/ endpoints
  - API endpoints include:
      /twell/longwell (flight/vendor metadata)
      /twell/flight/tags/onewayflight_groupdata.jsp (price listings)
      /twell/flight/tags/onewayflight_groupinfo.jsp (flight details)
      /twell/flight/tags/deduceonewayflight_groupdata.jsp (initial prices)
  - Price responses may contain random offsets (obfuscation)
  - Responses may be AES encrypted with decryption key in JS
  - Cookie validation and UADATA token generation are used

Strategy:
  - Use Playwright + stealth to load the full search page
  - Intercept XHR responses for structured flight data
  - Also scrape the rendered DOM as fallback
  - Handle CAPTCHA/verification with CapMonster/2Captcha
  - Both one-way and round-trip search support

Routes: PVG-LAX, PVG-SFO, CTU-LAX, CAN-LAX (+ PVG-LAX round-trip)
Target airlines: Sichuan Airlines, China Southern, China Eastern,
                 Air China, Hainan Airlines, XiamenAir

Setup:
  1. pip install playwright playwright-stealth
  2. python -m playwright install chromium
  3. Set CAPMONSTER_API_KEY and/or TWOCAPTCHA_API_KEY env vars
  4. Run: python qunar_crawler.py
"""

import asyncio
import base64
import json
import os
import re
import sys
import io
import time
import logging
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path

# Fix Windows console encoding for Chinese characters
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
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("qunar_crawler")


# =============================================================================
# CONFIGURATION
# =============================================================================

class Config:
    """All configurable parameters for the Qunar crawler."""

    # CAPTCHA solving keys
    CAPMONSTER_API_KEY = os.environ.get(
        "CAPMONSTER_API_KEY", "fbd1a806598b3db547bbcec4edf37393"
    )
    TWOCAPTCHA_API_KEY = os.environ.get(
        "TWOCAPTCHA_API_KEY", "938da6cab05e1640ec373ee1fec6d115"
    )

    # Proxy (optional - Chinese residential IP recommended)
    PROXY_URL = os.environ.get("PROXY_URL", "")

    # Browser settings
    HEADLESS = os.environ.get("QUNAR_HEADLESS", "true").lower() == "true"
    SLOW_MO = int(os.environ.get("QUNAR_SLOW_MO", "80"))
    NAVIGATION_TIMEOUT = int(os.environ.get("QUNAR_NAV_TIMEOUT", "90000"))
    PAGE_LOAD_WAIT = int(os.environ.get("QUNAR_PAGE_WAIT", "15"))
    MAX_SCROLL_WAIT = int(os.environ.get("QUNAR_SCROLL_WAIT", "8"))

    # City name mappings (Chinese names required for Qunar URLs)
    CITY_NAMES = {
        "PVG": {"cn": "上海", "en": "Shanghai", "airport": "浦东"},
        "SHA": {"cn": "上海", "en": "Shanghai", "airport": "虹桥"},
        "LAX": {"cn": "洛杉矶", "en": "Los Angeles", "airport": "洛杉矶"},
        "SFO": {"cn": "旧金山", "en": "San Francisco", "airport": "旧金山"},
        "CTU": {"cn": "成都", "en": "Chengdu", "airport": "双流"},
        "CAN": {"cn": "广州", "en": "Guangzhou", "airport": "白云"},
        "PEK": {"cn": "北京", "en": "Beijing", "airport": "首都"},
        "JFK": {"cn": "纽约", "en": "New York", "airport": "肯尼迪"},
        "ORD": {"cn": "芝加哥", "en": "Chicago", "airport": "奥黑尔"},
    }

    # Search routes
    ROUTES = [
        {"origin": "PVG", "destination": "LAX", "trip_type": "oneway"},
        {"origin": "PVG", "destination": "SFO", "trip_type": "oneway"},
        {"origin": "CTU", "destination": "LAX", "trip_type": "oneway"},
        {"origin": "CAN", "destination": "LAX", "trip_type": "oneway"},
        {"origin": "PVG", "destination": "LAX", "trip_type": "roundtrip",
         "return_date": "2026-06-15"},
    ]

    # Departure date
    DEPARTURE_DATE = "2026-05-15"

    # Target airlines we specifically want prices for
    TARGET_AIRLINES = [
        "川航", "四川航空", "Sichuan Airlines", "3U",
        "南航", "中国南方航空", "China Southern", "CZ",
        "东航", "中国东方航空", "China Eastern", "MU",
        "国航", "中国国际航空", "Air China", "CA",
        "海航", "海南航空", "Hainan Airlines", "HU",
        "厦航", "厦门航空", "XiamenAir", "Xiamen Air", "MF",
    ]

    # Qunar base URLs
    QUNAR_ONEWAY_URL = "https://flight.qunar.com/site/oneway_list.htm"
    QUNAR_ROUNDTRIP_URL = "https://flight.qunar.com/site/roundtrip_list.htm"

    # Output
    OUTPUT_FILE = "D:/claude/flights/qunar_results.json"

    # Qunar XHR patterns to intercept
    API_PATTERNS = [
        "twell/longwell",
        "onewayflight_groupdata",
        "onewayflight_groupinfo",
        "deduceonewayflight_groupdata",
        "roundtripflight_groupdata",
        "roundtripflight_groupinfo",
        "deduceroundtripflight_groupdata",
        "flight/tags/",
        "flightdata",
        "searchrt_ui",
        "domesticflight",
        "internationalflight",
        "flight_qzz",
    ]


# =============================================================================
# CAPTCHA SOLVER
# =============================================================================

class QunarCaptchaSolver:
    """
    CAPTCHA solver for Qunar verification pages.
    Uses CapMonster Cloud (primary) with 2Captcha fallback.

    Qunar may use various CAPTCHA types:
    - Image CAPTCHA (text recognition)
    - Slider CAPTCHA (similar to GeeTest)
    - Click-based CAPTCHA (click specific items)
    """

    def __init__(self, capmonster_key: str = "", twocaptcha_key: str = ""):
        self.capmonster_key = capmonster_key
        self.twocaptcha_key = twocaptcha_key
        self.capmonster_url = "https://api.capmonster.cloud"

    async def solve_image_captcha(self, image_base64: str, page_url: str) -> Optional[str]:
        """Solve image-based text CAPTCHA."""
        if self.capmonster_key:
            result = await self._solve_image_capmonster(image_base64)
            if result:
                return result

        if self.twocaptcha_key:
            result = await self._solve_image_2captcha(image_base64)
            if result:
                return result

        log.error("No CAPTCHA solver available or all solvers failed")
        return None

    async def _solve_image_capmonster(self, image_base64: str) -> Optional[str]:
        """Solve image CAPTCHA via CapMonster Cloud."""
        log.info("Solving image CAPTCHA via CapMonster Cloud...")
        loop = asyncio.get_event_loop()

        def _create_and_poll():
            req_body = json.dumps({
                "clientKey": self.capmonster_key,
                "task": {
                    "type": "ImageToTextTask",
                    "body": image_base64,
                }
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{self.capmonster_url}/createTask",
                data=req_body,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if data.get("errorId", 0) != 0:
                    log.error(f"CapMonster error: {data.get('errorCode')}")
                    return None
                task_id = data.get("taskId")
                log.info(f"CapMonster task created: {task_id}")
            except Exception as e:
                log.error(f"CapMonster createTask failed: {e}")
                return None

            # Poll for result
            for _ in range(30):
                time.sleep(2)
                poll_body = json.dumps({
                    "clientKey": self.capmonster_key,
                    "taskId": task_id,
                }).encode("utf-8")
                poll_req = urllib.request.Request(
                    f"{self.capmonster_url}/getTaskResult",
                    data=poll_body,
                    headers={"Content-Type": "application/json"},
                )
                try:
                    with urllib.request.urlopen(poll_req, timeout=30) as resp:
                        result = json.loads(resp.read().decode("utf-8"))
                    if result.get("status") == "ready":
                        text = result.get("solution", {}).get("text", "")
                        log.info(f"CapMonster solved: {text}")
                        return text
                    elif result.get("errorId", 0) != 0:
                        log.error(f"CapMonster error: {result.get('errorCode')}")
                        return None
                except Exception as e:
                    log.error(f"CapMonster poll error: {e}")
                    return None
            return None

        return await loop.run_in_executor(None, _create_and_poll)

    async def _solve_image_2captcha(self, image_base64: str) -> Optional[str]:
        """Solve image CAPTCHA via 2Captcha."""
        log.info("Solving image CAPTCHA via 2Captcha...")
        loop = asyncio.get_event_loop()

        def _solve():
            try:
                from twocaptcha import TwoCaptcha
                solver = TwoCaptcha(self.twocaptcha_key)
                result = solver.normal(image_base64)
                text = result.get("code", "")
                log.info(f"2Captcha solved: {text}")
                return text
            except ImportError:
                log.error("2captcha-python not installed")
                return None
            except Exception as e:
                log.error(f"2Captcha error: {e}")
                return None

        return await loop.run_in_executor(None, _solve)

    async def solve_slider_captcha(self, gt: str, challenge: str,
                                    page_url: str, api_server: str = "") -> Optional[Dict]:
        """Solve GeeTest/slider CAPTCHA."""
        if self.capmonster_key:
            result = await self._solve_slider_capmonster(gt, challenge, page_url, api_server)
            if result:
                return result

        if self.twocaptcha_key:
            result = await self._solve_slider_2captcha(gt, challenge, page_url, api_server)
            if result:
                return result

        return None

    async def _solve_slider_capmonster(self, gt, challenge, page_url, api_server):
        """Solve GeeTest via CapMonster Cloud."""
        log.info("Solving GeeTest/slider via CapMonster Cloud...")
        loop = asyncio.get_event_loop()

        def _create_and_poll():
            task = {
                "type": "GeeTestTaskProxyless",
                "websiteURL": page_url,
                "gt": gt,
                "challenge": challenge,
            }
            if api_server:
                task["geetestApiServerSubdomain"] = api_server
            req_body = json.dumps({
                "clientKey": self.capmonster_key,
                "task": task,
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{self.capmonster_url}/createTask",
                data=req_body,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if data.get("errorId", 0) != 0:
                    log.error(f"CapMonster GeeTest error: {data.get('errorCode')}")
                    return None
                task_id = data.get("taskId")
            except Exception as e:
                log.error(f"CapMonster createTask failed: {e}")
                return None

            for _ in range(60):
                time.sleep(3)
                poll_body = json.dumps({
                    "clientKey": self.capmonster_key,
                    "taskId": task_id,
                }).encode("utf-8")
                poll_req = urllib.request.Request(
                    f"{self.capmonster_url}/getTaskResult",
                    data=poll_body,
                    headers={"Content-Type": "application/json"},
                )
                try:
                    with urllib.request.urlopen(poll_req, timeout=30) as resp:
                        result = json.loads(resp.read().decode("utf-8"))
                    if result.get("status") == "ready":
                        solution = result.get("solution", {})
                        log.info("CapMonster GeeTest solved!")
                        return solution
                    elif result.get("errorId", 0) != 0:
                        log.error(f"CapMonster error: {result.get('errorCode')}")
                        return None
                except Exception:
                    pass
            return None

        return await loop.run_in_executor(None, _create_and_poll)

    async def _solve_slider_2captcha(self, gt, challenge, page_url, api_server):
        """Solve GeeTest via 2Captcha."""
        log.info("Solving GeeTest/slider via 2Captcha...")
        loop = asyncio.get_event_loop()

        def _solve():
            try:
                from twocaptcha import TwoCaptcha
                solver = TwoCaptcha(self.twocaptcha_key)
                result = solver.geetest(
                    gt=gt,
                    challenge=challenge,
                    url=page_url,
                    apiServer=api_server or "api.geetest.com",
                )
                log.info("2Captcha GeeTest solved!")
                return result.get("code", result)
            except Exception as e:
                log.error(f"2Captcha GeeTest error: {e}")
                return None

        return await loop.run_in_executor(None, _solve)


# =============================================================================
# FLIGHT DATA PARSER
# =============================================================================

class QunarFlightParser:
    """
    Parses flight data from Qunar's various response formats.

    Qunar uses multiple data formats:
    1. XHR JSON responses from /twell/ endpoints
    2. Rendered DOM elements with flight cards
    3. JavaScript-embedded data objects
    """

    # Airline code to name mapping
    AIRLINE_MAP = {
        "3U": "Sichuan Airlines (四川航空)",
        "CZ": "China Southern (南方航空)",
        "MU": "China Eastern (东方航空)",
        "CA": "Air China (国航)",
        "HU": "Hainan Airlines (海南航空)",
        "MF": "XiamenAir (厦门航空)",
        "ZH": "Shenzhen Airlines (深圳航空)",
        "SC": "Shandong Airlines (山东航空)",
        "FM": "Shanghai Airlines (上海航空)",
        "KN": "China United (中国联航)",
        "GS": "Tianjin Airlines (天津航空)",
        "9C": "Spring Airlines (春秋航空)",
        "HO": "Juneyao Airlines (吉祥航空)",
        "EU": "Chengdu Airlines (成都航空)",
        "AA": "American Airlines",
        "UA": "United Airlines",
        "DL": "Delta Air Lines",
        "OZ": "Asiana Airlines",
        "KE": "Korean Air",
        "NH": "ANA",
        "JL": "Japan Airlines",
        "SQ": "Singapore Airlines",
        "CX": "Cathay Pacific",
        "BR": "EVA Air",
        "CI": "China Airlines",
    }

    @staticmethod
    def is_target_airline(airline_text: str) -> bool:
        """Check if the airline is one of our target airlines."""
        targets = Config.TARGET_AIRLINES
        for target in targets:
            if target.lower() in airline_text.lower():
                return True
        return False

    @classmethod
    def parse_xhr_response(cls, data: Any, route: str, date: str) -> List[Dict]:
        """Parse flight data from intercepted XHR JSON responses."""
        flights = []
        if not isinstance(data, dict):
            return flights

        try:
            # Try various data structures Qunar might use
            # Structure 1: data.flightInfo or data.flightList
            flight_list = (
                data.get("flightInfo", [])
                or data.get("flightList", [])
                or data.get("flights", [])
                or data.get("data", {}).get("flightInfo", [])
                or data.get("data", {}).get("flightList", [])
                or data.get("data", {}).get("flights", [])
                or data.get("result", {}).get("flightInfo", [])
                or data.get("result", {}).get("flights", [])
            )

            if isinstance(flight_list, list):
                for item in flight_list:
                    flight = cls._parse_flight_item(item, route, date)
                    if flight:
                        flights.append(flight)

            # Structure 2: oneWayFlightData or similar
            ow_data = (
                data.get("oneWayFlightData", {})
                or data.get("flightData", {})
                or data.get("data", {}).get("oneWayFlightData", {})
            )
            if isinstance(ow_data, dict):
                for key, items in ow_data.items():
                    if isinstance(items, list):
                        for item in items:
                            flight = cls._parse_flight_item(item, route, date)
                            if flight:
                                flights.append(flight)
                    elif isinstance(items, dict):
                        flight = cls._parse_flight_item(items, route, date)
                        if flight:
                            flights.append(flight)

            # Structure 3: groupList with vendors
            group_list = (
                data.get("groupList", [])
                or data.get("data", {}).get("groupList", [])
            )
            if isinstance(group_list, list):
                for group in group_list:
                    flight = cls._parse_group_item(group, route, date)
                    if flight:
                        flights.append(flight)

        except Exception as e:
            log.debug(f"XHR parse error: {e}")

        return flights

    @classmethod
    def _parse_flight_item(cls, item: dict, route: str, date: str) -> Optional[Dict]:
        """Parse a single flight item from XHR data."""
        if not isinstance(item, dict):
            return None

        try:
            # Extract flight number
            flight_no = (
                item.get("flightNo", "")
                or item.get("flightNumber", "")
                or item.get("flight_no", "")
                or item.get("code", "")
                or ""
            )

            # Extract airline
            airline = (
                item.get("airline", "")
                or item.get("airlineName", "")
                or item.get("carrier", "")
                or item.get("carrierName", "")
                or ""
            )
            if not airline and flight_no and len(flight_no) >= 2:
                code = flight_no[:2].upper()
                airline = cls.AIRLINE_MAP.get(code, code)

            # Extract price
            price = (
                item.get("price", 0)
                or item.get("minPrice", 0)
                or item.get("lowestPrice", 0)
                or item.get("barePrice", 0)
                or 0
            )
            if isinstance(price, str):
                price = re.sub(r"[^\d.]", "", price)
                price = float(price) if price else 0

            # Extract times
            dep_time = (
                item.get("departureTime", "")
                or item.get("depTime", "")
                or item.get("dptTime", "")
                or ""
            )
            arr_time = (
                item.get("arrivalTime", "")
                or item.get("arrTime", "")
                or item.get("arvTime", "")
                or ""
            )

            # Extract airports
            dep_airport = (
                item.get("departureAirport", "")
                or item.get("dptAirport", "")
                or item.get("depAirport", "")
                or ""
            )
            arr_airport = (
                item.get("arrivalAirport", "")
                or item.get("arvAirport", "")
                or item.get("arrAirport", "")
                or ""
            )

            # Stops
            stops = item.get("stops", item.get("stopCount", item.get("stop", 0)))
            if isinstance(stops, str):
                stops = int(re.sub(r"\D", "", stops or "0") or "0")

            # Duration
            duration = (
                item.get("duration", "")
                or item.get("flyTime", "")
                or item.get("totalTime", "")
                or ""
            )

            if not flight_no and not airline:
                return None

            return {
                "source": "qunar",
                "search_route": route,
                "search_date": date,
                "flight_number": str(flight_no).strip(),
                "airline": str(airline).strip(),
                "price": float(price) if price else None,
                "currency": "CNY",
                "departure_time": str(dep_time).strip(),
                "arrival_time": str(arr_time).strip(),
                "departure_airport": str(dep_airport).strip(),
                "arrival_airport": str(arr_airport).strip(),
                "stops": int(stops) if stops else 0,
                "duration": str(duration).strip(),
                "is_target_airline": cls.is_target_airline(
                    f"{airline} {flight_no}"
                ),
                "scraped_at": datetime.now().isoformat(),
            }
        except Exception as e:
            log.debug(f"Flight item parse error: {e}")
            return None

    @classmethod
    def _parse_group_item(cls, group: dict, route: str, date: str) -> Optional[Dict]:
        """Parse a group item (flight + vendors) from Qunar data."""
        if not isinstance(group, dict):
            return None

        # Groups typically contain the flight info plus vendor pricing
        flight_info = group.get("flightInfo", group.get("flight", group))
        if isinstance(flight_info, dict):
            flight = cls._parse_flight_item(flight_info, route, date)
            if flight:
                # Add vendor/agent pricing if available
                vendors = group.get("vendors", group.get("agents", []))
                if isinstance(vendors, list) and vendors:
                    prices = []
                    for v in vendors:
                        vp = v.get("price", v.get("barePrice", 0))
                        vn = v.get("name", v.get("agentName", ""))
                        if vp:
                            prices.append({"vendor": vn, "price": float(vp)})
                    if prices:
                        flight["vendor_prices"] = prices
                        flight["price"] = min(p["price"] for p in prices)
                return flight
        return None


# =============================================================================
# DOM SCRAPER (FALLBACK)
# =============================================================================

class QunarDOMScraper:
    """
    Scrapes flight data from Qunar's rendered DOM as a fallback
    when XHR interception doesn't capture structured data.

    Qunar's React-rendered flight cards use various CSS selectors
    that may change. This scraper tries multiple selector patterns.
    """

    # Multiple selector strategies for resilience
    FLIGHT_CARD_SELECTORS = [
        # Modern React-rendered selectors
        '[class*="flight-item"]',
        '[class*="flightItem"]',
        '[class*="flight_item"]',
        '[class*="flight-card"]',
        '[class*="flightCard"]',
        # Table-based layouts
        'table[class*="flight"] tr',
        '.m-flight-item',
        '.flight-list-item',
        # Generic result containers
        '[class*="result-item"]',
        '[class*="resultItem"]',
        '.item-info',
        'li[class*="flight"]',
        # Qunar-specific patterns
        '.b_table tbody tr',
        '.m-flightInfo',
        '[data-reactid*="flight"]',
    ]

    PRICE_SELECTORS = [
        '[class*="price"]',
        '[class*="Price"]',
        '.b_price',
        '.price-tag',
        'em[class*="price"]',
        'span[class*="price"]',
        '.m-price',
        '[class*="cost"]',
    ]

    AIRLINE_SELECTORS = [
        '[class*="airline"]',
        '[class*="Airline"]',
        '[class*="carrier"]',
        '.airline-name',
        '.air-name',
        '.m-airline',
        '[class*="logo"] + span',
        '[class*="logo"] + div',
    ]

    TIME_SELECTORS = [
        '[class*="depart-time"]',
        '[class*="departTime"]',
        '[class*="departure-time"]',
        '[class*="dep-time"]',
        '.depart-time',
        'time',
        '[class*="time"]',
    ]

    FLIGHT_NO_SELECTORS = [
        '[class*="flight-no"]',
        '[class*="flightNo"]',
        '[class*="flight-number"]',
        '[class*="flightNumber"]',
        '.flight-no',
        '[class*="flight_no"]',
    ]

    @classmethod
    async def scrape_flights(cls, page, route: str, date: str) -> List[Dict]:
        """Scrape flight data from the rendered DOM."""
        flights = []

        try:
            # Try each flight card selector
            flight_cards = []
            for selector in cls.FLIGHT_CARD_SELECTORS:
                try:
                    cards = await page.query_selector_all(selector)
                    if cards and len(cards) > 0:
                        flight_cards = cards
                        log.info(f"  DOM: Found {len(cards)} flight cards with '{selector}'")
                        break
                except Exception:
                    continue

            if not flight_cards:
                log.info("  DOM: No flight cards found via predefined selectors")
                # Try a broader approach
                flight_cards = await cls._find_flight_elements_broad(page)

            for card in flight_cards:
                try:
                    flight = await cls._parse_dom_card(card, route, date)
                    if flight:
                        flights.append(flight)
                except Exception as e:
                    log.debug(f"  DOM card parse error: {e}")
                    continue

        except Exception as e:
            log.debug(f"DOM scraping error: {e}")

        return flights

    @classmethod
    async def _find_flight_elements_broad(cls, page) -> list:
        """Broader search for flight elements in the DOM."""
        # Look for elements containing flight-related text patterns
        try:
            elements = await page.query_selector_all(
                'div[class], li[class], tr[class]'
            )
            flight_elements = []
            for el in elements[:200]:  # Limit to avoid performance issues
                try:
                    text = await el.inner_text()
                    # Check if element contains flight-like data
                    if (re.search(r'[A-Z]{2}\d{3,4}', text)
                            and re.search(r'\d{2}:\d{2}', text)):
                        flight_elements.append(el)
                except Exception:
                    continue
            if flight_elements:
                log.info(f"  DOM: Broad search found {len(flight_elements)} potential flight elements")
            return flight_elements
        except Exception:
            return []

    @classmethod
    async def _parse_dom_card(cls, card, route: str, date: str) -> Optional[Dict]:
        """Parse a single DOM flight card element."""
        try:
            text = await card.inner_text()
            if not text or len(text) < 10:
                return None
        except Exception:
            return None

        # Extract flight number
        flight_no = ""
        for sel in cls.FLIGHT_NO_SELECTORS:
            try:
                el = await card.query_selector(sel)
                if el:
                    flight_no = (await el.inner_text()).strip()
                    break
            except Exception:
                continue
        if not flight_no:
            match = re.search(r'([A-Z]{2})\s*(\d{3,4})', text)
            if match:
                flight_no = f"{match.group(1)}{match.group(2)}"

        # Extract airline name
        airline = ""
        for sel in cls.AIRLINE_SELECTORS:
            try:
                el = await card.query_selector(sel)
                if el:
                    airline = (await el.inner_text()).strip()
                    break
            except Exception:
                continue
        if not airline and flight_no and len(flight_no) >= 2:
            code = flight_no[:2].upper()
            airline = QunarFlightParser.AIRLINE_MAP.get(code, code)

        # Extract price
        price = None
        for sel in cls.PRICE_SELECTORS:
            try:
                el = await card.query_selector(sel)
                if el:
                    price_text = (await el.inner_text()).strip()
                    price_match = re.search(r'[\d,]+', price_text.replace(",", ""))
                    if price_match:
                        price = float(price_match.group().replace(",", ""))
                        break
            except Exception:
                continue
        if price is None:
            price_match = re.search(r'(?:¥|CNY|￥)\s*([\d,]+)', text)
            if price_match:
                price = float(price_match.group(1).replace(",", ""))

        # Extract times
        times = re.findall(r'(\d{1,2}:\d{2})', text)
        dep_time = times[0] if len(times) >= 1 else ""
        arr_time = times[1] if len(times) >= 2 else ""

        # Extract stops info
        stops = 0
        if "直达" in text or "直飞" in text or "nonstop" in text.lower():
            stops = 0
        elif re.search(r'[经转](\d)', text):
            match = re.search(r'[经转](\d)', text)
            stops = int(match.group(1))
        elif "经停" in text or "中转" in text or "转机" in text:
            stops = 1

        # Duration
        dur_match = re.search(r'(\d+)[hH小时]\s*(\d+)?[mM分]?', text)
        duration = ""
        if dur_match:
            h = dur_match.group(1)
            m = dur_match.group(2) or "0"
            duration = f"{h}h{m}m"

        if not flight_no and not airline and price is None:
            return None

        return {
            "source": "qunar",
            "search_route": route,
            "search_date": date,
            "flight_number": flight_no,
            "airline": airline,
            "price": price,
            "currency": "CNY",
            "departure_time": dep_time,
            "arrival_time": arr_time,
            "departure_airport": "",
            "arrival_airport": "",
            "stops": stops,
            "duration": duration,
            "is_target_airline": QunarFlightParser.is_target_airline(
                f"{airline} {flight_no}"
            ),
            "scraped_at": datetime.now().isoformat(),
            "parse_method": "dom",
        }


# =============================================================================
# JAVASCRIPT DATA EXTRACTOR
# =============================================================================

class QunarJSExtractor:
    """
    Extracts flight data from JavaScript variables embedded in the page.
    Qunar may embed flight data in window.__INITIAL_STATE__,
    window.__NEXT_DATA__, or other global variables.
    """

    JS_EXTRACTION_SCRIPT = """
    () => {
        const result = {
            found: false,
            data: null,
            variables: [],
            flight_count: 0,
        };

        // Try various global state variables
        const stateVars = [
            '__INITIAL_STATE__', '__NEXT_DATA__', '__NUXT__',
            '__APP_DATA__', 'QCONFIG_DATA', '__pageData__',
            'flightData', 'searchResult', '__FLIGHT_DATA__',
            'globalFlightData', '__data__',
        ];

        for (const varName of stateVars) {
            try {
                const val = window[varName];
                if (val && typeof val === 'object') {
                    result.variables.push(varName);
                    const str = JSON.stringify(val);
                    // Check if it contains flight-related data
                    if (str.includes('flight') || str.includes('price') ||
                        str.includes('airline') || str.includes('flightNo')) {
                        result.found = true;
                        result.data = val;
                        break;
                    }
                }
            } catch(e) {}
        }

        // Try to find React/Vue state with flight data
        if (!result.found) {
            try {
                const root = document.getElementById('root') || document.getElementById('app');
                if (root && root._reactRootContainer) {
                    const fiber = root._reactRootContainer._internalRoot ||
                                  root._reactRootContainer;
                    result.variables.push('_reactRootContainer (found)');
                }
            } catch(e) {}
        }

        // Extract any data from script tags
        if (!result.found) {
            const scripts = document.querySelectorAll('script:not([src])');
            for (const script of scripts) {
                const text = script.textContent;
                if (text && text.includes('flightInfo') || text.includes('flightData')) {
                    try {
                        // Try to extract JSON objects
                        const match = text.match(/(?:var|let|const|window\\.\\w+)\\s*=\\s*({[\\s\\S]*?});/);
                        if (match) {
                            const parsed = JSON.parse(match[1]);
                            result.found = true;
                            result.data = parsed;
                            result.variables.push('inline_script');
                            break;
                        }
                    } catch(e) {}
                }
            }
        }

        return result;
    }
    """

    @classmethod
    async def extract(cls, page) -> Optional[Dict]:
        """Extract flight data from JavaScript context."""
        try:
            result = await page.evaluate(cls.JS_EXTRACTION_SCRIPT)
            if result and result.get("found"):
                log.info(f"  JS: Found data in variables: {result.get('variables', [])}")
                return result.get("data")
            else:
                vars_found = result.get("variables", []) if result else []
                log.info(f"  JS: No flight data in JS variables. Found vars: {vars_found}")
        except Exception as e:
            log.debug(f"  JS extraction error: {e}")
        return None


# =============================================================================
# MAIN CRAWLER
# =============================================================================

class QunarCrawler:
    """
    Main Qunar flight crawler using Playwright with stealth mode.

    Flow:
    1. Launch browser with stealth settings
    2. For each route/date combination:
       a. Build Qunar search URL
       b. Navigate and wait for page load
       c. Intercept XHR responses for structured data
       d. Extract data from JavaScript context
       e. Scrape rendered DOM as fallback
       f. Handle CAPTCHA if encountered
    3. Aggregate, deduplicate, and save results
    """

    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.all_results: List[Dict] = []
        self.intercepted_data: List[Dict] = []
        self.captcha_solver = QunarCaptchaSolver(
            capmonster_key=self.config.CAPMONSTER_API_KEY,
            twocaptcha_key=self.config.TWOCAPTCHA_API_KEY,
        )
        self.search_metadata: List[Dict] = []

    def _build_search_url(self, route: Dict) -> str:
        """Build Qunar flight search URL."""
        origin = route["origin"]
        dest = route["destination"]
        trip_type = route.get("trip_type", "oneway")

        origin_cn = self.config.CITY_NAMES.get(origin, {}).get("cn", origin)
        dest_cn = self.config.CITY_NAMES.get(dest, {}).get("cn", dest)

        dep_date = self.config.DEPARTURE_DATE

        if trip_type == "roundtrip":
            ret_date = route.get("return_date", "")
            base_url = self.config.QUNAR_ROUNDTRIP_URL
            params = {
                "searchDepartureAirport": origin_cn,
                "searchArrivalAirport": dest_cn,
                "searchDepartureTime": dep_date,
                "searchArrivalTime": ret_date,
                "nextNDays": "0",
                "startSearch": "true",
                "fromCode": origin,
                "toCode": dest,
                "from": "qunarindex",
                "lowestPrice": "null",
            }
        else:
            base_url = self.config.QUNAR_ONEWAY_URL
            params = {
                "searchDepartureAirport": origin_cn,
                "searchArrivalAirport": dest_cn,
                "searchDepartureTime": dep_date,
                "searchArrivalTime": "",
                "nextNDays": "0",
                "startSearch": "true",
                "fromCode": origin,
                "toCode": dest,
                "from": "qunarindex",
                "lowestPrice": "null",
            }

        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        return url

    async def run(self):
        """Main entry point - run the crawler."""
        log.info("=" * 70)
        log.info("QUNAR FLIGHT CRAWLER (去哪儿机票爬虫)")
        log.info("=" * 70)
        log.info(f"Departure date: {self.config.DEPARTURE_DATE}")
        log.info(f"Routes: {len(self.config.ROUTES)}")
        log.info(f"CapMonster key: {'set' if self.config.CAPMONSTER_API_KEY else 'not set'}")
        log.info(f"2Captcha key: {'set' if self.config.TWOCAPTCHA_API_KEY else 'not set'}")
        log.info(f"Proxy: {self.config.PROXY_URL or 'none (direct)'}")
        log.info(f"Headless: {self.config.HEADLESS}")
        log.info(f"Output: {self.config.OUTPUT_FILE}")
        log.info("")

        try:
            from playwright.async_api import async_playwright
            from playwright_stealth import Stealth
        except ImportError as e:
            log.error(f"Missing dependency: {e}")
            log.error("Install with: pip install playwright playwright-stealth")
            log.error("Then run: python -m playwright install chromium")
            return

        stealth = Stealth()

        async with stealth.use_async(async_playwright()) as p:
            # Launch browser with stealth options
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--lang=zh-CN,zh,en-US,en",
            ]

            browser_kwargs = {
                "headless": self.config.HEADLESS,
                "slow_mo": self.config.SLOW_MO,
                "args": launch_args,
            }

            if self.config.PROXY_URL:
                browser_kwargs["proxy"] = {"server": self.config.PROXY_URL}

            log.info("Launching Chromium browser...")
            browser = await p.chromium.launch(**browser_kwargs)

            # Create context with Chinese locale
            context = await browser.new_context(
                viewport={"width": 1366, "height": 768},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                extra_http_headers={
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                    "sec-ch-ua-platform": '"Windows"',
                },
            )

            # Process each route
            for i, route in enumerate(self.config.ROUTES):
                route_str = f"{route['origin']}-{route['destination']}"
                trip_type = route.get("trip_type", "oneway")
                if trip_type == "roundtrip":
                    route_str += f" (RT, return {route.get('return_date', '')})"

                log.info(f"\n{'=' * 60}")
                log.info(f"Route {i + 1}/{len(self.config.ROUTES)}: {route_str}")
                log.info(f"{'=' * 60}")

                try:
                    flights = await self._search_route(
                        context, route
                    )
                    if flights:
                        self.all_results.extend(flights)
                        log.info(f"  Found {len(flights)} flights for {route_str}")

                        # Show target airline results
                        target_flights = [f for f in flights if f.get("is_target_airline")]
                        if target_flights:
                            log.info(f"  Target airline flights: {len(target_flights)}")
                            for tf in target_flights[:5]:
                                log.info(
                                    f"    {tf['airline']:<30} {tf.get('flight_number', 'N/A'):<10} "
                                    f"CNY {tf.get('price', 'N/A'):>8}"
                                )
                    else:
                        log.warning(f"  No flights found for {route_str}")

                except Exception as e:
                    log.error(f"  Error searching {route_str}: {e}")

                # Delay between searches to avoid rate limiting
                if i < len(self.config.ROUTES) - 1:
                    delay = 8
                    log.info(f"  Waiting {delay}s before next search...")
                    await asyncio.sleep(delay)

            await browser.close()

        # Save results
        self._save_results()
        self._print_summary()

    async def _search_route(self, context, route: Dict) -> List[Dict]:
        """Search a single route on Qunar."""
        search_url = self._build_search_url(route)
        route_str = f"{route['origin']}-{route['destination']}"
        date = self.config.DEPARTURE_DATE
        trip_type = route.get("trip_type", "oneway")

        log.info(f"  URL: {search_url[:100]}...")

        page = await context.new_page()
        # Stealth is applied automatically via the hooked context

        # Collect flights from all sources
        xhr_flights: List[Dict] = []
        captcha_detected = False
        captcha_params = {}

        # --- Network interception ---
        async def handle_response(response):
            nonlocal xhr_flights, captcha_detected, captcha_params
            url = response.url
            try:
                # Check for flight data in XHR responses
                if any(pattern in url for pattern in self.config.API_PATTERNS):
                    if response.status == 200:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct or "javascript" in ct or "text" in ct:
                            try:
                                body = await response.text()
                                # Try to parse as JSON
                                # Qunar sometimes wraps JSON in callbacks
                                json_body = body
                                # Strip JSONP callback if present
                                jsonp_match = re.match(
                                    r'^\s*\w+\s*\(\s*([\s\S]*)\s*\)\s*;?\s*$',
                                    body
                                )
                                if jsonp_match:
                                    json_body = jsonp_match.group(1)

                                data = json.loads(json_body)
                                flights = QunarFlightParser.parse_xhr_response(
                                    data, route_str, date
                                )
                                if flights:
                                    xhr_flights.extend(flights)
                                    log.info(
                                        f"  XHR: Captured {len(flights)} flights "
                                        f"from {url[:80]}..."
                                    )

                                self.intercepted_data.append({
                                    "url": url[:200],
                                    "flight_count": len(flights),
                                    "response_size": len(body),
                                    "timestamp": datetime.now().isoformat(),
                                })
                            except (json.JSONDecodeError, ValueError):
                                # Not JSON - might be encrypted or JS
                                if len(body) > 500:
                                    self.intercepted_data.append({
                                        "url": url[:200],
                                        "note": "non-JSON response (possibly encrypted)",
                                        "response_size": len(body),
                                        "timestamp": datetime.now().isoformat(),
                                    })

                # Check for CAPTCHA / verification
                if any(kw in url.lower() for kw in [
                    "captcha", "verify", "geetest", "defense", "piccolo",
                    "validation", "authcode",
                ]):
                    try:
                        body = await response.text()
                        try:
                            data = json.loads(body)
                            if "gt" in data and "challenge" in data:
                                captcha_params = {
                                    "gt": data["gt"],
                                    "challenge": data["challenge"],
                                    "api_server": data.get("api_server", ""),
                                }
                                captcha_detected = True
                                log.warning(f"  CAPTCHA detected (GeeTest): gt={data['gt'][:16]}...")
                        except (json.JSONDecodeError, ValueError):
                            pass
                    except Exception:
                        pass

            except Exception as e:
                log.debug(f"  Response handler error: {e}")

        page.on("response", handle_response)

        try:
            # Navigate to search page
            log.info(f"  Navigating to Qunar flight search...")
            await page.goto(
                search_url,
                timeout=self.config.NAVIGATION_TIMEOUT,
                wait_until="domcontentloaded",
            )

            # Wait for initial page load and React hydration
            log.info(f"  Waiting for page load ({self.config.PAGE_LOAD_WAIT}s)...")
            await asyncio.sleep(self.config.PAGE_LOAD_WAIT)

            # Check for CAPTCHA / verification page
            captcha_el = await page.query_selector(
                '.captcha-container, [class*="captcha"], [class*="verify"], '
                '[class*="defense"], .geetest_panel, .geetest_popup, '
                '#gc-box, [class*="slider-verify"], [class*="Verify"]'
            )

            if captcha_el or captcha_detected:
                log.warning("  CAPTCHA/verification page detected!")
                solved = await self._handle_captcha(page, search_url, captcha_params)
                if solved:
                    log.info("  CAPTCHA solved! Waiting for results to load...")
                    await asyncio.sleep(self.config.PAGE_LOAD_WAIT)
                else:
                    log.warning("  Could not solve CAPTCHA. Trying to proceed anyway...")

            # Check for redirect or block page
            current_url = page.url
            if "verify" in current_url.lower() or "captcha" in current_url.lower():
                log.warning(f"  Redirected to verification page: {current_url[:80]}")
                # Try solving CAPTCHA on this page
                await self._handle_captcha(page, current_url, captcha_params)
                await asyncio.sleep(self.config.PAGE_LOAD_WAIT)

            # Scroll down to trigger lazy loading of more results
            log.info("  Scrolling to load more results...")
            for scroll_step in range(5):
                await page.evaluate(
                    f"window.scrollTo(0, {(scroll_step + 1) * 800})"
                )
                await asyncio.sleep(1.5)

            # Wait a bit more for async XHR to complete
            await asyncio.sleep(self.config.MAX_SCROLL_WAIT)

            # --- Source 2: JavaScript context extraction ---
            log.info("  Extracting data from JavaScript context...")
            js_data = await QunarJSExtractor.extract(page)
            js_flights = []
            if js_data:
                js_flights = QunarFlightParser.parse_xhr_response(
                    js_data, route_str, date
                )
                if js_flights:
                    log.info(f"  JS: Parsed {len(js_flights)} flights from JS context")

            # --- Source 3: DOM scraping ---
            log.info("  Scraping rendered DOM...")
            dom_flights = await QunarDOMScraper.scrape_flights(page, route_str, date)
            if dom_flights:
                log.info(f"  DOM: Scraped {len(dom_flights)} flights from page")

            # --- Source 4: Page text extraction (last resort) ---
            page_flights = await self._extract_from_page_text(page, route_str, date)

            # Take a screenshot for debugging
            screenshot_path = Path(self.config.OUTPUT_FILE).parent / "qunar_screenshots"
            screenshot_path.mkdir(exist_ok=True)
            ss_file = screenshot_path / f"qunar_{route['origin']}_{route['destination']}_{trip_type}.png"
            try:
                await page.screenshot(path=str(ss_file), full_page=True)
                log.info(f"  Screenshot saved: {ss_file}")
            except Exception as e:
                log.debug(f"  Screenshot error: {e}")

            # Save page HTML for debugging
            try:
                html_content = await page.content()
                html_file = screenshot_path / f"qunar_{route['origin']}_{route['destination']}_{trip_type}.html"
                with open(html_file, "w", encoding="utf-8") as f:
                    f.write(html_content)
                log.info(f"  HTML saved: {html_file}")
            except Exception as e:
                log.debug(f"  HTML save error: {e}")

            # Merge all flight sources (XHR takes priority)
            all_flights = self._merge_flights(
                xhr_flights, js_flights, dom_flights, page_flights
            )

            # Record search metadata
            self.search_metadata.append({
                "route": route_str,
                "trip_type": trip_type,
                "date": date,
                "url": search_url,
                "final_url": page.url,
                "xhr_flights": len(xhr_flights),
                "js_flights": len(js_flights),
                "dom_flights": len(dom_flights),
                "page_text_flights": len(page_flights),
                "total_flights": len(all_flights),
                "captcha_detected": captcha_detected,
                "timestamp": datetime.now().isoformat(),
            })

            return all_flights

        except Exception as e:
            log.error(f"  Navigation/scraping error: {e}")
            # Save error screenshot
            try:
                ss_file = (
                    Path(self.config.OUTPUT_FILE).parent
                    / "qunar_screenshots"
                    / f"error_{route['origin']}_{route['destination']}.png"
                )
                ss_file.parent.mkdir(exist_ok=True)
                await page.screenshot(path=str(ss_file))
            except Exception:
                pass
            return []
        finally:
            await page.close()

    async def _extract_from_page_text(self, page, route: str, date: str) -> List[Dict]:
        """Last resort: extract flight info from all visible text on the page."""
        flights = []
        try:
            # Get all text content
            text = await page.evaluate("() => document.body.innerText")
            if not text:
                return flights

            # Look for patterns like: CA123 Air China 08:30-14:50 ¥4,560
            lines = text.split("\n")
            current_flight = {}
            for line in lines:
                line = line.strip()
                if not line:
                    if current_flight.get("flight_number") or current_flight.get("airline"):
                        if current_flight.get("price"):
                            flights.append({
                                "source": "qunar",
                                "search_route": route,
                                "search_date": date,
                                "flight_number": current_flight.get("flight_number", ""),
                                "airline": current_flight.get("airline", ""),
                                "price": current_flight.get("price"),
                                "currency": "CNY",
                                "departure_time": current_flight.get("dep_time", ""),
                                "arrival_time": current_flight.get("arr_time", ""),
                                "departure_airport": "",
                                "arrival_airport": "",
                                "stops": current_flight.get("stops", 0),
                                "duration": current_flight.get("duration", ""),
                                "is_target_airline": QunarFlightParser.is_target_airline(
                                    f"{current_flight.get('airline', '')} "
                                    f"{current_flight.get('flight_number', '')}"
                                ),
                                "scraped_at": datetime.now().isoformat(),
                                "parse_method": "page_text",
                            })
                    current_flight = {}
                    continue

                # Flight number
                fn_match = re.search(r'\b([A-Z]{2})\s*(\d{3,4})\b', line)
                if fn_match:
                    current_flight["flight_number"] = f"{fn_match.group(1)}{fn_match.group(2)}"
                    code = fn_match.group(1)
                    if code in QunarFlightParser.AIRLINE_MAP:
                        current_flight["airline"] = QunarFlightParser.AIRLINE_MAP[code]

                # Airline name (Chinese)
                for name in ["四川航空", "川航", "南方航空", "南航", "东方航空", "东航",
                             "国航", "中国国际航空", "海南航空", "海航", "厦门航空", "厦航",
                             "深圳航空", "山东航空", "上海航空", "春秋航空", "吉祥航空"]:
                    if name in line:
                        current_flight["airline"] = name
                        break

                # Price
                price_match = re.search(r'[¥￥]\s*([\d,]+)', line)
                if price_match:
                    current_flight["price"] = float(
                        price_match.group(1).replace(",", "")
                    )

                # Time pattern
                time_match = re.findall(r'(\d{1,2}:\d{2})', line)
                if len(time_match) >= 2:
                    current_flight["dep_time"] = time_match[0]
                    current_flight["arr_time"] = time_match[1]
                elif len(time_match) == 1 and "dep_time" not in current_flight:
                    current_flight["dep_time"] = time_match[0]

                # Duration
                dur_match = re.search(r'(\d+)\s*[hH小时]\s*(\d+)\s*[mM分]', line)
                if dur_match:
                    current_flight["duration"] = f"{dur_match.group(1)}h{dur_match.group(2)}m"

                # Stops
                if "直达" in line or "直飞" in line:
                    current_flight["stops"] = 0
                elif "经停" in line or "中转" in line:
                    current_flight["stops"] = 1

            if flights:
                log.info(f"  Text: Extracted {len(flights)} flights from page text")
        except Exception as e:
            log.debug(f"  Page text extraction error: {e}")

        return flights

    def _merge_flights(self, *flight_lists) -> List[Dict]:
        """Merge flights from multiple sources, deduplicating by flight number + price."""
        seen = set()
        merged = []

        for flights in flight_lists:
            for flight in flights:
                # Create a dedup key
                key = (
                    flight.get("flight_number", "").upper(),
                    flight.get("price"),
                    flight.get("departure_time", ""),
                )
                if key not in seen and key != ("", None, ""):
                    seen.add(key)
                    merged.append(flight)

        return merged

    async def _handle_captcha(self, page, page_url: str,
                               captcha_params: Dict) -> bool:
        """Handle CAPTCHA on the page."""
        log.info("  Attempting to solve CAPTCHA...")

        # Try 1: GeeTest slider
        if captcha_params.get("gt") and captcha_params.get("challenge"):
            solution = await self.captcha_solver.solve_slider_captcha(
                gt=captcha_params["gt"],
                challenge=captcha_params["challenge"],
                page_url=page_url,
                api_server=captcha_params.get("api_server", ""),
            )
            if solution:
                log.info("  GeeTest solved! Injecting solution...")
                try:
                    await page.evaluate(f"""
                        (solution) => {{
                            if (window.captchaObj && window.captchaObj.verify) {{
                                // Direct GeeTest API
                                window.captchaObj.verify();
                            }}
                            // Try triggering form submission
                            const submitBtn = document.querySelector(
                                'button[type="submit"], [class*="submit"], .btn-verify'
                            );
                            if (submitBtn) submitBtn.click();
                        }}
                    """, solution)
                    await asyncio.sleep(3)
                    return True
                except Exception as e:
                    log.debug(f"  GeeTest injection error: {e}")

        # Try 2: Image CAPTCHA
        try:
            captcha_img = await page.query_selector(
                'img[class*="captcha"], img[id*="captcha"], '
                'img[src*="captcha"], img[class*="verify-img"], '
                '.captcha-img img, .verify-img'
            )
            if captcha_img:
                # Get image as base64
                img_src = await captcha_img.get_attribute("src")
                if img_src:
                    if img_src.startswith("data:"):
                        img_b64 = img_src.split(",", 1)[1]
                    else:
                        # Screenshot the element
                        img_bytes = await captcha_img.screenshot()
                        img_b64 = base64.b64encode(img_bytes).decode("utf-8")

                    solution = await self.captcha_solver.solve_image_captcha(
                        img_b64, page_url
                    )
                    if solution:
                        # Find input field and submit
                        captcha_input = await page.query_selector(
                            'input[class*="captcha"], input[id*="captcha"], '
                            'input[name*="captcha"], input[class*="verify-input"], '
                            '.captcha-input input'
                        )
                        if captcha_input:
                            await captcha_input.fill(solution)
                            await asyncio.sleep(0.5)
                            # Click submit
                            submit_btn = await page.query_selector(
                                'button[type="submit"], [class*="submit"], '
                                '.btn-verify, .captcha-submit, [class*="confirm"]'
                            )
                            if submit_btn:
                                await submit_btn.click()
                            else:
                                await captcha_input.press("Enter")
                            await asyncio.sleep(3)
                            return True
        except Exception as e:
            log.debug(f"  Image CAPTCHA handling error: {e}")

        # Try 3: Slider drag (visual slider, not GeeTest)
        try:
            slider = await page.query_selector(
                '[class*="slider"], [class*="drag"], '
                '.slide-btn, .drag-btn, [class*="slide-verify"]'
            )
            if slider:
                log.info("  Found slider element, attempting drag...")
                box = await slider.bounding_box()
                if box:
                    start_x = box["x"] + box["width"] / 2
                    start_y = box["y"] + box["height"] / 2
                    # Drag to the right with human-like movement
                    await page.mouse.move(start_x, start_y)
                    await page.mouse.down()
                    steps = 20
                    for step in range(steps):
                        offset = (step + 1) * (250 / steps)
                        await page.mouse.move(
                            start_x + offset,
                            start_y + (2 if step % 3 == 0 else -1),
                        )
                        await asyncio.sleep(0.03)
                    await page.mouse.up()
                    await asyncio.sleep(3)
                    return True
        except Exception as e:
            log.debug(f"  Slider drag error: {e}")

        log.warning("  Could not solve CAPTCHA automatically")
        return False

    def _save_results(self):
        """Save all collected results to JSON."""
        # Separate target airline results
        target_results = [
            f for f in self.all_results if f.get("is_target_airline")
        ]
        other_results = [
            f for f in self.all_results if not f.get("is_target_airline")
        ]

        output = {
            "crawl_timestamp": datetime.now().isoformat(),
            "crawler": "qunar_crawler",
            "crawler_version": "1.0.0",
            "source": "qunar.com (去哪儿网)",
            "config": {
                "departure_date": self.config.DEPARTURE_DATE,
                "routes_searched": [
                    f"{r['origin']}-{r['destination']} ({r.get('trip_type', 'oneway')})"
                    for r in self.config.ROUTES
                ],
                "headless": self.config.HEADLESS,
                "capmonster_key_set": bool(self.config.CAPMONSTER_API_KEY),
                "twocaptcha_key_set": bool(self.config.TWOCAPTCHA_API_KEY),
                "proxy_set": bool(self.config.PROXY_URL),
            },
            "summary": {
                "total_flights": len(self.all_results),
                "target_airline_flights": len(target_results),
                "other_flights": len(other_results),
                "routes_with_results": len(set(
                    f.get("search_route", "") for f in self.all_results
                )),
            },
            "target_airlines": {
                "description": (
                    "Flights from target Chinese airlines: "
                    "Sichuan Airlines (3U), China Southern (CZ), "
                    "China Eastern (MU), Air China (CA), "
                    "Hainan Airlines (HU), XiamenAir (MF)"
                ),
                "flights": sorted(
                    target_results,
                    key=lambda x: (x.get("price") or 999999),
                ),
            },
            "all_flights": sorted(
                self.all_results,
                key=lambda x: (
                    x.get("search_route", ""),
                    x.get("price") or 999999,
                ),
            ),
            "search_metadata": self.search_metadata,
            "intercepted_api_calls": self.intercepted_data,
            "notes": {
                "data_sources": (
                    "Flight data is collected from multiple sources: "
                    "1) XHR API response interception, "
                    "2) JavaScript context variables, "
                    "3) DOM scraping, "
                    "4) Page text extraction. "
                    "XHR data is most reliable; DOM/text are fallbacks."
                ),
                "price_accuracy": (
                    "Qunar may apply price obfuscation (random offsets) "
                    "to displayed prices. XHR-intercepted prices may differ "
                    "from displayed prices. Actual booking prices may vary."
                ),
                "currency": "All prices are in CNY (Chinese Yuan) unless noted.",
                "anti_bot_measures": (
                    "Qunar employs: React client-side rendering, "
                    "AES response encryption, price obfuscation, "
                    "cookie validation, UADATA token generation, "
                    "CAPTCHA challenges. This scraper uses Playwright "
                    "stealth mode and CAPTCHA solving to mitigate these."
                ),
            },
            "related_scrapers": {
                "google_flights": "search_flights.py",
                "ita_matrix": "ita_matrix_scraper.py",
                "ctrip": "ctrip_crawler.py",
                "qunar": "qunar_crawler.py (this file)",
            },
        }

        output_path = Path(self.config.OUTPUT_FILE)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)

        log.info(f"\nResults saved to: {output_path}")

    def _print_summary(self):
        """Print a summary of crawl results."""
        log.info("\n" + "=" * 70)
        log.info("QUNAR CRAWL SUMMARY")
        log.info("=" * 70)
        log.info(f"Total flights found: {len(self.all_results)}")

        if self.all_results:
            # Group by route
            by_route: Dict[str, List[Dict]] = {}
            for f in self.all_results:
                route = f.get("search_route", "Unknown")
                by_route.setdefault(route, []).append(f)

            for route, flights in sorted(by_route.items()):
                prices = [
                    f["price"] for f in flights
                    if f.get("price") and f["price"] > 0
                ]
                log.info(f"\n  {route}: {len(flights)} flights")
                if prices:
                    log.info(
                        f"    Price range: CNY {min(prices):,.0f} - {max(prices):,.0f}"
                    )

                # Show target airlines for this route
                targets = [f for f in flights if f.get("is_target_airline")]
                if targets:
                    log.info(f"    Target airlines ({len(targets)}):")
                    for tf in sorted(targets, key=lambda x: x.get("price") or 999999)[:8]:
                        log.info(
                            f"      {tf.get('airline', 'N/A'):<25} "
                            f"{tf.get('flight_number', 'N/A'):<10} "
                            f"CNY {tf.get('price', 'N/A'):>8} "
                            f"{tf.get('stops', '?')} stop(s) "
                            f"{tf.get('duration', '')}"
                        )
        else:
            log.info("  No flights were captured.")
            log.info("  Possible reasons:")
            log.info("    - Qunar blocked the request (CAPTCHA/anti-bot)")
            log.info("    - International routes not available from this IP")
            log.info("    - Page structure has changed")
            log.info("    - Need Chinese IP proxy for domestic pricing")
            log.info("  Check the screenshots and HTML files in qunar_screenshots/")

        # Show search metadata
        log.info(f"\nSearch details:")
        for meta in self.search_metadata:
            log.info(
                f"  {meta['route']} ({meta['trip_type']}): "
                f"XHR={meta['xhr_flights']}, JS={meta['js_flights']}, "
                f"DOM={meta['dom_flights']}, Text={meta['page_text_flights']} "
                f"| CAPTCHA={'YES' if meta['captcha_detected'] else 'no'}"
            )

        log.info("\n" + "=" * 70)


# =============================================================================
# ENTRY POINT
# =============================================================================

async def main():
    """Run the Qunar flight crawler."""
    config = Config()
    crawler = QunarCrawler(config)
    await crawler.run()


if __name__ == "__main__":
    asyncio.run(main())
