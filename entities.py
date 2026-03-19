"""
Canonical entity definitions for all airports, cities, and metro areas used by the scanner.

Every scanner stage must import from here — never scatter IDs across files.

Entity kinds:
  airport: specific airport code (IATA), use for exact verification searches
  metro:   Google Freebase metro/city ID (/m/xxxxx), use for Explore region scans
  city:    city-level ID, use for Explore when no metro ID is known

Rule:
  Explore scans  → use 'google_id' (may be airport or metro)
  Verification   → prefer airport IATA ('iata') for exact routing
"""

# ---------------------------------------------------------------------------
# Origin airports / cities (departure points)
# ---------------------------------------------------------------------------
ORIGINS = {
    # Chinese cities — home base
    "PVG": {"kind": "airport", "iata": "PVG", "google_id": "/m/06wjf",  "city": "Shanghai",    "country": "CN"},
    "HGH": {"kind": "airport", "iata": "HGH", "google_id": "/m/014vm4", "city": "Hangzhou",    "country": "CN"},
    "PEK": {"kind": "airport", "iata": "PEK", "google_id": "/m/01914",  "city": "Beijing",     "country": "CN"},
    "CAN": {"kind": "airport", "iata": "CAN", "google_id": "/m/0393g",  "city": "Guangzhou",   "country": "CN"},
    "SZX": {"kind": "airport", "iata": "SZX", "google_id": "/m/0lbmv",  "city": "Shenzhen",    "country": "CN"},
    "CTU": {"kind": "airport", "iata": "CTU", "google_id": "/m/016v46", "city": "Chengdu",     "country": "CN"},
    "CKG": {"kind": "airport", "iata": "CKG", "google_id": "/m/017236", "city": "Chongqing",   "country": "CN"},
    "WUH": {"kind": "airport", "iata": "WUH", "google_id": "/m/0l3cy",  "city": "Wuhan",       "country": "CN"},
    "NKG": {"kind": "airport", "iata": "NKG", "google_id": "/m/05gqy",  "city": "Nanjing",     "country": "CN"},
    "XMN": {"kind": "airport", "iata": "XMN", "google_id": "/m/0126c3", "city": "Xiamen",      "country": "CN"},
    "NGB": {"kind": "airport", "iata": "NGB", "google_id": "/m/01l33l", "city": "Ningbo",      "country": "CN"},
    "TAO": {"kind": "airport", "iata": "TAO", "google_id": "/m/01l3s0", "city": "Qingdao",     "country": "CN"},
    "DLC": {"kind": "airport", "iata": "DLC", "google_id": "/m/01l3k6", "city": "Dalian",      "country": "CN"},
    "TSN": {"kind": "airport", "iata": "TSN", "google_id": "/m/0df4y",  "city": "Tianjin",     "country": "CN"},
    "FOC": {"kind": "airport", "iata": "FOC", "google_id": "/m/01jzm9", "city": "Fuzhou",      "country": "CN"},
    # SE Asia
    "CGK": {"kind": "airport", "iata": "CGK", "google_id": "/m/044rv",  "city": "Jakarta",     "country": "ID"},
    "BKK": {"kind": "metro",   "iata": "BKK", "google_id": "/m/0fn2g",  "city": "Bangkok",     "country": "TH"},
    "SIN": {"kind": "airport", "iata": "SIN", "google_id": "/m/06t2t",  "city": "Singapore",   "country": "SG"},
    "MNL": {"kind": "airport", "iata": "MNL", "google_id": "/m/0195pd", "city": "Manila",      "country": "PH"},
    "KUL": {"kind": "airport", "iata": "KUL", "google_id": "/m/049d1",  "city": "Kuala Lumpur","country": "MY"},
    "SGN": {"kind": "airport", "iata": "SGN", "google_id": "/m/0hn4h",  "city": "Ho Chi Minh", "country": "VN"},
    # NE Asia
    "HKG": {"kind": "airport", "iata": "HKG", "google_id": "/m/03h64",  "city": "Hong Kong",   "country": "HK"},
    "ICN": {"kind": "airport", "iata": "ICN", "google_id": "/m/0hsqf",  "city": "Seoul",       "country": "KR"},
    "TYO": {"kind": "metro",   "iata": "NRT", "google_id": "/m/07dfk",  "city": "Tokyo",       "country": "JP"},
}

# Lookup by city name (for existing code that uses city names)
ORIGINS_BY_CITY = {v["city"]: k for k, v in ORIGINS.items()}

