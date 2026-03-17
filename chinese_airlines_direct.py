#!/usr/bin/env python3
"""
Chinese Airlines Direct Flight Search
======================================
Research and search tool for China Southern Airlines (CZ) and China Eastern Airlines (MU)
direct flights from China to the US West Coast.

Approach:
---------
1. Primary: Uses the `fast-flights` library (Google Flights scraper via protobuf)
   to search for flights on specific routes. This captures CZ and MU flights
   that appear in Google Flights results.

2. Secondary: Direct API probing of csair.com and ceair.com booking endpoints
   (documented but access-restricted).

3. Tertiary: Amadeus Self-Service API (requires free developer account signup).

Routes researched:
- CTU -> LAX (Chengdu to Los Angeles) - China Southern via CAN hub
- PVG -> LAX (Shanghai to Los Angeles) - China Eastern nonstop MU583/MU586
- PVG -> SFO (Shanghai to San Francisco) - China Eastern nonstop MU589/MU590

API Research Findings:
----------------------
China Southern Airlines (csair.com):
  - Main B2C booking: b2c.csair.com/B2C40/
  - Overseas booking: oversea.csair.com/tka/us/en/book/search (403 for bots)
  - NDC API: Level 4 certified, IATA NDC 17.2, partner-only access
  - Key JS module: searchInit.js -> bussinessLogic.searchFlight()
  - IP geolocation: csair.com/iplocator/getIpInfo
  - All search APIs are behind session/cookie authentication

China Eastern Airlines (ceair.com):
  - US site: us.ceair.com/en/booking-new.html (geo-restricted, password-gated)
  - Production env: window.ENVIRONMENT = 'production'
  - Cookie required: global_site_flag=en_US
  - PT Engine analytics: account 71d4c6a5
  - No public API endpoints discovered; all behind JS rendering

Third-party options:
  - Amadeus Self-Service: Free test env, pip install amadeus
  - Duffel API: Supports both CZ and MU
  - AirLabs API: Flight tracking for MU
  - fast-flights: Google Flights scraper (best free option)
"""

import json
import sys
import os
import time
import datetime
from typing import Optional


# ============================================================================
# SECTION 1: Route & Airline Reference Data
# ============================================================================

