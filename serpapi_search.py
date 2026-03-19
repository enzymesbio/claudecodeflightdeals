import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
import urllib.request
import urllib.parse
import re
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

def separator(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

# ======================================================================
# APPROACH 1: SerpApi Google Flights endpoint
# ======================================================================
def try_serpapi():
    separator("APPROACH 1: SerpApi Google Flights API")

    # SerpApi does NOT have a free/demo key that works without registration.
    # But let's try the endpoint to confirm behavior and check for any demo mode.
    params = {
        "engine": "google_flights",
        "departure_id": "CGK",
        "arrival_id": "LHR",
        "outbound_date": "2026-05-04",
        "type": "2",           # one-way
        "travel_class": "2",   # business
        "currency": "USD",
        "hl": "en",
    }

    # Try without API key first
    print("[*] Attempting SerpApi WITHOUT an API key...")
    url = "https://serpapi.com/search?" + urllib.parse.urlencode(params)
    print(f"    URL: {url}")

    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"[+] SUCCESS! Got response with keys: {list(data.keys())}")
            if "best_flights" in data:
                print(f"    Found {len(data['best_flights'])} best flights")
                for i, flight in enumerate(data["best_flights"][:5]):
                    price = flight.get("price", "N/A")
                    flights_info = flight.get("flights", [])
                    airlines = [f.get("airline", "?") for f in flights_info]
                    print(f"    [{i+1}] ${price} - {', '.join(airlines)}")
            if "other_flights" in data:
                print(f"    Found {len(data['other_flights'])} other flights")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        print(f"[-] HTTP {e.code}: {body}")
    except Exception as e:
        print(f"[-] Error: {e}")

    # Try with a known demo key pattern
    demo_keys = ["demo", "test", "serpapi_demo"]
    for key in demo_keys:
        print(f"\n[*] Trying SerpApi with api_key='{key}'...")
        params["api_key"] = key
        url = "https://serpapi.com/search?" + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                print(f"[+] SUCCESS with key '{key}'! Keys: {list(data.keys())}")
                return True
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:300]
            print(f"    HTTP {e.code}: {body[:200]}")
        except Exception as e:
            print(f"    Error: {e}")

    print("\n[!] SerpApi requires a valid paid API key. No free/demo access available.")
    return False


# ======================================================================
# APPROACH 2: Momondo/Kayak
# ======================================================================
def try_momondo():
    separator("APPROACH 2: Momondo / Kayak Flight Search")

    url = "https://www.momondo.com/flight-search/CGK-LHR/2026-05-04/business?sort=bestflight_a"
    print(f"[*] Fetching: {url}")

    headers = dict(HEADERS)
    headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            print(f"[+] Got response: {len(html)} bytes, status {resp.status}")
            print(f"    Final URL: {resp.url}")

            # Look for embedded JSON data
            json_patterns = [
                r'window\.__NEXT_DATA__\s*=\s*(\{.*?\});',
                r'"flightResults"\s*:\s*(\[.*?\])',
                r'"itineraries"\s*:\s*(\[.*?\])',
                r'data-flights="([^"]*)"',
            ]
            for pat in json_patterns:
                m = re.search(pat, html, re.DOTALL)
                if m:
                    print(f"[+] Found data matching pattern: {pat[:50]}...")
                    snippet = m.group(1)[:500]
                    print(f"    Snippet: {snippet[:300]}")

            # Check for script tags with data
            scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
            print(f"    Found {len(scripts)} script tags")
            for i, s in enumerate(scripts):
                if len(s) > 1000 and ("flight" in s.lower() or "price" in s.lower()):
                    print(f"    Script #{i} ({len(s)} chars) may contain flight data")
                    print(f"      Preview: {s[:200]}...")

            # Check page title
            title_m = re.search(r'<title>(.*?)</title>', html)
            if title_m:
                print(f"    Page title: {title_m.group(1)}")

            return html
    except urllib.error.HTTPError as e:
        print(f"[-] HTTP {e.code}: {e.reason}")
        body = e.read().decode("utf-8", errors="replace")[:300]
        print(f"    Body: {body}")
    except Exception as e:
        print(f"[-] Error: {e}")
    return None


