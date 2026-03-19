"""
Custom Flight Price Scraper - Skyscanner & Google Flights
No API keys needed. Scrapes public-facing endpoints.
"""
import urllib.request
import urllib.parse
import json
import time
import ssl
import re
import sys

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'


def skyscanner_create_search(origin, dest, date, adults=1, children_ages=None, currency='USD'):
    """Use Skyscanner's internal search/create endpoint"""
    url = "https://www.skyscanner.net/g/conductor/v1/fps3/search/"

    query_leg = {
        "originPlaceId": {"iata": origin},
        "destinationPlaceId": {"iata": dest},
        "date": {
            "year": int(date[:4]),
            "month": int(date[5:7]),
            "day": int(date[8:10])
        }
    }

    payload = {
        "query": {
            "market": "US",
            "locale": "en-US",
            "currency": currency,
            "queryLegs": [query_leg],
            "cabinClass": "CABIN_CLASS_ECONOMY",
            "adults": adults,
            "childrenAges": children_ages or []
        }
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'User-Agent': UA,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.9',
    })

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            result = json.loads(resp.read())
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')[:500]
        print(f"  HTTP {e.code}: {body[:200]}")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


def skyscanner_poll(session_token, currency='USD'):
    """Poll for results after creating search"""
    url = f"https://www.skyscanner.net/g/conductor/v1/fps3/search/{session_token}/poll"

    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'application/json',
    })

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  Poll error: {e}")
        return None


def parse_skyscanner_results(data):
    """Parse Skyscanner search results into clean format"""
    if not data:
        return []

    content = data.get('content', {})
    results_data = content.get('results', content.get('sortingOptions', {}))

    if not results_data:
        # Try alternate structure
        results_data = content

    itineraries = results_data.get('itineraries', {})
    legs = results_data.get('legs', {})
    segments = results_data.get('segments', {})
    places = results_data.get('places', {})
    carriers = results_data.get('carriers', {})

    flights = []

    for itin_id, itin in itineraries.items():
        pricing_options = itin.get('pricingOptions', [])
        if not pricing_options:
            continue

        # Get cheapest price
        best_price = float('inf')
        for po in pricing_options:
            price = po.get('price', {})
            amount = price.get('amount', '0')
            # Skyscanner returns price in milliunits
            try:
                p = float(amount) / 1000 if float(amount) > 10000 else float(amount)
                if p < best_price:
                    best_price = p
            except:
                pass

        if best_price == float('inf'):
            continue

        # Get leg details
        leg_ids = itin.get('legIds', [])
        leg_details = []
        total_duration = 0
        total_stops = 0
        airline_names = set()

        for lid in leg_ids:
            leg = legs.get(lid, {})
            origin_place = places.get(leg.get('originPlaceId', ''), {})
            dest_place = places.get(leg.get('destinationPlaceId', ''), {})
            duration = leg.get('durationInMinutes', 0)
            stop_count = leg.get('stopCount', 0)

            seg_ids = leg.get('segmentIds', [])
            for sid in seg_ids:
                seg = segments.get(sid, {})
                carrier = carriers.get(seg.get('marketingCarrierId', ''), {})
                airline_names.add(carrier.get('name', 'Unknown'))

            leg_details.append({
                'origin': origin_place.get('iata', leg.get('originPlaceId', '?')),
                'dest': dest_place.get('iata', leg.get('destinationPlaceId', '?')),
                'duration': duration,
                'stops': stop_count,
            })
            total_duration += duration
            total_stops += stop_count

        flights.append({
            'price': round(best_price, 2),
            'airlines': list(airline_names),
            'legs': leg_details,
            'total_duration': total_duration,
            'total_stops': total_stops,
        })

    flights.sort(key=lambda x: x['price'])
    return flights


def search_flight(origin, dest, date, adults=1, children=0, currency='USD'):
    """Complete flight search with retry"""
    children_ages = [2] * children  # age 2 for child seats

    print(f"\n{'='*60}")
    print(f"Searching: {origin} -> {dest} | {date} | {adults}A+{children}C | {currency}")
    print(f"{'='*60}")

    # Create search
    result = skyscanner_create_search(origin, dest, date, adults, children_ages, currency)

    if result:
        # Check if we need to poll
        status = result.get('status', '')
        session = result.get('sessionToken', '')

        if session and status != 'RESULT_STATUS_COMPLETE':
            print(f"  Session: {session[:20]}... polling...")
            time.sleep(2)
            for attempt in range(3):
                poll_result = skyscanner_poll(session, currency)
                if poll_result:
                    poll_status = poll_result.get('status', '')
                    result = poll_result
                    if poll_status == 'RESULT_STATUS_COMPLETE':
                        break
                time.sleep(2)

        flights = parse_skyscanner_results(result)

        if flights:
            print(f"  Found {len(flights)} flights!")
            for i, f in enumerate(flights[:8]):
                airlines = ', '.join(f['airlines'][:2])
                dur = f['total_duration']
                h, m = dur // 60, dur % 60
                stops = f['total_stops']
                stop_str = 'nonstop' if stops == 0 else f'{stops}stop'
                legs_str = ' -> '.join([l['origin'] + '-' + l['dest'] for l in f['legs']])
                print(f"  #{i+1}: ${f['price']:,.0f} | {h}h{m}m | {stop_str} | {airlines} | {legs_str}")
            return flights
        else:
            print("  Got response but no parseable flights")
            # Debug: show structure
            content = result.get('content', {})
            res = content.get('results', {})
            print(f"  Keys in content: {list(content.keys())[:5]}")
            print(f"  Keys in results: {list(res.keys())[:5]}")
            itin = res.get('itineraries', {})
            print(f"  Itineraries count: {len(itin)}")
            if itin:
                first_key = list(itin.keys())[0]
                first = itin[first_key]
                print(f"  First itinerary: {json.dumps(first, indent=2)[:500]}")
            return []
    else:
        print("  No response from Skyscanner")
        return []


