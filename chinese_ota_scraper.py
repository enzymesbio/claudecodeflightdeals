#!/usr/bin/env python3
"""
Chinese OTA Flight Scraper
==========================
Researches and attempts to scrape flight prices from major Chinese OTAs:
  1. Ctrip (flights.ctrip.com) -- WORKING: lowestPrice API for domestic routes
  2. Ctrip International -- PARTIAL: batchSearch returns structure but needs CAPTCHA
  3. Trip.com (www.trip.com) -- BLOCKED: 428 crypto challenge (Akamai-style anti-bot)
  4. Fliggy (fliggy.com) -- BLOCKED: Requires Alibaba OAuth 2.0

Target routes:
  - CTU (Chengdu) -> LAX (Los Angeles), May 15, 2026
  - PVG (Shanghai) -> LAX, May 15, 2026
  - PVG -> SFO (San Francisco), May 15, 2026

Target airlines: Sichuan Airlines (3U), China Southern (CZ), China Eastern (MU)

=== KEY FINDINGS ===

1. CTRIP DOMESTIC API - /itinerary/api/12808/products
   STATUS: DECOMMISSIONED ("接口下线")
   The original products endpoint discovered by Ctrip-Crawler (2018) has been
   taken offline. It returns: {"status":0,"data":{"error":{"code":"","msg":"接口下线"}}}

2. CTRIP LOWEST PRICE API - /itinerary/api/12808/lowestPrice  [WORKING]
   STATUS: FUNCTIONAL for domestic Chinese routes
   Returns lowest prices per date for a city pair over ~6 months.
   Does NOT work for international routes (returns null prices).
   Method: GET with query params (flightWay, dcity, acity, direct, army)

3. CTRIP INTERNATIONAL - /international/search/api/search/batchSearch
   STATUS: REQUIRES CAPTCHA/SESSION
   Returns {"status":0,"msg":"success","data":{"context":{"searchId":"","finished":true,
   "flag":2,"showAuthCode":true}}}. The "showAuthCode":true means CAPTCHA is needed.
   Requires browser session cookies to bypass.

4. TRIP.COM GraphQL - /flights/graphql/ctFlightDetailSearch
   STATUS: BLOCKED (HTTP 428 "Precondition Required")
   Returns: {"sec-cp-challenge":"true","provider":"crypto","chlge_content_url":"..."}
   This is an Akamai Bot Manager crypto challenge. Cannot be solved with plain HTTP.

5. TRIP.COM SOA2 REST - /restapi/soa2/27015/flightListSearch
   STATUS: BLOCKED (HTTP 432)
   Custom status code, likely anti-bot protection.

6. FLIGGY - us.fliggytravel.com
   STATUS: NOT FEASIBLE
   Requires Alibaba Cloud OAuth 2.0 (mtop gateway protocol).
   International site redirects away from flight search.

=== RECOMMENDATIONS ===
- For Ctrip: Use Selenium + SeleniumWire (see github.com/Suysker/Ctrip-Crawler)
- For Trip.com: Use Playwright with stealth plugins to solve crypto challenges
- For Chinese carrier fares specifically: Try airline direct sites or Duffel API
  (Duffel uses Travelport GDS which has Sichuan Airlines content)
- The lowestPrice API works well for tracking domestic China price trends
"""

import requests
import json
import random
import time
import sys
import os
import io
from datetime import datetime
from typing import Optional

# Fix Windows console encoding for Chinese characters
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")


# ============================================================================
# CONFIGURATION
# ============================================================================

SEARCH_ROUTES = [
    {
        "name": "CTU-LAX One-way",
        "dcity": "CTU", "acity": "LAX",
        "dcityname": "成都", "acityname": "洛杉矶",
        "dcityname_en": "Chengdu", "acityname_en": "Los Angeles",
        "date": "2026-05-15",
        "flightWay": "Oneway",
        "dcityid": 28, "acityid": 0,
    },
    {
        "name": "CTU-LAX Round-trip",
        "dcity": "CTU", "acity": "LAX",
        "dcityname": "成都", "acityname": "洛杉矶",
        "dcityname_en": "Chengdu", "acityname_en": "Los Angeles",
        "date": "2026-05-15",
        "return_date": "2026-06-15",
        "flightWay": "Roundtrip",
        "dcityid": 28, "acityid": 0,
    },
    {
        "name": "PVG-LAX One-way",
        "dcity": "PVG", "acity": "LAX",
        "dcityname": "上海", "acityname": "洛杉矶",
        "dcityname_en": "Shanghai", "acityname_en": "Los Angeles",
        "date": "2026-05-15",
        "flightWay": "Oneway",
        "dcityid": 2, "acityid": 0,
    },
    {
        "name": "PVG-SFO One-way",
        "dcity": "PVG", "acity": "SFO",
        "dcityname": "上海", "acityname": "旧金山",
        "dcityname_en": "Shanghai", "acityname_en": "San Francisco",
        "date": "2026-05-15",
        "flightWay": "Oneway",
        "dcityid": 2, "acityid": 0,
    },
]