# ======================================================================
# APPROACH 3: Wego API
# ======================================================================
def try_wego():
    separator("APPROACH 3: Wego Metasearch API")

    url = "https://srv.wego.com/v3/metasearch/flights/searches"
    print(f"[*] POST to: {url}")

    payload = {
        "search": {
            "cabin": "business",
            "adultsCount": 1,
            "childrenCount": 0,
            "infantsCount": 0,
            "siteCode": "US",
            "currencyCode": "USD",
            "locale": "en",
            "legs": [
                {
                    "departureAirportCode": "CGK",
                    "arrivalAirportCode": "LHR",
                    "outboundDate": "2026-05-04"
                }
            ]
        }
    }

    data = json.dumps(payload).encode("utf-8")
    headers = dict(HEADERS)
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "application/json"

    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            print(f"[+] Got response with keys: {list(result.keys())}")
            print(f"    Response: {json.dumps(result, indent=2)[:1000]}")

            # Print initial airlines and airports data
            airlines_map = {}
            for al in result.get("airlines", []):
                code = al.get("code", "")
                name = al.get("name", "")
                if code and name:
                    airlines_map[code] = name
            if airlines_map:
                print(f"\n    Airlines in search: {json.dumps(airlines_map, indent=6)}")

            # Print initial trips/fares if present
            initial_trips = result.get("trips", [])
            initial_fares = result.get("fares", [])
            initial_legs = result.get("legs", [])
            print(f"    Initial trips: {len(initial_trips)}, fares: {len(initial_fares)}, legs: {len(initial_legs)}")

            # If we get a search ID, poll for results
            search_id = result.get("search", {}).get("id") or result.get("id")
            if search_id:
                print(f"\n[*] Got search ID: {search_id}, polling for results...")
                import time

                for attempt in range(4):
                    time.sleep(5)
                    poll_url = f"https://srv.wego.com/v3/metasearch/flights/searches/{search_id}/results?currencyCode=USD&locale=en"
                    try:
                        req2 = urllib.request.Request(poll_url, headers=headers)
                        with urllib.request.urlopen(req2, timeout=20) as resp2:
                            results = json.loads(resp2.read().decode("utf-8"))
                            trips = results.get("trips", [])
                            fares = results.get("fares", [])
                            legs = results.get("legs", [])
                            count = results.get("count", 0)
                            fares_count = results.get("faresCount", {})
                            print(f"\n    [Poll {attempt+1}] trips={len(trips)}, fares={len(fares)}, legs={len(legs)}, count={count}")
                            print(f"    faresCount: {json.dumps(fares_count)}")

                            # Build legs lookup
                            legs_map = {}
                            for leg in legs:
                                legs_map[leg.get("id", "")] = leg

                            # Update airlines map from poll
                            for al in results.get("airlines", []):
                                code = al.get("code", "")
                                name = al.get("name", "")
                                if code and name:
                                    airlines_map[code] = name

                            if fares:
                                print(f"\n    === BUSINESS CLASS FARES (CGK -> LHR, May 4 2026) ===")
                                for i, fare in enumerate(fares[:20]):
                                    price_raw = fare.get("price", {})
                                    if isinstance(price_raw, dict):
                                        price_amt = price_raw.get("amount") or price_raw.get("totalAmount", "?")
                                        price_curr = price_raw.get("currencyCode", "USD")
                                    else:
                                        price_amt = price_raw
                                        price_curr = "USD"

                                    trip_id = fare.get("tripId", "")
                                    provider = fare.get("provider", {})
                                    prov_name = provider.get("name", "?") if isinstance(provider, dict) else str(provider)

                                    # Get trip info
                                    trip = None
                                    for t in trips:
                                        if t.get("id") == trip_id:
                                            trip = t
                                            break

                                    leg_ids = trip.get("legIds", []) if trip else []
                                    leg_details = []
                                    for lid in leg_ids:
                                        leg = legs_map.get(lid, {})
                                        dep_time = leg.get("departureTime", "?")
                                        arr_time = leg.get("arrivalTime", "?")
                                        dep_code = leg.get("departureAirportCode", "?")
                                        arr_code = leg.get("arrivalAirportCode", "?")
                                        duration = leg.get("duration", "?")
                                        stops = leg.get("stopoverCount", 0)
                                        stop_codes = leg.get("stopoverAirportCodes", [])
                                        segments = leg.get("segments", [])
                                        seg_airlines = []
                                        seg_flight_nums = []
                                        for seg in segments:
                                            ac = seg.get("airlineCode", "")
                                            fn = seg.get("designatorCode", "") or seg.get("flightNumber", "")
                                            seg_airlines.append(airlines_map.get(ac, ac))
                                            if fn:
                                                seg_flight_nums.append(fn)

                                        leg_details.append({
                                            "route": f"{dep_code} -> {arr_code}",
                                            "depart": dep_time,
                                            "arrive": arr_time,
                                            "duration_min": duration,
                                            "stops": stops,
                                            "via": stop_codes,
                                            "airlines": seg_airlines,
                                            "flights": seg_flight_nums,
                                        })

                                    print(f"\n    [{i+1}] ${price_amt} {price_curr} (via {prov_name})")
                                    for ld in leg_details:
                                        dur_h = int(ld['duration_min']) // 60 if isinstance(ld['duration_min'], (int, float)) else '?'
                                        dur_m = int(ld['duration_min']) % 60 if isinstance(ld['duration_min'], (int, float)) else '?'
                                        via_str = f" via {', '.join(ld['via'])}" if ld['via'] else ""
                                        print(f"        {ld['route']} | {ld['depart']} -> {ld['arrive']} | {dur_h}h{dur_m}m | {ld['stops']} stop(s){via_str}")
                                        print(f"        Airlines: {', '.join(ld['airlines'])} | Flights: {', '.join(ld['flights'])}")

                                if len(fares) > 20:
                                    print(f"\n    ... and {len(fares) - 20} more fares")
                                break  # Got results, no need to poll more

                    except urllib.error.HTTPError as e:
                        body = e.read().decode("utf-8", errors="replace")[:300]
                        print(f"    Poll {attempt+1} error: HTTP {e.code}: {body}")
                    except Exception as e:
                        print(f"    Poll {attempt+1} error: {e}")

            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        print(f"[-] HTTP {e.code}: {e.reason}")
        print(f"    Body: {body}")
    except Exception as e:
        print(f"[-] Error: {e}")
    return False