def search_multi_city(legs, adults=1, children=0, currency='USD'):
    """Search multi-city itinerary"""
    children_ages = [2] * children

    query_legs = []
    for origin, dest, date in legs:
        query_legs.append({
            "originPlaceId": {"iata": origin},
            "destinationPlaceId": {"iata": dest},
            "date": {
                "year": int(date[:4]),
                "month": int(date[5:7]),
                "day": int(date[8:10])
            }
        })

    print(f"\n{'='*60}")
    legs_str = ' | '.join([f"{o}->{d} {dt}" for o, d, dt in legs])
    print(f"Multi-city: {legs_str} | {adults}A+{children}C")
    print(f"{'='*60}")

    url = "https://www.skyscanner.net/g/conductor/v1/fps3/search/"
    payload = {
        "query": {
            "market": "US",
            "locale": "en-US",
            "currency": currency,
            "queryLegs": query_legs,
            "cabinClass": "CABIN_CLASS_ECONOMY",
            "adults": adults,
            "childrenAges": children_ages
        }
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'User-Agent': UA,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    })

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            result = json.loads(resp.read())

            session = result.get('sessionToken', '')
            if session:
                print(f"  Session created, polling...")
                time.sleep(3)
                for attempt in range(3):
                    poll_result = skyscanner_poll(session)
                    if poll_result:
                        result = poll_result
                        if poll_result.get('status') == 'RESULT_STATUS_COMPLETE':
                            break
                    time.sleep(2)

            flights = parse_skyscanner_results(result)
            if flights:
                print(f"  Found {len(flights)} options!")
                for i, f in enumerate(flights[:6]):
                    airlines = ', '.join(f['airlines'][:2])
                    stops = f['total_stops']
                    print(f"  #{i+1}: ${f['price']:,.0f} | {stops}stop | {airlines}")
            else:
                print("  No parseable results")
                content = result.get('content', {})
                print(f"  Response keys: {list(content.keys())[:5]}")
            return flights
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')[:200]}")
    except Exception as e:
        print(f"  Error: {e}")

    return []


if __name__ == '__main__':
    all_results = {}

    # === ONE-WAY SEARCHES (cheapest approach) ===
    one_way_searches = [
        # Outbound: Various Asia -> LAX
        ("HKG", "LAX", "2026-06-09", 1, 0),
        ("HKG", "LAX", "2026-06-02", 1, 0),
        ("PVG", "LAX", "2026-06-01", 1, 0),
        ("CAN", "LAX", "2026-05-20", 1, 0),
        ("ICN", "LAX", "2026-06-02", 1, 0),
        # Returns: LAX -> Asia
        ("LAX", "HKG", "2026-06-29", 1, 0),
        ("LAX", "PVG", "2026-06-29", 1, 0),
        ("LAX", "CAN", "2026-06-29", 1, 0),
    ]

    for origin, dest, date, adults, children in one_way_searches:
        key = f"OW_{origin}-{dest}_{date}_{adults}A{children}C"
        flights = search_flight(origin, dest, date, adults, children)
        if flights:
            all_results[key] = flights
        time.sleep(1)  # Be respectful

    # === 3-SEGMENT TRICK SEARCHES ===
    multi_city_searches = [
        # HKG -> LAX, LAX -> PVG, PVG -> BKK (the trick)
        [("HKG", "LAX", "2026-06-02"), ("LAX", "PVG", "2026-06-29"), ("PVG", "BKK", "2026-06-30")],
        # HKG -> JFK, JFK -> PVG, PVG -> BKK
        [("HKG", "JFK", "2026-05-20"), ("JFK", "PVG", "2026-06-28"), ("PVG", "BKK", "2026-06-29")],
        # CAN -> LAX, LAX -> CAN, CAN -> BKK
        [("CAN", "LAX", "2026-05-20"), ("LAX", "CAN", "2026-06-28"), ("CAN", "BKK", "2026-06-29")],
    ]

    for legs in multi_city_searches:
        key = f"MC_{'_'.join(l[0]+'-'+l[1] for l in legs)}"
        flights = search_multi_city(legs, adults=1, children=0)
        if flights:
            all_results[key] = flights
        time.sleep(1)

    # Save everything
    with open('D:/claude/flights/skyscanner_results.json', 'w') as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print(f"DONE! Saved {len(all_results)} searches to skyscanner_results.json")
    print(f"{'='*60}")