# ---------------------------------------------------------------------------
# US destination airports (for exact verification)
# ---------------------------------------------------------------------------
DESTS_US = {
    "LAX": {"kind": "airport", "iata": "LAX", "google_id": "LAX", "city": "Los Angeles",    "state": "CA"},
    "SFO": {"kind": "airport", "iata": "SFO", "google_id": "SFO", "city": "San Francisco",  "state": "CA"},
    "JFK": {"kind": "airport", "iata": "JFK", "google_id": "JFK", "city": "New York",        "state": "NY"},
    "EWR": {"kind": "airport", "iata": "EWR", "google_id": "EWR", "city": "Newark",          "state": "NJ"},
    "ORD": {"kind": "airport", "iata": "ORD", "google_id": "ORD", "city": "Chicago",         "state": "IL"},
    "IAH": {"kind": "airport", "iata": "IAH", "google_id": "IAH", "city": "Houston",         "state": "TX"},
    "DFW": {"kind": "airport", "iata": "DFW", "google_id": "DFW", "city": "Dallas",          "state": "TX"},
    "SEA": {"kind": "airport", "iata": "SEA", "google_id": "SEA", "city": "Seattle",         "state": "WA"},
    "BOS": {"kind": "airport", "iata": "BOS", "google_id": "BOS", "city": "Boston",          "state": "MA"},
    "MIA": {"kind": "airport", "iata": "MIA", "google_id": "MIA", "city": "Miami",           "state": "FL"},
    "ATL": {"kind": "airport", "iata": "ATL", "google_id": "ATL", "city": "Atlanta",         "state": "GA"},
    "LAS": {"kind": "airport", "iata": "LAS", "google_id": "LAS", "city": "Las Vegas",       "state": "NV"},
    "DEN": {"kind": "airport", "iata": "DEN", "google_id": "DEN", "city": "Denver",          "state": "CO"},
    "SJC": {"kind": "airport", "iata": "SJC", "google_id": "SJC", "city": "San Jose",        "state": "CA"},
    "PDX": {"kind": "airport", "iata": "PDX", "google_id": "PDX", "city": "Portland",        "state": "OR"},
    "MSP": {"kind": "airport", "iata": "MSP", "google_id": "MSP", "city": "Minneapolis",     "state": "MN"},
    "DTW": {"kind": "airport", "iata": "DTW", "google_id": "DTW", "city": "Detroit",         "state": "MI"},
    "BWI": {"kind": "airport", "iata": "BWI", "google_id": "BWI", "city": "Baltimore",       "state": "MD"},
    "IAD": {"kind": "airport", "iata": "IAD", "google_id": "IAD", "city": "Washington DC",   "state": "VA"},
    "SLC": {"kind": "airport", "iata": "SLC", "google_id": "SLC", "city": "Salt Lake City",  "state": "UT"},
    "HNL": {"kind": "airport", "iata": "HNL", "google_id": "HNL", "city": "Honolulu",        "state": "HI", "exclude": True},
}

# Lookup by city name (handles "Los Angeles" → "LAX")
DESTS_US_BY_CITY = {v["city"]: k for k, v in DESTS_US.items()}

# Explore-level US target (the whole country)
US_EXPLORE_ID = "/m/09c7w0"   # Google Freebase ID for United States

# ---------------------------------------------------------------------------
# Known stopover hubs (for extended-stay detection)
# ---------------------------------------------------------------------------
HUB_AIRPORTS = {
    "ICN": {"kind": "airport", "iata": "ICN", "google_id": "/m/0hsqf",  "city": "Seoul",     "country": "KR"},
    "NRT": {"kind": "airport", "iata": "NRT", "google_id": "/m/07dfk",  "city": "Tokyo",     "country": "JP"},
    "HKG": {"kind": "airport", "iata": "HKG", "google_id": "/m/03h64",  "city": "Hong Kong", "country": "HK"},
    "SIN": {"kind": "airport", "iata": "SIN", "google_id": "/m/06t2t",  "city": "Singapore", "country": "SG"},
    "TPE": {"kind": "airport", "iata": "TPE", "google_id": "/m/06nrt",  "city": "Taipei",    "country": "TW"},
    "PVG": {"kind": "airport", "iata": "PVG", "google_id": "/m/06wjf",  "city": "Shanghai",  "country": "CN"},
    "PEK": {"kind": "airport", "iata": "PEK", "google_id": "/m/01914",  "city": "Beijing",   "country": "CN"},
    "DOH": {"kind": "airport", "iata": "DOH", "google_id": "/m/01f62",  "city": "Doha",      "country": "QA"},
    "DXB": {"kind": "airport", "iata": "DXB", "google_id": "/m/0c46q",  "city": "Dubai",     "country": "AE"},
}

