#!/usr/bin/env python3
"""
Ctrip & Trip.com International Flight Crawler with CAPTCHA Solving
===================================================================

A production-ready scraper for Chinese OTA international flights using
Playwright (stealth mode) with automated CAPTCHA solving via 2Captcha,
Anti-Captcha, or CapSolver.

Architecture (adapted from github.com/Suysker/Ctrip-Crawler):
  - Playwright replaces Selenium for better stealth and performance
  - playwright-stealth hides automation fingerprints
  - Network request interception captures flight data from XHR responses
  - 2Captcha/Anti-Captcha/CapSolver API solves slider/image CAPTCHAs
  - Proxy support for residential/Chinese IP rotation

Targets:
  - Ctrip International: flights.ctrip.com/international/
  - Trip.com (fallback): www.trip.com/flights/
  - Chinese airline sites: sichuanair.com, csair.com, ceair.com

Routes: CTU-LAX, PVG-LAX, PVG-SFO, CAN-LAX, ICN-LAX
Dates:  May-June 2026, September 2026

Setup:
  1. pip install playwright playwright-stealth 2captcha-python
  2. python -m playwright install chromium
  3. Set environment variable: CAPTCHA_API_KEY=your_2captcha_key
  4. Optionally set: CAPTCHA_SERVICE=2captcha (or anticaptcha, capsolver)
  5. Optionally set: PROXY_URL=http://user:pass@host:port
  6. Run: python ctrip_crawler.py

=== CAPTCHA SERVICE COMPARISON ===

Service       | Price/1000   | Python SDK              | CAPTCHA Types              | Speed
------------- | ------------ | ----------------------- | -------------------------- | --------
2Captcha      | $0.50-$2.99  | pip install 2captcha-python | Image, reCAPTCHA, GeeTest, Slider | 5-30s
Anti-Captcha  | $0.50-$2.00  | pip install anticaptchaofficial | Image, reCAPTCHA, GeeTest | 5-30s
CapSolver     | $0.40-$2.00  | pip install capsolver   | Image, reCAPTCHA, GeeTest, Turnstile | 1-5s
DeathByCaptcha| $1.39-$6.95  | Custom SDK              | Image, reCAPTCHA           | 10-60s

Recommendation: 2Captcha for reliability, CapSolver for speed.
Ctrip typically uses GeeTest slider CAPTCHAs ($1.45/1000 on 2Captcha).

=== PROXY SERVICE COMPARISON ===

Provider      | China IPs | Price           | Protocol       | Best For
------------- | --------- | --------------- | -------------- | --------
Bright Data   | 72M+ IPs  | $5.04/GB+       | HTTP/SOCKS5    | Largest pool
Decodo        | Available | From $10/mo     | HTTP/SOCKS5    | Budget option
IPRoyal       | 2.5M IPs  | $1.75/GB        | HTTP/SOCKS5    | Good value
Oxylabs       | Available | From $15/GB     | HTTP/SOCKS5    | Enterprise
SOAX          | 31K IPs   | $99/mo+         | HTTP/SOCKS5    | China specialist

Recommendation: IPRoyal or Bright Data for China IP residential proxies.
For Ctrip: Chinese residential IPs avoid geo-blocks on domestic pricing.

=== IMPORTANT NOTES ===

1. Ctrip's international API (batchSearch) requires a browser session.
   Plain HTTP requests get "showAuthCode: true" (CAPTCHA gate).
   The Suysker/Ctrip-Crawler project's products endpoint (/api/12808/products)
   has been decommissioned ("interface offline" / "jiekou xiaxian").

2. Trip.com uses Akamai Bot Manager with crypto challenges (HTTP 428/432).
   Even with Playwright stealth, you may need residential proxies.

3. The crawler intercepts XHR/fetch responses from the search pages.
   Flight data arrives as JSON in network responses, not in the DOM.

4. GeeTest slider CAPTCHAs on Ctrip require extracting the gt, challenge,
   and api_server parameters, then sending them to the solving service.
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
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path

# Fix Windows console encoding
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
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ctrip_crawler")


# =============================================================================
# CONFIGURATION
# =============================================================================

class Config:
    """All configurable parameters for the crawler."""

    # CAPTCHA solving service
    CAPTCHA_SERVICE = os.environ.get("CAPTCHA_SERVICE", "2captcha")  # 2captcha | anticaptcha | capsolver
    CAPTCHA_API_KEY = os.environ.get("CAPTCHA_API_KEY", "")

    # Proxy (optional)
    PROXY_URL = os.environ.get("PROXY_URL", "")  # http://user:pass@host:port

    # Browser settings
    HEADLESS = os.environ.get("CRAWLER_HEADLESS", "true").lower() == "true"
    SLOW_MO = int(os.environ.get("CRAWLER_SLOW_MO", "50"))  # ms between actions
    NAVIGATION_TIMEOUT = int(os.environ.get("CRAWLER_NAV_TIMEOUT", "60000"))  # ms
    PAGE_LOAD_WAIT = int(os.environ.get("CRAWLER_PAGE_WAIT", "8"))  # seconds after navigation

    # Search parameters
    ROUTES = [
        {"origin": "CTU", "destination": "LAX", "origin_cn": "成都", "dest_cn": "洛杉矶",
         "origin_en": "Chengdu", "dest_en": "Los Angeles"},
        {"origin": "PVG", "destination": "LAX", "origin_cn": "上海", "dest_cn": "洛杉矶",
         "origin_en": "Shanghai", "dest_en": "Los Angeles"},
        {"origin": "PVG", "destination": "SFO", "origin_cn": "上海", "dest_cn": "旧金山",
         "origin_en": "Shanghai", "dest_en": "San Francisco"},
        {"origin": "CAN", "destination": "LAX", "origin_cn": "广州", "dest_cn": "洛杉矶",
         "origin_en": "Guangzhou", "dest_en": "Los Angeles"},
        {"origin": "ICN", "destination": "LAX", "origin_cn": "首尔", "dest_cn": "洛杉矶",
         "origin_en": "Seoul", "dest_en": "Los Angeles"},
    ]

    # Date ranges to search
    DATES = []

    @classmethod
    def build_dates(cls):
        """Generate search dates for May-June 2026 and September 2026."""
        dates = []
        # May 2026: 1st, 8th, 15th, 22nd, 29th
        for day in [1, 8, 15, 22, 29]:
            dates.append(f"2026-05-{day:02d}")
        # June 2026: 1st, 8th, 15th, 22nd, 29th
        for day in [1, 8, 15, 22, 29]:
            dates.append(f"2026-06-{day:02d}")
        # September 2026: 1st, 8th, 15th, 22nd, 29th
        for day in [1, 8, 15, 22, 29]:
            dates.append(f"2026-09-{day:02d}")
        cls.DATES = dates
        return dates

    # Output
    OUTPUT_FILE = "D:/claude/flights/ctrip_results.json"

    @classmethod
    def validate(cls):
        """Validate configuration and print warnings."""
        issues = []
        if not cls.CAPTCHA_API_KEY:
            issues.append(
                "CAPTCHA_API_KEY not set. Set it via environment variable.\n"
                "  The crawler will still attempt to scrape, but will fail on CAPTCHA pages.\n"
                "  Sign up at:\n"
                "    - 2Captcha:      https://2captcha.com  ($0.50-2.99/1000 solves)\n"
                "    - Anti-Captcha:  https://anti-captcha.com  ($0.50-2.00/1000)\n"
                "    - CapSolver:     https://capsolver.com  ($0.40-2.00/1000)"
            )
        if not cls.PROXY_URL:
            issues.append(
                "PROXY_URL not set. The crawler will use your direct IP.\n"
                "  For best results with Ctrip, use a Chinese residential proxy.\n"
                "  Recommended providers:\n"
                "    - IPRoyal:    https://iproyal.com  ($1.75/GB, 2.5M China IPs)\n"
                "    - Bright Data: https://brightdata.com  ($5.04/GB+, 72M+ IPs)\n"
                "    - SOAX:       https://soax.com  ($99/mo, 31K China IPs)"
            )
        return issues


# =============================================================================
# CAPTCHA SOLVERS
# =============================================================================

class CaptchaSolver:
    """
    Unified interface for CAPTCHA solving services.
    Supports CapMonster Cloud (primary), 2Captcha (fallback), Anti-Captcha, and CapSolver.
    """

    def __init__(self, service: str, api_key: str):
        self.service = service.lower()
        self.api_key = api_key
        self._solver = None
        self._capmonster_url = os.environ.get("CAPMONSTER_URL", "https://api.capmonster.cloud")
        self._twocaptcha_key = os.environ.get("TWOCAPTCHA_API_KEY", "")

        if not api_key:
            log.warning("No CAPTCHA API key provided. CAPTCHA solving is disabled.")
            return

        if self.service == "capmonster":
            self._init_capmonster()
        elif self.service == "2captcha":
            self._init_2captcha()
        elif self.service == "anticaptcha":
            self._init_anticaptcha()
        elif self.service == "capsolver":
            self._init_capsolver()
        else:
            log.warning(f"Unknown CAPTCHA service: {service}. Using capmonster as default.")
            self.service = "capmonster"
            self._init_capmonster()

    def _init_capmonster(self):
        """Initialize CapMonster Cloud solver."""
        import urllib.request
        log.info(f"CapMonster Cloud solver initialized (endpoint: {self._capmonster_url})")
        # Also initialize 2Captcha as fallback if key available
        if self._twocaptcha_key:
            try:
                from twocaptcha import TwoCaptcha
                self._solver = TwoCaptcha(self._twocaptcha_key)
                log.info("2Captcha fallback solver also initialized")
            except ImportError:
                pass

    def _init_2captcha(self):
        """Initialize 2Captcha solver."""
        try:
            from twocaptcha import TwoCaptcha
            self._solver = TwoCaptcha(self.api_key)
            self._solver.soft_id = 0  # No affiliate tracking
            log.info("2Captcha solver initialized")
        except ImportError:
            log.error("2captcha-python not installed. Run: pip install 2captcha-python")

    def _init_anticaptcha(self):
        """Initialize Anti-Captcha solver."""
        try:
            from anticaptchaofficial.geetestproxyless import geetestProxyless
            self._anticaptcha_module = True
            log.info("Anti-Captcha solver initialized")
        except ImportError:
            log.error("anticaptchaofficial not installed. Run: pip install anticaptchaofficial")
            self._anticaptcha_module = False

    def _init_capsolver(self):
        """Initialize CapSolver."""
        try:
            import capsolver
            capsolver.api_key = self.api_key
            self._capsolver_module = capsolver
            log.info("CapSolver initialized")
        except ImportError:
            log.error("capsolver not installed. Run: pip install capsolver")
            self._capsolver_module = None

    async def solve_geetest(self, gt: str, challenge: str, page_url: str,
                            api_server: str = "api.geetest.com") -> Optional[Dict]:
        """
        Solve a GeeTest v3 slider CAPTCHA.

        Ctrip uses GeeTest for verification. This method sends the CAPTCHA
        parameters to the solving service and returns the solution tokens.

        Args:
            gt: GeeTest public key (found in page JS / initGeetest call)
            challenge: Dynamic challenge value (changes per session)
            page_url: URL of the page with the CAPTCHA
            api_server: GeeTest API server domain

        Returns:
            dict with challenge, validate, seccode keys, or None on failure
        """
        if not self.api_key:
            log.error("Cannot solve CAPTCHA: no API key configured")
            return None

        log.info(f"Solving GeeTest CAPTCHA via {self.service}...")
        log.info(f"  gt={gt[:16]}..., challenge={challenge[:16]}...")

        try:
            if self.service == "capmonster":
                result = await self._solve_geetest_capmonster(gt, challenge, page_url, api_server)
                if result:
                    return result
                # Fallback to 2Captcha
                if self._solver:
                    log.info("CapMonster failed, trying 2Captcha fallback for GeeTest...")
                    return await self._solve_geetest_2captcha(gt, challenge, page_url, api_server)
                return None
            elif self.service == "2captcha":
                return await self._solve_geetest_2captcha(gt, challenge, page_url, api_server)
            elif self.service == "anticaptcha":
                return await self._solve_geetest_anticaptcha(gt, challenge, page_url, api_server)
            elif self.service == "capsolver":
                return await self._solve_geetest_capsolver(gt, challenge, page_url, api_server)
        except Exception as e:
            log.error(f"CAPTCHA solving failed: {e}")
            return None

    async def _solve_geetest_capmonster(self, gt, challenge, page_url, api_server):
        """Solve GeeTest via CapMonster Cloud API."""
        import urllib.request
        import urllib.error

        log.info("Solving GeeTest via CapMonster Cloud...")
        loop = asyncio.get_event_loop()

        def _create_and_poll():
            # Create task
            req_body = json.dumps({
                "clientKey": self.api_key,
                "task": {
                    "type": "GeeTestTaskProxyless",
                    "websiteURL": page_url,
                    "gt": gt,
                    "challenge": challenge,
                    "geetestApiServerSubdomain": api_server,
                }
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{self._capmonster_url}/createTask",
                data=req_body,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if data.get("errorId", 0) != 0:
                    log.error(f"CapMonster createTask error: {data.get('errorCode')}")
                    return None
                task_id = data.get("taskId")
                log.info(f"CapMonster GeeTest task created: {task_id}")
            except Exception as e:
                log.error(f"CapMonster createTask failed: {e}")
                return None

            # Poll for result
            poll_body = json.dumps({
                "clientKey": self.api_key,
                "taskId": task_id,
            }).encode("utf-8")
            for _ in range(40):
                time.sleep(3)
                poll_req = urllib.request.Request(
                    f"{self._capmonster_url}/getTaskResult",
                    data=poll_body,
                    headers={"Content-Type": "application/json"},
                )
                try:
                    with urllib.request.urlopen(poll_req, timeout=30) as resp:
                        result = json.loads(resp.read().decode("utf-8"))
                    if result.get("errorId", 0) != 0:
                        log.error(f"CapMonster poll error: {result.get('errorCode')}")
                        return None
                    if result.get("status") == "ready":
                        log.info("CapMonster GeeTest solved successfully")
                        return result.get("solution", {})
                except Exception as e:
                    log.error(f"CapMonster poll failed: {e}")
                    return None
            log.error("CapMonster GeeTest timed out")
            return None

        return await loop.run_in_executor(None, _create_and_poll)

    async def _solve_geetest_2captcha(self, gt, challenge, page_url, api_server):
        """Solve GeeTest via 2Captcha."""
        if not self._solver:
            return None
        # Run in executor since 2captcha SDK is synchronous
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._solver.geetest(
                gt=gt,
                challenge=challenge,
                url=page_url,
                apiServer=api_server,
            )
        )
        log.info(f"2Captcha GeeTest solved successfully")
        return result.get("code", result) if isinstance(result, dict) else result

    async def _solve_geetest_anticaptcha(self, gt, challenge, page_url, api_server):
        """Solve GeeTest via Anti-Captcha."""
        if not getattr(self, '_anticaptcha_module', False):
            return None
        from anticaptchaofficial.geetestproxyless import geetestProxyless
        solver = geetestProxyless()
        solver.set_key(self.api_key)
        solver.set_website_url(page_url)
        solver.set_gt_key(gt)
        solver.set_challenge_key(challenge)
        solver.set_js_api_domain(api_server)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, solver.solve_and_return_solution)
        if result:
            log.info("Anti-Captcha GeeTest solved successfully")
            return result
        log.error(f"Anti-Captcha error: {solver.error_code}")
        return None

    async def _solve_geetest_capsolver(self, gt, challenge, page_url, api_server):
        """Solve GeeTest via CapSolver."""
        if not getattr(self, '_capsolver_module', None):
            return None
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._capsolver_module.solve({
                "type": "GeeTestTaskProxyLess",
                "websiteURL": page_url,
                "gt": gt,
                "challenge": challenge,
                "geetestApiServerSubdomain": api_server,
            })
        )
        log.info("CapSolver GeeTest solved successfully")
        return result

    async def solve_image_captcha(self, image_base64: str) -> Optional[str]:
        """
        Solve an image-based CAPTCHA (text recognition).

        Args:
            image_base64: Base64-encoded CAPTCHA image

        Returns:
            Recognized text string, or None on failure
        """
        if not self.api_key:
            return None

        log.info(f"Solving image CAPTCHA via {self.service}...")

        try:
            if self.service == "capmonster":
                # Primary: CapMonster Cloud
                import urllib.request
                loop = asyncio.get_event_loop()
                def _solve_image_capmonster():
                    req_body = json.dumps({
                        "clientKey": self.api_key,
                        "task": {"type": "ImageToTextTask", "body": image_base64}
                    }).encode("utf-8")
                    req = urllib.request.Request(
                        f"{self._capmonster_url}/createTask",
                        data=req_body,
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    if data.get("errorId", 0) != 0:
                        return None
                    task_id = data.get("taskId")
                    poll_body = json.dumps({"clientKey": self.api_key, "taskId": task_id}).encode("utf-8")
                    for _ in range(40):
                        time.sleep(3)
                        poll_req = urllib.request.Request(
                            f"{self._capmonster_url}/getTaskResult",
                            data=poll_body,
                            headers={"Content-Type": "application/json"},
                        )
                        with urllib.request.urlopen(poll_req, timeout=30) as resp:
                            result = json.loads(resp.read().decode("utf-8"))
                        if result.get("status") == "ready":
                            return result.get("solution", {}).get("text")
                    return None
                text = await loop.run_in_executor(None, _solve_image_capmonster)
                if text:
                    log.info(f"CapMonster image CAPTCHA solved: {text}")
                    return text
                # Fallback to 2Captcha
                if self._solver:
                    log.info("CapMonster image failed, trying 2Captcha fallback...")
                    result = await loop.run_in_executor(
                        None, lambda: self._solver.normal(image_base64)
                    )
                    text = result.get("code", result) if isinstance(result, dict) else result
                    log.info(f"2Captcha image CAPTCHA solved: {text}")
                    return text

            elif self.service == "2captcha" and self._solver:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self._solver.normal(image_base64)
                )
                text = result.get("code", result) if isinstance(result, dict) else result
                log.info(f"Image CAPTCHA solved: {text}")
                return text
        except Exception as e:
            log.error(f"Image CAPTCHA solving failed: {e}")
            return None

    async def solve_slider_captcha(self, bg_image_b64: str, slider_image_b64: str) -> Optional[int]:
        """
        Solve a slider CAPTCHA by determining the X offset.

        Some Ctrip pages use custom slider CAPTCHAs (not GeeTest).
        This sends the background and slider images to the service
        for recognition of the correct slide distance.

        Args:
            bg_image_b64: Base64-encoded background image
            slider_image_b64: Base64-encoded slider piece image

        Returns:
            X offset in pixels, or None on failure
        """
        if not self.api_key:
            return None

        log.info(f"Solving slider CAPTCHA via {self.service}...")

        try:
            if self.service == "2captcha" and self._solver:
                loop = asyncio.get_event_loop()
                # 2Captcha supports slider via coordinates method
                result = await loop.run_in_executor(
                    None,
                    lambda: self._solver.coordinates(bg_image_b64, lang="en")
                )
                if result:
                    log.info(f"Slider CAPTCHA solved: offset={result}")
                    return result
        except Exception as e:
            log.error(f"Slider CAPTCHA solving failed: {e}")
            return None


# =============================================================================
# FLIGHT DATA PARSER
# =============================================================================

class FlightDataParser:
    """
    Parses flight data from intercepted Ctrip/Trip.com API responses.

    Ctrip international search returns data in JSON format via XHR.
    The response structure has evolved; this parser handles multiple formats.
    """

    @staticmethod
    def parse_ctrip_international(data: dict) -> List[Dict]:
        """
        Parse Ctrip international batchSearch response.

        Expected response path: data.flightItineraryList[]
        Each itinerary has: flightSegments[], priceList[], miseryIndex, etc.
        """
        flights = []

        itinerary_list = (
            data.get("data", {}).get("flightItineraryList")
            or data.get("data", {}).get("routeList")
            or data.get("flightItineraryList")
            or []
        )

        for itinerary in itinerary_list:
            try:
                flight_info = FlightDataParser._parse_ctrip_itinerary(itinerary)
                if flight_info:
                    flights.append(flight_info)
            except Exception as e:
                log.debug(f"Failed to parse itinerary: {e}")
                continue

        return flights

    @staticmethod
    def _parse_ctrip_itinerary(itinerary: dict) -> Optional[Dict]:
        """Parse a single Ctrip flight itinerary."""
        segments = (
            itinerary.get("flightSegments")
            or itinerary.get("legs")
            or []
        )
        if not segments:
            return None

        # Price extraction - try multiple paths
        price = None
        currency = "CNY"

        price_list = itinerary.get("priceList") or []
        if price_list:
            # Find economy class price
            for p in price_list:
                cabin = p.get("cabin", {})
                if cabin.get("cabinClass") in ("Y", "S", "Economy", None):
                    adt_price = p.get("adultPrice") or p.get("price") or p.get("salePrice")
                    if adt_price:
                        price = adt_price
                        currency = p.get("currency", "CNY")
                        break
            if price is None and price_list:
                first_price = price_list[0]
                price = first_price.get("adultPrice") or first_price.get("price")
                currency = first_price.get("currency", "CNY")

        # Also check characteristic/lowestPrice path (older format)
        if price is None:
            for seg in segments:
                char = seg.get("characteristic", {})
                lp = char.get("lowestPrice")
                if lp:
                    price = lp
                    break

        # Parse segments for flight details
        all_flight_numbers = []
        all_airlines = []
        total_duration_min = 0
        stops = 0
        dep_time = None
        arr_time = None
        dep_airport = None
        arr_airport = None

        for seg_idx, segment in enumerate(segments):
            flight_list = segment.get("flightList") or segment.get("flights") or []
            if not flight_list:
                # The segment itself might be the flight
                flight_list = [segment]

            for f_idx, flight in enumerate(flight_list):
                fn = (
                    flight.get("flightNumber")
                    or flight.get("flightNo")
                    or f"{flight.get('airlineCode', '??')}{flight.get('number', '?')}"
                )
                all_flight_numbers.append(fn)

                airline_name = (
                    flight.get("airlineName")
                    or flight.get("airlineNameEn")
                    or flight.get("marketAirlineName")
                    or flight.get("airlineCode", "")
                )
                if airline_name and airline_name not in all_airlines:
                    all_airlines.append(airline_name)

                # Duration
                dur = flight.get("duration") or flight.get("flightDuration") or 0
                if isinstance(dur, str):
                    # Parse "12h30m" format
                    h = re.search(r"(\d+)h", dur)
                    m = re.search(r"(\d+)m", dur)
                    dur = (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)
                total_duration_min += dur

                # Departure info (first flight in first segment)
                if seg_idx == 0 and f_idx == 0:
                    dep_info = flight.get("departureAirportInfo") or flight.get("departure") or {}
                    dep_time = (
                        flight.get("departureDate")
                        or flight.get("departureDateTime")
                        or dep_info.get("dateTime")
                        or dep_info.get("at")
                    )
                    dep_airport = (
                        dep_info.get("airportTlc")
                        or dep_info.get("airportCode")
                        or dep_info.get("iataCode")
                        or flight.get("departureAirport", "")
                    )

                # Arrival info (last flight in last segment)
                arr_info = flight.get("arrivalAirportInfo") or flight.get("arrival") or {}
                arr_time = (
                    flight.get("arrivalDate")
                    or flight.get("arrivalDateTime")
                    or arr_info.get("dateTime")
                    or arr_info.get("at")
                )
                arr_airport = (
                    arr_info.get("airportTlc")
                    or arr_info.get("airportCode")
                    or arr_info.get("iataCode")
                    or flight.get("arrivalAirport", "")
                )

            if len(flight_list) > 1:
                stops += len(flight_list) - 1
            if seg_idx > 0:
                stops += 1

        # Transfer count from itinerary metadata
        transfer_count = itinerary.get("transferCount") or itinerary.get("stopCount")
        if transfer_count is not None:
            stops = transfer_count

        # Format duration
        if total_duration_min > 0:
            hours = total_duration_min // 60
            mins = total_duration_min % 60
            duration_str = f"{hours}h{mins:02d}m"
        else:
            duration_str = itinerary.get("totalDuration", "N/A")
            if isinstance(duration_str, int):
                hours = duration_str // 60
                mins = duration_str % 60
                duration_str = f"{hours}h{mins:02d}m"

        return {
            "flight_numbers": all_flight_numbers,
            "flight_number": " / ".join(all_flight_numbers),
            "airlines": all_airlines,
            "airline": " / ".join(all_airlines) if all_airlines else "Unknown",
            "departure_airport": dep_airport,
            "arrival_airport": arr_airport,
            "departure_time": dep_time,
            "arrival_time": arr_time,
            "duration": duration_str,
            "duration_minutes": total_duration_min if total_duration_min > 0 else None,
            "stops": stops,
            "price": price,
            "currency": currency,
            "source": "Ctrip International",
        }

    @staticmethod
    def parse_tripcom_response(data: dict) -> List[Dict]:
        """
        Parse Trip.com flight search response.
        Trip.com uses different field names than Ctrip Chinese site.
        """
        flights = []

        flight_list = (
            data.get("data", {}).get("flightItineraryList")
            or data.get("data", {}).get("flights")
            or data.get("flightSearch", {}).get("flights")
            or []
        )

        for item in flight_list:
            try:
                # Trip.com format
                segments = item.get("flightSegments") or item.get("segments") or []
                price_info = item.get("priceList", [{}])[0] if item.get("priceList") else {}

                all_fns = []
                for seg in segments:
                    for fl in seg.get("flightList", [seg]):
                        fn = fl.get("flightNumber") or fl.get("flightNo", "")
                        if fn:
                            all_fns.append(fn)

                flights.append({
                    "flight_number": " / ".join(all_fns),
                    "airline": item.get("airlineName", ""),
                    "price": price_info.get("adultPrice") or price_info.get("price"),
                    "currency": price_info.get("currency", "USD"),
                    "stops": item.get("transferCount", 0),
                    "duration": item.get("totalDuration", "N/A"),
                    "source": "Trip.com",
                })
            except Exception:
                continue

        return flights


# =============================================================================
# MAIN CRAWLER
# =============================================================================

class CtripCrawler:
    """
    Main crawler class using Playwright with stealth and CAPTCHA solving.

    Strategy (adapted from Suysker/Ctrip-Crawler):
    1. Launch browser with stealth patches to avoid detection
    2. Navigate to Ctrip/Trip.com search page
    3. Set up network interception to capture flight API responses
    4. If CAPTCHA appears, solve it via external service
    5. Parse intercepted API responses for flight data
    6. Save structured results to JSON
    """

    # Known API endpoints that return flight data
    CTRIP_API_PATTERNS = [
        "search/api/search/batchSearch",
        "international/search/api",
        "itinerary/api/12808/products",
        "flightListSearch",
        "search/api/flightlist",
        "/search/",  # Broad match for search-related responses
    ]

    TRIPCOM_API_PATTERNS = [
        "graphql/ctFlightDetailSearch",
        "soa2/27015/flightListSearch",
        "flights/graphql",
        "/restapi/soa2/",
    ]

    def __init__(self, config: Config = None):
        self.config = config or Config
        self.config.build_dates()
        self.captcha_solver = CaptchaSolver(
            self.config.CAPTCHA_SERVICE,
            self.config.CAPTCHA_API_KEY,
        )
        self.all_results = []
        self.intercepted_data = []
        self._browser = None
        self._context = None

    async def run(self):
        """Execute the full crawl across all routes and dates."""
        log.info("=" * 70)
        log.info("CTRIP INTERNATIONAL FLIGHT CRAWLER")
        log.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log.info(f"CAPTCHA Service: {self.config.CAPTCHA_SERVICE}")
        log.info(f"CAPTCHA Key: {'configured' if self.config.CAPTCHA_API_KEY else 'NOT SET'}")
        log.info(f"Proxy: {self.config.PROXY_URL[:30] + '...' if self.config.PROXY_URL else 'none'}")
        log.info(f"Headless: {self.config.HEADLESS}")
        log.info(f"Routes: {len(self.config.ROUTES)}")
        log.info(f"Dates: {len(self.config.DATES)}")
        log.info("=" * 70)

        issues = self.config.validate()
        for issue in issues:
            log.warning(issue)

        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            await self._launch_browser(p)

            try:
                # Try Ctrip International first
                log.info("\n--- PHASE 1: Ctrip International (flights.ctrip.com) ---")
                await self._crawl_ctrip_international()

                # If insufficient results, try Trip.com as fallback
                if len(self.all_results) < 5:
                    log.info("\n--- PHASE 2: Trip.com Fallback (www.trip.com) ---")
                    await self._crawl_tripcom()

            finally:
                await self._close_browser()

        # Save results
        self._save_results()
        self._print_summary()

        return self.all_results

    async def _launch_browser(self, playwright):
        """Launch Playwright browser with stealth and proxy settings."""
        from playwright_stealth import Stealth

        launch_args = {
            "headless": self.config.HEADLESS,
            "slow_mo": self.config.SLOW_MO,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-web-security",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--lang=zh-CN,zh,en-US,en",
            ],
        }

        # Proxy configuration
        proxy_config = None
        if self.config.PROXY_URL:
            proxy_parts = self.config.PROXY_URL
            proxy_config = {"server": proxy_parts}
            # Parse user:pass if present
            if "@" in proxy_parts:
                auth_part = proxy_parts.split("://")[1].split("@")[0]
                server_part = proxy_parts.split("://")[0] + "://" + proxy_parts.split("@")[1]
                user, password = auth_part.split(":")
                proxy_config = {
                    "server": server_part,
                    "username": user,
                    "password": password,
                }
            launch_args["proxy"] = proxy_config

        self._browser = await playwright.chromium.launch(**launch_args)

        # Create context with realistic viewport and user agent
        context_opts = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "geolocation": {"latitude": 30.5728, "longitude": 104.0668},  # Chengdu
            "permissions": ["geolocation"],
            "extra_http_headers": {
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        }

        self._context = await self._browser.new_context(**context_opts)

        # Apply stealth to each new page
        # playwright-stealth v2 uses Stealth class
        self._stealth = Stealth()

        log.info("Browser launched with stealth mode")

    async def _close_browser(self):
        """Clean up browser resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        log.info("Browser closed")

    async def _crawl_ctrip_international(self):
        """
        Crawl Ctrip international flight search.

        Strategy:
        1. Navigate to the search page URL directly (pre-filled with route/date)
        2. Intercept XHR responses containing flight data
        3. Handle CAPTCHA if triggered
        4. Extract and parse flight listings
        """
        for route in self.config.ROUTES:
            # Search a subset of dates to avoid rate limiting
            n = len(self.config.DATES)
            if n <= 3:
                sample_dates = self.config.DATES
            else:
                indices = [0, min(4, n - 1), min(10, n - 1)]
                sample_dates = list(dict.fromkeys(self.config.DATES[i] for i in indices))
            for date in sample_dates:
                try:
                    flights = await self._search_ctrip_route(route, date)
                    if flights:
                        for f in flights:
                            f["search_route"] = f"{route['origin']}-{route['destination']}"
                            f["search_date"] = date
                        self.all_results.extend(flights)
                        log.info(f"  Found {len(flights)} flights for "
                                 f"{route['origin']}-{route['destination']} on {date}")
                    else:
                        log.info(f"  No flights found for "
                                 f"{route['origin']}-{route['destination']} on {date}")

                    # Rate limiting
                    await asyncio.sleep(3)

                except Exception as e:
                    log.error(f"  Error crawling {route['origin']}-{route['destination']} "
                              f"on {date}: {e}")
                    await asyncio.sleep(5)

    async def _search_ctrip_route(self, route: dict, date: str) -> List[Dict]:
        """
        Search a single route/date on Ctrip International.

        The URL format is:
        https://flights.ctrip.com/international/search/oneway-{origin}-{dest}
          ?depdate={date}&cabin=y&adult=1&child=0&infant=0

        For round-trips:
        https://flights.ctrip.com/international/search/round-{origin}-{dest}
          ?depdate={date}&rdate={return_date}&cabin=y&adult=1&child=0&infant=0
        """
        origin = route["origin"].lower()
        dest = route["destination"].lower()
        search_url = (
            f"https://flights.ctrip.com/international/search/"
            f"oneway-{origin}-{dest}"
            f"?depdate={date}&cabin=y&adult=1&child=0&infant=0"
        )

        log.info(f"Searching Ctrip: {route['origin']}-{route['destination']} on {date}")

        page = await self._context.new_page()
        await self._stealth.apply_stealth_async(page)

        # Set up response interception
        captured_flights = []
        captcha_detected = False
        captcha_params = {}

        async def handle_response(response):
            nonlocal captured_flights, captcha_detected, captcha_params
            url = response.url
            try:
                # Check for flight data responses
                if any(pattern in url for pattern in self.CTRIP_API_PATTERNS):
                    if response.status == 200:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct or "javascript" in ct:
                            body = await response.text()
                            try:
                                data = json.loads(body)

                                # Check for CAPTCHA gate
                                context = data.get("data", {}).get("context", {})
                                if context.get("showAuthCode"):
                                    captcha_detected = True
                                    log.warning("CAPTCHA detected in API response")
                                    return

                                # Parse flight data
                                flights = FlightDataParser.parse_ctrip_international(data)
                                if flights:
                                    captured_flights.extend(flights)
                                    log.info(f"  Intercepted {len(flights)} flights from {url[:80]}...")

                                # Also store raw data for debugging
                                self.intercepted_data.append({
                                    "url": url[:200],
                                    "flight_count": len(flights),
                                    "timestamp": datetime.now().isoformat(),
                                })
                            except json.JSONDecodeError:
                                pass

                # Check for GeeTest CAPTCHA parameters in responses
                if "geetest" in url.lower() or "captcha" in url.lower():
                    try:
                        body = await response.text()
                        data = json.loads(body)
                        if "gt" in data and "challenge" in data:
                            captcha_params = {
                                "gt": data["gt"],
                                "challenge": data["challenge"],
                                "api_server": data.get("api_server", "api.geetest.com"),
                            }
                            log.info(f"  GeeTest params captured: gt={data['gt'][:16]}...")
                    except Exception:
                        pass

            except Exception as e:
                log.debug(f"  Response handler error for {url[:50]}: {e}")

        page.on("response", handle_response)

        try:
            # Navigate to search page
            await page.goto(search_url, timeout=self.config.NAVIGATION_TIMEOUT,
                            wait_until="domcontentloaded")

            # Wait for page to load and API calls to complete
            await asyncio.sleep(self.config.PAGE_LOAD_WAIT)

            # Check for CAPTCHA elements in the DOM
            captcha_element = await page.query_selector(
                ".verification-code, .geetest_popup, .geetest_panel, "
                ".captcha-container, [class*='captcha'], [class*='verify'], "
                "#gc-box, .alert-title"
            )

            if captcha_element or captcha_detected:
                log.warning("CAPTCHA page detected! Attempting to solve...")
                solved = await self._handle_captcha(page, search_url, captcha_params)
                if solved:
                    # Wait for page to reload with results
                    await asyncio.sleep(self.config.PAGE_LOAD_WAIT)
                else:
                    log.error("CAPTCHA solving failed. Skipping this search.")

            # Try to extract flights from the page DOM as fallback
            if not captured_flights:
                dom_flights = await self._extract_flights_from_dom(page, route, date)
                if dom_flights:
                    captured_flights.extend(dom_flights)

            # Wait a bit more for any late XHR responses
            await asyncio.sleep(3)

        except Exception as e:
            log.error(f"Navigation error: {e}")
        finally:
            await page.close()

        return captured_flights

    async def _handle_captcha(self, page, page_url: str,
                               captcha_params: dict = None) -> bool:
        """
        Handle CAPTCHA on the page.

        Supports:
        1. GeeTest slider CAPTCHA (most common on Ctrip)
        2. Image text CAPTCHA
        3. Custom slider CAPTCHA
        """
        if not self.config.CAPTCHA_API_KEY:
            log.error("Cannot solve CAPTCHA: CAPTCHA_API_KEY not configured")
            return False

        # Try to extract GeeTest parameters from the page
        if not captcha_params:
            captcha_params = await self._extract_geetest_params(page)

        if captcha_params and captcha_params.get("gt"):
            return await self._solve_geetest_on_page(page, page_url, captcha_params)

        # Try image CAPTCHA
        captcha_img = await page.query_selector(
            "img.captcha-image, img[class*='captcha'], "
            ".verification-code img, #captcha-img"
        )
        if captcha_img:
            return await self._solve_image_captcha_on_page(page, captcha_img)

        # Try slider CAPTCHA (non-GeeTest)
        slider = await page.query_selector(
            ".slider-container, .slide-verify, [class*='slider']"
        )
        if slider:
            return await self._solve_slider_on_page(page, slider)

        log.warning("Could not identify CAPTCHA type on page")
        return False

    async def _extract_geetest_params(self, page) -> dict:
        """
        Extract GeeTest initialization parameters from the page.

        GeeTest is typically initialized via:
          initGeetest({ gt: "...", challenge: "...", ... }, handler)
        or via an API call that returns the params.
        """
        try:
            # Method 1: Look for GeeTest params in page JS
            params = await page.evaluate("""
                () => {
                    // Check global variables
                    if (window.geetestParams) return window.geetestParams;
                    if (window.gt) return { gt: window.gt, challenge: window.challenge };

                    // Check data attributes on elements
                    const el = document.querySelector('[data-gt]');
                    if (el) {
                        return {
                            gt: el.getAttribute('data-gt'),
                            challenge: el.getAttribute('data-challenge'),
                            api_server: el.getAttribute('data-api-server') || 'api.geetest.com',
                        };
                    }

                    // Check for GeeTest container
                    const container = document.querySelector('.geetest_holder, #geetest-box');
                    if (container) {
                        // GeeTest stores params in its own object
                        const scripts = document.querySelectorAll('script');
                        for (const script of scripts) {
                            const text = script.textContent || '';
                            const gtMatch = text.match(/gt['"\\s]*:['"\\s]*([a-f0-9]{32})/);
                            const challengeMatch = text.match(/challenge['"\\s]*:['"\\s]*([a-f0-9]{32})/);
                            if (gtMatch && challengeMatch) {
                                return {
                                    gt: gtMatch[1],
                                    challenge: challengeMatch[1],
                                    api_server: 'api.geetest.com',
                                };
                            }
                        }
                    }

                    return {};
                }
            """)

            if params and params.get("gt"):
                log.info(f"GeeTest params extracted from page: gt={params['gt'][:16]}...")
                return params

        except Exception as e:
            log.debug(f"Failed to extract GeeTest params from JS: {e}")

        return {}

    async def _solve_geetest_on_page(self, page, page_url: str,
                                      captcha_params: dict) -> bool:
        """Solve GeeTest CAPTCHA and inject the solution into the page."""
        solution = await self.captcha_solver.solve_geetest(
            gt=captcha_params["gt"],
            challenge=captcha_params["challenge"],
            page_url=page_url,
            api_server=captcha_params.get("api_server", "api.geetest.com"),
        )

        if not solution:
            return False

        # Inject solution into the page
        try:
            # The solution contains challenge, validate, seccode
            if isinstance(solution, dict):
                challenge = solution.get("geetest_challenge", solution.get("challenge", ""))
                validate = solution.get("geetest_validate", solution.get("validate", ""))
                seccode = solution.get("geetest_seccode", solution.get("seccode", ""))
            else:
                # Some solvers return a string; try to parse it
                challenge = str(solution)
                validate = ""
                seccode = ""

            await page.evaluate(f"""
                () => {{
                    // Set GeeTest validation fields
                    const inputs = document.querySelectorAll('input');
                    for (const input of inputs) {{
                        const name = input.name || input.id || '';
                        if (name.includes('challenge')) input.value = '{challenge}';
                        if (name.includes('validate')) input.value = '{validate}';
                        if (name.includes('seccode')) input.value = '{seccode}';
                    }}

                    // Try to trigger the GeeTest callback
                    if (window.geetestCallback) {{
                        window.geetestCallback({{
                            geetest_challenge: '{challenge}',
                            geetest_validate: '{validate}',
                            geetest_seccode: '{seccode}',
                        }});
                    }}

                    // Try clicking any submit/verify button
                    const submitBtn = document.querySelector(
                        '.geetest_commit, .verify-btn, [class*="submit"], button[type="submit"]'
                    );
                    if (submitBtn) submitBtn.click();
                }}
            """)

            log.info("GeeTest solution injected into page")
            await asyncio.sleep(3)
            return True

        except Exception as e:
            log.error(f"Failed to inject GeeTest solution: {e}")
            return False

    async def _solve_image_captcha_on_page(self, page, captcha_img) -> bool:
        """Solve image text CAPTCHA and enter the result."""
        try:
            # Screenshot the captcha image
            img_bytes = await captcha_img.screenshot()
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")

            # Solve via API
            text = await self.captcha_solver.solve_image_captcha(img_b64)
            if not text:
                return False

            # Find the input field and enter the solution
            input_field = await page.query_selector(
                "input.captcha-input, input[class*='captcha'], "
                "input[name*='captcha'], input[name*='code'], "
                "input[placeholder*='code'], input[placeholder*='captcha']"
            )
            if input_field:
                await input_field.fill(text)
                # Click submit
                submit_btn = await page.query_selector(
                    "button.submit, button[type='submit'], .captcha-submit, "
                    "[class*='submit'], [class*='verify']"
                )
                if submit_btn:
                    await submit_btn.click()
                else:
                    await input_field.press("Enter")
                log.info(f"Image CAPTCHA solved and submitted: {text}")
                await asyncio.sleep(3)
                return True

        except Exception as e:
            log.error(f"Image CAPTCHA handling failed: {e}")
        return False

    async def _solve_slider_on_page(self, page, slider_el) -> bool:
        """
        Attempt to solve a slider CAPTCHA by simulating mouse drag.
        This is a simpler approach for non-GeeTest sliders.
        """
        try:
            # Get slider element bounds
            box = await slider_el.bounding_box()
            if not box:
                return False

            # Take screenshot of the background for API solving
            bg_el = await page.query_selector(
                ".slider-bg, .slide-verify-bg, [class*='slider-bg']"
            )
            if bg_el:
                bg_bytes = await bg_el.screenshot()
                bg_b64 = base64.b64encode(bg_bytes).decode("utf-8")
                slider_bytes = await slider_el.screenshot()
                slider_b64 = base64.b64encode(slider_bytes).decode("utf-8")

                offset = await self.captcha_solver.solve_slider_captcha(bg_b64, slider_b64)
                if offset:
                    # Simulate human-like drag
                    start_x = box["x"] + 10
                    start_y = box["y"] + box["height"] / 2
                    await page.mouse.move(start_x, start_y)
                    await page.mouse.down()
                    # Move in small steps to simulate human behavior
                    target_x = start_x + offset
                    steps = 20
                    for i in range(steps):
                        x = start_x + (target_x - start_x) * (i + 1) / steps
                        y = start_y + (2 if i % 2 == 0 else -2)  # slight vertical wobble
                        await page.mouse.move(x, y)
                        await asyncio.sleep(0.02)
                    await page.mouse.up()
                    log.info(f"Slider dragged to offset {offset}")
                    await asyncio.sleep(2)
                    return True

        except Exception as e:
            log.error(f"Slider CAPTCHA handling failed: {e}")
        return False

    async def _extract_flights_from_dom(self, page, route: dict,
                                         date: str) -> List[Dict]:
        """
        Fallback: extract flight data directly from the page DOM.
        Used when XHR interception doesn't capture the data.
        """
        flights = []

        try:
            # Wait for flight list to appear
            await page.wait_for_selector(
                ".flight-list, .flight-item, [class*='flight'], "
                "[class*='FlightItem'], .search-result",
                timeout=10000,
            )

            # Extract flight cards
            flight_cards = await page.query_selector_all(
                ".flight-item, [class*='FlightItem'], .search-result-item, "
                "[class*='flight-card'], [class*='flightCard']"
            )

            for card in flight_cards[:20]:  # Limit to 20 results
                try:
                    flight_info = await self._parse_flight_card(card)
                    if flight_info:
                        flight_info["source"] = "Ctrip DOM"
                        flight_info["search_route"] = f"{route['origin']}-{route['destination']}"
                        flight_info["search_date"] = date
                        flights.append(flight_info)
                except Exception:
                    continue

        except Exception as e:
            log.debug(f"DOM extraction failed (may be normal for CAPTCHA pages): {e}")

        return flights

    async def _parse_flight_card(self, card) -> Optional[Dict]:
        """Parse a single flight card element from the DOM."""
        try:
            # Extract text content from common flight card elements
            text = await card.inner_text()
            if not text or len(text) < 10:
                return None

            # Try to find structured data
            flight_number = ""
            airline = ""
            price = None
            departure = ""
            arrival = ""
            duration = ""
            stops = 0

            # Flight number (e.g., "3U8695", "CZ327", "MU583")
            fn_match = re.search(r'\b([A-Z]{2}\d{3,4})\b', text)
            if fn_match:
                flight_number = fn_match.group(1)

            # Price (Chinese yuan or USD)
            price_match = re.search(r'[¥$]\s*(\d[\d,]+)', text)
            if price_match:
                price = int(price_match.group(1).replace(",", ""))

            # Time pattern (HH:MM)
            times = re.findall(r'(\d{2}:\d{2})', text)
            if len(times) >= 2:
                departure = times[0]
                arrival = times[1]

            # Duration pattern
            dur_match = re.search(r'(\d+)[hH]\s*(\d+)?[mM]?', text)
            if dur_match:
                h = dur_match.group(1)
                m = dur_match.group(2) or "0"
                duration = f"{h}h{int(m):02d}m"

            # Stops
            if "nonstop" in text.lower() or "direct" in text.lower() or "直飞" in text:
                stops = 0
            elif re.search(r'[12]\s*stop|[12]\s*转', text):
                stop_match = re.search(r'([12])', text)
                stops = int(stop_match.group(1)) if stop_match else 1

            if flight_number or price:
                return {
                    "flight_number": flight_number,
                    "airline": airline,
                    "price": price,
                    "currency": "CNY",
                    "departure_time": departure,
                    "arrival_time": arrival,
                    "duration": duration,
                    "stops": stops,
                }

        except Exception:
            pass
        return None

    async def _crawl_tripcom(self):
        """
        Crawl Trip.com as a fallback for international flights.

        Trip.com URL format:
        https://www.trip.com/flights/{from}-to-{to}/tickets-{from}-{to}
          ?dcity={from}&acity={to}&ddate={date}&flighttype=ow
        """
        for route in self.config.ROUTES[:3]:  # Limit fallback searches
            date = self.config.DATES[0]  # Just check one date
            try:
                flights = await self._search_tripcom_route(route, date)
                if flights:
                    self.all_results.extend(flights)
                    log.info(f"  Trip.com: {len(flights)} flights for "
                             f"{route['origin']}-{route['destination']}")
                await asyncio.sleep(5)
            except Exception as e:
                log.error(f"  Trip.com error: {e}")

    async def _search_tripcom_route(self, route: dict, date: str) -> List[Dict]:
        """Search a single route on Trip.com."""
        origin_en = route["origin_en"].lower().replace(" ", "-")
        dest_en = route["dest_en"].lower().replace(" ", "-")
        origin = route["origin"].lower()
        dest = route["destination"].lower()

        search_url = (
            f"https://www.trip.com/flights/{origin_en}-to-{dest_en}/"
            f"tickets-{origin}-{dest}"
            f"?dcity={origin}&acity={dest}&ddate={date}&flighttype=ow"
        )

        log.info(f"Searching Trip.com: {route['origin']}-{route['destination']} on {date}")

        page = await self._context.new_page()
        await self._stealth.apply_stealth_async(page)

        captured_flights = []

        async def handle_response(response):
            nonlocal captured_flights
            url = response.url
            if any(p in url for p in self.TRIPCOM_API_PATTERNS):
                try:
                    if response.status == 200:
                        body = await response.text()
                        data = json.loads(body)
                        flights = FlightDataParser.parse_tripcom_response(data)
                        if flights:
                            for f in flights:
                                f["search_route"] = f"{route['origin']}-{route['destination']}"
                                f["search_date"] = date
                            captured_flights.extend(flights)
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            await page.goto(search_url, timeout=self.config.NAVIGATION_TIMEOUT,
                            wait_until="domcontentloaded")
            await asyncio.sleep(self.config.PAGE_LOAD_WAIT + 2)
        except Exception as e:
            log.error(f"Trip.com navigation error: {e}")
        finally:
            await page.close()

        return captured_flights

    def _save_results(self):
        """Save all collected results to JSON."""
        output = {
            "crawl_timestamp": datetime.now().isoformat(),
            "crawler_version": "1.0.0",
            "config": {
                "captcha_service": self.config.CAPTCHA_SERVICE,
                "captcha_key_set": bool(self.config.CAPTCHA_API_KEY),
                "proxy_set": bool(self.config.PROXY_URL),
                "headless": self.config.HEADLESS,
                "routes_searched": [
                    f"{r['origin']}-{r['destination']}" for r in self.config.ROUTES
                ],
                "dates_searched": self.config.DATES,
            },
            "results_count": len(self.all_results),
            "results": self.all_results,
            "intercepted_api_calls": self.intercepted_data,
            "captcha_service_info": {
                "2captcha": {
                    "signup_url": "https://2captcha.com",
                    "pricing": "$0.50-$2.99 per 1000 solves",
                    "python_sdk": "pip install 2captcha-python",
                    "geetest_rate": "$1.45/1000 (reduced from $2.99 in May 2025)",
                    "env_var": "CAPTCHA_API_KEY",
                },
                "anticaptcha": {
                    "signup_url": "https://anti-captcha.com",
                    "pricing": "$0.50-$2.00 per 1000 solves",
                    "python_sdk": "pip install anticaptchaofficial",
                    "env_var": "CAPTCHA_API_KEY",
                },
                "capsolver": {
                    "signup_url": "https://capsolver.com",
                    "pricing": "$0.40-$2.00 per 1000 solves",
                    "python_sdk": "pip install capsolver",
                    "geetest_rate": "$0.80/1000",
                    "env_var": "CAPTCHA_API_KEY",
                    "note": "Fastest solver (1-5 seconds average)",
                },
            },
            "proxy_service_info": {
                "iproyal": {
                    "url": "https://iproyal.com",
                    "china_ips": "2,532,825+",
                    "pricing": "$1.75/GB residential",
                    "protocols": "HTTP/HTTPS/SOCKS5",
                },
                "brightdata": {
                    "url": "https://brightdata.com",
                    "china_ips": "72M+ (global pool)",
                    "pricing": "From $5.04/GB",
                    "protocols": "HTTP/HTTPS/SOCKS5",
                },
                "soax": {
                    "url": "https://soax.com",
                    "china_ips": "31,800",
                    "pricing": "From $99/month",
                    "protocols": "HTTP/HTTPS/SOCKS5",
                },
            },
        }

        output_path = Path(self.config.OUTPUT_FILE)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)

        log.info(f"\nResults saved to: {output_path}")

    def _print_summary(self):
        """Print summary of crawl results."""
        log.info("\n" + "=" * 70)
        log.info("CRAWL SUMMARY")
        log.info("=" * 70)
        log.info(f"Total flights found: {len(self.all_results)}")

        if self.all_results:
            # Group by route
            by_route = {}
            for f in self.all_results:
                route = f.get("search_route", "Unknown")
                by_route.setdefault(route, []).append(f)

            for route, flights in by_route.items():
                prices = [f["price"] for f in flights if f.get("price")]
                log.info(f"\n  {route}: {len(flights)} flights")
                if prices:
                    log.info(f"    Price range: {min(prices)} - {max(prices)}")
                for f in flights[:5]:
                    fn = f.get("flight_number", "N/A")
                    p = f.get("price", "N/A")
                    d = f.get("duration", "N/A")
                    s = f.get("stops", "N/A")
                    log.info(f"    {fn:<20} {p:>8} {f.get('currency', 'CNY'):<5} "
                             f"{d:<10} {s} stops")

        log.info("\n" + "=" * 70)