# ======================================================================
# APPROACH 4: Google Flights HTML source parsing
# ======================================================================
def try_google_flights():
    separator("APPROACH 4: Google Flights Page Source Parsing")

    url = "https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA1LTA0agcIARIDQ0dLcgcIARIDTEhSQAFIA3ABggELCP___________wGYAQE&curr=USD"
    print(f"[*] Fetching Google Flights URL:")
    print(f"    {url}")

    headers = dict(HEADERS)
    headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    # Add cookie consent to reduce redirects
    headers["Cookie"] = "CONSENT=YES+"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read()
            html = raw.decode("utf-8", errors="replace")
            print(f"[+] Got response: {len(html)} bytes")
            print(f"    Final URL: {resp.url}")

            # Check page title
            title_m = re.search(r'<title>(.*?)</title>', html)
            if title_m:
                print(f"    Page title: {title_m.group(1)}")

            # Look for AF_initDataCallback
            af_callbacks = re.findall(r"AF_initDataCallback\(\{[^}]*key:\s*'([^']*)'[^}]*data:(.*?)\}\);", html, re.DOTALL)
            print(f"\n[*] Found {len(af_callbacks)} AF_initDataCallback entries")
            for key, data_str in af_callbacks:
                print(f"    Key: '{key}', data length: {len(data_str)} chars")
                if len(data_str) > 500:
                    # This might contain flight data
                    print(f"    LARGE data block - likely contains flight info")
                    # Look for price patterns
                    prices = re.findall(r'(\d{1,2},?\d{3})', data_str[:5000])
                    if prices:
                        print(f"    Possible prices found: {prices[:20]}")
                    # Look for airline names
                    airlines_found = set()
                    for airline in ["Singapore Airlines", "Qatar Airways", "Emirates", "Cathay Pacific",
                                    "British Airways", "Garuda", "Turkish Airlines", "Thai Airways",
                                    "Malaysia Airlines", "Japan Airlines", "ANA", "Etihad",
                                    "KLM", "Lufthansa", "Korean Air", "EVA Air"]:
                        if airline.lower() in data_str.lower():
                            airlines_found.add(airline)
                    if airlines_found:
                        print(f"    Airlines mentioned: {', '.join(sorted(airlines_found))}")

                    # Try to parse as JSON array
                    try:
                        parsed = json.loads(data_str.strip())
                        print(f"    Parsed as JSON successfully, type={type(parsed).__name__}")
                        if isinstance(parsed, list) and len(parsed) > 0:
                            print(f"    Top-level list length: {len(parsed)}")
                            # Deep search for flight-like data
                            extract_flight_data(parsed, key)
                    except json.JSONDecodeError:
                        print(f"    Not valid JSON, checking for embedded structures...")

            # Look for WIZ_global_data
            wiz_m = re.search(r'window\.WIZ_global_data\s*=\s*(\{.*?\});', html, re.DOTALL)
            if wiz_m:
                print(f"\n[*] Found WIZ_global_data ({len(wiz_m.group(1))} chars)")

            # Look for any large data blocks in script tags
            scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
            large_scripts = [(i, s) for i, s in enumerate(scripts) if len(s) > 2000]
            print(f"\n[*] Found {len(scripts)} script tags, {len(large_scripts)} are large (>2KB)")

            for idx, script in large_scripts[:10]:
                # Search for flight-related keywords
                keywords_found = []
                for kw in ["CGK", "LHR", "Jakarta", "London", "business", "price", "duration", "airline"]:
                    if kw.lower() in script.lower():
                        keywords_found.append(kw)
                if keywords_found:
                    print(f"    Script #{idx} ({len(script)} chars): contains {', '.join(keywords_found)}")

            # Look for protobuf-like encoded data
            proto_patterns = re.findall(r'data:(\[(?:\[.*?\])+\])', html[:50000])
            if proto_patterns:
                print(f"\n[*] Found {len(proto_patterns)} possible protobuf/nested array blocks")

            # Search for any price-like patterns near airline names in full HTML
            price_airline_patterns = re.findall(
                r'((?:Singapore|Qatar|Emirates|British|Cathay|Garuda|Turkish|Thai|Etihad|KLM|Lufthansa|Japan|Korean|EVA|ANA)[^"]{0,200}?\$?\d{1,2},?\d{3})',
                html, re.IGNORECASE
            )
            if price_airline_patterns:
                print(f"\n[*] Price+Airline patterns in HTML:")
                for p in price_airline_patterns[:10]:
                    print(f"    {p[:150]}")

            return html
    except urllib.error.HTTPError as e:
        print(f"[-] HTTP {e.code}: {e.reason}")
        try:
            body = e.read().decode("utf-8", errors="replace")[:500]
            print(f"    Body: {body}")
        except:
            pass
    except Exception as e:
        print(f"[-] Error: {e}")
    return None