# Alias keywords for stopover detection from page text
HUB_KEYWORDS = {
    "ICN": ["Seoul", "ICN", "Incheon"],
    "NRT": ["Tokyo", "NRT", "HND", "Narita", "Haneda"],
    "HKG": ["Hong Kong", "HKG"],
    "SIN": ["Singapore", "SIN", "Changi"],
    "TPE": ["Taipei", "TPE", "Taoyuan"],
    "PVG": ["Shanghai", "PVG", "Pudong"],
    "PEK": ["Beijing", "PEK", "Capital"],
    "DOH": ["Doha", "DOH"],
    "DXB": ["Dubai", "DXB"],
}

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def get_origin_google_id(iata: str) -> str:
    """Get the Google Freebase or airport ID for Explore scanning."""
    entry = ORIGINS.get(iata)
    return entry["google_id"] if entry else iata


def get_dest_iata(city_name: str) -> str | None:
    """Map a destination city name (from Explore page) to IATA code."""
    return DESTS_US_BY_CITY.get(city_name)


def get_origin_iata_by_city(city_name: str) -> str | None:
    """Map origin city name to IATA code."""
    return ORIGINS_BY_CITY.get(city_name)


def is_excluded_dest(city_name: str) -> bool:
    """True if destination should be excluded (Hawaii etc.)."""
    iata = DESTS_US_BY_CITY.get(city_name)
    if iata:
        return DESTS_US[iata].get("exclude", False)
    # Also catch by keyword
    exclude_keywords = {"Honolulu", "Kauai", "Maui", "Hilo", "Hawaii",
                        "1.5h drive", "1h drive"}
    return any(kw in city_name for kw in exclude_keywords)


def detect_stopover_iata(text: str, origin_iata: str, dest_iata: str) -> str | None:
    """
    Detect the most likely stopover airport from page text.
    Checks known hub keywords first, then raw IATA regex.
    Excludes origin and destination codes.
    """
    exclude = {origin_iata, dest_iata}

    # Check known hubs by keyword (most reliable)
    for iata, keywords in HUB_KEYWORDS.items():
        if iata in exclude:
            continue
        if any(kw in text for kw in keywords):
            return iata

    # Fallback: find any 3-letter uppercase code in text
    import re
    codes = re.findall(r'\b([A-Z]{3})\b', text)
    for code in codes:
        if code not in exclude and code in HUB_AIRPORTS:
            return code

    return None


# ---------------------------------------------------------------------------
# US destination Freebase city IDs (for point-to-point search URL building)
# Distinct from airport IATA codes — these are Google/Freebase metro IDs
# ---------------------------------------------------------------------------
DESTS_US_FREEBASE = {
    "Los Angeles":   "/m/030qb3t",
    "San Francisco": "/m/0d6lp",
    "New York":      "/m/02_286",
    "Newark":        "/m/02_286",   # same metro as NYC
    "Chicago":       "/m/01_d4",
    "Houston":       "/m/03l2n",
    "Dallas":        "/m/0f2rq",
    "Seattle":       "/m/0d9jr",
    "Boston":        "/m/01cx_",
    "Miami":         "/m/02_3yh",
    "Atlanta":       "/m/013yq",
    "Las Vegas":     "/m/0cv3w",
    "Denver":        "/m/02cl1",
    "Portland":      "/m/02frhbc",
    "Minneapolis":   "/m/0fpzwf",
    "Baltimore":     "/m/094jv",
    "Washington DC": "/m/0rh6k",
    "Salt Lake City": "/m/0f2r6",
    # Additional cities from drill results
    "Austin":        "/m/0vzm",
    "Nashville":     "/m/05jbn",
    "Philadelphia":  "/m/0dclg",
    "Phoenix":       "/m/0d35y",
    "San Diego":     "/m/071vr",
    "Orlando":       "/m/0ply0",
    "Savannah":      "/m/0lhn5",
    # Additional cities seen in scan results
    "Tampa":         "/m/0hyxv",
    "Fort Lauderdale": "/m/0fvyg",
    "Charlotte":     "/m/0fttg",
    "New Orleans":   "/m/0f8l9c",
    "Pittsburgh":    "/m/068p2",
    "San Antonio":   "/m/06mxs",
    "San Jose":      "/m/0d5jd",
    "Detroit":       "/m/02dtg",
    "St. Louis":     "/m/0rh62",
}

# Hub cities: IATA → Freebase ID (convenient for building stopover URLs)
HUB_CITIES_FREEBASE = {v["city"]: v["google_id"] for v in HUB_AIRPORTS.values()}


def get_dest_freebase_id(city_name: str) -> str:
    """Return Freebase city ID for a US destination, or US_EXPLORE_ID as fallback."""
    return DESTS_US_FREEBASE.get(city_name, US_EXPLORE_ID)


def get_origin_cid_by_city(city_name: str) -> str | None:
    """Return Google Freebase ID for an origin city (looked up by city name)."""
    iata = ORIGINS_BY_CITY.get(city_name)
    if iata:
        return ORIGINS[iata]["google_id"]
    return None