# Domestic Chinese routes for demonstrating the working lowestPrice API
DOMESTIC_DEMO_ROUTES = [
    {"name": "CTU-SHA (Chengdu-Shanghai)", "dcity": "CTU", "acity": "SHA", "direct": "true"},
    {"name": "SHA-CTU (Shanghai-Chengdu)", "dcity": "SHA", "acity": "CTU", "direct": "true"},
    # NOTE: API uses CITY codes not AIRPORT codes. SHA=Shanghai, not PVG (Pudong airport).
    {"name": "SHA-CAN (Shanghai-Guangzhou)", "dcity": "SHA", "acity": "CAN", "direct": "true"},
    {"name": "CTU-BJS (Chengdu-Beijing)", "dcity": "CTU", "acity": "BJS", "direct": "false"},
]

TARGET_AIRLINES = {
    "3U": "Sichuan Airlines",
    "CZ": "China Southern",
    "MU": "China Eastern",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


def random_ua():
    return random.choice(USER_AGENTS)


def random_porting_token():
    """Generate 32-char hex string for Ctrip's portingToken parameter."""
    return "".join(random.choice("0123456789abcdef") for _ in range(32))


# ============================================================================
# METHOD 1: CTRIP LOWEST PRICE API  [WORKING - DOMESTIC ONLY]
# ============================================================================
# Endpoint: GET https://flights.ctrip.com/itinerary/api/12808/lowestPrice
# Params: flightWay, dcity, acity, direct, army
#
# Returns lowest one-way prices per date for ~6 months.
# CONFIRMED WORKING for domestic Chinese routes.
# Returns null prices for international routes.
#
# Response format:
# {
#   "data": {
#     "oneWayPrice": [["2026-03-17", 330], ["2026-03-18", 330], ...],
#     "roundTripPrice": null,
#     "singleToRoundPrice": null
#   },
#   "status": 0,
#   "msg": "success"
# }
# ============================================================================

class CtripLowestPriceScraper:
    """
    WORKING scraper for Ctrip's lowest price API.
    Returns daily lowest prices for domestic Chinese routes.
    """

    BASE_URL = "https://flights.ctrip.com/itinerary/api/12808/lowestPrice"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": random_ua()})

    def search(self, dcity: str, acity: str, flight_way: str = "Oneway",
               direct: str = "false") -> dict:
        """
        Search lowest prices for a city pair.

        Args:
            dcity: Departure city IATA code (e.g., "CTU", "SHA", "PVG")
            acity: Arrival city IATA code
            flight_way: "Oneway" or "Roundtrip"
            direct: "true" for direct flights only, "false" for all

        Returns:
            dict with status and price data
        """
        params = {
            "flightWay": flight_way,
            "dcity": dcity,
            "acity": acity,
            "direct": direct,
            "army": "false",
        }

        result = {
            "source": "Ctrip-LowestPrice",
            "route": f"{dcity}-{acity}",
            "endpoint": self.BASE_URL,
            "status": "unknown",
            "prices": {},
            "error": None,
        }

        try:
            resp = self.session.get(self.BASE_URL, params=params, timeout=15)
            result["http_status"] = resp.status_code

            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == 0 and data.get("msg") == "success":
                    price_data = data.get("data", {})
                    ow_prices_raw = price_data.get("oneWayPrice")
                    rt_prices_raw = price_data.get("roundTripPrice")

                    # Parse oneWayPrice -- format is a list containing one dict
                    # with keys like "20260515": 550
                    ow_prices = {}
                    if ow_prices_raw:
                        for item in ow_prices_raw:
                            if isinstance(item, dict):
                                for date_key, price in item.items():
                                    # Convert "20260515" to "2026-05-15"
                                    if len(date_key) == 8 and date_key.isdigit():
                                        formatted = f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:]}"
                                        ow_prices[formatted] = price
                                    else:
                                        ow_prices[str(date_key)] = price
                            elif isinstance(item, (list, tuple)) and len(item) == 2:
                                # Legacy format: [date, price]
                                ow_prices[str(item[0])] = item[1]

                    rt_prices = {}
                    if rt_prices_raw:
                        for item in rt_prices_raw:
                            if isinstance(item, dict):
                                for date_key, price in item.items():
                                    if len(date_key) == 8 and date_key.isdigit():
                                        formatted = f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:]}"
                                        rt_prices[formatted] = price
                                    else:
                                        rt_prices[str(date_key)] = price

                    if ow_prices:
                        result["status"] = "success"
                        result["prices"] = {
                            "oneway": ow_prices,
                            "roundtrip": rt_prices if rt_prices else None,
                        }
                        result["price_count"] = len(ow_prices)
                        prices_list = list(ow_prices.values())
                        result["min_price"] = min(prices_list)
                        result["max_price"] = max(prices_list)
                        result["currency"] = "CNY"
                    else:
                        result["status"] = "no_prices"
                        result["error"] = "All price fields returned null (route may be international)"
                else:
                    result["status"] = "api_error"
                    result["error"] = data.get("msg", "Unknown error")
            else:
                result["status"] = f"http_{resp.status_code}"

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

        return result

    def get_price_for_date(self, dcity: str, acity: str, date: str,
                           flight_way: str = "Oneway", direct: str = "false") -> Optional[int]:
        """Get the lowest price for a specific date."""
        result = self.search(dcity, acity, flight_way, direct)
        if result["status"] == "success":
            return result["prices"].get("oneway", {}).get(date)
        return None