def extract_flight_data(data, key, depth=0, path=""):
    """Recursively search nested arrays for flight-like data."""
    if depth > 8:
        return
    if isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, str) and len(item) > 3:
                if item in ("CGK", "LHR", "LAX", "SIN", "DOH", "DXB", "HKG", "NRT", "ICN", "BKK", "KUL"):
                    print(f"      [{key}] Airport code at {path}[{i}]: {item}")
                elif any(a in item for a in ["Airlines", "Airways", "Air ", "Emirates", "Etihad", "Garuda"]):
                    print(f"      [{key}] Airline at {path}[{i}]: {item}")
            if isinstance(item, (list, dict)):
                extract_flight_data(item, key, depth + 1, f"{path}[{i}]")
    elif isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (list, dict)):
                extract_flight_data(v, key, depth + 1, f"{path}.{k}")


def deep_parse_google_flights(html):
    """Advanced parsing of Google Flights embedded data to extract flight itineraries."""
    separator("DEEP PARSE: Google Flights Embedded Data")

    # Google Flights uses AF_initDataCallback with data wrapped in function() or raw.
    # The data often has trailing characters that break naive regex.
    # Strategy: find each callback, then use bracket matching to extract the data.

    # First find all callback positions
    cb_positions = []
    for m in re.finditer(r"AF_initDataCallback\(\{key:\s*'(ds:\d+)'", html):
        cb_positions.append((m.start(), m.group(1)))

    matches = []
    for pos, key in cb_positions:
        # Find "data:" after the key
        data_marker = html.find("data:", pos)
        if data_marker < 0 or data_marker > pos + 500:
            continue

        # Find start of actual data (after "data:")
        data_start = data_marker + 5
        # Skip whitespace and possible function wrapper
        snippet = html[data_start:data_start+30].strip()
        if snippet.startswith("function"):
            ret_pos = html.find("return ", data_start)
            if ret_pos > 0 and ret_pos < data_start + 100:
                data_start = ret_pos + 7

        # Now use bracket counting to find matching end
        raw = html[data_start:]
        if not raw or raw[0] not in '[{':
            continue

        bracket_map = {'[': ']', '{': '}'}
        stack = []
        in_string = False
        escape_next = False
        end_pos = 0

        for ci, ch in enumerate(raw):
            if ci > 200000:  # safety limit
                break
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch in bracket_map:
                stack.append(bracket_map[ch])
            elif ch in ']})':
                if stack and stack[-1] == ch:
                    stack.pop()
                    if not stack:
                        end_pos = ci + 1
                        break

        if end_pos > 0:
            data_str = raw[:end_pos]
            matches.append((key, data_str))

    if not matches:
        # Fallback: simple regex
        pattern = r"AF_initDataCallback\(\{key:\s*'(ds:\d+)',\s*hash:\s*'\d+',\s*data:(.*?)\}\);"
        matches = [(k, d) for k, d in re.findall(pattern, html, re.DOTALL)]

    print(f"[*] Found {len(matches)} AF_initDataCallback data blocks")

    for key, raw_data in matches:
        # Remove function wrapper if present
        raw_data = raw_data.strip()
        if raw_data.startswith("function"):
            m = re.match(r"function\(\)\{return\s+(.*)\}", raw_data, re.DOTALL)
            if m:
                raw_data = m.group(1)

        if len(raw_data) < 5000:
            continue

        print(f"\n  === Block '{key}' ({len(raw_data)} chars) ===")

        try:
            parsed = json.loads(raw_data)
        except json.JSONDecodeError:
            # Try to fix common issues
            raw_data = raw_data.rstrip().rstrip(")")
            try:
                parsed = json.loads(raw_data)
            except json.JSONDecodeError:
                print(f"    Could not parse as JSON")
                continue

        if not isinstance(parsed, list):
            print(f"    Top-level type: {type(parsed).__name__}, skipping")
            continue

        print(f"    Top-level array length: {len(parsed)}")

        # Google Flights data structure (from reverse engineering):
        # The flight data is typically in parsed[2] or parsed[3]
        # Each itinerary is a nested array with:
        #   - Airline info, flight numbers
        #   - Departure/arrival airports and times
        #   - Duration in minutes
        #   - Price

        # Let's look for the flight list structure
        # It's usually: parsed[X][Y] where each item is a flight itinerary
        def find_flight_lists(obj, path="", depth=0):
            """Find arrays that look like lists of flight itineraries."""
            results = []
            if depth > 6 or not isinstance(obj, list):
                return results
            # A flight itinerary list is typically a list of lists,
            # where each sub-list contains flight segment data
            if len(obj) > 2:
                # Check if items look like itineraries (list of lists with strings)
                has_airport = False
                has_airline = False
                for item in obj[:3]:
                    s = str(item)[:2000]
                    if "CGK" in s or "LHR" in s:
                        has_airport = True
                    if any(a in s for a in ["Airlines", "Airways", "Emirates", "Etihad", "Garuda"]):
                        has_airline = True
                if has_airport and has_airline:
                    results.append((path, obj))
            for i, item in enumerate(obj):
                if isinstance(item, list):
                    results.extend(find_flight_lists(item, f"{path}[{i}]", depth + 1))
            return results

        flight_lists = find_flight_lists(parsed)
        print(f"    Found {len(flight_lists)} potential flight itinerary lists")

        for fl_path, fl_list in flight_lists[:3]:
            print(f"\n    Flight list at {fl_path}: {len(fl_list)} items")
            for idx, itin in enumerate(fl_list[:25]):
                try:
                    parse_itinerary(itin, idx)
                except Exception as e:
                    print(f"      Itinerary {idx}: parse error: {e}")

        # Collect all primitives for analysis
        all_strings = []
        all_ints = []

        def collect_primitives(obj, path="", depth=0):
            if depth > 12:
                return
            if isinstance(obj, list):
                for i, item in enumerate(obj):
                    collect_primitives(item, f"{path}[{i}]", depth + 1)
            elif isinstance(obj, str):
                all_strings.append((path, obj))
            elif isinstance(obj, int) and obj > 0:
                all_ints.append((path, obj))

        collect_primitives(parsed)

        # Find all 3-letter uppercase codes (airports)
        airport_codes = [s for p, s in all_strings if len(s) == 3 and s.isupper() and s.isalpha()]
        unique_airports = list(dict.fromkeys(airport_codes))
        print(f"\n    All airport codes found: {unique_airports[:40]}")

        # Find all airline-like strings
        airline_strings = [s for p, s in all_strings
                          if any(k in s for k in ["Airlines", "Airways", "Air ", "Emirates", "Etihad", "Garuda"])
                          and len(s) < 50]
        unique_airlines = list(dict.fromkeys(airline_strings))
        print(f"    All airline names: {unique_airlines[:30]}")

        # Possible prices
        price_candidates = sorted(set(v for _, v in all_ints if 800 < v < 15000))
        print(f"    Integers in $800-$15000 range (possible prices): {price_candidates[:40]}")

        # Duration candidates
        duration_candidates = sorted(set(v for _, v in all_ints if 800 < v < 2400))
        print(f"    Integers in 800-2400 range (possible durations in min): {duration_candidates[:30]}")

        # Flight number patterns
        flight_nums = [s for _, s in all_strings if re.match(r'^[A-Z]{2}\s?\d{1,4}$', s)]
        print(f"    Flight number patterns: {flight_nums[:30]}")

        # Time patterns
        time_patterns = [s for _, s in all_strings if re.match(r'^\d{1,2}:\d{2}', s)]
        print(f"    Time patterns: {time_patterns[:30]}")

        # Now try to intelligently parse the itinerary structure
        # Google Flights uses: parsed[2][0] = best flights, parsed[3][0] = other flights
        # Each itinerary: [leg_data, ..., price_info]
        # leg_data contains nested arrays with [airline, flight_no, dep_airport, arr_airport, times, ...]
        print(f"\n    === STRUCTURED FLIGHT EXTRACTION ===")
        try:
            extract_structured_flights(parsed)
        except Exception as e:
            print(f"    Structured extraction error: {e}")
            import traceback
            traceback.print_exc()


