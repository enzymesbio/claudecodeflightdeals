import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

"""
Search for business class flights from Jakarta (CGK) using multiple APIs:
1. Google Flights (via fast_flights scraper - works without API key)
2. Amadeus Self-Service API (test environment)
3. Kiwi.com / Tequila API
4. Aviationstack API
5. FlightAPI.io
6. SerpAPI Google Flights
7. Skyscanner via RapidAPI
8. Travelpayouts / Aviasales
9. Direct airline API probes
10. Trip.com / Ctrip API
"""

import requests
import json
import traceback
from datetime import datetime
from urllib.parse import urlencode

# ============================================================
# Common settings
# ============================================================
ORIGIN = "CGK"
DESTINATIONS = ["LHR", "LAX"]
DEPARTURE_DATE = "2026-05-04"
TRAVEL_CLASS = "BUSINESS"
ADULTS = 1
CURRENCY = "USD"
MAX_RESULTS = 10

all_results = []

def print_separator(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

def format_price(price, currency="USD"):
    if price is None:
        return "N/A"
    try:
        return f"{currency} {float(str(price).replace(',','').replace('$','')):,.2f}"
    except (ValueError, TypeError):
        return f"{currency} {price}"


# ============================================================
# 1. GOOGLE FLIGHTS (via fast_flights scraper - NO API key needed)
# ============================================================
def search_google_flights_scraper():
    print_separator("1. GOOGLE FLIGHTS (via fast_flights scraper + Playwright)")
    print("  This method scrapes Google Flights directly - no API key required.")
    print("  Uses local Playwright browser to bypass consent walls.\n")

    try:
        from fast_flights import FlightData, Passengers, get_flights
    except ImportError:
        print("  fast_flights not installed. Run: pip install fast_flights")
        return

    for dest in DESTINATIONS:
        try:
            print(f"  Searching {ORIGIN} -> {dest} on {DEPARTURE_DATE} (Business class)...")

            # Use 'local' fetch_mode which uses local Playwright to bypass
            # Google's cookie consent wall (affects EU/non-US servers)
            result = get_flights(
                flight_data=[
                    FlightData(
                        date=DEPARTURE_DATE,
                        from_airport=ORIGIN,
                        to_airport=dest,
                    )
                ],
                trip="one-way",
                seat="business",
                passengers=Passengers(adults=ADULTS),
                max_stops=2,
                fetch_mode="local",
            )

            if result and result.flights:
                price_level = getattr(result, 'current_price', '?')
                print(f"  SUCCESS! Found {len(result.flights)} flights. "
                      f"Current price level: {price_level}\n")

                for i, flight in enumerate(result.flights):
                    try:
                        price_str = flight.price
                        price_num = None
                        if price_str:
                            # Extract numeric price (could be EUR or USD symbol)
                            price_clean = str(price_str)
                            for ch in ['$', ',', 'USD', 'EUR', '\u20ac', '\u00a3']:
                                price_clean = price_clean.replace(ch, '')
                            price_clean = price_clean.strip()
                            try:
                                price_num = float(price_clean)
                            except ValueError:
                                pass

                        # Detect currency from price string
                        detected_currency = "USD"
                        if price_str:
                            if '\u20ac' in str(price_str) or 'EUR' in str(price_str).upper():
                                detected_currency = "EUR"
                            elif '\u00a3' in str(price_str) or 'GBP' in str(price_str).upper():
                                detected_currency = "GBP"

                        result_entry = {
                            "source": "Google Flights",
                            "route": f"{ORIGIN}->{dest}",
                            "price": price_num,
                            "price_display": str(price_str),
                            "currency": detected_currency,
                            "airline": flight.name,
                            "departure_time": flight.departure,
                            "arrival_time": flight.arrival,
                            "arrival_time_ahead": flight.arrival_time_ahead,
                            "duration": flight.duration,
                            "stops": flight.stops,
                            "delay": flight.delay,
                            "class": "Business",
                            "is_best": flight.is_best,
                        }
                        all_results.append(result_entry)

                        best_tag = " [BEST]" if flight.is_best else ""
                        delay_tag = f" (Delay: {flight.delay})" if flight.delay else ""
                        ahead_tag = f" (+{flight.arrival_time_ahead})" if flight.arrival_time_ahead else ""
                        stops_str = "Nonstop" if flight.stops == 0 else f"{flight.stops} stop{'s' if flight.stops > 1 else ''}"

                        print(f"    #{i+1}: {price_str:>8s} | "
                              f"{flight.name:40s} | "
                              f"Dep {flight.departure} -> Arr {flight.arrival}{ahead_tag} | "
                              f"{flight.duration:20s} | "
                              f"{stops_str}{best_tag}{delay_tag}")
                    except Exception as e:
                        print(f"    #{i+1}: Error parsing flight: {e}")
                        print(f"         Raw: {flight}")
            else:
                print(f"  No flights found for {ORIGIN}->{dest}")
                if result:
                    print(f"  Result: {result}")

            print()
        except Exception as e:
            print(f"  Error searching {ORIGIN}->{dest}: {type(e).__name__}: {e}")
            traceback.print_exc()
            print()


# ============================================================
# 2. AMADEUS SELF-SERVICE API (Test Environment)
# ============================================================
def search_amadeus():
    print_separator("2. AMADEUS SELF-SERVICE API (Test Environment)")

    test_credentials = []

    # Check environment variables first
    env_id = os.environ.get("AMADEUS_API_KEY") or os.environ.get("AMADEUS_CLIENT_ID")
    env_secret = os.environ.get("AMADEUS_API_SECRET") or os.environ.get("AMADEUS_CLIENT_SECRET")
    if env_id and env_secret:
        test_credentials.append({"client_id": env_id, "client_secret": env_secret})
        print(f"  Found Amadeus credentials in environment variables.")
    else:
        print("  No Amadeus credentials found in environment.")
        print("  Set AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET to use this API.")
        print("  Free signup: https://developers.amadeus.com/ (test tier: 500 free calls/month)")
        return

    auth_url = "https://test.api.amadeus.com/v1/security/oauth2/token"
    search_url = "https://test.api.amadeus.com/v2/shopping/flight-offers"

    for cred in test_credentials:
        try:
            print(f"  Attempting authentication...")
            auth_resp = requests.post(auth_url, data={
                "grant_type": "client_credentials",
                "client_id": cred["client_id"],
                "client_secret": cred["client_secret"],
            }, timeout=15)

            if auth_resp.status_code == 200:
                token = auth_resp.json().get("access_token")
                print(f"  Auth SUCCESS! Token obtained.")

                for dest in DESTINATIONS:
                    print(f"\n  Searching {ORIGIN} -> {dest} on {DEPARTURE_DATE}...")
                    params = {
                        "originLocationCode": ORIGIN,
                        "destinationLocationCode": dest,
                        "departureDate": DEPARTURE_DATE,
                        "adults": ADULTS,
                        "travelClass": TRAVEL_CLASS,
                        "currencyCode": CURRENCY,
                        "max": MAX_RESULTS,
                    }
                    headers = {"Authorization": f"Bearer {token}"}
                    resp = requests.get(search_url, params=params, headers=headers, timeout=30)

                    if resp.status_code == 200:
                        data = resp.json()
                        offers = data.get("data", [])
                        print(f"  Found {len(offers)} offers for {ORIGIN}->{dest}")
                        for i, offer in enumerate(offers):
                            price = offer.get("price", {})
                            total = price.get("grandTotal") or price.get("total")
                            curr = price.get("currency", CURRENCY)
                            segments = []
                            for itin in offer.get("itineraries", []):
                                for seg in itin.get("segments", []):
                                    carrier = seg.get("carrierCode", "??")
                                    flight_num = seg.get("number", "?")
                                    dep = seg.get("departure", {})
                                    arr = seg.get("arrival", {})
                                    segments.append(
                                        f"{carrier}{flight_num} {dep.get('iataCode','?')}->{arr.get('iataCode','?')} "
                                        f"dep {dep.get('at','?')}"
                                    )
                            duration = offer.get("itineraries", [{}])[0].get("duration", "?")
                            result = {
                                "source": "Amadeus",
                                "route": f"{ORIGIN}->{dest}",
                                "price": total,
                                "currency": curr,
                                "segments": segments,
                                "duration": duration,
                                "class": TRAVEL_CLASS,
                            }
                            all_results.append(result)
                            print(f"    #{i+1}: {format_price(total, curr)} | "
                                  f"{' / '.join(segments)} | Duration: {duration}")
                    else:
                        print(f"  Search failed ({resp.status_code}): {resp.text[:300]}")
                return
            else:
                print(f"  Auth failed ({auth_resp.status_code}): {auth_resp.text[:200]}")
        except Exception as e:
            print(f"  Error: {e}")


# ============================================================
# 3. KIWI.COM / TEQUILA API
# ============================================================
def search_kiwi():
    print_separator("3. KIWI.COM / TEQUILA API")

    api_key = os.environ.get("KIWI_API_KEY") or os.environ.get("TEQUILA_API_KEY")
    if not api_key:
        print("  No KIWI_API_KEY or TEQUILA_API_KEY found in environment.")
        print("  Free signup: https://tequila.kiwi.com/")
        return

    search_url = "https://api.tequila.kiwi.com/v2/search"
    headers = {"apikey": api_key}

    for dest in DESTINATIONS:
        dep_date_formatted = datetime.strptime(DEPARTURE_DATE, "%Y-%m-%d").strftime("%d/%m/%Y")
        params = {
            "fly_from": ORIGIN,
            "fly_to": dest,
            "date_from": dep_date_formatted,
            "date_to": dep_date_formatted,
            "selected_cabins": "C",
            "curr": CURRENCY,
            "adults": ADULTS,
            "limit": MAX_RESULTS,
            "sort": "price",
        }

        try:
            print(f"  Searching {ORIGIN}->{dest}...")
            resp = requests.get(search_url, params=params, headers=headers, timeout=20)

            if resp.status_code == 200:
                data = resp.json()
                flights = data.get("data", [])
                print(f"  Found {len(flights)} flights for {ORIGIN}->{dest}")
                for i, flight in enumerate(flights[:MAX_RESULTS]):
                    price = flight.get("price")
                    airlines = flight.get("airlines", [])
                    route_parts = flight.get("route", [])
                    segments = []
                    for r in route_parts:
                        segments.append(
                            f"{r.get('airline','?')}{r.get('flight_no','?')} "
                            f"{r.get('flyFrom','?')}->{r.get('flyTo','?')} "
                            f"dep {r.get('local_departure','?')[:16]}"
                        )
                    duration_sec = flight.get("duration", {}).get("total", 0)
                    duration_h = duration_sec // 3600
                    duration_m = (duration_sec % 3600) // 60
                    result = {
                        "source": "Kiwi.com",
                        "route": f"{ORIGIN}->{dest}",
                        "price": price,
                        "currency": CURRENCY,
                        "segments": segments,
                        "duration": f"{duration_h}h{duration_m}m",
                        "airlines": airlines,
                        "class": "Business",
                    }
                    all_results.append(result)
                    print(f"    #{i+1}: {format_price(price)} | "
                          f"{', '.join(airlines)} | {' / '.join(segments)} | "
                          f"{duration_h}h{duration_m}m")
            else:
                print(f"  Response {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"  Error: {e}")


# ============================================================
# 4. AVIATIONSTACK API
# ============================================================
def search_aviationstack():
    print_separator("4. AVIATIONSTACK API")

    api_key = os.environ.get("AVIATIONSTACK_API_KEY")
    if not api_key:
        print("  No AVIATIONSTACK_API_KEY found in environment.")
        print("  Note: Free tier only supports flight tracking, not price search.")
        print("  Free signup: https://aviationstack.com/ (100 req/month)")
        return

    url = "http://api.aviationstack.com/v1/flights"
    params = {
        "access_key": api_key,
        "dep_iata": ORIGIN,
        "flight_status": "scheduled",
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            flights = data.get("data", [])
            print(f"  Found {len(flights)} scheduled flights from {ORIGIN}")
            for f in flights[:5]:
                airline = f.get("airline", {}).get("name", "?")
                dep = f.get("departure", {})
                arr = f.get("arrival", {})
                print(f"    {airline}: {dep.get('iata','?')}->{arr.get('iata','?')} "
                      f"at {dep.get('scheduled','?')}")
        else:
            print(f"  Error ({resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        print(f"  Error: {e}")


# ============================================================
# 5. FLIGHTAPI.IO
# ============================================================
def search_flightapi():
    print_separator("5. FLIGHTAPI.IO")

    api_key = os.environ.get("FLIGHTAPI_KEY")
    if not api_key:
        print("  No FLIGHTAPI_KEY found in environment.")
        print("  Free trial: https://www.flightapi.io/")
        return

    for dest in DESTINATIONS:
        try:
            url = f"https://api.flightapi.io/onewaytrip/{api_key}/{ORIGIN}/{dest}/{DEPARTURE_DATE}/1/0/0/Business/{CURRENCY}"
            print(f"  Trying {ORIGIN}->{dest}...")
            resp = requests.get(url, timeout=20)

            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and data.get("error"):
                    print(f"  API error: {data.get('error', data.get('message', 'Unknown'))}")
                    continue

                fares = data.get("fares", []) if isinstance(data, dict) else []
                if fares:
                    print(f"  Found {len(fares)} fares for {ORIGIN}->{dest}")
                    for i, fare in enumerate(fares[:MAX_RESULTS]):
                        price_info = fare.get("price", {})
                        total = price_info.get("totalAmount") or price_info.get("amount")
                        curr = price_info.get("currencyCode", CURRENCY)
                        result = {
                            "source": "FlightAPI.io",
                            "route": f"{ORIGIN}->{dest}",
                            "price": total,
                            "currency": curr,
                            "class": "Business",
                        }
                        all_results.append(result)
                        print(f"    #{i+1}: {format_price(total, curr)}")
                else:
                    print(f"  Response keys: {list(data.keys())[:10]}")
            else:
                print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"  Error: {e}")


# ============================================================
# 6. GOOGLE FLIGHTS (via SerpAPI)
# ============================================================
def search_google_flights_api():
    print_separator("6. GOOGLE FLIGHTS (via SerpAPI)")

    serpapi_key = os.environ.get("SERPAPI_KEY") or os.environ.get("SERPAPI_API_KEY")
    if not serpapi_key:
        print("  No SERPAPI_KEY found in environment.")
        print("  Free trial: https://serpapi.com/ (100 searches/month)")
        return

    for dest in DESTINATIONS:
        try:
            params = {
                "engine": "google_flights",
                "departure_id": ORIGIN,
                "arrival_id": dest,
                "outbound_date": DEPARTURE_DATE,
                "travel_class": 2,
                "currency": CURRENCY,
                "type": 2,
                "api_key": serpapi_key,
            }
            print(f"  Searching {ORIGIN}->{dest}...")
            resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                flights = data.get("best_flights", []) + data.get("other_flights", [])
                print(f"  Found {len(flights)} options for {ORIGIN}->{dest}")
                for i, group in enumerate(flights[:MAX_RESULTS]):
                    price = group.get("price")
                    flight_legs = group.get("flights", [])
                    airlines = [f.get("airline", "?") for f in flight_legs]
                    result = {
                        "source": "Google Flights (SerpAPI)",
                        "route": f"{ORIGIN}->{dest}",
                        "price": price,
                        "currency": CURRENCY,
                        "airlines": airlines,
                        "class": "Business",
                    }
                    all_results.append(result)
                    print(f"    #{i+1}: {format_price(price)} | {', '.join(airlines)}")
            else:
                print(f"  Error ({resp.status_code}): {resp.text[:200]}")
        except Exception as e:
            print(f"  Error: {e}")


# ============================================================
# 7. SKYSCANNER via RapidAPI
# ============================================================
def search_skyscanner_rapid():
    print_separator("7. SKYSCANNER via RapidAPI")

    rapid_key = os.environ.get("RAPIDAPI_KEY") or os.environ.get("X_RAPIDAPI_KEY")
    if not rapid_key:
        print("  No RAPIDAPI_KEY found in environment.")
        print("  Free signup: https://rapidapi.com/ (freemium)")
        return

    headers = {
        "X-RapidAPI-Key": rapid_key,
        "X-RapidAPI-Host": "sky-scanner3.p.rapidapi.com",
    }

    for dest in DESTINATIONS:
        try:
            print(f"  Searching {ORIGIN}->{dest}...")
            url = "https://sky-scanner3.p.rapidapi.com/flights/search-one-way"
            params = {
                "fromEntityId": ORIGIN,
                "toEntityId": dest,
                "departDate": DEPARTURE_DATE,
                "cabinClass": "business",
                "currency": CURRENCY,
                "adults": ADULTS,
            }
            resp = requests.get(url, headers=headers, params=params, timeout=20)

            if resp.status_code == 200:
                data = resp.json()
                itineraries = data.get("data", {}).get("itineraries", [])
                print(f"  Found {len(itineraries)} itineraries for {ORIGIN}->{dest}")
                for i, itin in enumerate(itineraries[:MAX_RESULTS]):
                    price_raw = itin.get("price", {}).get("raw") or itin.get("price", {}).get("formatted")
                    legs = itin.get("legs", [])
                    carriers = []
                    for leg in legs:
                        for carrier in leg.get("carriers", {}).get("marketing", []):
                            carriers.append(carrier.get("name", "?"))
                    result = {
                        "source": "Skyscanner (RapidAPI)",
                        "route": f"{ORIGIN}->{dest}",
                        "price": price_raw,
                        "currency": CURRENCY,
                        "airlines": carriers,
                        "class": "Business",
                    }
                    all_results.append(result)
                    print(f"    #{i+1}: {format_price(price_raw)} | {', '.join(carriers)}")
            else:
                print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"  Error: {e}")


# ============================================================
# 8. TRAVELPAYOUTS / AVIASALES
# ============================================================
def search_travelpayouts():
    print_separator("8. TRAVELPAYOUTS / AVIASALES")

    token = os.environ.get("TRAVELPAYOUTS_TOKEN", "")
    if not token:
        print("  No TRAVELPAYOUTS_TOKEN found in environment.")
        print("  Free signup: https://travelpayouts.com/")
        return

    for dest in DESTINATIONS:
        try:
            url = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
            params = {
                "origin": ORIGIN,
                "destination": dest,
                "departure_at": DEPARTURE_DATE,
                "one_way": "true",
                "trip_class": 1,
                "currency": CURRENCY.lower(),
                "sorting": "price",
                "limit": MAX_RESULTS,
                "token": token,
            }

            print(f"  Trying {ORIGIN}->{dest}...")
            resp = requests.get(url, params=params, timeout=20,
                              headers={"X-Access-Token": token})

            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    tickets = data.get("data", [])
                    print(f"  Found {len(tickets)} price records for {ORIGIN}->{dest}")
                    for i, ticket in enumerate(tickets[:MAX_RESULTS]):
                        price = ticket.get("price")
                        airline = ticket.get("airline")
                        dep_date = ticket.get("departure_at", "?")
                        transfers = ticket.get("transfers", 0)
                        result = {
                            "source": "Travelpayouts",
                            "route": f"{ORIGIN}->{dest}",
                            "price": price,
                            "currency": CURRENCY,
                            "airline": airline,
                            "departure": dep_date,
                            "transfers": transfers,
                            "class": "Business",
                        }
                        all_results.append(result)
                        print(f"    #{i+1}: {format_price(price)} | {airline} | "
                              f"Transfers: {transfers} | Dep: {dep_date}")
                else:
                    print(f"  API returned: {data.get('error', 'unknown')}")
            else:
                print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"  Error: {e}")


# ============================================================
# 9. DIRECT AIRLINE API PROBES
# ============================================================
def search_airline_direct():
    print_separator("9. DIRECT AIRLINE API PROBES")

    airlines_to_try = [
        {"name": "Garuda Indonesia", "url": "https://www.garuda-indonesia.com/api/flight/search"},
        {"name": "Singapore Airlines", "url": "https://www.singaporeair.com/api/flight-search"},
        {"name": "Qatar Airways", "url": "https://www.qatarairways.com/api/offer/search"},
    ]

    for airline in airlines_to_try:
        try:
            print(f"  Probing {airline['name']}...")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }
            resp = requests.get(airline["url"], headers=headers, timeout=10, allow_redirects=True)
            print(f"    Response: {resp.status_code} (Content-Type: {resp.headers.get('Content-Type', '?')[:50]})")
            if resp.status_code == 200 and 'json' in resp.headers.get('Content-Type', ''):
                print(f"    Data: {resp.text[:200]}")
        except requests.exceptions.ConnectionError:
            print(f"    Connection failed (endpoint may not exist)")
        except requests.exceptions.ReadTimeout:
            print(f"    Timeout (server did not respond in time)")
        except Exception as e:
            print(f"    Error: {type(e).__name__}: {e}")