# ============================================================================
# METHOD 2: CTRIP PRODUCTS API  [DECOMMISSIONED]
# ============================================================================
# Endpoint: POST https://flights.ctrip.com/itinerary/api/12808/products
# Status: OFFLINE as of 2025+
# Returns: {"status":0,"data":{"error":{"code":"","msg":"接口下线"}}}
#
# Documented for reference -- this was the primary API used by Ctrip-Crawler.
# Response structure (when it worked):
#   data.routeList[].legs[].flight.{flightNumber, airlineCode, airlineName,
#     departureAirportInfo, arrivalAirportInfo, departureDate, arrivalDate}
#   data.routeList[].legs[].cabins[].{cabinClass, price.salePrice, price.rate}
#   data.routeList[].legs[].characteristic.{lowestPrice, lowestCfPrice}
# ============================================================================

class CtripProductsScraper:
    """
    Ctrip products API -- DECOMMISSIONED.
    Included to test and confirm the endpoint is offline.
    """

    BASE_URL = "https://flights.ctrip.com/itinerary/api/12808/products"

    def __init__(self):
        self.session = requests.Session()

    def search(self, route: dict) -> dict:
        dcity = route["dcity"]
        acity = route["acity"]
        date = route["date"]
        token = random_porting_token()

        headers = {
            "User-Agent": random_ua(),
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Content-Type": "application/json",
            "Origin": "https://flights.ctrip.com",
            "Referer": f"https://flights.ctrip.com/itinerary/oneway/{dcity.lower()}-{acity.lower()}?date={date}&portingToken={token}",
        }

        payload = {
            "flightWay": route.get("flightWay", "Oneway"),
            "classType": "ALL",
            "hasChild": False,
            "hasBaby": False,
            "searchIndex": 1,
            "airportParams": [{
                "dcity": dcity,
                "acity": acity,
                "dcityname": route.get("dcityname", ""),
                "acityname": route.get("acityname", ""),
                "date": date,
            }],
        }

        result = {
            "source": "Ctrip-Products",
            "route": route.get("name", f"{dcity}-{acity}"),
            "endpoint": self.BASE_URL,
            "status": "unknown",
            "flights": [],
            "error": None,
        }

        try:
            resp = self.session.post(self.BASE_URL, headers=headers, json=payload, timeout=30)
            result["http_status"] = resp.status_code

            if resp.status_code == 200:
                data = resp.json()
                raw = json.dumps(data, ensure_ascii=False)
                result["raw_response"] = raw[:500]

                if "接口下线" in raw:
                    result["status"] = "decommissioned"
                    result["error"] = "API is offline (接口下线). This endpoint was decommissioned."
                elif data.get("data", {}).get("routeList"):
                    result["status"] = "success"
                    result["flights"] = self._parse_flights(data)
                else:
                    err = data.get("data", {}).get("error", {})
                    result["status"] = "api_error"
                    result["error"] = f"Code={err.get('code')}, Msg={err.get('msg')}"
            else:
                result["status"] = f"http_{resp.status_code}"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

        return result

    def _parse_flights(self, data) -> list:
        """Parse flight data from the (formerly working) products API."""
        flights = []
        for route_item in data.get("data", {}).get("routeList", []):
            if route_item.get("routeType") != "Flight":
                continue
            legs = route_item.get("legs", [])
            if not legs:
                continue
            leg = legs[0]
            fi = leg.get("flight", {})
            char = leg.get("characteristic", {})
            cabins = leg.get("cabins", [])

            economy_price = None
            for c in cabins:
                if c.get("cabinClass") == "Y":
                    p = c.get("price", {}).get("salePrice")
                    if p and (economy_price is None or p < economy_price):
                        economy_price = p

            flights.append({
                "flight_number": fi.get("flightNumber", ""),
                "airline_code": fi.get("airlineCode", ""),
                "airline_name": fi.get("airlineName", ""),
                "aircraft": fi.get("craftTypeName", ""),
                "dep_airport": fi.get("departureAirportInfo", {}).get("airportName", ""),
                "arr_airport": fi.get("arrivalAirportInfo", {}).get("airportName", ""),
                "dep_time": fi.get("departureDate", ""),
                "arr_time": fi.get("arrivalDate", ""),
                "lowest_price": char.get("lowestPrice"),
                "economy_price": economy_price,
                "business_price": char.get("lowestCfPrice"),
                "is_target": fi.get("airlineCode", "") in TARGET_AIRLINES,
                "currency": "CNY",
            })
        return flights