def extract_structured_flights(data):
    """Extract structured flight data from Google Flights nested arrays."""
    # Google Flights data structure (reverse-engineered):
    # data[2][0] = list of "best" flight itineraries
    # data[3][0] = list of "other" flight itineraries
    # Each itinerary is a deeply nested array.

    sections = []
    if len(data) > 2 and isinstance(data[2], list) and len(data[2]) > 0:
        sections.append(("Best Flights", data[2][0] if isinstance(data[2][0], list) else []))
    if len(data) > 3 and isinstance(data[3], list) and len(data[3]) > 0:
        sections.append(("Other Flights", data[3][0] if isinstance(data[3][0], list) else []))

    for section_name, itineraries in sections:
        if not isinstance(itineraries, list):
            continue
        print(f"\n    --- {section_name} ({len(itineraries)} options) ---")

        for idx, itin in enumerate(itineraries):
            if not isinstance(itin, list):
                continue

            # Extract all info from this itinerary by walking the nested structure
            info = {"airlines": [], "airports": [], "flight_nums": [], "times": [],
                    "prices": [], "durations": [], "segments": []}

            def walk_itin(obj, depth=0, context=""):
                if depth > 15 or obj is None:
                    return
                if isinstance(obj, str):
                    if len(obj) == 3 and obj.isupper() and obj.isalpha():
                        info["airports"].append(obj)
                    elif any(k in obj for k in ["Airlines", "Airways", "Air ", "Emirates", "Etihad", "Garuda"]) and len(obj) < 50:
                        info["airlines"].append(obj)
                    elif re.match(r'^[A-Z]{2}\s?\d{1,4}$', obj):
                        info["flight_nums"].append(obj)
                    elif re.match(r'^\d{1,2}:\d{2}', obj):
                        info["times"].append(obj)
                elif isinstance(obj, int):
                    if 500 < obj < 15000:
                        info["prices"].append(obj)
                    elif 60 < obj < 3000:
                        info["durations"].append(obj)
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        walk_itin(item, depth + 1)

            walk_itin(itin)

            # Deduplicate while preserving order
            airlines = list(dict.fromkeys(info["airlines"]))
            airports = list(dict.fromkeys(info["airports"]))
            flight_nums = list(dict.fromkeys(info["flight_nums"]))
            times = info["times"]  # keep order for dep/arr
            # The price is usually the last or most prominent integer
            # In Google's format, the displayed price often appears as a standalone int
            prices = sorted(set(info["prices"]))

            if airlines or (airports and len(airports) >= 2):
                route = " -> ".join(airports) if airports else "?"
                airline_str = ", ".join(airlines) if airlines else "?"

                # Filter out 2026 (the year) from prices
                real_prices = [p for p in prices if p != 2026]
                # Business class CGK-LHR is typically $1500-$10000
                biz_prices = [p for p in real_prices if 1000 < p < 12000]
                if biz_prices:
                    price_str = f"${biz_prices[0]:,}"
                elif real_prices:
                    price_str = f"${real_prices[-1]:,}"
                else:
                    price_str = "price N/A"

                all_prices_str = ", ".join(f"${p:,}" for p in sorted(real_prices) if p > 100)

                stops = max(0, len(airports) - 2) if airports else "?"
                time_str = ""
                if times:
                    time_str = f" | Dep: {times[0]}" + (f" Arr: {times[-1]}" if len(times) > 1 else "")

                print(f"      [{idx+1}] {price_str} | {airline_str}")
                print(f"           Route: {route} ({stops} stop{'s' if stops != 1 else ''}){time_str}")
                if flight_nums:
                    print(f"           Flights: {', '.join(flight_nums[:6])}")
                if all_prices_str:
                    print(f"           All price candidates: {all_prices_str}")