# ============================================================
# 10. TRIP.COM / CTRIP API
# ============================================================
def search_trip_com():
    print_separator("10. TRIP.COM FLIGHT SEARCH API")

    for dest in DESTINATIONS:
        try:
            print(f"  Trying Trip.com API for {ORIGIN}->{dest}...")
            url = "https://flights.ctrip.com/international/search/api/search/batchSearch"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Origin": "https://flights.ctrip.com",
                "Referer": "https://flights.ctrip.com/",
            }
            payload = {
                "flightWay": "Oneway",
                "classType": "C",
                "hasChild": False,
                "hasBaby": False,
                "searchIndex": 1,
                "airportParams": [{
                    "dcity": ORIGIN,
                    "acity": dest,
                    "dcityname": "Jakarta",
                    "acityname": "London" if dest == "LHR" else "Los Angeles",
                    "date": DEPARTURE_DATE,
                }],
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=20)

            if resp.status_code == 200:
                data = resp.json()
                if data.get("data"):
                    flight_list = data["data"].get("flightItineraryList", [])
                    print(f"  Found {len(flight_list)} flights {ORIGIN}->{dest}")
                    for i, flight in enumerate(flight_list[:MAX_RESULTS]):
                        price_list = flight.get("priceList", [])
                        if price_list:
                            price = price_list[0].get("adultPrice", 0)
                            currency = price_list[0].get("currency", CURRENCY)
                        else:
                            price = "?"
                            currency = CURRENCY
                        leg = flight.get("flightSegments", [{}])[0]
                        segments_info = leg.get("flightList", [])
                        seg_strs = []
                        for s in segments_info:
                            seg_strs.append(
                                f"{s.get('airlineCode','?')}{s.get('flightNo','?')} "
                                f"{s.get('departureAirportCode','?')}->{s.get('arrivalAirportCode','?')}"
                            )
                        result = {
                            "source": "Trip.com",
                            "route": f"{ORIGIN}->{dest}",
                            "price": price,
                            "currency": currency,
                            "segments": seg_strs,
                            "class": "Business",
                        }
                        all_results.append(result)
                        print(f"    #{i+1}: {format_price(price, currency)} | {' / '.join(seg_strs)}")
                else:
                    print(f"  No data in response. Status: {data.get('status', '?')}")
            else:
                print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"  Error: {type(e).__name__}: {e}")