# ============================================================================
# METHOD 3: CTRIP INTERNATIONAL batchSearch  [NEEDS CAPTCHA]
# ============================================================================
# Endpoint: POST https://flights.ctrip.com/international/search/api/search/batchSearch
# Returns context with searchId and showAuthCode=true flag requiring CAPTCHA.
# With a valid browser session (cookies from Selenium), this returns flight data.
# ============================================================================

class CtripInternationalScraper:
    """
    Ctrip international search API.
    Returns a search context but requires CAPTCHA completion in browser.
    """

    ENDPOINT = "https://flights.ctrip.com/international/search/api/search/batchSearch"

    def __init__(self):
        self.session = requests.Session()

    def search(self, route: dict) -> dict:
        headers = {
            "User-Agent": random_ua(),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://flights.ctrip.com",
            "Referer": f"https://flights.ctrip.com/international/search/oneway-{route['dcity'].lower()}-{route['acity'].lower()}?depdate={route['date']}&cabin=y&adult=1&child=0&infant=0",
        }

        payload = {
            "flightWay": "S" if route.get("flightWay") == "Oneway" else "D",
            "classType": "ALL",
            "hasChild": False,
            "hasBaby": False,
            "searchIndex": 1,
            "airportParams": [{
                "dcity": route["dcity"],
                "acity": route["acity"],
                "ddate": route["date"],
            }],
            "cabin": "Y",
            "adult": 1,
            "child": 0,
            "infant": 0,
        }

        result = {
            "source": "Ctrip-International-batchSearch",
            "route": route.get("name", f"{route['dcity']}-{route['acity']}"),
            "endpoint": self.ENDPOINT,
            "status": "unknown",
            "flights": [],
            "error": None,
        }

        try:
            resp = self.session.post(self.ENDPOINT, headers=headers, json=payload, timeout=30)
            result["http_status"] = resp.status_code

            if resp.status_code == 200:
                data = resp.json()
                result["raw_response"] = json.dumps(data, ensure_ascii=False)[:500]
                context = data.get("data", {}).get("context", {})

                if context.get("showAuthCode"):
                    result["status"] = "captcha_required"
                    result["error"] = (
                        "API requires CAPTCHA (showAuthCode=true). "
                        "Use Selenium/Playwright to complete CAPTCHA first, "
                        "then pass session cookies to this API."
                    )
                    result["search_context"] = context
                elif data.get("data", {}).get("flightItineraryList"):
                    result["status"] = "success"
                    result["flight_count"] = len(data["data"]["flightItineraryList"])
                else:
                    result["status"] = "no_data"
                    result["data_keys"] = list(data.get("data", {}).keys())
            else:
                result["status"] = f"http_{resp.status_code}"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

        return result


# ============================================================================
# METHOD 4: TRIP.COM GraphQL + SOA2  [BLOCKED]
# ============================================================================
# GraphQL endpoints discovered in Trip.com page source:
#   - /flights/graphql/ctFlightDetailSearch  (HTTP 428 - crypto challenge)
#   - /flights/graphql/intlCTCreateOrder     (order creation)
#   - /flights/graphql/intlCTBookingVerify   (booking verification)
#
# SOA2 REST endpoints:
#   - /restapi/soa2/27015/  (flight ops, HTTP 432)
#   - /restapi/soa2/28471/  (flight services)
#   - /restapi/soa2/14427/  (additional services)
#   - /restapi/soa2/37106/userRecognize (auth)
#
# All blocked by Akamai Bot Manager crypto challenges.
# ============================================================================