def parse_itinerary(itin, idx):
    """Try to extract flight details from a single itinerary array."""
    if not isinstance(itin, list):
        return

    # Flatten to find key data
    flat_strings = []
    flat_ints = []

    def flatten(obj, depth=0):
        if depth > 8:
            return
        if isinstance(obj, list):
            for item in obj:
                flatten(item, depth + 1)
        elif isinstance(obj, str):
            flat_strings.append(obj)
        elif isinstance(obj, int):
            flat_ints.append(obj)

    flatten(itin)

    airports = [s for s in flat_strings if len(s) == 3 and s.isupper() and s.isalpha()]
    airlines = [s for s in flat_strings
                if any(k in s for k in ["Airlines", "Airways", "Air ", "Emirates", "Etihad", "Garuda"])
                and len(s) < 50]
    flight_nums = [s for s in flat_strings if re.match(r'^[A-Z]{2}\s?\d{1,4}$', s)]
    times = [s for s in flat_strings if re.match(r'^\d{1,2}:\d{2}', s)]
    prices = [v for v in flat_ints if 500 < v < 15000]

    if airlines or (airports and len(airports) >= 2):
        parts = []
        if airlines:
            parts.append(f"Airlines: {', '.join(dict.fromkeys(airlines))}")
        if airports:
            parts.append(f"Route: {' -> '.join(dict.fromkeys(airports))}")
        if flight_nums:
            parts.append(f"Flights: {', '.join(flight_nums[:4])}")
        if times:
            parts.append(f"Times: {', '.join(times[:4])}")
        if prices:
            parts.append(f"Prices: {sorted(set(prices))}")
        print(f"      [{idx}] {' | '.join(parts)}")