# ============================================================
# MAIN EXECUTION
# ============================================================
if __name__ == "__main__":
    print(f"{'#'*70}")
    print(f"#  BUSINESS CLASS FLIGHT SEARCH: {ORIGIN} (Jakarta)")
    print(f"#  Destinations: {', '.join(DESTINATIONS)}")
    print(f"#  Date: {DEPARTURE_DATE}")
    print(f"#  Class: {TRAVEL_CLASS}")
    print(f"#  Search time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*70}")

    # Run all search methods - Google Flights scraper first (most likely to work)
    search_google_flights_scraper()
    search_amadeus()
    search_kiwi()
    search_aviationstack()
    search_flightapi()
    search_google_flights_api()
    search_skyscanner_rapid()
    search_travelpayouts()
    search_airline_direct()
    search_trip_com()

    # ============================================================
    # SUMMARY
    # ============================================================
    print_separator("SUMMARY OF ALL RESULTS")

    if all_results:
        # Sort by price where possible
        priced_results = []
        unpriced_results = []
        for r in all_results:
            p = r.get("price")
            if p is not None:
                try:
                    float(str(p).replace(',', '').replace('$', ''))
                    priced_results.append(r)
                except (ValueError, TypeError):
                    unpriced_results.append(r)
            else:
                unpriced_results.append(r)

        # Group results by route
        for dest in DESTINATIONS:
            route = f"{ORIGIN}->{dest}"
            route_results = [r for r in priced_results if r.get("route") == route]
            if route_results:
                route_results.sort(key=lambda x: float(str(x["price"]).replace(',', '').replace('$', '')))
                print(f"\n  --- {route} ({len(route_results)} results) ---\n")
                for i, r in enumerate(route_results[:15]):
                    price_display = r.get('price_display') or format_price(r['price'], r.get('currency', CURRENCY))
                    airline_str = r.get('airline', '') or ', '.join(r.get('airlines', []))
                    stops = r.get("stops", "?")
                    stops_str = "Nonstop" if stops == 0 else f"{stops} stop{'s' if str(stops) not in ('0','1') else ''}"
                    dur = r.get("duration", "")
                    best = " [BEST]" if r.get("is_best") else ""

                    print(f"  {i+1:2d}. {price_display:>8s} | "
                          f"{airline_str:40s} | "
                          f"{dur:20s} | {stops_str}{best}")
                    if r.get("segments"):
                        for seg in r["segments"]:
                            print(f"      {seg}")

        # Overall summary
        if priced_results:
            print(f"\n  TOTAL: {len(priced_results)} priced results across all routes.")
            # Show cheapest per route
            for dest in DESTINATIONS:
                route = f"{ORIGIN}->{dest}"
                route_results = [r for r in priced_results if r.get("route") == route]
                if route_results:
                    cheapest = min(route_results, key=lambda x: float(str(x["price"]).replace(',', '').replace('$', '')))
                    price_display = cheapest.get('price_display') or format_price(cheapest['price'], cheapest.get('currency', CURRENCY))
                    airline = cheapest.get('airline', '') or ', '.join(cheapest.get('airlines', []))
                    print(f"  Cheapest {route}: {price_display} on {airline}")

        if unpriced_results:
            print(f"\n  {len(unpriced_results)} results without clear pricing.")

        # Save to JSON
        output_file = "D:/claude/flights/amadeus_search_results.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({
                "search_params": {
                    "origin": ORIGIN,
                    "destinations": DESTINATIONS,
                    "date": DEPARTURE_DATE,
                    "class": TRAVEL_CLASS,
                    "search_time": datetime.now().isoformat(),
                },
                "results": all_results,
                "total_results": len(all_results),
            }, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n  Results saved to: {output_file}")
    else:
        print("  No results found from any API.")
        print("\n  To get results, you can sign up for free tiers:")
        print("    - Amadeus: https://developers.amadeus.com/ (free test tier)")
        print("    - Kiwi/Tequila: https://tequila.kiwi.com/ (free tier)")
        print("    - SerpAPI: https://serpapi.com/ (100 free searches)")
        print("    - Travelpayouts: https://travelpayouts.com/ (free)")
        print("    - RapidAPI: https://rapidapi.com/ (freemium)")

    print(f"\n{'='*70}")
    print(f"  Search complete.")
    print(f"{'='*70}")