class TripcomScraper:
    """
    Trip.com API scraper -- all endpoints blocked by anti-bot.
    Documented for endpoint discovery purposes.
    """

    GRAPHQL_URL = "https://www.trip.com/flights/graphql/ctFlightDetailSearch"
    SOA2_URL = "https://www.trip.com/restapi/soa2/27015/flightListSearch"

    def __init__(self):
        self.session = requests.Session()

    def search_graphql(self, route: dict) -> dict:
        """Try Trip.com GraphQL endpoint."""
        dcity_en = route["dcityname_en"].lower().replace(" ", "-")
        acity_en = route["acityname_en"].lower().replace(" ", "-")
        search_url = (
            f"https://www.trip.com/flights/{dcity_en}-to-{acity_en}/"
            f"tickets-{route['dcity'].lower()}-{route['acity'].lower()}"
            f"?dcity={route['dcity'].lower()}&acity={route['acity'].lower()}"
            f"&ddate={route['date']}&flighttype=ow"
        )

        headers = {
            "User-Agent": random_ua(),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://www.trip.com",
            "Referer": search_url,
        }

        payload = {
            "operationName": "ctFlightDetailSearch",
            "variables": {
                "request": {
                    "searchCriteria": {
                        "cabinClass": "Economy",
                        "adultCount": 1,
                        "segments": [{
                            "departureCity": route["dcity"],
                            "arrivalCity": route["acity"],
                            "departureDate": route["date"],
                        }],
                    },
                    "currency": "USD",
                    "locale": "en-US",
                }
            },
            "query": "query ctFlightDetailSearch($request: FlightSearchRequest!) { flightSearch(request: $request) { flights { flightNumber airlineCode prices { totalPrice } } } }"
        }

        result = {
            "source": "Trip.com-GraphQL",
            "route": route.get("name", f"{route['dcity']}-{route['acity']}"),
            "endpoint": self.GRAPHQL_URL,
            "status": "unknown",
            "error": None,
        }

        try:
            resp = self.session.post(self.GRAPHQL_URL, headers=headers, json=payload, timeout=15)
            result["http_status"] = resp.status_code

            if resp.status_code == 428:
                try:
                    challenge = resp.json()
                    result["status"] = "crypto_challenge_428"
                    result["error"] = (
                        "Akamai Bot Manager crypto challenge. "
                        f"Provider: {challenge.get('provider', 'unknown')}. "
                        "Requires browser JavaScript execution to solve."
                    )
                    result["challenge_info"] = {
                        "provider": challenge.get("provider"),
                        "challenge_url": challenge.get("chlge_content_url", "")[:100],
                    }
                except Exception:
                    result["status"] = "blocked_428"
                    result["error"] = "HTTP 428 - anti-bot challenge"
            elif resp.status_code == 200:
                data = resp.json()
                if "errors" in data:
                    result["status"] = "graphql_error"
                    result["error"] = str(data["errors"])[:200]
                else:
                    result["status"] = "success"
                    result["data_preview"] = json.dumps(data, ensure_ascii=False)[:300]
            else:
                result["status"] = f"http_{resp.status_code}"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

        return result

    def search_soa2(self, route: dict) -> dict:
        """Try Trip.com SOA2 REST endpoint."""
        headers = {
            "User-Agent": random_ua(),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://www.trip.com",
        }

        payload = {
            "contentType": "json",
            "head": {"cid": "", "ctok": "", "cver": "1.0", "lang": "01", "sid": "0", "syscode": "999"},
            "flightWay": "S",
            "classType": "ALL",
            "hasChild": False,
            "hasBaby": False,
            "searchIndex": 1,
            "airportParams": [{"dcity": route["dcity"], "acity": route["acity"], "ddate": route["date"]}],
        }

        result = {
            "source": "Trip.com-SOA2",
            "route": route.get("name", f"{route['dcity']}-{route['acity']}"),
            "endpoint": self.SOA2_URL,
            "status": "unknown",
            "error": None,
        }

        try:
            resp = self.session.post(self.SOA2_URL, headers=headers, json=payload, timeout=15)
            result["http_status"] = resp.status_code

            if resp.status_code == 432:
                result["status"] = "blocked_432"
                result["error"] = "Custom HTTP 432 -- Trip.com anti-bot protection"
            elif resp.status_code == 200:
                result["status"] = "success"
            else:
                result["status"] = f"http_{resp.status_code}"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

        return result