# =============================================================================
# AIRLINE DIRECT SITE CRAWLERS
# =============================================================================

class AirlineDirectCrawler:
    """
    Crawlers for Chinese airline direct booking sites.

    These sites typically use:
    - Heavy JavaScript rendering
    - Session-based authentication
    - GeeTest or custom CAPTCHAs
    - Geo-restrictions for some regions
    """

    def __init__(self, captcha_solver: CaptchaSolver):
        self.captcha_solver = captcha_solver

    async def crawl_sichuan_air(self, route: dict, date: str,
                                 playwright) -> List[Dict]:
        """
        Crawl Sichuan Airlines (sichuanair.com / global.sichuanair.com).

        Known routes: TFU-LAX nonstop (3U8695/3U8696), 3x/week
        Site: global.sichuanair.com/en/booking
        Authentication: Session-based, may require CAPTCHA
        CAPTCHA type: Image text CAPTCHA on booking page
        """
        log.info("Attempting Sichuan Airlines direct site...")

        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )

        flights = []
        try:
            page = await context.new_page()
            from playwright_stealth import Stealth
            await Stealth().apply_stealth_async(page)

            search_url = (
                f"https://global.sichuanair.com/en/booking?"
                f"from={route['origin']}&to={route['destination']}"
                f"&depart={date}&adult=1&child=0&infant=0"
            )

            await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(5)

            # Check for CAPTCHA
            captcha_el = await page.query_selector("[class*='captcha'], [class*='verify']")
            if captcha_el:
                log.warning("Sichuan Air: CAPTCHA detected")
                # Would solve here if image CAPTCHA

            # Try to extract any flight data from the page
            content = await page.content()
            if "3U8695" in content or "3U8696" in content or "sichuan" in content.lower():
                log.info("Sichuan Air: Page loaded with flight content")

        except Exception as e:
            log.error(f"Sichuan Air error: {e}")
        finally:
            await browser.close()

        return flights

    async def crawl_china_southern(self, route: dict, date: str,
                                    playwright) -> List[Dict]:
        """
        Crawl China Southern Airlines (csair.com).

        Known routes: CAN-LAX nonstop (CZ327/CZ328)
        Site: www.csair.com/en/ or oversea.csair.com
        Authentication: Session cookies, JS-rendered search
        CAPTCHA type: Slider CAPTCHA on booking flow
        API: NDC Level 4 certified (partner-only)

        Key endpoints discovered:
        - b2c.csair.com/B2C40/ (main booking system)
        - oversea.csair.com/tka/us/en/book/search (overseas booking)
        - csair.com/iplocator/getIpInfo (IP geolocation)
        """
        log.info("Attempting China Southern direct site...")

        flights = []
        # csair.com requires heavy JS rendering and session cookies
        # The overseas booking endpoint (oversea.csair.com) returns 403 for bots
        # The NDC API is partner-only access
        # Best approach: Playwright with stealth + solve any CAPTCHAs

        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )

        try:
            page = await context.new_page()
            from playwright_stealth import Stealth
            await Stealth().apply_stealth_async(page)

            # Try the overseas booking site
            url = (
                f"https://www.csair.com/en/flights/booking?"
                f"flexibleSearch=true&flex=0&tt=OW&c=0&i=0"
                f"&cl=Y&dep={route['origin']}&arr={route['destination']}"
                f"&dd={date}&a=1"
            )

            await page.goto("https://www.csair.com/en/", timeout=30000,
                            wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # Check page content
            content = await page.content()
            if "flight" in content.lower():
                log.info("China Southern: Main page loaded")

        except Exception as e:
            log.error(f"China Southern error: {e}")
        finally:
            await browser.close()

        return flights

    async def crawl_china_eastern(self, route: dict, date: str,
                                   playwright) -> List[Dict]:
        """
        Crawl China Eastern Airlines (ceair.com).

        Known routes: PVG-LAX nonstop (MU583/586), PVG-SFO nonstop (MU589/590)
        Site: us.ceair.com/en/booking-new.html
        Authentication: Cookie-based (global_site_flag=en_US)
        CAPTCHA type: Custom verification on search
        Restrictions: Password-gated for TW, PH, RU, KR, JP regions

        Key endpoints:
        - us.ceair.com/en/booking-new.html (booking page)
        - us.ceair.com/en/flight-list.html?oriCode=PVG&desCode=LAX&... (results)
        """
        log.info("Attempting China Eastern direct site...")

        flights = []
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            extra_http_headers={"Cookie": "global_site_flag=en_US"},
        )

        try:
            page = await context.new_page()
            from playwright_stealth import Stealth
            await Stealth().apply_stealth_async(page)

            await page.goto("https://us.ceair.com/en/booking-new.html",
                            timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            content = await page.content()
            if "booking" in content.lower():
                log.info("China Eastern: Booking page loaded")

        except Exception as e:
            log.error(f"China Eastern error: {e}")
        finally:
            await browser.close()

        return flights


# =============================================================================
# FLIGGY CRAWLER (RESEARCH DOCUMENTATION)
# =============================================================================

class FliggyCrawlerInfo:
    """
    Documentation for Fliggy (fliggy.com) scraping.

    STATUS: NOT FEASIBLE without Alibaba Cloud account

    Fliggy (owned by Alibaba Group) uses the mtop gateway protocol,
    which requires OAuth 2.0 authentication via an Alibaba Cloud account.

    Key findings:
    - Gateway: h5api.m.taobao.com/h5/mtop.trip.flight.search/1.0/
    - Alternative: acs.m.taobao.com/gw/mtop.trip.flight.search/1.0/
    - Auth: OAuth 2.0 via Alibaba Cloud
    - Rate limit: 500 requests/minute
    - The international site (us.fliggytravel.com) redirects away from flight search
    - Requires a Chinese phone number for Alibaba Cloud account registration

    To access Fliggy's flight data:
    1. Register an Alibaba Cloud account (Chinese phone number needed)
    2. Create an app to get OAuth 2.0 credentials
    3. Sign requests with the mtop protocol
    4. The mtop protocol uses: appKey, token, sign (HMAC), data, type, api, v, ttid

    Alternatives:
    - Use Ctrip instead (same flights are listed on both platforms)
    - Use Trip.com (Ctrip's international brand)
    - Fliggy's prices are typically competitive with Ctrip
    """

    @staticmethod
    def get_info() -> dict:
        return {
            "platform": "Fliggy (飞猪)",
            "owner": "Alibaba Group",
            "status": "NOT FEASIBLE without Alibaba Cloud OAuth",
            "auth_requirements": {
                "type": "OAuth 2.0 via Alibaba Cloud",
                "gateway": "h5api.m.taobao.com/h5/mtop.trip.flight.search/1.0/",
                "rate_limit": "500 req/min",
                "requires_chinese_phone": True,
            },
            "captcha_info": {
                "type": "Alibaba NCMS (Non-Critical Mode Security)",
                "slider": "Custom Alibaba slider verification",
                "frequency": "Triggered on suspicious behavior or high request rate",
            },
            "recommendation": (
                "Skip Fliggy. Use Ctrip or Trip.com instead. "
                "The same airlines and similar prices appear on all three platforms. "
                "Ctrip is more accessible for automated scraping."
            ),
        }


# =============================================================================
# ENTRY POINT
# =============================================================================

async def main():
    """Main entry point for the crawler."""
    print("=" * 70)
    print("CTRIP INTERNATIONAL FLIGHT CRAWLER")
    print("with CAPTCHA Solving & Proxy Support")
    print("=" * 70)
    print()
    print("Target Routes: CTU-LAX, PVG-LAX, PVG-SFO, CAN-LAX, ICN-LAX")
    print("Target Dates:  May-June 2026, September 2026")
    print()

    # Check configuration
    issues = Config.validate()
    if issues:
        print("CONFIGURATION WARNINGS:")
        for i, issue in enumerate(issues, 1):
            print(f"\n  {i}. {issue}")
        print()

        if not Config.CAPTCHA_API_KEY:
            print("-" * 70)
            print("QUICK START GUIDE:")
            print("-" * 70)
            print()
            print("1. Sign up for a CAPTCHA solving service:")
            print("   - RECOMMENDED: https://2captcha.com (cheapest, most reliable)")
            print("   - Alternative: https://capsolver.com (fastest)")
            print()
            print("2. Set your API key:")
            print("   Windows CMD:   set CAPTCHA_API_KEY=your_key_here")
            print("   Windows PS:    $env:CAPTCHA_API_KEY='your_key_here'")
            print("   Linux/Mac:     export CAPTCHA_API_KEY=your_key_here")
            print()
            print("3. Optional - Set up a proxy for better results:")
            print("   set PROXY_URL=http://user:pass@proxy.iproyal.com:12321")
            print()
            print("4. Re-run this script:")
            print("   python ctrip_crawler.py")
            print()
            print("Estimated cost for one full crawl (5 routes x 15 dates):")
            print("   - CAPTCHA solving: ~$0.10 (75 solves at $1.45/1000)")
            print("   - Proxy traffic:   ~$0.50 (300MB at $1.75/GB)")
            print("   - Total:           ~$0.60")
            print()

    # Run the crawler
    crawler = CtripCrawler()

    try:
        results = await crawler.run()
    except Exception as e:
        log.error(f"Crawler failed: {e}")
        import traceback
        traceback.print_exc()

        # Save error report
        error_report = {
            "crawl_timestamp": datetime.now().isoformat(),
            "status": "error",
            "error": str(e),
            "results_before_error": crawler.all_results,
            "setup_guide": {
                "step1": "Install dependencies: pip install playwright playwright-stealth 2captcha-python",
                "step2": "Install browser: python -m playwright install chromium",
                "step3": "Set API key: set CAPTCHA_API_KEY=your_2captcha_key",
                "step4": "Optional proxy: set PROXY_URL=http://user:pass@host:port",
                "step5": "Run: python ctrip_crawler.py",
            },
        }
        with open(Config.OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(error_report, f, indent=2, ensure_ascii=False, default=str)
        log.info(f"Error report saved to {Config.OUTPUT_FILE}")

    # Also document Fliggy findings
    fliggy_info = FliggyCrawlerInfo.get_info()
    log.info(f"\nFliggy status: {fliggy_info['status']}")
    log.info(f"Fliggy recommendation: {fliggy_info['recommendation']}")


if __name__ == "__main__":
    asyncio.run(main())
