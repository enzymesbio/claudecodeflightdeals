#!/usr/bin/env python3
"""
Flight Search Script - Search for flight prices using Google Flights data.

No API keys, proxies, or paid services required.
Works by fetching Google Flights search pages and parsing the structured
accessibility data embedded in the HTML (ARIA labels).

Usage:
    python search_flights.py --origin HKG --destination LAX --date 2026-06-15
    python search_flights.py --origin HKG --destination LAX --date 2026-06-15 --return-date 2026-06-22
    python search_flights.py --multi "HKG-LAX:2026-06-15,LAX-SFO:2026-06-17"
    python search_flights.py --origin HKG --destination LAX --date 2026-06-15 --adults 2 --children 1 --currency USD
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library is required. Install with: pip install requests")
    sys.exit(1)


# ----- Freebase MID Database for Common Airports/Cities -----
# Google Flights uses Freebase MIDs (e.g., /m/03hrk for Hong Kong)
# We need these to build the TFS search parameter

AIRPORT_MIDS = {
    # Asia
    "HKG": "/m/03hrk",   # Hong Kong
    "NRT": "/m/0d5gx",   # Tokyo Narita
    "HND": "/m/01lfy",   # Tokyo Haneda
    "TYO": "/m/07dfk",   # Tokyo (city)
    "KIX": "/m/0drr3",   # Osaka Kansai
    "ICN": "/m/0hsqf",   # Seoul Incheon
    "SEL": "/m/0hsqf",   # Seoul (city)
    "PEK": "/m/01914",   # Beijing Capital
    "PKX": "/m/01914",   # Beijing Daxing (uses Beijing MID)
    "PVG": "/m/06wjf",   # Shanghai Pudong
    "SHA": "/m/06wjf",   # Shanghai Hongqiao
    "CTU": "/m/016v46",  # Chengdu Shuangliu
    "TFU": "/m/0_gzwvx", # Chengdu Tianfu
    "SIN": "/m/06t2t",   # Singapore
    "BKK": "/m/0fngc",   # Bangkok
    "TPE": "/m/0ftkx",   # Taipei
    "MNL": "/m/0195pd",  # Manila
    "KUL": "/m/04lh6",   # Kuala Lumpur
    "SGN": "/m/0hn4h",   # Ho Chi Minh City
    "HAN": "/m/0130t_",  # Hanoi
    "DEL": "/m/09f07",   # Delhi
    "BOM": "/m/04vmp",   # Mumbai
    "DPS": "/m/01c3q1",  # Bali / Denpasar
    "CGK": "/m/04lrg",   # Jakarta
    "CTS": "/m/01lhtp",  # Sapporo

    # North America
    "LAX": "/m/030qb3t", # Los Angeles
    "SFO": "/m/0d6lp",   # San Francisco
    "JFK": "/m/02_286",  # New York
    "EWR": "/m/02_286",  # Newark (uses NYC MID)
    "LGA": "/m/02_286",  # LaGuardia (uses NYC MID)
    "NYC": "/m/02_286",  # New York (city)
    "ORD": "/m/01_d4",   # Chicago
    "ATL": "/m/013yq",   # Atlanta
    "DFW": "/m/0f2rq",   # Dallas
    "IAH": "/m/03l2n",   # Houston
    "DEN": "/m/02cl1",   # Denver
    "SEA": "/m/0d9jr",   # Seattle
    "MIA": "/m/0f8l9c",  # Miami
    "BOS": "/m/01cx_",   # Boston
    "IAD": "/m/0rh6k",   # Washington DC
    "DCA": "/m/0rh6k",   # Washington DC (Reagan)
    "LAS": "/m/0cv3w",   # Las Vegas
    "PHX": "/m/0d35y",   # Phoenix
    "MSP": "/m/0fpzwf",  # Minneapolis
    "DTW": "/m/02dtg",   # Detroit
    "YVR": "/m/080h2",   # Vancouver
    "YYZ": "/m/0h7h6",   # Toronto
    "YUL": "/m/052p7",   # Montreal
    "YOW": "/m/05ksh",   # Ottawa
    "YYC": "/m/01r32",   # Calgary
    "MEX": "/m/0164v",   # Mexico City
    "CUN": "/m/01_1kp",  # Cancun
    "HNL": "/m/02hrh0_", # Honolulu

    # Europe
    "LHR": "/m/04jpl",   # London Heathrow
    "LGW": "/m/04jpl",   # London Gatwick (uses London MID)
    "LON": "/m/04jpl",   # London (city)
    "CDG": "/m/05qtj",   # Paris CDG
    "ORY": "/m/05qtj",   # Paris Orly (uses Paris MID)
    "PAR": "/m/05qtj",   # Paris (city)
    "FRA": "/m/02j9z",   # Frankfurt
    "AMS": "/m/0k3p",    # Amsterdam
    "MAD": "/m/056_y",   # Madrid
    "BCN": "/m/01f62",   # Barcelona
    "FCO": "/m/06c62",   # Rome
    "MXP": "/m/0947l",   # Milan
    "MUC": "/m/02h6_6p", # Munich
    "ZRH": "/m/08966",   # Zurich
    "VIE": "/m/07blr",   # Vienna
    "IST": "/m/09949m",  # Istanbul
    "ATH": "/m/0n2z",    # Athens
    "LIS": "/m/04llb",   # Lisbon
    "DUB": "/m/02cft",   # Dublin
    "CPH": "/m/01lfy",   # Copenhagen
    "OSL": "/m/05l64",   # Oslo
    "ARN": "/m/06vxs",   # Stockholm

    # Oceania
    "SYD": "/m/06y57",   # Sydney
    "MEL": "/m/0chgzm",  # Melbourne
    "BNE": "/m/01m1d6",  # Brisbane
    "AKL": "/m/0196g7",  # Auckland

    # Middle East
    "DXB": "/m/0170s4",  # Dubai
    "DOH": "/m/01hjy",   # Doha
    "AUH": "/m/01c7j1",  # Abu Dhabi
    "TLV": "/m/0d9y6",   # Tel Aviv

    # Africa
    "JNB": "/m/0cv_2",   # Johannesburg
    "CPT": "/m/01yj2",   # Cape Town
    "CAI": "/m/01w2v",   # Cairo
    "NBO": "/m/05g56",   # Nairobi

    # South America
    "GRU": "/m/02cft",   # Sao Paulo
    "EZE": "/m/0130g_",  # Buenos Aires
    "SCL": "/m/0fvzg",   # Santiago
    "BOG": "/m/01rl2n",  # Bogota
    "LIM": "/m/04w58",   # Lima
}


def get_freebase_mid(iata_code: str) -> str:
    """Get the Freebase MID for an airport IATA code."""
    code = iata_code.upper().strip()
    if code in AIRPORT_MIDS:
        return AIRPORT_MIDS[code]
    # If not found, try using the IATA code directly (Google sometimes accepts this)
    return None


def build_tfs_param(legs: list, num_adults: int = 1, num_children: int = 0) -> str:
    """
    Build the TFS parameter for Google Flights URL.

    legs: list of dicts with keys: origin, destination, date
    Returns base64-encoded protobuf string.
    """
    import base64

    def encode_varint(value):
        result = b''
        if value < 0:
            value = value & 0xFFFFFFFFFFFFFFFF
        while value > 0x7f:
            result += bytes([(value & 0x7f) | 0x80])
            value >>= 7
        result += bytes([value])
        return result

    def encode_varint_field(field_num, value):
        tag = (field_num << 3) | 0
        return encode_varint(tag) + encode_varint(value)

    def encode_bytes_field(field_num, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        tag = (field_num << 3) | 2
        return encode_varint(tag) + encode_varint(len(data)) + data

    # Build each leg
    legs_data = b''
    for leg in legs:
        origin_mid = get_freebase_mid(leg['origin'])
        dest_mid = get_freebase_mid(leg['destination'])

        if not origin_mid or not dest_mid:
            raise ValueError(
                f"Unknown airport code: {leg['origin'] if not origin_mid else leg['destination']}. "
                f"Please add the Freebase MID for this airport to AIRPORT_MIDS."
            )

        origin_place = encode_varint_field(1, 2) + encode_bytes_field(2, origin_mid)
        dest_place = encode_varint_field(1, 2) + encode_bytes_field(2, dest_mid)

        leg_data = (
            encode_bytes_field(2, leg['date']) +
            encode_bytes_field(13, origin_place) +
            encode_bytes_field(14, dest_place)
        )
        legs_data += encode_bytes_field(3, leg_data)

    # Determine trip type
    is_oneway = len(legs) == 1
    trip_type = 2 if not is_oneway else 1

    # Passenger config: field 16
    passengers = encode_varint_field(1, num_adults)
    if num_children > 0:
        passengers += encode_varint_field(2, num_children)

    # Build main message
    msg = (
        encode_varint_field(1, 28) +
        encode_varint_field(2, trip_type) +
        legs_data +
        encode_varint_field(14, 1) +
        encode_bytes_field(16,
            b'\x08' + b'\xff' * 9 + b'\x01' +
            b'\x40\x01\x48\x01'
        ) +
        encode_varint_field(19, 1) +
        encode_bytes_field(22,
            encode_varint_field(3, 1) +
            encode_varint_field(4, 1)
        )
    )

    return base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')


class FlightSearcher:
    """Searches for flights using Google Flights."""

    CONSENT_COOKIES = {
        'CONSENT': 'YES+',
        'SOCS': 'CAISNQgDEitib3FfaWRlbnRpdHlmcm9udGVuZHVpc2VydmVyXzIwMjMxMDA5LjA5X3AwGgJlbiACGgYIgO6JqgY',
    }

    def __init__(self, currency: str = "USD", language: str = "en", country: str = "us"):
        self.currency = currency.upper()
        self.language = language
        self.country = country
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept-Language': f'{language}-{country.upper()},{language};q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })
        for name, value in self.CONSENT_COOKIES.items():
            self.session.cookies.set(name, value, domain='.google.com')

    def _build_search_url(self, legs: list, adults: int = 1, children: int = 0) -> str:
        """Build the Google Flights search URL using natural language query.

        Google Flights renders full flight results (with prices in ARIA labels)
        when accessed via the ?q= parameter with a natural language query.
        """
        leg = legs[0]
        date_obj = datetime.strptime(leg['date'], '%Y-%m-%d')
        date_str = date_obj.strftime('%B %d %Y')

        if len(legs) == 1:
            trip = "one way"
        else:
            trip = "round trip"

        parts = [f"flights from {leg['origin']} to {leg['destination']} on {date_str} {trip}"]

        if adults > 1:
            parts.append(f"{adults} adults")
        if children > 0:
            parts.append(f"{children} children")

        query = " ".join(parts)

        return (
            f"https://www.google.com/travel/flights"
            f"?q={requests.utils.quote(query)}"
            f"&curr={self.currency}"
            f"&hl={self.language}"
            f"&gl={self.country}"
        )

    def _parse_flight_labels(self, html: str) -> list:
        """Parse flight information from ARIA labels in the HTML."""
        # Normalize unicode whitespace characters to regular spaces
        html = html.replace('\u202f', ' ').replace('\u00a0', ' ')
        labels = re.findall(r'aria-label="([^"]{50,})"', html)

        flights = []
        current_flight = None
        pending_layovers = []

        # Process labels in order -- flights and their layovers appear sequentially
        for label in labels:
            # Match flight offer labels
            # One-way: "From X US dollars. ..."
            # Round-trip: "From X US dollars round trip total. ..."
            flight_match = re.match(
                r'From (\d[\d,]*) US dollars?(?:\s+round\s+trip\s+total)?\.\s*'
                r'(Nonstop|(\d+) stops?) flight with ([^.]+)\.\s*'
                r'(?:Operated by [^.]+\.\s*)?'
                r'Leaves ([^.]+?) at (\d{1,2}:\d{2}\s*[AP]M) on ([^.]+?) '
                r'and arrives at ([^.]+?) at (\d{1,2}:\d{2}\s*[AP]M) on ([^.]+?)\.\s*'
                r'Total duration (\d+\s*hr\s*(?:\d+\s*min)?)',
                label
            )
            if flight_match:
                # Save previous flight if any
                if current_flight:
                    current_flight['layovers'] = pending_layovers
                    flights.append(current_flight)
                    pending_layovers = []

                price = int(flight_match.group(1).replace(',', ''))
                stops_text = flight_match.group(2)
                airline = flight_match.group(4).strip()
                dep_airport = flight_match.group(5).strip()
                dep_time = flight_match.group(6).strip()
                dep_date_str = flight_match.group(7).strip()
                arr_airport = flight_match.group(8).strip()
                arr_time = flight_match.group(9).strip()
                arr_date_str = flight_match.group(10).strip()
                duration = flight_match.group(11).strip()

                num_stops = 0 if stops_text == 'Nonstop' else int(flight_match.group(3))

                current_flight = {
                    'price': price,
                    'currency': self.currency,
                    'airline': airline,
                    'stops': num_stops,
                    'departure': {
                        'airport': dep_airport,
                        'time': dep_time,
                        'date': dep_date_str,
                    },
                    'arrival': {
                        'airport': arr_airport,
                        'time': arr_time,
                        'date': arr_date_str,
                    },
                    'duration': duration,
                    'layovers': [],
                }
                continue

            # Match layover labels
            layover_match = re.match(
                r'Layover \((\d+) of (\d+)\) is a (.+?) layover at (.+?) in (.+?)\.',
                label
            )
            if layover_match:
                pending_layovers.append({
                    'index': int(layover_match.group(1)),
                    'total': int(layover_match.group(2)),
                    'duration': layover_match.group(3).strip(),
                    'airport': layover_match.group(4).strip(),
                    'city': layover_match.group(5).strip(),
                })

        # Don't forget the last flight
        if current_flight:
            current_flight['layovers'] = pending_layovers
            flights.append(current_flight)

        return flights

    def search(
        self,
        origin: str,
        destination: str,
        date: str,
        return_date: Optional[str] = None,
        adults: int = 1,
        children: int = 0,
        max_retries: int = 3,
    ) -> dict:
        """
        Search for flights.

        Args:
            origin: IATA airport code (e.g., 'HKG')
            destination: IATA airport code (e.g., 'LAX')
            date: Departure date in YYYY-MM-DD format
            return_date: Return date for round trip (optional)
            adults: Number of adult passengers
            children: Number of child passengers
            max_retries: Number of retry attempts on failure

        Returns:
            Dictionary with search results
        """
        legs = [{'origin': origin.upper(), 'destination': destination.upper(), 'date': date}]
        if return_date:
            legs.append({'origin': destination.upper(), 'destination': origin.upper(), 'date': return_date})

        trip_type = "round_trip" if return_date else "one_way"
        url = self._build_search_url(legs, adults, children)

        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, timeout=30, allow_redirects=True)

                if resp.status_code != 200:
                    if attempt < max_retries - 1:
                        wait = (attempt + 1) * 2
                        print(f"  [Retry {attempt+1}] HTTP {resp.status_code}, waiting {wait}s...", file=sys.stderr)
                        time.sleep(wait)
                        continue
                    return self._error_result(f"HTTP {resp.status_code}", origin, destination, date)

                # Check for consent redirect
                if 'consent.google' in resp.url:
                    # Try to bypass by fetching with extra cookies
                    self.session.cookies.set('CONSENT', 'YES+cb.20231008-14-p0.en+FX+999', domain='.google.com')
                    resp = self.session.get(url, timeout=30, allow_redirects=True)
                    if 'consent.google' in resp.url:
                        return self._error_result("Blocked by consent page", origin, destination, date)

                flights = self._parse_flight_labels(resp.text)

                # Deduplicate (Google sometimes renders flights twice)
                seen = set()
                unique_flights = []
                for f in flights:
                    key = (f['price'], f['airline'], f['departure']['time'], f['stops'])
                    if key not in seen:
                        seen.add(key)
                        unique_flights.append(f)

                return {
                    'status': 'success',
                    'search': {
                        'origin': origin.upper(),
                        'destination': destination.upper(),
                        'date': date,
                        'return_date': return_date,
                        'trip_type': trip_type,
                        'adults': adults,
                        'children': children,
                        'currency': self.currency,
                    },
                    'results_count': len(unique_flights),
                    'flights': unique_flights,
                    'source': 'google_flights',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                }

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait = (attempt + 1) * 3
                    print(f"  [Retry {attempt+1}] Timeout, waiting {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                return self._error_result("Request timed out", origin, destination, date)

            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait = (attempt + 1) * 2
                    print(f"  [Retry {attempt+1}] Error: {e}, waiting {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                return self._error_result(str(e), origin, destination, date)

        return self._error_result("Max retries exceeded", origin, destination, date)

    def search_multi_city(self, legs: list, adults: int = 1, children: int = 0) -> dict:
        """
        Search for multi-city flights by searching each leg separately.

        Args:
            legs: List of dicts with keys: origin, destination, date
            adults: Number of adult passengers
            children: Number of child passengers

        Returns:
            Dictionary with search results for all legs
        """
        all_results = []
        total_min_price = 0

        for i, leg in enumerate(legs):
            print(f"  Searching leg {i+1}: {leg['origin']} -> {leg['destination']} on {leg['date']}...", file=sys.stderr)
            result = self.search(
                origin=leg['origin'],
                destination=leg['destination'],
                date=leg['date'],
                adults=adults,
                children=children,
            )
            all_results.append(result)

            if result['status'] == 'success' and result['flights']:
                cheapest = min(f['price'] for f in result['flights'])
                total_min_price += cheapest

            # Rate limiting between searches
            if i < len(legs) - 1:
                time.sleep(2)

        return {
            'status': 'success',
            'trip_type': 'multi_city',
            'legs': all_results,
            'total_legs': len(legs),
            'estimated_min_total_price': total_min_price,
            'currency': self.currency,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

    def _error_result(self, error_msg: str, origin: str, destination: str, date: str) -> dict:
        return {
            'status': 'error',
            'error': error_msg,
            'search': {
                'origin': origin,
                'destination': destination,
                'date': date,
            },
            'results_count': 0,
            'flights': [],
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }


def format_results_table(results: dict) -> str:
    """Format search results as a readable table."""
    lines = []

    if results.get('trip_type') == 'multi_city':
        lines.append("=" * 120)
        lines.append("MULTI-CITY FLIGHT SEARCH RESULTS")
        lines.append("=" * 120)

        for i, leg_result in enumerate(results['legs']):
            search = leg_result.get('search', {})
            lines.append(f"\n--- Leg {i+1}: {search.get('origin', '?')} -> {search.get('destination', '?')} on {search.get('date', '?')} ---")
            lines.append(_format_flights_table(leg_result))

        lines.append(f"\nEstimated minimum total price: ${results.get('estimated_min_total_price', '?')} {results.get('currency', 'USD')}")
        return '\n'.join(lines)

    search = results.get('search', {})
    lines.append("=" * 120)
    lines.append(f"FLIGHT SEARCH: {search.get('origin', '?')} -> {search.get('destination', '?')}")
    lines.append(f"Date: {search.get('date', '?')}" + (f"  Return: {search.get('return_date')}" if search.get('return_date') else "  (One-way)"))
    lines.append(f"Passengers: {search.get('adults', 1)} adult(s)" + (f", {search.get('children')} child(ren)" if search.get('children') else ""))
    lines.append(f"Currency: {search.get('currency', 'USD')}")
    if search.get('return_date'):
        lines.append("NOTE: Prices shown are ROUND-TRIP totals (outbound leg shown; return included in price)")
    lines.append("=" * 120)
    lines.append(_format_flights_table(results))

    return '\n'.join(lines)


def _format_flights_table(results: dict) -> str:
    """Format a single search result as a table."""
    lines = []
    flights = results.get('flights', [])

    if not flights:
        if results.get('status') == 'error':
            lines.append(f"  ERROR: {results.get('error', 'Unknown error')}")
        else:
            lines.append("  No flights found.")
        return '\n'.join(lines)

    lines.append(f"\n{'Price':>8}  {'Airline':<35} {'Stops':>5}  {'Depart':>8}  {'Arrive':>8}  {'Duration':<15}  {'Route'}")
    lines.append("-" * 120)

    for f in sorted(flights, key=lambda x: x['price']):
        dep = f['departure']
        arr = f['arrival']
        stops_str = "Nonstop" if f['stops'] == 0 else f"{f['stops']} stop{'s' if f['stops'] > 1 else ''}"

        route = f"{dep['airport'][:30]} -> {arr['airport'][:30]}"

        lines.append(
            f"${f['price']:>7,}  {f['airline']:<35} {stops_str:>7}  {dep['time']:>8}  {arr['time']:>8}  {f['duration']:<15}  {route}"
        )

        # Show layover details
        for lo in f.get('layovers', []):
            lines.append(f"{'':>60} Layover: {lo['duration']} at {lo['airport']}, {lo['city']}")

    lines.append(f"\nTotal: {len(flights)} flight(s) found")

    if flights:
        cheapest = min(f['price'] for f in flights)
        nonstop = [f for f in flights if f['stops'] == 0]
        cheapest_nonstop = min(f['price'] for f in nonstop) if nonstop else None

        lines.append(f"Cheapest: ${cheapest:,}")
        if cheapest_nonstop is not None:
            lines.append(f"Cheapest nonstop: ${cheapest_nonstop:,}")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Search for flight prices using Google Flights data.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # One-way search
  python search_flights.py --origin HKG --destination LAX --date 2026-06-15

  # Round trip
  python search_flights.py --origin HKG --destination LAX --date 2026-06-15 --return-date 2026-06-22

  # Multi-city
  python search_flights.py --multi "HKG-LAX:2026-06-15,LAX-SFO:2026-06-17"

  # With passengers
  python search_flights.py --origin HKG --destination LAX --date 2026-06-15 --adults 2 --children 1

  # JSON output
  python search_flights.py --origin HKG --destination LAX --date 2026-06-15 --json
        """
    )

    parser.add_argument('--origin', '-o', help='Origin airport IATA code (e.g., HKG)')
    parser.add_argument('--destination', '-d', help='Destination airport IATA code (e.g., LAX)')
    parser.add_argument('--date', '-dt', help='Departure date (YYYY-MM-DD)')
    parser.add_argument('--return-date', '-rd', help='Return date for round trip (YYYY-MM-DD)')
    parser.add_argument('--multi', '-m', help='Multi-city search: "HKG-LAX:2026-06-15,LAX-SFO:2026-06-17"')
    parser.add_argument('--adults', '-a', type=int, default=1, help='Number of adults (default: 1)')
    parser.add_argument('--children', '-c', type=int, default=0, help='Number of children (default: 0)')
    parser.add_argument('--currency', '-cur', default='USD', help='Currency code (default: USD)')
    parser.add_argument('--json', '-j', action='store_true', help='Output raw JSON')
    parser.add_argument('--output', '-out', help='Save results to a JSON file')

    args = parser.parse_args()

    # Validate arguments
    if not args.multi and not (args.origin and args.destination and args.date):
        parser.error("Either --multi or --origin/--destination/--date are required")

    searcher = FlightSearcher(currency=args.currency)

    if args.multi:
        # Parse multi-city input
        legs = []
        for segment in args.multi.split(','):
            segment = segment.strip()
            route, date = segment.split(':')
            origin, destination = route.split('-')
            legs.append({
                'origin': origin.strip().upper(),
                'destination': destination.strip().upper(),
                'date': date.strip(),
            })

        print(f"Searching {len(legs)} legs...", file=sys.stderr)
        results = searcher.search_multi_city(
            legs=legs,
            adults=args.adults,
            children=args.children,
        )
    else:
        trip_desc = f"{args.origin} -> {args.destination} on {args.date}"
        if args.return_date:
            trip_desc += f" (return {args.return_date})"
        print(f"Searching: {trip_desc}...", file=sys.stderr)

        results = searcher.search(
            origin=args.origin,
            destination=args.destination,
            date=args.date,
            return_date=args.return_date,
            adults=args.adults,
            children=args.children,
        )

    # Output
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print(format_results_table(results))

    # Save to file if requested
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {args.output}", file=sys.stderr)

    return 0 if results.get('status') == 'success' else 1


if __name__ == '__main__':
    sys.exit(main())