# ============================================================================
# METHOD 5: FLIGGY  [NOT FEASIBLE]
# ============================================================================
# Fliggy uses Alibaba's mtop gateway protocol:
#   - h5api.m.taobao.com/h5/mtop.trip.flight.search/1.0/
#   - acs.m.taobao.com/gw/mtop.trip.flight.search/1.0/
# Requires OAuth 2.0 via Alibaba Cloud. Rate limit: 500 req/min.
# ============================================================================

class FliggyScraper:
    """Fliggy scraper -- documents the approach. Requires Alibaba OAuth."""

    def search(self, route: dict) -> dict:
        result = {
            "source": "Fliggy",
            "route": route.get("name", f"{route['dcity']}-{route['acity']}"),
            "status": "not_feasible",
            "error": (
                "Fliggy requires Alibaba Cloud OAuth 2.0 authentication. "
                "The mtop gateway protocol at h5api.m.taobao.com requires signed requests "
                "with Alibaba account credentials. The international site (us.fliggytravel.com) "
                "redirects away from flight search pages."
            ),
            "api_info": {
                "gateway": "h5api.m.taobao.com/h5/mtop.trip.flight.search/1.0/",
                "auth": "OAuth 2.0 via Alibaba Cloud",
                "rate_limit": "500 req/min",
            },
        }

        # Quick check if the intl site has anything useful
        try:
            resp = requests.get(
                "https://us.fliggytravel.com/",
                headers={"User-Agent": random_ua()},
                timeout=10,
            )
            result["http_status"] = resp.status_code
            result["intl_site_accessible"] = resp.status_code == 200
        except Exception:
            result["intl_site_accessible"] = False

        return result


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

def print_separator(char="=", length=80):
    print(char * length)