CHINESE_AIRLINE_ROUTES = {
    "china_southern": {
        "iata_code": "CZ",
        "icao_code": "CSN",
        "hub": "CAN (Guangzhou Baiyun)",
        "website": "csair.com",
        "booking_urls": {
            "main": "https://www.csair.com/en/",
            "us_site": "https://www.csair.com/us/en/",
            "b2c_search": "https://b2c.csair.com/B2C40/newTrips/static/main/page/search/index.html",
            "overseas_booking": "https://oversea.csair.com/tka/us/en/book/search",
            "mileage_search": "https://b2c.csair.com/B2C40/modules/bookingnew/mileage/search.html?lang=en",
        },
        "api_notes": {
            "ndc_level": "Level 4 (highest in China)",
            "ndc_version": "IATA NDC 17.2",
            "access": "Partner-only NDC API; no public REST endpoints",
            "js_entry": "B2C40/newTrips/static/main/scripts/search/searchInit.js",
            "search_fn": "bussinessLogic.searchFlight()",
            "ip_service": "csair.com/iplocator/getIpInfo",
        },
        "us_routes": {
            "CAN-LAX": {
                "flight_numbers": ["CZ327 (CAN->LAX)", "CZ328 (LAX->CAN)"],
                "frequency": "Daily",
                "aircraft": "Boeing 777",
                "nonstop": True,
                "flight_time": "~13h (westbound), ~15h (eastbound)",
                "notes": "Primary transpacific route from CZ hub",
            },
            "CTU-LAX": {
                "flight_numbers": ["Via CAN hub (CZ domestic + CZ327/328)"],
                "frequency": "Daily (with connection)",
                "nonstop": False,
                "connection": "CAN (Guangzhou) - 2-4hr layover",
                "notes": "No CZ nonstop CTU-LAX; Sichuan Airlines (3U) operates nonstop TFU-LAX",
            },
        },
    },
    "china_eastern": {
        "iata_code": "MU",
        "icao_code": "CES",
        "hub": "PVG (Shanghai Pudong)",
        "website": "ceair.com",
        "booking_urls": {
            "main": "https://us.ceair.com/en/",
            "booking": "https://us.ceair.com/en/booking-new.html",
            "flight_status": "https://us.ceair.com/en/flight-result.html",
        },
        "api_notes": {
            "access": "No public API; site uses heavy JS rendering",
            "env_flag": "window.ENVIRONMENT = 'production'",
            "cookie": "global_site_flag=en_US",
            "geo_restrictions": "Password-gated for TW, PH, RU, KR, JP regions",
            "analytics": "PT Engine (cjs.ptengine.com), account: 71d4c6a5",
        },
        "us_routes": {
            "PVG-LAX": {
                "flight_numbers": ["MU583 (PVG->LAX)", "MU586 (LAX->PVG)"],
                "frequency": "7x weekly (daily nonstop)",
                "aircraft": "Boeing 777",
                "nonstop": True,
                "flight_time": "~11h55m (eastbound), ~14h30m (westbound)",
                "departure_times": {
                    "PVG_depart": "Various, arrives LAX afternoon",
                    "LAX_depart": "11:00-13:45, arrives PVG next day",
                },
                "notes": "Primary MU transpacific to LA",
            },
            "PVG-SFO": {
                "flight_numbers": ["MU589 (PVG->SFO)", "MU590 (SFO->PVG)"],
                "frequency": "Daily nonstop",
                "aircraft": "Boeing 777-39P(ER)",
                "nonstop": True,
                "flight_time": "~11h10m-11h35m (eastbound), ~13h13m (westbound)",
                "departure_times": {
                    "PVG_depart": "12:10-14:05",
                },
                "distance_km": 9877,
                "notes": "Both MU and United operate nonstop PVG-SFO",
            },
        },
    },
}

# Pricing data gathered from multiple sources (Expedia, Travelocity, Kayak, Skyscanner, Momondo)
RESEARCHED_PRICING = {
    "CTU_to_LAX": {
        "airline": "China Southern (CZ) via CAN",
        "route_type": "One-stop via Guangzhou",
        "economy": {
            "one_way_from": 438,
            "round_trip_range": {"low": 692, "high": 909},
            "sample_fares": [
                {"depart": "2026-04-19", "return": "2026-05-17", "price": 724, "source": "Travelocity"},
            ],
            "currency": "USD",
        },
        "notes": "No CZ nonstop CTU-LAX. Sichuan Airlines (3U) has nonstop TFU-LAX 3x/week.",
    },
    "LAX_to_CTU": {
        "airline": "China Southern / Multiple carriers",
        "economy": {
            "one_way_range": {"low": 441, "high": 4278},
            "round_trip_range": {"low": 885, "high": 8109},
            "currency": "USD",
        },
        "notes": "June is peak demand - 25% price increase on average. Book 2+ months ahead for 10% savings.",
    },
    "PVG_to_LAX": {
        "airline": "China Eastern (MU) nonstop",
        "route_type": "Nonstop",
        "economy": {
            "one_way_from": 480,
            "round_trip_from": 928,
            "round_trip_range": {"low": 871, "high": 9974},
            "currency": "USD",
        },
        "notes": "MU583 daily nonstop, ~12h flight time",
    },
    "LAX_to_PVG": {
        "airline": "China Eastern (MU) nonstop",
        "route_type": "Nonstop",
        "economy": {
            "one_way_from": 632,
            "round_trip_range": {"low": 871, "high": 9974},
            "currency": "USD",
        },
        "notes": "MU586 daily nonstop. All carriers: flights from $353 one-way",
    },
    "PVG_to_SFO": {
        "airline": "China Eastern (MU) nonstop",
        "route_type": "Nonstop",
        "economy": {
            "one_way_from": 456,
            "round_trip_estimated": {"low": 900, "high": 1400},
            "currency": "USD",
        },
        "notes": "MU589/MU590 daily nonstop. United also operates nonstop.",
    },
    "CAN_to_LAX": {
        "airline": "China Southern (CZ) nonstop",
        "route_type": "Nonstop",
        "economy": {
            "one_way_from": 400,
            "round_trip_estimated": {"low": 800, "high": 1200},
            "sample_fares": [
                {"depart": "2026-04-11", "price_ow": 400, "source": "Expedia"},
            ],
            "currency": "USD",
        },
        "notes": "CZ327/CZ328 daily nonstop on Boeing 777",
    },
}