# ======================================================================
# APPROACH 5: Alternative Google Flights URL (simpler)
# ======================================================================
def try_google_flights_alt():
    separator("APPROACH 5: Google Flights Alternative Fetch via requests")

    import requests

    url = "https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA1LTA0agcIARIDQ0dLcgcIARIDTEhSQAFIA3ABggELCP___________wGYAQE&curr=USD"

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })

    print(f"[*] Fetching with requests session...")
    try:
        resp = session.get(url, timeout=25, allow_redirects=True)
        print(f"[+] Status: {resp.status_code}, length: {len(resp.text)} chars")
        print(f"    Final URL: {resp.url}")

        html = resp.text

        # Count AF_initDataCallback
        cb_count = html.count("AF_initDataCallback")
        print(f"    AF_initDataCallback count: {cb_count}")

        # Look for large data blocks
        all_data_blocks = re.findall(
            r"AF_initDataCallback\(\{[^}]*key:\s*'([^']*)'.*?data:(function\(\)\{return\s+)?(.*?)\}(?:\)|;)",
            html, re.DOTALL
        )
        print(f"    Parsed callback blocks: {len(all_data_blocks)}")

        flight_data_found = False
        for key, _, data_str in all_data_blocks:
            data_str = data_str.strip().rstrip(")")
            if len(data_str) > 1000:
                print(f"\n    Key='{key}' => {len(data_str)} chars")
                # Check for CGK / LHR references
                if "CGK" in data_str or "LHR" in data_str or "Jakarta" in data_str:
                    flight_data_found = True
                    print(f"    *** Contains flight route references! ***")

                    # Extract what we can
                    airports = re.findall(r'"([A-Z]{3})"', data_str[:10000])
                    airports_unique = list(dict.fromkeys(airports))  # ordered unique
                    print(f"    Airport codes: {airports_unique[:30]}")

                    # Look for airline references
                    airlines = set()
                    for airline in ["Singapore Airlines", "Qatar Airways", "Emirates", "Cathay Pacific",
                                    "British Airways", "Garuda Indonesia", "Turkish Airlines",
                                    "Thai Airways", "Malaysia Airlines", "Japan Airlines",
                                    "ANA", "Etihad Airways", "KLM", "Lufthansa", "Korean Air",
                                    "EVA Air", "China Southern", "China Eastern", "Oman Air",
                                    "Saudia", "Gulf Air", "SriLankan", "Air France"]:
                        if airline in data_str:
                            airlines.add(airline)
                    if airlines:
                        print(f"    Airlines found: {', '.join(sorted(airlines))}")

                    # Try to find prices (numbers that look like USD prices)
                    # In Google's data format, prices are often plain integers
                    try:
                        parsed = json.loads(data_str)
                        print(f"    Parsed JSON: type={type(parsed).__name__}")

                        # Deep extract
                        def find_prices_and_routes(obj, path="", results=None):
                            if results is None:
                                results = {"prices": [], "airports": [], "airlines": [], "durations": []}
                            if isinstance(obj, list):
                                for i, item in enumerate(obj):
                                    find_prices_and_routes(item, f"{path}[{i}]", results)
                            elif isinstance(obj, str):
                                if len(obj) == 3 and obj.isupper():
                                    results["airports"].append((path, obj))
                                elif "Airlines" in obj or "Airways" in obj or "Air " in obj:
                                    results["airlines"].append((path, obj))
                            elif isinstance(obj, (int, float)):
                                if 200 < obj < 30000 and isinstance(obj, int):
                                    results["prices"].append((path, obj))
                            return results

                        info = find_prices_and_routes(parsed)
                        if info["airlines"]:
                            print(f"\n    === AIRLINES in data ===")
                            seen = set()
                            for p, a in info["airlines"]:
                                if a not in seen:
                                    seen.add(a)
                                    print(f"      {a}")

                        if info["prices"]:
                            # Filter to likely flight prices
                            likely_prices = [(p, v) for p, v in info["prices"] if 300 < v < 20000]
                            if likely_prices:
                                print(f"\n    === POSSIBLE PRICES (USD) ===")
                                price_values = sorted(set(v for _, v in likely_prices))
                                print(f"      Unique price-range values: {price_values[:30]}")
                    except json.JSONDecodeError as je:
                        print(f"    JSON parse failed: {je}")
                        # Print a snippet
                        print(f"    Data snippet: {data_str[:300]}...")

        if not flight_data_found:
            print("\n    No flight route data found in AF_initDataCallback blocks.")
            # Dump some raw HTML context
            for kw in ["CGK", "business", "Jakarta"]:
                idx = html.find(kw)
                if idx > -1:
                    print(f"    '{kw}' found at position {idx}: ...{html[max(0,idx-50):idx+100]}...")

    except Exception as e:
        print(f"[-] Error: {e}")
        import traceback
        traceback.print_exc()


