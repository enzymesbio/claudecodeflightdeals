# Bug Fare Scanner System Design

**Document Version:** 1.0
**Date:** 2026-03-17
**Purpose:** Comprehensive design document for a redesigned bug fare scanner system, based on all lessons learned from the conversation and experiments.

---

## Table of Contents

1. [What Worked](#what-worked)
2. [What Failed](#what-failed)
3. [User Preferences](#user-preferences)
4. [Scanner Architecture](#scanner-architecture)
5. [Data Model](#data-model)
6. [Monitoring and Alerting](#monitoring-and-alerting)
7. [Implementation Roadmap](#implementation-roadmap)

---

## What Worked

### Tier 1: Reliable, Production-Ready Methods

**1. Google Flights Explore via Playwright (protobuf TFS URLs)**
- Loads the full Explore map with prices for any origin city to a country-level destination.
- Protobuf TFS parameter encoding is fully reverse-engineered:
  - Field 1=28 (version), Field 2=3 (explore round-trip), Field 3=legs, Field 8=adults, Field 9=cabin class (1=economy, 2=premium economy, 3=business, 4=first).
  - Origin type=3 (city), Destination type=4 (country).
  - City IDs use Freebase /m/ format (e.g., /m/044rv = Jakarta, /m/09c7w0 = United States).
- Clicking city tabs triggers fresh real-time searches from Google's backend.
- "View flights" links extracted via JS (`document.querySelectorAll('a[href*="travel/flights"]')`) navigate to actual booking pages with full flight details.
- Cookie consent and "Proceed anyway" browser upgrade dialogs handled reliably.
- Currency controlled via `curr=USD` parameter; locale via `gl=hk` and `hl=en`.
- **Key limitation:** Explore pages show prices for a specific departure date and flexible return. Does not show multi-city or open-jaw.
- **Current script:** `D:/claude/flights/bug_fare_scanner.py`

**2. AF_initDataCallback parsing from raw HTML (no browser needed)**
- Fetch Google Flights search URLs with `urllib.request` + cookie `CONSENT=YES+`.
- Parse `AF_initDataCallback` blocks (specifically `ds:1`) from raw HTML.
- Contains complete flight data as deeply nested JSON arrays: airlines, prices, stops, durations, layover details.
- No browser/Playwright needed -- pure HTTP request with cookie injection.
- Good for rapid scanning of specific routes.
- Prices confirmed accurate against live Google Flights results.
- **Discovered by:** SerpAPI agent experiment.

**3. Playwright XHR Intercept (GetShoppingResults API)**
- Intercept `GetShoppingResults` API at `/_/FlightsFrontendUi/data/travel.frontend.flights.FlightsFrontendService/GetShoppingResults`.
- Returns full JSON with all flight options, prices, airlines, layover details.
- Captured 120KB+ JSON response with 32+ flight results in a single intercept.
- Best for deep verification of specific routes after Explore discovery.
- **Discovered by:** XHR intercept agent experiment.

**4. Google Flights ARIA Label Parsing (search_flights.py)**
- Fetches Google Flights via `?q=` natural language query URLs.
- Parses structured ARIA accessibility labels from server-rendered HTML.
- Regex: `r'From (\d[\d,]*) US dollars?(?:\s+round\s+trip\s+total)?\..*'`
- No API keys, no proxies, no JavaScript execution needed.
- Zero blocks across 700+ searches.
- Supports one-way, round-trip, multi-city.
- **Key limitation:** Only reliably returns economy class results. Adding "business class" to the query text does NOT guarantee business class results. Cannot be trusted for cabin class differentiation.
- **Current script:** `D:/claude/flights/search_flights.py`

**5. fast_flights Python Library**
- Used by the Amadeus agent experiment.
- A protobuf-encoded Google Flights scraper that uses local Playwright to bypass the consent wall.
- Returned 196 priced business class flights in a single run.
- Install: `pip install fast-flights`.

### Tier 2: Partially Working Methods

**6. Trip.com Direct URLs**
- URLs with specific route parameters load and return economy flight data.
- 106+ flights found per search with DOM price extraction.
- **Limitation:** `cabin=c` parameter for business class is silently ignored. All results return economy regardless of cabin parameter.
- **Limitation:** Third visit from same IP triggers CAPTCHA slider.

**7. Apify Google Flights Actor**
- Actor: `johnvc~google-flights-data-scraper-flight-and-price-search`
- Works for economy class searches.
- **Limitation:** `travel_class` parameter is completely ignored -- all results return `[Economy, Economy]` regardless of setting.
- **Limitation:** $5 free credit limit.

**8. ITA Matrix via Playwright**
- ITA Matrix v5 uses Angular Material (not the old GWT).
- Playwright can fill forms, select cabin class, click search, and extract results.
- Up to 500 results per search.
- All Chinese airlines appear (China Eastern, China Southern, Sichuan Airlines, Air China).
- **Limitation:** Form interaction is fragile -- GWT widgets can cause Playwright to fill wrong fields (e.g., "CGK" entered into Currency field instead of Origin).
- **Limitation:** Search takes 10-35 seconds per query.
- **Current script:** `D:/claude/flights/ita_matrix_scraper.py`

**9. Ctrip lowestPrice API**
- `GET https://flights.ctrip.com/itinerary/api/12808/lowestPrice?flightWay=Oneway&dcity=CTU&acity=SHA`
- No authentication required.
- Returns daily lowest prices for ~170 dates.
- **Limitation:** Domestic China routes only (uses Ctrip city codes, not airport codes).

**10. Locale/Currency Independence Verified**
- Tested 6+ locales (`gl=hk`, `gl=jp`, `gl=sg`, `gl=cn`, `gl=us`, `gl=de`).
- Prices do NOT vary by locale/geolocation parameter -- same fare data returned regardless.
- Currency display changes but underlying fare is identical.
- **Conclusion:** No pricing bias from locale settings. Use `gl=hk` with `curr=USD` as standard.

---

## What Failed

### Complete Blocks (CAPTCHA / Bot Detection)

| Platform | Blocking Mechanism | Details |
|----------|-------------------|---------|
| **Skyscanner** | PerimeterX (`PXrf8vapwA`) | "Are you a person or a robot?" on all search pages. Homepage loads fine. Tried Chromium, Firefox, system Chrome, headed mode, playwright-stealth, Skyscanner.co.id variant, API endpoints. All blocked at IP reputation level (datacenter IP). |
| **Expedia** | 429 "Bot or Not?" | All searches return CAPTCHA. Tried Firefox engine, playwright-stealth. Blocked. |
| **Kayak/Momondo** | CAPTCHA redirect | Immediately redirected to `sitecaptcha.html`. Cannot be scraped without residential proxy. |
| **Trip.com** (after 2-3 visits) | Slider CAPTCHA | First 2 visits work, third triggers "Sorry, you have made too many attempts." |

### Parameter Ignored / Data Not Returned

| Platform | Issue | Details |
|----------|-------|---------|
| **Google Flights `?q=` business class** | Cabin class not enforced | Adding "business class" to natural language query does NOT guarantee business class results. ARIA labels do not indicate cabin class. Proven by comparing identical prices between "economy" and "business" queries. |
| **Apify actor travel_class** | Parameter silently ignored | `travel_class=2` and `travel_class=3` both return economy results tagged `[Economy, Economy]`. |
| **Trip.com cabin=c** | Parameter silently ignored | All results display "1 adult - Economy" regardless of `cabin=c` URL parameter. |

### API/Authentication Barriers

| Platform | Issue |
|----------|-------|
| **Amadeus API** | Requires paid API key (free tier exists but needs registration) |
| **Kiwi/Tequila API** | Requires API key (403 without it) |
| **SerpApi** | Requires paid key; no free/demo key exists |
| **Wego API** | Accepted search but returned 0 trips/fares -- likely needs additional auth headers |
| **Aviationstack** | Requires API key (401 without it) |
| **FlightAPI.io** | Requires API key |
| **Skypicker/Kiwi public API** | Retired -- returns 404 |

### Form Interaction Failures

| Platform | Issue |
|----------|-------|
| **Google Flights form** | Material Design overlay (`VfPpkd-aPP78e` div) intercepts pointer events. Even `force=True` and JavaScript `dispatchEvent` fail to properly fill origin/destination fields. Business class can be set via JS dropdown, but form submits with empty fields. |
| **ITA Matrix form** | Complex GWT/Angular Material widgets cause mismatched field filling. Currency field catches airport code input. |

### Chinese Platform Barriers

| Platform | Issue |
|----------|-------|
| **Ctrip International** | `batchSearch` endpoint returns `showAuthCode:true` (CAPTCHA required for international routes). Domestic `products` endpoint decommissioned (`"msg":"API offline"`). |
| **Trip.com REST API** | `soa2/14021/flightListSearch` and `soa2/16769/flightListSearch` endpoints return 404 (decommissioned). `soa2/27015/FlightMiddleSearch` works via XHR intercept but triggers CAPTCHA. Returns HTTP 428 (Akamai Bot Manager) and HTTP 432 (custom anti-bot). |
| **Fliggy** | Requires Alibaba Cloud OAuth 2.0 (Chinese phone number needed). Uses proprietary NCMS CAPTCHA that third-party solvers cannot handle. |
| **Airline direct sites** (sichuanair.com, csair.com, ceair.com) | All fully JavaScript-rendered with anti-bot protections (Tencent Cloud device fingerprinting on sichuanair.com). Mobile sites use Flutter compiled/obfuscated code. |

---

## User Preferences

### Family Composition
- 2 adults + 1 toddler (~2 years 7 months old, needs own seat -- not lap infant)
- First international trip for child

### Location
- Lives in Jiaxing, Zhejiang, China
- Closest airports: Shanghai Pudong (PVG), Hangzhou Xiaoshan (HGH)
- Shanghai Hongqiao (SHA) also close but mostly domestic

### Cabin Class Preference (priority order)
1. **Business class** -- strong preference for comfort with small child
2. **Premium Economy** -- acceptable alternative
3. **First class** -- if bug fare found, would be excellent
4. **Economy** -- only if significantly cheaper

### Trip Planning
- **3 separate round-trip bug fare trips from Jakarta**, spaced approximately 3 months apart
- **Trip 1:** Jakarta (CGK) to USA -- LAX or Houston preferred
- **Trip later:** Jakarta (CGK) to Frankfurt, Germany (no Schengen visa yet; need to apply at German consulate in Shanghai)
- Daycare ends April 11, prefer departure after that date
- Avoid Chinese holidays: May 1 (Labor Day), October 1 (National Day), Spring Festival (Chinese New Year)
- Open to RT vs two one-ways, or mix -- whichever is cheaper
- Open to slightly more expensive cash fare IF it earns meaningful award points/miles

### Booking Strategy
- **Search using 1 adult** to find deals (faster, simpler, more results returned by Google)
- **Book using 2 adults + 1 child (2A+1C)** for final pricing
- Price estimation: 1-adult price x 2.75 approximates 2A+1C (child at ~75% of adult fare)
- Price is #1 priority, airline reputation is #2
- Wants reputable airlines less likely to cancel

### Airline Preferences
- **Preferred:** Star Alliance airlines (for mile earning and reliability)
- **OK with:** All Chinese airlines (China Eastern, China Southern, Air China, Sichuan, Hainan, Xiamen), Korean (Korean Air, Asiana, Air Premia), Japanese (ANA, JAL), Cathay Pacific, US carriers (United, Delta, American), Singapore Airlines, Garuda Indonesia, Thai Airways, Qatar, Emirates
- **Avoid:** Taiwan airlines (EVA Air, China Airlines, STARLUX) -- user explicitly excluded
- **Avoid:** ZIPAIR (budget carrier)
- **No budget airlines** generally

### Loyalty Programs
- Marriott Bonvoy Platinum member
- United MileagePlus (status matched from Marriott)
- Prefers Star Alliance airlines for earning miles

### Route Flexibility
- Flexible on departure cities in Asia -- any city with cheap positioning is acceptable
- Flexible on US arrival cities -- all mainland US destinations OK
- Prefers West Coast (LAX, SFO), then Houston (IAH), then safe Florida cities (Tampa recommended)
- Flexible on duration (2-6 weeks, longer if cheaper)
- Open to open-jaw, multi-city, one-way combinations

### Display Preferences
- Display prices in USD or CNY (not HKD)
- Do not use Chinese locale flags when scraping (`gl=cn`) -- use `gl=hk`, `gl=jp`, or `gl=sg` instead
- HTML reports: light theme, nice fonts, no dark backgrounds

### Search Types Wanted
- One-way (OW)
- Round-trip (RT)
- Open jaw (e.g., depart CGK to LAX, return from IAH to CGK)
- Multi-city (e.g., CGK to LAX, LAX to IAH, IAH to CGK)

---

## Scanner Architecture

### Design Philosophy

The scanner should be a **two-phase system**: a fast, lightweight **Discovery Phase** that scans broadly for anomalies, followed by a targeted **Verification Phase** that drills into detected anomalies with full flight details. This mirrors the natural process the user follows: browse Google Flights Explore for cheap spots, then click through for details.

### Phase 1: Discovery (Explore Scanner)

**Purpose:** Rapidly scan multiple origin-destination pairs across all cabin classes to detect price anomalies.

**Method:** Google Flights Explore via Playwright with protobuf TFS URLs.

**Why this method:** It is the only method that reliably supports all 4 cabin classes, shows prices for an entire destination region at once, and returns real-time data that matches what the user sees on their own device.

```
Configuration:
  Origins:       10 Asian cities (Jakarta, Bangkok, Singapore, Manila, KL, HCMC, HK, Taipei, Seoul, Tokyo)
                 + PVG, HGH (user's local airports)
  Destinations:  United States (/m/09c7w0), Europe/Germany (/m/0d060g), United Kingdom (/m/07ssc)
  Cabins:        1 (economy), 2 (premium economy), 3 (business), 4 (first)
  Dates:         Rolling window: 30, 60, 90, 120, 150, 180 days out
  Currency:      USD
  Locale:        gl=hk, hl=en
```

**Scan Matrix:**
- 12 origins x 3 destination regions x 4 cabin classes x 6 date windows = 864 scans per full cycle
- Each scan returns 10-30 destination cities with prices
- Estimated time per scan: 8-12 seconds (load page + parse)
- Full cycle: ~2-3 hours

**Output per scan:**
- Origin city, destination city, cabin class, price (USD), dates, stops count, scan timestamp
- Classification: BUG_FARE / CHEAP / NORMAL / EXPENSIVE

**Price Anomaly Detection:**

```
Normal price ranges (round-trip, per person, in USD):

Economy:         $800 - $2,000
Premium Economy: $1,200 - $3,000
Business:        $3,000 - $8,000
First:           $8,000 - $20,000

Bug fare threshold: price < 60% of normal_min
  Economy:         < $480
  Premium Economy: < $720
  Business:        < $1,800
  First:           < $4,800

Near-bug (CHEAP) threshold: price < normal_min
  Any fare below the normal minimum but above bug threshold
```

**Rate Limiting:**
- 3-second delay between page loads (current scanner default)
- Rotate browser context every 50 scans
- Close and reopen browser every 100 scans

### Phase 2: Verification (Deep Drill)

**Purpose:** When Phase 1 detects a potential bug fare, drill into the specific route with multiple methods to confirm the price, extract airline/flight details, and generate a booking-ready URL.

**Method 1 -- Explore Click-Through:**
1. On the Explore page, click the city tab for the detected bug fare destination.
2. Wait for results to refresh.
3. Extract "View flights" links via JS.
4. Navigate to the booking page.
5. Parse full flight details (airline, stops, duration, layover, price).

**Method 2 -- AF_initDataCallback (no browser):**
1. Construct a Google Flights search URL with the specific route, date, and cabin class via TFS protobuf encoding.
2. Fetch with `urllib.request` + `CONSENT=YES+` cookie.
3. Parse `AF_initDataCallback` `ds:1` block for complete flight data.
4. Extract prices, airlines, stops, durations from nested JSON arrays.

**Method 3 -- GetShoppingResults XHR Intercept:**
1. Load the Google Flights search page via Playwright.
2. Intercept the `GetShoppingResults` API call.
3. Parse the full JSON response with all flight options.
4. Cross-reference prices against Phase 1 discovery.

**Method 4 -- fast_flights Library:**
1. Use the `fast_flights` Python library for protobuf-encoded searches.
2. Supports cabin class selection natively.
3. Returns structured flight data.

**Verification Success Criteria:**
- Price confirmed by at least 2 independent methods
- Airline and routing extracted
- Booking URL generated
- Price < bug fare threshold confirmed

### Phase 3: Alert and Report

**When a bug fare is confirmed:**
1. Save to results database with full metadata.
2. Generate an alert entry with:
   - Route (origin -> destination)
   - Cabin class
   - Price per person (USD)
   - Airlines involved
   - Number of stops
   - Duration
   - Booking URL
   - Timestamp of discovery
   - Timestamp of last verification
3. Optional: Send notification (email, webhook, or desktop alert).

### Supporting Components

**A. TFS URL Builder**

The existing protobuf encoder (`build_explore_tfs` in `bug_fare_scanner.py`) should be extended to support:
- Multi-leg trips (currently supports RT with 2 legs; needs N-leg support)
- Child passengers (field 10 or similar for child count)
- Flexible date ranges (currently only single-date or no-date)

```
Supported URL types:
  Explore:    /travel/explore?tfs={tfs}&tfu=GgA&hl=en&gl=hk&curr=USD
  Search:     /travel/flights/{origin}/{dest}/{date}?tfs={tfs}&...
  Booking:    Links extracted from Explore/Search result pages
```

**B. Price History Database**

Store all scan results with timestamps for trend analysis.

```
Schema (JSON or SQLite):
  scan_id:          UUID
  scan_timestamp:   ISO 8601
  origin_code:      IATA code (e.g., CGK)
  origin_city:      City name
  destination_code: IATA code or city name
  destination_country: Country
  cabin_class:      1-4
  cabin_label:      Economy/Premium Economy/Business/First
  price_usd:        Decimal
  price_raw:        Original price as shown
  price_currency:   Currency of raw price
  dates:            Travel dates shown
  stops:            Number of stops
  duration:         Travel duration
  airline:          Airline name(s)
  classification:   BUG_FARE/CHEAP/NORMAL/EXPENSIVE
  verification:     JSON object with verification details
  booking_url:      URL if available
  scan_method:      explore/search/af_callback/xhr
```

**C. Trend Analyzer**

Compare current prices against historical data to detect:
- Price drops (current < previous_min for same route/cabin)
- New routes appearing at anomalous prices
- Fare class transitions (e.g., business class suddenly priced at economy level)
- Seasonal patterns

**D. Scheduling**

```
Recommended scan schedule:
  Full scan (all origins, all cabins, all dates):    Every 6 hours
  Hot routes (Jakarta to US/Europe, business):       Every 1 hour
  Verification of known bug fares:                   Every 15 minutes
  Historical trend analysis:                         Daily
```

Implementation options:
- Windows Task Scheduler (simplest, runs on current machine)
- Python `schedule` library (in-process scheduler)
- Cron-like wrapper script with lockfile to prevent overlapping runs

---

## Data Model

### Origin Cities

```python
ORIGIN_CITIES = {
    # User's local airports
    'shanghai':      {'code': 'PVG', 'city_id': '/m/06wjf',  'name': 'Shanghai'},
    'hangzhou':      {'code': 'HGH', 'city_id': '/m/0fhzf',  'name': 'Hangzhou'},
    # Asian hub cities for bug fare origins
    'jakarta':       {'code': 'CGK', 'city_id': '/m/044rv',  'name': 'Jakarta'},
    'bangkok':       {'code': 'BKK', 'city_id': '/m/0fngf',  'name': 'Bangkok'},
    'singapore':     {'code': 'SIN', 'city_id': '/m/06t2t',  'name': 'Singapore'},
    'manila':        {'code': 'MNL', 'city_id': '/m/0195fg', 'name': 'Manila'},
    'kuala_lumpur':  {'code': 'KUL', 'city_id': '/m/04f_d',  'name': 'Kuala Lumpur'},
    'ho_chi_minh':   {'code': 'SGN', 'city_id': '/m/0hnp7',  'name': 'Ho Chi Minh City'},
    'hong_kong':     {'code': 'HKG', 'city_id': '/m/03h64',  'name': 'Hong Kong'},
    'taipei':        {'code': 'TPE', 'city_id': '/m/0ftkx',  'name': 'Taipei'},
    'seoul':         {'code': 'ICN', 'city_id': '/m/0hsqf',  'name': 'Seoul'},
    'tokyo':         {'code': 'TYO', 'city_id': '/m/07dfk',  'name': 'Tokyo'},
}
```

### Destination Regions

```python
DESTINATION_REGIONS = {
    'united_states': {'city_id': '/m/09c7w0', 'name': 'United States'},
    'germany':       {'city_id': '/m/0d060g', 'name': 'Germany'},
    'united_kingdom':{'city_id': '/m/07ssc',  'name': 'United Kingdom'},
    'europe':        {'city_id': '/m/0j0k',   'name': 'Europe'},  # broader Europe scan
}
```

### Cabin Classes

```python
CABIN_INFO = {
    1: {'label': 'Economy',         'normal_min_usd': 800,   'normal_max_usd': 2000,  'bug_threshold_pct': 0.60},
    2: {'label': 'Premium Economy', 'normal_min_usd': 1200,  'normal_max_usd': 3000,  'bug_threshold_pct': 0.60},
    3: {'label': 'Business',        'normal_min_usd': 3000,  'normal_max_usd': 8000,  'bug_threshold_pct': 0.60},
    4: {'label': 'First',           'normal_min_usd': 8000,  'normal_max_usd': 20000, 'bug_threshold_pct': 0.60},
}
```

### Excluded Airlines

```python
EXCLUDED_AIRLINES = [
    'EVA Air', 'China Airlines', 'STARLUX',  # Taiwan airlines
    'ZIPAIR',                                  # Budget carrier
    'Tigerair',                                # Budget carrier
]
```

---

## Monitoring and Alerting

### Alert Levels

| Level | Condition | Action |
|-------|-----------|--------|
| **CRITICAL** | Business/First class < 60% of normal minimum ($1,800 biz / $4,800 first) | Immediate alert + auto-verify + generate booking URL |
| **HIGH** | Any cabin < 70% of normal minimum | Alert within 15 minutes + verify |
| **MEDIUM** | Any cabin below normal minimum | Log + include in daily report |
| **LOW** | Price drop > 20% from previous scan for same route | Log for trend analysis |

### Notification Options (Future)

1. **Desktop notification** (simplest) -- Python `plyer` or `win10toast` library
2. **Email** -- SMTP via Gmail or similar
3. **WeChat** -- via WeCom/Enterprise WeChat webhook (since user is in China)
4. **Webhook** -- POST to any URL for integration with other tools

### Dashboard (Future)

A simple HTML page (similar to `flight_deals_report.html`) that auto-refreshes and shows:
- Latest scan results
- Active bug fares
- Price trend charts per route
- Scan health status (last successful scan, error count)

---

## Implementation Roadmap

### Phase A: Core Scanner Redesign (Immediate)

1. **Refactor `bug_fare_scanner.py`** to separate concerns:
   - `tfs_encoder.py` -- Protobuf TFS URL builder (reusable)
   - `explore_scanner.py` -- Phase 1 discovery via Explore pages
   - `flight_verifier.py` -- Phase 2 verification (AF_initDataCallback, XHR intercept, fast_flights)
   - `price_classifier.py` -- Anomaly detection and classification
   - `results_store.py` -- JSON/SQLite storage with deduplication

2. **Add destination regions:** Currently only scans US. Add Germany, UK, broader Europe.

3. **Add date windowing:** Scan multiple departure dates (30/60/90/120/150/180 days out) instead of single flexible date.

4. **Fix currency handling:** Current scanner has a potential double-conversion bug. When `curr=USD` is used, prices are already in USD -- do not apply HKD-to-USD conversion. The scanner should detect the actual currency displayed and convert only when necessary.

5. **Add search type support:**
   - Current: RT only (Explore mode).
   - Add: OW scanning (modify TFS to omit return leg or set trip type to 2).
   - Add: Open-jaw detection (compare OW outbound from city A with OW return to city B).

### Phase B: Verification Pipeline (Week 1)

1. **Implement AF_initDataCallback parser** as a standalone module:
   - Input: origin IATA, destination IATA, date, cabin class
   - Output: list of flights with price, airline, stops, duration
   - No browser needed (pure HTTP).

2. **Implement XHR intercept verifier** for cases where AF_initDataCallback is insufficient:
   - Uses existing Playwright infrastructure
   - Captures `GetShoppingResults` API response
   - Extracts full flight JSON

3. **Cross-verify:** Require at least 2 methods to agree on bug fare price before alerting.

### Phase C: Scheduling and Storage (Week 2)

1. **Set up Windows Task Scheduler** entries:
   - Full scan every 6 hours
   - Hot routes every 1 hour
   - Verification every 15 minutes for active bug fares

2. **Implement SQLite storage** (upgrade from flat JSON):
   - Price history table
   - Bug fare alerts table
   - Scan health/status table

3. **Build trend analysis queries:**
   - "Show me all prices for CGK-LAX business over the last 7 days"
   - "Alert me when any business fare drops below $2,000"

### Phase D: Multi-Trip Planner (Week 3)

1. **Trip optimizer** that considers:
   - 3 separate RT trips spaced ~3 months apart
   - Positioning costs from Jiaxing to various Asian origin cities
   - Holiday avoidance (May 1, Oct 1, Spring Festival)
   - Visa requirements (US visa: have it; Schengen: need to apply)
   - Net cost including loyalty point value

2. **Multi-city itinerary builder:**
   - CGK -> LAX -> IAH -> CGK (with domestic US segment)
   - CGK -> FRA -> CGK (after Schengen visa obtained)
   - Mix of bug fare legs + normal fare domestic legs

### Phase E: Dashboard and Alerts (Week 4)

1. **HTML dashboard** auto-generated from scan data
2. **Desktop notifications** for critical bug fares
3. **Daily email summary** of price changes

---

## Appendix: Known Freebase City IDs

```
Jakarta:         /m/044rv
Bangkok:         /m/0fngf
Singapore:       /m/06t2t
Manila:          /m/0195fg
Kuala Lumpur:    /m/04f_d
Ho Chi Minh:     /m/0hnp7
Hong Kong:       /m/03h64
Taipei:          /m/0ftkx
Seoul:           /m/0hsqf
Tokyo:           /m/07dfk
Shanghai:        /m/06wjf
Hangzhou:        /m/0fhzf
Chengdu:         /m/016v46 (CTU) / /m/0_gzwvx (TFU)
Guangzhou:       /m/065k5 (CAN)
Beijing:         /m/01914 (PEK)

United States:   /m/09c7w0
Germany:         /m/0d060g
United Kingdom:  /m/07ssc
Europe:          /m/0j0k
```

## Appendix: Scraping Method Comparison

| Method | Cabin Class Support | Speed | Browser Required | Reliability | Best For |
|--------|-------------------|-------|-----------------|-------------|----------|
| Explore + Playwright | All 4 | 8-12s/scan | Yes | High | Discovery (Phase 1) |
| AF_initDataCallback | All 4 (via TFS URL) | 2-3s/scan | No | High | Rapid verification |
| XHR Intercept | All 4 | 10-15s/scan | Yes | Medium | Deep verification |
| ARIA Label (`?q=`) | Economy only | 1-2s/scan | No | High | Economy-only scans |
| fast_flights | All 4 | 3-5s/scan | Playwright | Medium | Alternative to AF_initDataCallback |
| ITA Matrix + Playwright | All 4 | 10-35s/scan | Yes | Medium | Cross-platform validation |
| Trip.com | Economy only | 5-8s/scan | Yes | Low (CAPTCHA) | Supplementary |
| Apify actor | Economy only | 30-60s/scan | No (API) | Medium | Supplementary (limited credits) |

## Appendix: Bug Fare Characteristics (from conversation)

The Jakarta business class bug fare discovered during the conversation had these characteristics:
- **Route:** CGK to LHR/LAX/Europe
- **Cabin:** Business class
- **Airlines:** Star Alliance interline fares -- THAI + Austrian, Singapore Airlines + SWISS/Lufthansa
- **Price:** $200-453/pp one-way ($809-946 RT) -- cheaper than economy on same routes
- **Booking channels:** Seen on Google Flights, Expedia (WeChat users reported buying there)
- **Duration:** Appeared within hours, some fares disappeared same day
- **Pattern:** Available on specific dates (April 27+, May 1, 4, 8, 15) but not all dates
- **Key lesson:** Bug fares are extremely time-sensitive. The scanner must detect and alert within minutes, not hours. The user confirmed seeing ~$200 in Google Flights calendar popup, but by the time automated verification was attempted, some fares had changed. WeChat community members who spotted it 3 hours before the user had already booked.