# ============================================================================
# SECTION 2: Google Flights Scraper (fast-flights)
# ============================================================================

def search_with_fast_flights(
    from_airport: str,
    to_airport: str,
    depart_date: str,
    return_date: Optional[str] = None,
    seat_class: str = "economy",
    adults: int = 1,
) -> dict:
    """
    Search flights using the fast-flights library (Google Flights scraper).

    This library encodes search parameters as Base64 protobuf and queries
    Google Flights directly, returning structured results.

    Requirements:
        pip install fast-flights

    Args:
        from_airport: IATA code (e.g., "CTU", "PVG")
        to_airport: IATA code (e.g., "LAX", "SFO")
        depart_date: "YYYY-MM-DD"
        return_date: "YYYY-MM-DD" (optional, for round-trip)
        seat_class: "economy", "premium-economy", "business", "first"
        adults: number of adult passengers

    Returns:
        dict with flight results or error information
    """
    try:
        from fast_flights import FlightData, Passengers, get_flights
        import fast_flights.core as _ff_core
        from fast_flights.primp import Client as _PrimpClient
    except ImportError:
        return {
            "error": "fast-flights not installed. Run: pip install fast-flights",
            "install_cmd": "pip install fast-flights",
        }

    try:
        # Patch the fetch function to bypass EU consent wall
        # by adding CONSENT cookie and gl=us parameter
        def _patched_fetch(params):
            client = _PrimpClient(impersonate="random", verify=False)
            params["gl"] = "us"
            res = client.get(
                "https://www.google.com/travel/flights",
                params=params,
                headers={
                    "Cookie": "CONSENT=YES+cb; SOCS=CAESEwgDEgk2MTcyODMzNTYaAmVuIAEaBgiA_LGJBQ",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            assert res.status_code == 200, f"{res.status_code} Result: {res.text_markdown[:500]}"
            return res

        _ff_core.fetch = _patched_fetch

        flight_data = [FlightData(date=depart_date, from_airport=from_airport, to_airport=to_airport)]

        if return_date:
            flight_data.append(FlightData(date=return_date, from_airport=to_airport, to_airport=from_airport))
            trip_type = "round-trip"
        else:
            trip_type = "one-way"

        result = get_flights(
            flight_data=flight_data,
            trip=trip_type,
            seat=seat_class,
            passengers=Passengers(adults=adults),
        )

        flights_data = []
        if hasattr(result, 'flights') and result.flights:
            for flight in result.flights:
                flight_info = {
                    "name": getattr(flight, 'name', 'N/A'),
                    "departure": getattr(flight, 'departure', 'N/A'),
                    "arrival": getattr(flight, 'arrival', 'N/A'),
                    "duration": getattr(flight, 'duration', 'N/A'),
                    "stops": getattr(flight, 'stops', 'N/A'),
                    "price": getattr(flight, 'price', 'N/A'),
                    "is_best": getattr(flight, 'is_best', False),
                }
                flights_data.append(flight_info)

        return {
            "success": True,
            "route": f"{from_airport}-{to_airport}",
            "depart_date": depart_date,
            "return_date": return_date,
            "trip_type": trip_type,
            "seat_class": seat_class,
            "current_price": getattr(result, 'current_price', 'N/A'),
            "flights_found": len(flights_data),
            "flights": flights_data,
        }

    except Exception as e:
        error_msg = str(e)
        # Truncate long error messages (Google Flights page dumps)
        if len(error_msg) > 300:
            error_msg = error_msg[:200] + "... [truncated - Google Flights page not rendering results for this route]"
        return {
            "error": error_msg,
            "route": f"{from_airport}-{to_airport}",
            "depart_date": depart_date,
            "return_date": return_date,
            "note": "Route may not be available on Google Flights for these dates, or results require JS rendering",
        }


# ============================================================================
# SECTION 3: CSAIR (China Southern) Direct API Probe
# ============================================================================

def probe_csair_api(from_city: str, to_city: str, depart_date: str, return_date: str = "") -> dict:
    """
    Attempt to use China Southern's B2C search API.

    Research findings:
    - The B2C system at b2c.csair.com uses session-based auth
    - The JS module `searchInit.js` calls `bussinessLogic.searchFlight()`
    - Parameters identified: segtype, fromcity, city1_code, tocity, city2_code,
      departuredate, returndate, adultnum, childnum, infantnum, searchtype, passengertype
    - The overseas site (oversea.csair.com) returns 403 for automated requests
    - The NDC API is partner-only (Level 4 certified)

    This function documents the known API structure even though direct access
    is blocked without a browser session.
    """
    import urllib.request
    import urllib.error

    api_structure = {
        "airline": "China Southern Airlines (CZ)",
        "approach": "B2C API probe",
        "known_endpoints": {
            "b2c_search": "https://b2c.csair.com/B2C40/newTrips/static/main/page/search/index.html",
            "overseas_search": "https://oversea.csair.com/tka/us/en/book/search",
            "mileage_search": "https://b2c.csair.com/B2C40/modules/bookingnew/mileage/search.html",
            "ip_locator": "https://www.csair.com/iplocator/getIpInfo",
        },
        "search_parameters": {
            "segtype": "round-trip or one-way",
            "fromcity": from_city,
            "city1_code": from_city,
            "tocity": to_city,
            "city2_code": to_city,
            "departuredate": depart_date,
            "returndate": return_date,
            "adultnum": 1,
            "childnum": 0,
            "infantnum": 0,
            "searchtype": "CASH",
            "passengertype": "ADT",
        },
    }

    # Try the IP locator endpoint (one that actually responds)
    try:
        req = urllib.request.Request(
            "https://www.csair.com/iplocator/getIpInfo",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            ip_data = json.loads(resp.read().decode('utf-8'))
            api_structure["ip_locator_response"] = ip_data
            api_structure["ip_locator_status"] = "accessible"
    except Exception as e:
        api_structure["ip_locator_status"] = f"error: {str(e)}"

    # Try the overseas booking endpoint
    try:
        req = urllib.request.Request(
            "https://oversea.csair.com/tka/us/en/book/search",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            api_structure["overseas_booking_status"] = f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        api_structure["overseas_booking_status"] = f"HTTP {e.code} - {e.reason} (requires browser session)"
    except Exception as e:
        api_structure["overseas_booking_status"] = f"error: {str(e)}"

    return api_structure


# ============================================================================
# SECTION 4: CEAIR (China Eastern) Direct API Probe
# ============================================================================

def probe_ceair_api(from_city: str, to_city: str, depart_date: str, return_date: str = "") -> dict:
    """
    Attempt to use China Eastern's search API.

    Research findings:
    - The US site (us.ceair.com) uses heavy JavaScript rendering
    - Booking page: us.ceair.com/en/booking-new.html
    - Flight results page pattern: us.ceair.com/en/flight-list.html?oriCode=PVG&desCode=LAX&...
    - The flight-list.html URL returns 404 (requires JS rendering)
    - Site sets cookie: global_site_flag=en_US
    - Some regions are geo-restricted with password gates
    """
    import urllib.request
    import urllib.error

    api_structure = {
        "airline": "China Eastern Airlines (MU)",
        "approach": "Website API probe",
        "known_endpoints": {
            "booking_page": "https://us.ceair.com/en/booking-new.html",
            "flight_list_pattern": (
                f"https://us.ceair.com/en/flight-list.html?"
                f"oriCode={from_city}&desCode={to_city}&oriDate={depart_date}"
                f"&retDate={return_date}&adtCount=1&chdCount=0&infCount=0"
                f"&tripType=RT&directFlight=false"
            ),
            "flight_status": "https://us.ceair.com/en/flight-result.html",
            "alt_au_site": "https://oa.ceair.com/au/en/",
        },
        "search_parameters": {
            "oriCode": from_city,
            "desCode": to_city,
            "oriDate": depart_date,
            "retDate": return_date,
            "adtCount": 1,
            "chdCount": 0,
            "infCount": 0,
            "tripType": "RT",
            "directFlight": False,
        },
    }

    # Try the main US site
    try:
        req = urllib.request.Request(
            "https://us.ceair.com/en/",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html",
                "Accept-Language": "en-US,en;q=0.9",
                "Cookie": "global_site_flag=en_US",
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            api_structure["us_site_status"] = f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        api_structure["us_site_status"] = f"HTTP {e.code} - requires browser/JS"
    except Exception as e:
        api_structure["us_site_status"] = f"error: {str(e)}"

    return api_structure


# ============================================================================
# SECTION 5: Amadeus API Integration (requires free signup)
# ============================================================================

def search_with_amadeus(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: Optional[str] = None,
    adults: int = 1,
    travel_class: str = "ECONOMY",
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> dict:
    """
    Search flights using the Amadeus Self-Service API.

    To use this:
    1. Sign up free at https://developers.amadeus.com/
    2. Create an app to get client_id and client_secret
    3. pip install amadeus
    4. Set AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET env vars
       or pass them as parameters

    The test environment provides free monthly API call quotas.
    Supports 400+ airlines including CZ (China Southern) and MU (China Eastern).
    """
    client_id = client_id or os.environ.get("AMADEUS_CLIENT_ID")
    client_secret = client_secret or os.environ.get("AMADEUS_CLIENT_SECRET")

    if not client_id or not client_secret:
        return {
            "error": "Amadeus API credentials not configured",
            "setup_instructions": {
                "step1": "Sign up free at https://developers.amadeus.com/",
                "step2": "Create an application in your workspace",
                "step3": "pip install amadeus",
                "step4": "Set env vars AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET",
                "note": "Test environment has free monthly quotas",
            },
        }

    try:
        from amadeus import Client, ResponseError
    except ImportError:
        return {"error": "amadeus not installed. Run: pip install amadeus"}

    try:
        amadeus = Client(client_id=client_id, client_secret=client_secret)

        params = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": depart_date,
            "adults": adults,
            "travelClass": travel_class,
            "max": 20,
        }
        if return_date:
            params["returnDate"] = return_date

        response = amadeus.shopping.flight_offers_search.get(**params)

        offers = []
        for offer in response.data:
            offer_info = {
                "id": offer.get("id"),
                "price": offer.get("price", {}).get("grandTotal"),
                "currency": offer.get("price", {}).get("currency"),
                "segments": [],
            }
            for itin in offer.get("itineraries", []):
                for seg in itin.get("segments", []):
                    offer_info["segments"].append({
                        "carrier": seg.get("carrierCode"),
                        "flight_number": f"{seg.get('carrierCode')}{seg.get('number')}",
                        "departure": seg.get("departure", {}).get("iataCode"),
                        "departure_time": seg.get("departure", {}).get("at"),
                        "arrival": seg.get("arrival", {}).get("iataCode"),
                        "arrival_time": seg.get("arrival", {}).get("at"),
                        "duration": seg.get("duration"),
                        "cabin": seg.get("cabin", "N/A"),
                    })
            offers.append(offer_info)

        return {
            "success": True,
            "source": "Amadeus Self-Service API",
            "route": f"{origin}-{destination}",
            "depart_date": depart_date,
            "return_date": return_date,
            "travel_class": travel_class,
            "offers_found": len(offers),
            "offers": offers,
        }

    except Exception as e:
        return {"error": str(e), "source": "Amadeus API"}


# ============================================================================
# SECTION 6: Main Search Orchestrator
# ============================================================================

def run_all_searches() -> dict:
    """
    Run all available search methods for the target routes.
    """
    results = {
        "search_timestamp": datetime.datetime.now().isoformat(),
        "target_routes": [
            "CTU -> LAX (Chengdu to Los Angeles) round-trip, May-June 2026",
            "PVG -> LAX (Shanghai to Los Angeles) round-trip, May-June 2026",
            "PVG -> SFO (Shanghai to San Francisco) round-trip, May-June 2026",
        ],
        "airline_reference": CHINESE_AIRLINE_ROUTES,
        "researched_pricing": RESEARCHED_PRICING,
        "api_probes": {},
        "google_flights_results": {},
        "amadeus_results": {},
    }

    # Target search parameters
    searches = [
        {"from": "CTU", "to": "LAX", "depart": "2026-05-15", "return": "2026-06-15", "label": "CTU-LAX May-Jun"},
        {"from": "PVG", "to": "LAX", "depart": "2026-05-15", "return": "2026-06-15", "label": "PVG-LAX May-Jun"},
        {"from": "PVG", "to": "SFO", "depart": "2026-05-15", "return": "2026-06-15", "label": "PVG-SFO May-Jun"},
        {"from": "CTU", "to": "LAX", "depart": "2026-06-01", "return": "2026-06-30", "label": "CTU-LAX Jun"},
        {"from": "PVG", "to": "LAX", "depart": "2026-06-01", "return": "2026-06-30", "label": "PVG-LAX Jun"},
        {"from": "PVG", "to": "SFO", "depart": "2026-06-01", "return": "2026-06-30", "label": "PVG-SFO Jun"},
        # Also search the CZ hub route directly
        {"from": "CAN", "to": "LAX", "depart": "2026-05-15", "return": "2026-06-15", "label": "CAN-LAX May-Jun (CZ nonstop hub)"},
    ]

    # --- API Probes ---
    print("=" * 60)
    print("PROBING AIRLINE DIRECT APIs")
    print("=" * 60)

    print("\n[1/2] Probing China Southern (csair.com)...")
    results["api_probes"]["china_southern"] = probe_csair_api("CTU", "LAX", "2026-05-15", "2026-06-15")
    print(f"  IP Locator: {results['api_probes']['china_southern'].get('ip_locator_status', 'N/A')}")
    print(f"  Overseas Booking: {results['api_probes']['china_southern'].get('overseas_booking_status', 'N/A')}")

    print("\n[2/2] Probing China Eastern (ceair.com)...")
    results["api_probes"]["china_eastern"] = probe_ceair_api("PVG", "LAX", "2026-05-15", "2026-06-15")
    print(f"  US Site: {results['api_probes']['china_eastern'].get('us_site_status', 'N/A')}")

    # --- Google Flights via fast-flights ---
    print("\n" + "=" * 60)
    print("SEARCHING GOOGLE FLIGHTS (fast-flights library)")
    print("=" * 60)

    for search in searches:
        label = search["label"]
        print(f"\n  Searching: {label}...")
        result = search_with_fast_flights(
            from_airport=search["from"],
            to_airport=search["to"],
            depart_date=search["depart"],
            return_date=search["return"],
            seat_class="economy",
        )
        results["google_flights_results"][label] = result

        if "error" in result:
            print(f"    Error: {result['error']}")
            if "not installed" in str(result.get("error", "")):
                print("    Skipping remaining Google Flights searches (library not available)")
                for remaining in searches[searches.index(search) + 1:]:
                    results["google_flights_results"][remaining["label"]] = {
                        "skipped": True,
                        "reason": "fast-flights library not installed",
                    }
                break
        else:
            print(f"    Found {result.get('flights_found', 0)} flights")
            if result.get('flights'):
                for f in result['flights'][:3]:
                    print(f"      {f.get('name', 'N/A')} | {f.get('price', 'N/A')} | {f.get('stops', 'N/A')} stops")

        time.sleep(1)  # Rate limiting

    # --- Amadeus API ---
    print("\n" + "=" * 60)
    print("SEARCHING AMADEUS API")
    print("=" * 60)

    for search in searches[:3]:  # Just the main 3 routes
        label = search["label"]
        print(f"\n  Searching Amadeus: {label}...")
        result = search_with_amadeus(
            origin=search["from"],
            destination=search["to"],
            depart_date=search["depart"],
            return_date=search["return"],
        )
        results["amadeus_results"][label] = result

        if "error" in result:
            print(f"    {result['error']}")
            if "credentials" in str(result.get("error", "")).lower():
                print("    Skipping remaining Amadeus searches")
                for remaining in searches[1:3]:
                    if remaining["label"] not in results["amadeus_results"]:
                        results["amadeus_results"][remaining["label"]] = {
                            "skipped": True,
                            "reason": "Amadeus credentials not configured",
                        }
                break
        else:
            print(f"    Found {result.get('offers_found', 0)} offers")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("SEARCH SUMMARY")
    print("=" * 60)
    print_summary(results)

    return results


def print_summary(results: dict):
    """Print a human-readable summary of all findings."""

    print("\n--- RESEARCHED PRICING (from Expedia/Travelocity/Kayak/Skyscanner) ---\n")
    for route, data in results["researched_pricing"].items():
        airline = data.get("airline", "N/A")
        eco = data.get("economy", {})
        rt_range = eco.get("round_trip_range", eco.get("round_trip_estimated", {}))
        ow_from = eco.get("one_way_from", "N/A")
        rt_from = eco.get("round_trip_from", "N/A")
        print(f"  {route}:")
        print(f"    Airline: {airline}")
        print(f"    One-way from: ${ow_from}")
        if rt_range:
            print(f"    Round-trip: ${rt_range.get('low', 'N/A')} - ${rt_range.get('high', 'N/A')}")
        if rt_from != "N/A":
            print(f"    Round-trip from: ${rt_from}")
        print(f"    Notes: {data.get('notes', '')}")
        print()

    print("--- ROUTE DETAILS ---\n")
    for airline_key, airline_data in results["airline_reference"].items():
        code = airline_data["iata_code"]
        print(f"  {airline_key.upper()} ({code}):")
        for route_key, route_data in airline_data["us_routes"].items():
            nonstop = "NONSTOP" if route_data.get("nonstop") else "CONNECTING"
            flights = ", ".join(route_data.get("flight_numbers", []))
            print(f"    {route_key} [{nonstop}]: {flights}")
            print(f"      Frequency: {route_data.get('frequency', 'N/A')}")
            if route_data.get("aircraft"):
                print(f"      Aircraft: {route_data['aircraft']}")
            if route_data.get("flight_time"):
                print(f"      Flight time: {route_data['flight_time']}")
        print()

    print("--- API ACCESS STATUS ---\n")
    for airline, probe in results.get("api_probes", {}).items():
        print(f"  {airline}:")
        for key, val in probe.items():
            if key not in ("known_endpoints", "search_parameters"):
                print(f"    {key}: {val}")
        print()


# ============================================================================
# SECTION 7: Entry Point
# ============================================================================

if __name__ == "__main__":
    print("Chinese Airlines Direct Flight Search")
    print("=" * 60)
    print(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Target: CTU/PVG -> LAX/SFO, May-June 2026")
    print(f"Airlines: China Southern (CZ), China Eastern (MU)")
    print("=" * 60)

    results = run_all_searches()

    # Save results
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chinese_airlines_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nResults saved to: {output_path}")
    print("Done.")