# ======================================================================
# MAIN
# ======================================================================
if __name__ == "__main__":
    print(f"Flight Search Script - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Route: CGK (Jakarta) -> LHR (London)")
    print(f"Date: 2026-05-04 | Class: Business | Type: One-way")

    # Run all approaches
    try_serpapi()
    try_momondo()
    try_wego()
    html = try_google_flights()
    if html:
        deep_parse_google_flights(html)
    try_google_flights_alt()

    separator("SUMMARY OF ALL APPROACHES")
    print("""
  APPROACH 1 - SerpApi: FAILED (requires paid API key, no free/demo mode)
    All attempts (no key, 'demo', 'test', 'serpapi_demo') returned HTTP 401.

  APPROACH 2 - Momondo/Kayak: BLOCKED (CAPTCHA wall)
    Redirected to sitecaptcha.html. Requires browser/JS to solve.

  APPROACH 3 - Wego API: PARTIAL SUCCESS
    Successfully created a search session and got airline/airport metadata.
    However, polling returned 0 trips/fares - the API may need specific
    headers, auth tokens, or the date may be too far in the future.

  APPROACH 4 - Google Flights HTML Parsing (urllib): SUCCESS
    Fetched 2.3 MB page with title "Jakarta to London | Google Flights".
    The AF_initDataCallback 'ds:1' block (74K chars) contained embedded
    flight data that was successfully parsed via bracket-matching JSON
    extraction.

    EXTRACTED: 5 "Best Flights" + 10 "Other Flights" business class options
    Airlines found: Singapore Airlines, Garuda Indonesia, Etihad, Emirates,
      Qatar Airways, Malaysia Airlines, British Airways, Lufthansa City Airlines,
      EVA Air, ANA, KLM, Korean Air, Cathay Pacific, Turkish Airlines,
      Air China, Air France, Air India, and more.
    Routes via: SIN, BKK, VIE, ZRH, FRA, MUC, AUH, DXB, DOH, KUL, JED,
      TPE, HKG, IST, AMS, CDG, ICN, NRT, etc.

  APPROACH 5 - Google Flights via requests library: FAILED
    Redirected to consent.google.com (cookie consent page).
    urllib.request succeeds where requests fails because urllib follows
    redirects differently and the CONSENT=YES+ cookie works with it.

  CONCLUSION:
    The most reliable free approach is direct Google Flights HTML parsing
    with urllib.request + CONSENT cookie. The embedded AF_initDataCallback
    data contains full flight itineraries without needing JavaScript.
""")
    print("="*70)