def run_all_searches():
    """Execute all search methods and produce comprehensive results."""

    print_separator()
    print("CHINESE OTA FLIGHT SCRAPER -- COMPREHENSIVE TEST")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_separator()

    all_results = []

    # =========================================================================
    # TEST 1: Ctrip lowestPrice API (WORKING for domestic)
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 1: CTRIP LOWEST PRICE API  [EXPECTED: WORKING FOR DOMESTIC]")
    print("Endpoint: GET /itinerary/api/12808/lowestPrice")
    print("=" * 80)

    lp_scraper = CtripLowestPriceScraper()

    # Test international routes (expected: no prices)
    print("\n--- International routes (expected: null prices) ---")
    for route in SEARCH_ROUTES:
        if route["flightWay"] == "Roundtrip":
            continue
        result = lp_scraper.search(route["dcity"], route["acity"])
        all_results.append(result)
        print(f"  {result['route']:<15} Status: {result['status']:<20} "
              f"Prices: {result.get('price_count', 0)}")
        if result.get("error"):
            print(f"    -> {result['error']}")
        time.sleep(0.5)

    # Test domestic routes (expected: working with prices)
    print("\n--- Domestic routes (expected: working with prices) ---")
    for dr in DOMESTIC_DEMO_ROUTES:
        result = lp_scraper.search(dr["dcity"], dr["acity"], direct=dr["direct"])
        all_results.append(result)

        if result["status"] == "success":
            # Find price for May 15
            may15_price = result["prices"].get("oneway", {}).get("2026-05-15")
            print(f"  {result['route']:<30} [OK] {result['price_count']} dates | "
                  f"Range: {result['min_price']}-{result['max_price']} CNY | "
                  f"May 15: {may15_price or 'N/A'} CNY")
        else:
            print(f"  {result['route']:<30} [--] {result['status']}: {result.get('error', '')}")
        time.sleep(0.5)

    # =========================================================================
    # TEST 2: Ctrip Products API (DECOMMISSIONED)
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 2: CTRIP PRODUCTS API  [EXPECTED: DECOMMISSIONED]")
    print("Endpoint: POST /itinerary/api/12808/products")
    print("=" * 80)

    prod_scraper = CtripProductsScraper()
    # Just test one route to confirm it's offline
    result = prod_scraper.search(SEARCH_ROUTES[0])
    all_results.append(result)
    print(f"  {result['route']:<25} Status: {result['status']}")
    if result.get("error"):
        print(f"    -> {result['error']}")

    # =========================================================================
    # TEST 3: Ctrip International batchSearch (CAPTCHA)
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 3: CTRIP INTERNATIONAL SEARCH  [EXPECTED: CAPTCHA REQUIRED]")
    print("Endpoint: POST /international/search/api/search/batchSearch")
    print("=" * 80)

    intl_scraper = CtripInternationalScraper()
    for route in SEARCH_ROUTES:
        if route["flightWay"] == "Roundtrip":
            continue
        result = intl_scraper.search(route)
        all_results.append(result)
        print(f"  {result['route']:<25} Status: {result['status']}")
        if result.get("error"):
            print(f"    -> {result['error'][:100]}")
        if result.get("search_context"):
            ctx = result["search_context"]
            print(f"    Context: searchId={ctx.get('searchId', 'empty')}, "
                  f"finished={ctx.get('finished')}, flag={ctx.get('flag')}")
        time.sleep(1)

    # =========================================================================
    # TEST 4: Trip.com GraphQL + SOA2 (BLOCKED)
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 4: TRIP.COM ENDPOINTS  [EXPECTED: BLOCKED BY ANTI-BOT]")
    print("Endpoints: GraphQL + SOA2 REST")
    print("=" * 80)

    tripcom = TripcomScraper()
    # Test one route each to demonstrate the blocks
    test_route = SEARCH_ROUTES[0]

    result_gql = tripcom.search_graphql(test_route)
    all_results.append(result_gql)
    print(f"  GraphQL:  {result_gql['route']:<20} HTTP {result_gql.get('http_status', 'N/A')} -> {result_gql['status']}")
    if result_gql.get("error"):
        print(f"    -> {result_gql['error'][:120]}")

    time.sleep(1)

    result_soa = tripcom.search_soa2(test_route)
    all_results.append(result_soa)
    print(f"  SOA2:     {result_soa['route']:<20} HTTP {result_soa.get('http_status', 'N/A')} -> {result_soa['status']}")
    if result_soa.get("error"):
        print(f"    -> {result_soa['error'][:120]}")

    # =========================================================================
    # TEST 5: Fliggy (NOT FEASIBLE)
    # =========================================================================
    print("\n" + "=" * 80)
    print("TEST 5: FLIGGY  [EXPECTED: NOT FEASIBLE]")
    print("=" * 80)

    fliggy = FliggyScraper()
    result = fliggy.search(test_route)
    all_results.append(result)
    print(f"  Status: {result['status']}")
    print(f"  -> {result['error'][:120]}")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 80)
    print("COMPREHENSIVE RESULTS SUMMARY")
    print("=" * 80)

    statuses = {}
    for r in all_results:
        s = r["status"]
        statuses[s] = statuses.get(s, 0) + 1

    print("\nStatus breakdown:")
    for s, count in sorted(statuses.items()):
        print(f"  {s:<30} {count}")

    print(f"\nTotal API calls: {len(all_results)}")
    print(f"Successful with data: {statuses.get('success', 0)}")

    # Print working domestic results in detail
    working = [r for r in all_results if r["status"] == "success"]
    if working:
        print("\n" + "-" * 80)
        print("WORKING RESULTS (Ctrip Domestic LowestPrice)")
        print("-" * 80)
        for r in working:
            may15 = r.get("prices", {}).get("oneway", {}).get("2026-05-15")
            print(f"  {r['route']:<30} {r.get('price_count', 0)} dates | "
                  f"Range: {r.get('min_price')}-{r.get('max_price')} CNY | "
                  f"May 15: {may15 or 'N/A'} CNY")

    # =========================================================================
    # ENDPOINT DOCUMENTATION
    # =========================================================================
    print("\n" + "=" * 80)
    print("DISCOVERED API ENDPOINTS REFERENCE")
    print("=" * 80)

    endpoints = [
        {
            "platform": "Ctrip",
            "endpoint": "GET https://flights.ctrip.com/itinerary/api/12808/lowestPrice",
            "params": "?flightWay=Oneway&dcity=CTU&acity=SHA&direct=false&army=false",
            "status": "WORKING (domestic only)",
            "returns": "Daily lowest prices for ~6 months, CNY",
            "auth": "None required",
        },
        {
            "platform": "Ctrip",
            "endpoint": "GET https://flights.ctrip.com/itinerary/api/poi/get",
            "params": "None",
            "status": "WORKING",
            "returns": "City/airport code dictionary for domestic China",
            "auth": "None required",
        },
        {
            "platform": "Ctrip",
            "endpoint": "POST https://flights.ctrip.com/itinerary/api/12808/products",
            "params": "JSON body with flightWay, classType, airportParams[]",
            "status": "DECOMMISSIONED (接口下线)",
            "returns": "Was: routeList with flight details + pricing. Now: error.",
            "auth": "None (was working without auth until decommissioned)",
        },
        {
            "platform": "Ctrip International",
            "endpoint": "POST https://flights.ctrip.com/international/search/api/search/batchSearch",
            "params": "JSON with flightWay, airportParams[].{dcity,acity,ddate}, cabin, adult",
            "status": "REQUIRES CAPTCHA (showAuthCode=true)",
            "returns": "Search context; needs browser session for actual results",
            "auth": "Browser cookies + CAPTCHA completion",
        },
        {
            "platform": "Trip.com",
            "endpoint": "POST https://www.trip.com/flights/graphql/ctFlightDetailSearch",
            "params": "GraphQL query with operationName + variables",
            "status": "BLOCKED (HTTP 428 Akamai crypto challenge)",
            "returns": "sec-cp-challenge JSON with crypto puzzle",
            "auth": "Must solve browser-side crypto challenge first",
        },
        {
            "platform": "Trip.com",
            "endpoint": "POST https://www.trip.com/restapi/soa2/27015/flightListSearch",
            "params": "JSON with head{}, flightWay, airportParams[]",
            "status": "BLOCKED (HTTP 432)",
            "returns": "Custom anti-bot response",
            "auth": "Browser session required",
        },
        {
            "platform": "Trip.com",
            "endpoint": "POST https://www.trip.com/restapi/soa2/37106/userRecognize",
            "params": "User recognition request",
            "status": "FOUND IN PAGE SOURCE (not tested separately)",
            "returns": "Auth/session data",
            "auth": "Part of anti-bot flow",
        },
        {
            "platform": "Fliggy",
            "endpoint": "POST https://h5api.m.taobao.com/h5/mtop.trip.flight.search/1.0/",
            "params": "mtop protocol with signed parameters",
            "status": "NOT FEASIBLE without Alibaba OAuth",
            "returns": "Flight search results (with valid auth)",
            "auth": "OAuth 2.0 via Alibaba Cloud account",
        },
    ]

    for ep in endpoints:
        print(f"\n  [{ep['status']}]")
        print(f"  Platform: {ep['platform']}")
        print(f"  Endpoint: {ep['endpoint']}")
        print(f"  Params:   {ep['params']}")
        print(f"  Returns:  {ep['returns']}")
        print(f"  Auth:     {ep['auth']}")

    # =========================================================================
    # SAVE RESULTS
    # =========================================================================
    output = {
        "scrape_time": datetime.now().isoformat(),
        "routes_searched": [r["name"] for r in SEARCH_ROUTES],
        "target_airlines": TARGET_AIRLINES,
        "results": all_results,
        "endpoints_discovered": endpoints,
        "key_findings": {
            "working": [
                "Ctrip lowestPrice API works for domestic Chinese routes without authentication",
                "Ctrip POI API (city/airport codes) works without authentication",
            ],
            "partially_working": [
                "Ctrip international batchSearch responds but requires CAPTCHA (browser session)",
            ],
            "blocked": [
                "Ctrip products API is decommissioned (接口下线)",
                "Trip.com GraphQL returns HTTP 428 Akamai crypto challenge",
                "Trip.com SOA2 REST returns HTTP 432 (custom anti-bot)",
                "Fliggy requires Alibaba Cloud OAuth 2.0",
            ],
            "recommendations_for_international": [
                "Use Selenium+SeleniumWire (github.com/Suysker/Ctrip-Crawler) to handle Ctrip CAPTCHA",
                "Use Playwright with stealth plugins for Trip.com crypto challenges",
                "Consider Duffel API (duffel.com) which has Sichuan Airlines via Travelport GDS",
                "Check airline direct sites: global.sichuanair.com, csair.com, ceair.com",
                "SerpApi Google Flights API or Skyscanner API as alternatives",
            ],
        },
    }

    output_path = "D:/claude/flights/chinese_ota_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n\nResults saved to: {output_path}")

    return output


# ============================================================================
# CONVENIENCE / UTILITY FUNCTIONS
# ============================================================================

def get_domestic_prices(dcity: str, acity: str, target_date: str = None) -> dict:
    """
    Quick function to get domestic flight prices from Ctrip.

    Example:
        >>> prices = get_domestic_prices("CTU", "SHA", "2026-05-15")
        >>> print(prices)
        {'route': 'CTU-SHA', 'status': 'success', 'target_date_price': 580, ...}
    """
    scraper = CtripLowestPriceScraper()
    result = scraper.search(dcity, acity)

    if target_date and result["status"] == "success":
        result["target_date"] = target_date
        result["target_date_price"] = result["prices"].get("oneway", {}).get(target_date)

    return result


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    print("Chinese OTA Flight Scraper")
    print("Target: Sichuan Airlines (3U), China Southern (CZ), China Eastern (MU)")
    print("Routes: CTU-LAX, PVG-LAX, PVG-SFO | Date: May 15, 2026")
    print()

    results = run_all_searches()

    print("\n" + "=" * 80)
    print("SCRAPING COMPLETE")
    print("=" * 80)
