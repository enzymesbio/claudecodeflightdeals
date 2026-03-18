"""Generate an HTML page with clickable Google Flights verification links for all bug fares found."""
import json
import re
import base64
from datetime import datetime, timedelta, timezone

# --- Protobuf encoding (same as bug_fare_scanner.py) ---
def encode_varint(value):
    result = b''
    while value > 0x7f:
        result += bytes([(value & 0x7f) | 0x80])
        value >>= 7
    result += bytes([value])
    return result

def field_varint(num, val):
    return encode_varint((num << 3) | 0) + encode_varint(val)

def field_bytes(num, data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return encode_varint((num << 3) | 2) + encode_varint(len(data)) + data

def build_explore_tfs(origin_city_id, dest_city_id, date=None, cabin=3):
    origin_msg = field_varint(1, 3) + field_bytes(2, origin_city_id)
    dest_msg = field_varint(1, 4) + field_bytes(2, dest_city_id)
    if date:
        leg1 = field_bytes(2, date) + field_bytes(13, origin_msg) + field_bytes(14, dest_msg)
    else:
        leg1 = field_bytes(13, origin_msg) + field_bytes(14, dest_msg)
    leg2 = field_bytes(13, dest_msg) + field_bytes(14, origin_msg)
    pax_config = b'\x08\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01'
    field22 = field_varint(3, 1) + field_varint(4, 1)
    msg = (field_varint(1, 28) + field_varint(2, 3) + field_bytes(3, leg1) +
           field_bytes(3, leg2) + field_varint(8, 1) + field_varint(9, cabin) +
           field_varint(14, 2) + field_bytes(16, pax_config) + field_varint(19, 1) +
           field_bytes(22, field22))
    return base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')

def build_explore_url(origin_city_id, dest_city_id='/m/09c7w0', date=None, cabin=3):
    if not date:
        default_date = datetime.now() + timedelta(days=120)
        date = default_date.strftime('%Y-%m-%d')
    tfs = build_explore_tfs(origin_city_id, dest_city_id, date=date, cabin=cabin)
    return f'https://www.google.com/travel/explore?tfs={tfs}&tfu=GgA&hl=en&gl=hk&curr=USD'

def build_search_tfs(origin_city_id, dest_airport_id, depart_date, return_date, cabin=3):
    """Build TFS for a direct flight search page (not explore)."""
    origin_msg = field_varint(1, 3) + field_bytes(2, origin_city_id)
    dest_msg = field_varint(1, 2) + field_bytes(2, dest_airport_id)
    leg1 = field_bytes(2, depart_date) + field_bytes(13, origin_msg) + field_bytes(14, dest_msg)
    leg2 = field_bytes(2, return_date) + field_bytes(13, dest_msg) + field_bytes(14, origin_msg)
    pax_config = b'\x08\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01'
    field22 = field_varint(3, 1) + field_varint(4, 1)
    msg = (field_varint(1, 27) + field_varint(2, 2) + field_bytes(3, leg1) +
           field_bytes(3, leg2) + field_varint(8, 1) + field_varint(9, cabin) +
           field_varint(14, 2) + field_bytes(16, pax_config) + field_varint(19, 1) +
           field_bytes(22, field22))
    return base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')

def build_search_url(origin_city_id, dest_airport_id, depart_date, return_date, cabin=3):
    tfs = build_search_tfs(origin_city_id, dest_airport_id, depart_date, return_date, cabin)
    return f'https://www.google.com/travel/flights?tfs={tfs}&tfu=GgA&hl=en&gl=hk&curr=USD'

# --- City data ---
ORIGINS = {
    'Jakarta': {'city_id': '/m/044rv', 'code': 'CGK'},
    'Kuala Lumpur': {'city_id': '/m/049d1', 'code': 'KUL'},
    'Bangkok': {'city_id': '/m/0fn2g', 'code': 'BKK'},
    'Singapore': {'city_id': '/m/06t2t', 'code': 'SIN'},
    'Manila': {'city_id': '/m/0195pd', 'code': 'MNL'},
    'Ho Chi Minh City': {'city_id': '/m/0hn4h', 'code': 'SGN'},
    'Hong Kong': {'city_id': '/m/03h64', 'code': 'HKG'},
    'Seoul': {'city_id': '/m/0hsqf', 'code': 'ICN'},
    'Tokyo': {'city_id': '/m/07dfk', 'code': 'TYO'},
    'Taipei': {'city_id': '/m/0ftkx', 'code': 'TPE'},
    'Shanghai': {'city_id': '/m/06wjf', 'code': 'PVG'},
    'Hangzhou': {'city_id': '/m/014vm4', 'code': 'HGH'},
    'Ningbo': {'city_id': '/m/01l33l', 'code': 'NGB'},
    'Beijing': {'city_id': '/m/01914', 'code': 'PEK'},
    'Guangzhou': {'city_id': '/m/0393g', 'code': 'CAN'},
    'Chengdu': {'city_id': '/m/016v46', 'code': 'CTU'},
    'Chongqing': {'city_id': '/m/017236', 'code': 'CKG'},
    'Shenzhen': {'city_id': '/m/0lbmv', 'code': 'SZX'},
    'Nanjing': {'city_id': '/m/05gqy', 'code': 'NKG'},
    'Qingdao': {'city_id': '/m/01l3s0', 'code': 'TAO'},
    'Dalian': {'city_id': '/m/01l3k6', 'code': 'DLC'},
    'Wuhan': {'city_id': '/m/0l3cy', 'code': 'WUH'},
    'Xiamen': {'city_id': '/m/0126c3', 'code': 'XMN'},
    'Tianjin': {'city_id': '/m/0df4y', 'code': 'TSN'},
    'Fuzhou': {'city_id': '/m/01jzm9', 'code': 'FOC'},
}

# Airport IDs for direct search URLs (Freebase format)
US_DEST = {
    'Los Angeles': '/m/030qb3t',
    'Houston': '/m/04lh6',
    'New York': '/m/02_286',
    'San Francisco': '/m/0d6lp',
    'Chicago': '/m/01_d4',
    'Washington, D.C.': '/m/0rh6k',
    'Denver': '/m/02cl1',
    'Las Vegas': '/m/0cv3w',
    'Seattle': '/m/0d9jr',
    'Boston': '/m/01cx_',
    'Miami': '/m/0f2v0',
    'Atlanta': '/m/013yq',
    'Tampa': '/m/0hyxv',
    'Austin': '/m/0vzm',
    'Dallas': '/m/0f2rq',
    'Portland': '/m/02frhbc',
    'San Diego': '/m/071vr',
    'Philadelphia': '/m/0dclg',
    'Orlando': '/m/0ply0',
    'Fort Lauderdale': '/m/0fvyg',
    'Charlotte': '/m/0fttg',
    'Nashville': '/m/05jbn',
    'Phoenix': '/m/0d35y',
    'Minneapolis': '/m/0fpzwf',
    'Detroit': '/m/02dtg',
    'Baltimore': '/m/094jv',
    'Pittsburgh': '/m/068p2',
    'New Orleans': '/m/0f8l9c',
    'Salt Lake City': '/m/0f2r6',
    'Honolulu': '/m/02hrh0_',
    'San Antonio': '/m/0f2v0',
    'Savannah': '/m/0lhn5',
}

US_CITY_ID = '/m/09c7w0'

CABIN_LABELS = {1: 'Economy', 2: 'Premium Economy', 3: 'Business', 4: 'First'}
CABIN_COLORS = {1: '#276749', 2: '#2b6cb0', 3: '#6b21a8', 4: '#c2410c'}
CABIN_EMOJI = {1: '', 2: '', 3: '', 4: ''}

US_DEST_IATA = {
    'Los Angeles': 'LAX', 'Houston': 'IAH', 'New York': 'JFK',
    'San Francisco': 'SFO', 'Chicago': 'ORD', 'Washington, D.C.': 'IAD',
    'Denver': 'DEN', 'Las Vegas': 'LAS', 'Seattle': 'SEA',
    'Boston': 'BOS', 'Miami': 'MIA', 'Atlanta': 'ATL',
    'Tampa': 'TPA', 'Austin': 'AUS', 'Dallas': 'DFW',
    'Portland': 'PDX', 'San Diego': 'SAN', 'Philadelphia': 'PHL',
    'Orlando': 'MCO', 'Fort Lauderdale': 'FLL', 'Charlotte': 'CLT',
    'Nashville': 'BNA', 'Phoenix': 'PHX', 'Minneapolis': 'MSP',
    'Detroit': 'DTW', 'Baltimore': 'BWI', 'Pittsburgh': 'PIT',
    'New Orleans': 'MSY', 'Salt Lake City': 'SLC', 'Honolulu': 'HNL',
    'San Antonio': 'SAT', 'Kauai': 'LIH',
}

TRIPCABIN = {1: 'Y', 2: 'S', 3: 'C', 4: 'F'}
EXPEDIA_CABIN = {1: 'economy', 2: 'premium', 3: 'business', 4: 'first'}

# --- Load scan results ---
with open('D:/claude/flights/scanner_results.json', encoding='utf-8') as f:
    data = json.load(f)

bugs = [d for d in data['destinations'] if d['classification'] in ('BUG_FARE', 'CHEAP')]
all_fares = data['destinations']

# Group by origin + cabin (for legacy highlight summary)
from collections import defaultdict
grouped = defaultdict(list)
for b in bugs:
    key = (b['origin_city'], b['cabin_num'])
    grouped[key].append(b)

# Sort within groups by price
for key in grouped:
    grouped[key].sort(key=lambda x: x['price_usd'])

# --- Date parsing helper ---
def parse_dates(date_str):
    """Parse 'Jul 16 – 22' or 'May 23 – Jun 1' into (depart, return) date strings."""
    if not date_str:
        return None, None
    date_str = date_str.replace('\u2009', ' ').replace('\u200a', ' ')
    parts = date_str.replace('\u2013', '-').replace('–', '-').split('-')
    if len(parts) != 2:
        return None, None
    start = parts[0].strip()
    end = parts[1].strip()
    # Parse start
    months = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
    try:
        start_parts = start.split()
        start_month = months[start_parts[0]]
        start_day = int(start_parts[1])
        end_parts = end.split()
        if len(end_parts) == 1:
            end_month = start_month
            end_day = int(end_parts[0])
        else:
            end_month = months[end_parts[0]]
            end_day = int(end_parts[1])
        depart = f'2026-{start_month:02d}-{start_day:02d}'
        ret = f'2026-{end_month:02d}-{end_day:02d}'
        return depart, ret
    except:
        return None, None

# --- Generate HTML ---
shanghai_tz = timezone(timedelta(hours=8))
timestamp = datetime.now(shanghai_tz).strftime('%Y-%m-%d %H:%M Shanghai time')

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bug Fare Scanner - Live Verification Links</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif; background: #fff; color: #2d3748; font-size: 16px; line-height: 1.7; }}
.container {{ max-width: 1400px; margin: 0 auto; padding: 24px 28px; }}
h1 {{ color: #1a202c; font-size: 26px; font-weight: 600; margin-bottom: 4px; }}
.subtitle {{ color: #718096; margin-bottom: 20px; font-size: 14px; }}
.alert {{ background: #fff5f5; border: 1px solid #feb2b2; border-radius: 6px; padding: 14px 18px; margin-bottom: 20px; }}
.alert h3 {{ color: #c53030; margin-bottom: 6px; font-size: 15px; font-weight: 600; }}
.alert p {{ color: #742a2a; font-size: 14px; }}
.section {{ border: 1px solid #d0d5dd; border-radius: 6px; margin-bottom: 20px; overflow: hidden; }}
.section-header {{ padding: 14px 20px; border-bottom: 1px solid #e2e6ea; display: flex; align-items: center; gap: 12px; background: #f7fafc; }}
.section-header h2 {{ font-size: 17px; font-weight: 600; color: #1a202c; }}
.section-header .badge {{ padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
.explore-links {{ padding: 14px 20px; border-bottom: 1px solid #e2e6ea; background: #f7fafc; }}
.explore-links a {{ display: inline-block; padding: 5px 12px; margin: 3px; border-radius: 4px; text-decoration: none; font-weight: 500; font-size: 13px; transition: opacity 0.2s; }}
.explore-links a:hover {{ opacity: 0.75; }}
.fare-table {{ width: 100%; border-collapse: collapse; }}
.fare-table th {{ text-align: left; padding: 10px 14px; color: #4a5568; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 2px solid #d0d5dd; font-weight: 600; }}
.fare-table td {{ padding: 10px 14px; border-bottom: 1px solid #e2e6ea; font-size: 14px; color: #2d3748; }}
.fare-table tr:hover {{ background: #f7fafc; }}
.price {{ font-weight: 700; font-size: 15px; }}
.price-bug {{ color: #b91c1c; }}
.price-cheap {{ color: #92400e; }}
a.verify-btn {{ display: inline-block; padding: 3px 10px; border-radius: 4px; text-decoration: none; font-size: 12px; font-weight: 600; }}
a.explore-btn {{ background: #ebf8ff; color: #2b6cb0; border: 1px solid #90cdf4; }}
a.search-btn {{ background: #f0fff4; color: #276749; border: 1px solid #9ae6b4; }}
a.trip-btn {{ background: #e6f3ff; color: #0066cc; border: 1px solid #99ccff; }}
a.expedia-btn {{ background: #fff8e6; color: #cc8800; border: 1px solid #ffcc66; }}
a.verify-btn:hover {{ opacity: 0.75; }}
.instructions {{ border: 1px solid #d0d5dd; border-radius: 6px; padding: 14px 20px; margin-bottom: 20px; }}
.instructions h3 {{ color: #2b6cb0; margin-bottom: 8px; font-size: 15px; font-weight: 600; }}
.instructions ol {{ padding-left: 20px; }}
.instructions li {{ margin-bottom: 5px; color: #4a5568; font-size: 14px; }}
.instructions li strong {{ color: #1a202c; }}
.stats {{ display: flex; gap: 14px; margin-bottom: 20px; flex-wrap: wrap; }}
.stat-card {{ border: 1px solid #d0d5dd; border-radius: 6px; padding: 18px 20px; flex: 1; min-width: 150px; }}
.stat-card .num {{ font-size: 26px; font-weight: 700; }}
.stat-card .label {{ color: #718096; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
.top-deal {{ border: 2px solid #805ad5; background: #faf5ff; }}
.timestamp {{ color: #718096; font-size: 13px; text-align: right; margin-top: 20px; padding-top: 16px; border-top: 1px solid #e2e6ea; }}
@media (max-width: 640px) {{
  .container {{ padding: 12px 10px; }}
  .stats {{ gap: 8px; }}
  .stat-card {{ min-width: 120px; padding: 12px; }}
  .stat-card .num {{ font-size: 22px; }}
  .fare-table th, .fare-table td {{ padding: 8px 8px; font-size: 13px; }}
  .section-header {{ flex-wrap: wrap; }}
}}
#login-gate {{ display: flex; justify-content: center; align-items: center; height: 100vh; }}
#login-gate form {{ border: 1px solid #d0d5dd; border-radius: 6px; padding: 30px 40px; text-align: center; }}
#login-gate h2 {{ margin-bottom: 12px; font-size: 20px; color: #1a202c; }}
#login-gate input {{ padding: 8px 14px; border: 1px solid #d0d5dd; border-radius: 4px; font-size: 14px; width: 200px; }}
#login-gate button {{ padding: 8px 20px; background: #2b6cb0; color: #fff; border: none; border-radius: 4px; font-size: 14px; cursor: pointer; margin-left: 8px; }}
#login-gate button:hover {{ background: #2c5282; }}
#login-gate .error {{ color: #b91c1c; font-size: 13px; margin-top: 8px; display: none; }}
#main-content {{ display: none; }}
</style>
</head>
<body>

<div id="login-gate">
<form onsubmit="return checkPass()">
<h2>Bug Fare Scanner</h2>
<p style="color:#718096;font-size:13px;margin-bottom:14px">Enter access key to continue</p>
<input type="password" id="access-key" placeholder="Access key" autofocus>
<button type="submit">Enter</button>
<p class="error" id="login-error">Invalid key</p>
</form>
</div>

<div id="main-content">
<div class="container">

<h1>Bug Fare Scanner</h1>
<p class="subtitle">Scan: {data['scan_timestamp'][:19]} | Updated: {timestamp} | All prices USD, round-trip, per person</p>

<div class="alert">
<h3>How to verify fares are LIVE</h3>
<p>Explore overview prices may be cached. Click a city tab on the map to trigger a <strong>fresh real-time search</strong>, wait 3-5s, then click "View flights" to confirm.</p>
</div>

<div class="instructions">
<h3>Verification Steps</h3>
<ol>
<li><strong>Click an Explore link</strong> below to open Google Flights Explore map</li>
<li><strong>Click a city name tab</strong> on the map &mdash; triggers a fresh search</li>
<li><strong>Wait 3-5 seconds</strong> for the price panel to reload</li>
<li><strong>Click "View flights"</strong> to see the actual booking page</li>
<li>If the price persists on booking page, <strong>fare is confirmed live</strong></li>
<li>For 2A+1C pricing, multiply 1-adult price by <strong>2.75</strong></li>
</ol>
</div>
"""

# Stats
bug_count = len([b for b in bugs if b['classification'] == 'BUG_FARE'])
cheap_count = len([b for b in bugs if b['classification'] == 'CHEAP'])
all_count = len(data['destinations'])

# --- VERIFIED BOOKABLE DEALS (from deep verification JSON files) ---
# Load real booking URLs from deep verify results
verified_deals = []
EXCLUDE_DESTINATIONS = ['Honolulu', 'Kauai', '1.5h drive from Washington', '1h drive from Miami', '1h drive from Washington']
EXCLUDE_ORIGINS = {'Taipei'}  # Taiwan excluded — transit visa complications
EXCLUDE_AIRLINES = ['ZIPAIR', 'Philippine Airlines', 'Malaysia Airlines', 'Cebu Pacific']

# HK results
try:
    with open('D:/claude/flights/deep_verify_hk_results.json', encoding='utf-8') as f:
        hk_data = json.load(f)
    for r in hk_data.get('results', []):
        if r.get('booking_url') and r.get('status') in ('BOOKABLE', 'SEARCH_CONFIRMED'):
            dest = r.get('city', '')
            airline = r.get('airline') or 'Unknown'
            if dest in EXCLUDE_DESTINATIONS:
                continue
            if any(excl.lower() in airline.lower() for excl in EXCLUDE_AIRLINES):
                continue
            verified_deals.append({
                'origin': 'Hong Kong',
                'dest': dest,
                'cabin': r.get('cabin', 'Economy'),
                'price': r.get('price', 0),
                'airline': airline,
                'booking_url': r['booking_url'],
                'has_booking': True,
            })
except Exception as e:
    print(f"Note: no HK verify results yet: {e}")

# Deep verify ALL results (50 fares under $2000 family)
deep_verify_lookup = {}  # (origin, dest, dates) -> result, for fare table linking
try:
    with open('D:/claude/flights/deep_verify_all_results.json', encoding='utf-8') as f:
        deep_all_data = json.load(f)
    for r in deep_all_data.get('results', []):
        if not r.get('booking_url') or not r.get('has_booking_page'):
            continue
        origin = r.get('origin', '')
        dest = r.get('city', '')
        airline = r.get('airline') or ''
        dates = r.get('dates', '')
        price = r.get('price', 0)
        if dest in EXCLUDE_DESTINATIONS:
            continue
        if any(excl.lower() in airline.lower() for excl in EXCLUDE_AIRLINES):
            continue
        # Skip fares where booking price is >40% higher than explore price (wrong city ID)
        explore_price = r.get('explore_price', 0)
        if price and explore_price and price > explore_price * 1.4:
            continue
        # Skip fares with no price (couldn't extract from booking page)
        if not price:
            continue
        # Add to lookup for fare table
        deep_verify_lookup[(origin, dest, dates)] = r
        # Add to verified deals if not already present (avoid duplicates with Tokyo/Seoul/HK)
        already = any(d['origin'] == origin and d['dest'] == dest for d in verified_deals)
        if not already:
            verified_deals.append({
                'origin': origin,
                'dest': dest,
                'cabin': r.get('cabin', 'Economy'),
                'price': price,
                'airline': airline or 'Unknown',
                'booking_url': r['booking_url'],
                'has_booking': True,
            })
except Exception as e:
    print(f"Warning: could not load deep_verify_all results: {e}")

# Load trend lookup (from archive_run.py — price deltas vs previous run)
trend_lookup = {}  # fare_key_str → delta_pct or None (new) or 999 (gone)
trend_prev_date = ''
try:
    with open('D:/claude/flights/trend_lookup.json', encoding='utf-8') as f:
        tl = json.load(f)
    trend_lookup = tl.get('lookup', {})
    trend_prev_date = tl.get('prev_date', '')
    if trend_lookup:
        print(f"Loaded trend data vs {trend_prev_date} ({len(trend_lookup)} routes tracked)")
except Exception:
    pass

# Load drill results (Phase 2 — duration / open-jaw / stopover data)
# keyed by (origin, dest) -> drill result dict
drill_lookup = {}
try:
    with open('D:/claude/flights/drill_results.json', encoding='utf-8') as f:
        drill_data = json.load(f)
    for r in drill_data.get('results', []):
        key = (r['origin'], r['dest'])
        drill_lookup[key] = r
    print(f"Loaded {len(drill_lookup)} drill results")
except Exception as e:
    pass  # drill_results.json is optional — only exists after drill_promising.py runs

# Sort by price
verified_deals.sort(key=lambda x: x['price'])

# --- Trend summary banner (shown when trend data exists) ---
if trend_lookup:
    # Count categories
    n_new    = sum(1 for v in trend_lookup.values() if v is None)
    n_cheap  = sum(1 for v in trend_lookup.values() if isinstance(v,(int,float)) and v < -3)
    n_pricey = sum(1 for v in trend_lookup.values() if isinstance(v,(int,float)) and v > 3 and v != 999)
    n_gone   = sum(1 for v in trend_lookup.values() if v == 999)
    parts = []
    if n_new:    parts.append(f'<span style="color:#90cdf4">✦ {n_new} new routes</span>')
    if n_cheap:  parts.append(f'<span style="color:#68d391">↓ {n_cheap} got cheaper</span>')
    if n_pricey: parts.append(f'<span style="color:#fc8181">↑ {n_pricey} got pricier</span>')
    if n_gone:   parts.append(f'<span style="color:#a0aec0">✕ {n_gone} disappeared</span>')
    banner_content = ' &nbsp;|&nbsp; '.join(parts) if parts else 'No changes'
    html += f"""
<div style="background:#1a202c;border:1px solid #2d3748;border-radius:6px;
            padding:10px 18px;margin:0 0 16px;font-size:13px">
  <strong style="color:#a0aec0">Trend vs {trend_prev_date}:</strong> &nbsp;
  {banner_content}
  &nbsp;— <em style="color:#718096">arrows shown inline in fare table</em>
</div>
"""

html += """
<div class="section" style="border:2px solid #276749;background:#f0fff4">
<div class="section-header" style="background:#c6f6d5;border-bottom:2px solid #9ae6b4">
<h2 style="color:#276749">CONFIRMED BOOKABLE \u2014 Deep Verified</h2>
<span style="color:#276749;font-size:13px">Clicked through Google Flights booking page \u2014 real "Book with" links extracted</span>
</div>
<table class="fare-table">
<tr><th>Route</th><th>Cabin</th><th>Price</th><th>Family (2A+1C)</th><th>Book With</th><th>Verified Booking Link</th></tr>
"""

for deal in verified_deals:
    fam = deal['price'] * 2.75
    bg = ' style="background:#f0fff4"' if fam <= 3000 else ''
    html += f"""<tr{bg}>
<td><strong>{deal['origin']} &rarr; {deal['dest']}</strong></td><td>{deal['cabin']}</td>
<td class="price" style="color:#276749">${deal['price']:,}</td><td>${fam:,.0f}</td>
<td>{deal['airline']}</td>
<td><a href="{deal['booking_url']}" target="_blank" rel="noopener" class="verify-btn" style="background:#276749;color:#fff;border:none">Google Booking Page</a></td>
</tr>
"""

html += """</table>
<div style="padding:14px 20px;color:#276749;font-size:14px;border-top:1px solid #9ae6b4;background:#f0fff4">
<strong>All "Google Booking Page" links go to the real Google Flights booking page with live prices.</strong> These URLs were extracted by clicking through the full Explore &rarr; View Flights &rarr; Select Flights &rarr; Booking flow. Links may expire after ~24 hours.
</div>
</div>
"""

# --- GHOST FARES WARNING ---
html += """
<div class="section" style="border:2px solid #c53030;background:#fff5f5">
<div class="section-header" style="background:#fed7d7;border-bottom:2px solid #feb2b2">
<h2 style="color:#c53030">GHOST FARES &mdash; Jakarta (NOT Bookable)</h2>
<span style="color:#c53030;font-size:13px">Shows in search results but "We can't find booking options" on booking page</span>
</div>
<div style="padding:14px 20px;color:#742a2a;font-size:14px">
<strong>Jakarta Business $839-$946 to 20 US cities</strong> &mdash; prices display on Explore map and flight search, but final booking page returns "We can't find booking options for this itinerary." Verified via Playwright click-through on 5 routes (Houston, LA, Boston, Washington, New York). All ghost fares.<br><br>
<strong>Jakarta Premium Economy $651-$712 to 17 US cities</strong> &mdash; same pattern. Airlines: THAI/Austrian/Singapore Airlines routing via BKK/VIE. The fare was likely real briefly but booking partners pulled it.
</div>
</div>
"""

# --- Stats ---
html += f"""
<div class="stats">
<div class="stat-card"><div class="num" style="color:#276749">{len(verified_deals)}</div><div class="label">Verified Bookable</div></div>
<div class="stat-card"><div class="num" style="color:#c53030">37</div><div class="label">Ghost Fares (Jakarta)</div></div>
<div class="stat-card"><div class="num" style="color:#92400e">{cheap_count}</div><div class="label">Cheap Fares</div></div>
<div class="stat-card"><div class="num" style="color:#718096">{all_count}</div><div class="label">Total Destinations</div></div>
</div>
"""

# --- Explore overview links section ---
html += """
<div class="section">
<div class="section-header"><h2>Quick Explore Links (Overview Maps)</h2></div>
<div class="explore-links">
"""

# Generate explore URLs for key origin+cabin combos
explore_combos = [
    ('Jakarta', '/m/044rv', 2, '#2196F3'),
    ('Jakarta', '/m/044rv', 3, '#9C27B0'),
    ('Jakarta', '/m/044rv', 4, '#FF9800'),
    ('Kuala Lumpur', '/m/049d1', 2, '#2196F3'),
    ('Kuala Lumpur', '/m/049d1', 3, '#9C27B0'),
    ('Kuala Lumpur', '/m/049d1', 4, '#FF9800'),
    ('Bangkok', '/m/0fn2g', 3, '#9C27B0'),
    ('Bangkok', '/m/0fn2g', 4, '#FF9800'),
    ('Singapore', '/m/06t2t', 3, '#9C27B0'),
    ('Singapore', '/m/06t2t', 4, '#FF9800'),
    ('Manila', '/m/0195pd', 3, '#9C27B0'),
    ('Manila', '/m/0195pd', 4, '#FF9800'),
    ('Ho Chi Minh City', '/m/0hn4h', 3, '#9C27B0'),
    ('Hong Kong', '/m/03h64', 3, '#9C27B0'),
    ('Seoul', '/m/0hsqf', 2, '#2196F3'),
    ('Seoul', '/m/0hsqf', 3, '#9C27B0'),
    ('Tokyo', '/m/07dfk', 3, '#9C27B0'),
    ('Tokyo', '/m/07dfk', 4, '#FF9800'),
    ('Taipei', '/m/0ftkx', 3, '#9C27B0'),
]

for city, cid, cabin, color in explore_combos:
    url = build_explore_url(cid, US_CITY_ID, cabin=cabin)
    label = f'{city} {CABIN_LABELS[cabin]}'
    html += f'<a href="{url}" target="_blank" style="background:{color}11;color:{color};border:1px solid {color}44">{label}</a>\n'

html += """
</div>
</div>
"""

FAMILY_BUDGET = 3000  # USD total for 2A+1C
PP_BUDGET = FAMILY_BUDGET / 2.75  # ~$1091 per person

def clean_dates(s):
    """Replace thin spaces (U+2009) and en-dashes (U+2013) with plain ASCII."""
    return s.replace('\u2009', ' ').replace('\u2013', '-').replace('\u200a', ' ')

def build_trip_url(origin_iata, dest_iata, depart_date, return_date, cabin_num):
    """Build Trip.com search URL."""
    cabin_code = TRIPCABIN.get(cabin_num, 'Y')
    o = origin_iata.lower()
    d = dest_iata.lower()
    dep = depart_date.replace('-', '')
    ret = return_date.replace('-', '')
    return f'https://www.trip.com/flights/list/roundtrip-{o}-{d}-{dep}-{ret}/?cabin={cabin_code}&adult=1'

def build_expedia_url(origin_iata, dest_iata, depart_date, return_date, cabin_num):
    """Build Expedia search URL."""
    cabin_name = EXPEDIA_CABIN.get(cabin_num, 'economy')
    return f'https://www.expedia.com/Flights-search/{origin_iata}-{dest_iata}/{depart_date}/{return_date}/?cabinclass={cabin_name}'

def fare_trend_badge(origin_city, dest, cabin_label):
    """Return HTML trend badge for a fare row, using the global trend_lookup."""
    key = f"{origin_city}|{dest}|{cabin_label}"
    if key not in trend_lookup:
        return ''
    delta = trend_lookup[key]
    if delta is None:
        return '<span style="background:#1a365d;color:#90cdf4;border-radius:3px;padding:1px 5px;font-size:10px;font-weight:700">NEW</span>'
    if delta == 999:
        return ''
    if delta < -10:
        return f'<span style="color:#68d391;font-weight:700;font-size:12px">↓↓{delta:+.0f}%</span>'
    elif delta < -3:
        return f'<span style="color:#9ae6b4;font-size:12px">↓{delta:+.0f}%</span>'
    elif delta > 10:
        return f'<span style="color:#fc8181;font-weight:700;font-size:12px">↑↑{delta:+.0f}%</span>'
    elif delta > 3:
        return f'<span style="color:#feb2b2;font-size:12px">↑{delta:+.0f}%</span>'
    return ''


def render_fare_row(fare, origin_cid, cabin_num, deep_lookup=None, drill_lookup=None):
    """Render a single fare table row."""
    dest = fare['destination']
    price = fare['price_usd']
    family_price = price * 2.75
    dates = clean_dates(fare.get('dates', ''))
    stops = fare.get('stops', '')
    cls = fare['classification']
    origin_code = fare.get('origin_code', '')
    origin_city = fare.get('origin_city', '')
    cabin_label = CABIN_LABELS.get(cabin_num, '?')

    # Jakarta bug fares are ghost fares (verified: no booking options)
    is_ghost = (origin_city == 'Jakarta' and cls == 'BUG_FARE')

    if is_ghost:
        price_class = ''
        type_style = 'color:#a0aec0;font-weight:600;text-decoration:line-through'
        type_label = 'GHOST'
    elif cls == 'BUG_FARE':
        price_class = 'price-bug'
        type_style = 'color:#b91c1c;font-weight:700'
        type_label = 'BUG'
    elif cls == 'CHEAP':
        price_class = 'price-cheap'
        type_style = 'color:#92400e;font-weight:700'
        type_label = 'CHEAP'
    else:
        price_class = ''
        type_style = 'color:#a0aec0;font-weight:400'
        type_label = 'NORMAL'

    # Build verify links
    verify_links = ''
    depart, ret = parse_dates(dates)

    # Use scanner detail_urls when available (all city IDs now corrected)
    v = fare.get('verification', {})
    detail_url = v.get('detail_url', '')
    if detail_url and detail_url != 'none':
        verify_links += f'<a href="{detail_url}" target="_blank" rel="noopener" class="verify-btn search-btn">View Flights</a> '

    # Explore URL -- always generate one (use departure date if available, else default)
    explore_url_dated = build_explore_url(origin_cid, US_CITY_ID, date=depart, cabin=cabin_num)
    verify_links += f'<a href="{explore_url_dated}" target="_blank" rel="noopener" class="verify-btn explore-btn">Explore</a> '

    # Deep verified booking link (under $2000 family)
    if deep_lookup:
        dv = deep_lookup.get((origin_city, dest, dates))
        if dv and dv.get('booking_url'):
            dv_airline = (dv.get('airline') or '')[:20]
            dv_price = dv.get('price', '')
            label = f'Booking Page'
            if dv_price:
                label = f'Book ${dv_price}'
            if dv_airline:
                label += f' ({dv_airline})'
            verify_links += f'<a href="{dv["booking_url"]}" target="_blank" rel="noopener" class="verify-btn" style="background:#276749;color:#fff;border:none;font-size:11px">{label}</a> '

    # Drill data badges (duration range, open-jaw, stopover)
    if drill_lookup:
        dr = drill_lookup.get((origin_city, dest))
        if dr:
            dmin = dr.get('valid_duration_min')
            dmax = dr.get('valid_duration_max')
            if dmin and dmax:
                verify_links += (f'<span style="background:#2d3748;color:#e2e8f0;'
                                 f'border-radius:4px;padding:2px 6px;font-size:10px;'
                                 f'margin-right:3px">Stay {dmin}-{dmax}d</span> ')
            oj_price = dr.get('open_jaw_price')
            oj_url   = dr.get('open_jaw_url', '')
            if oj_price and oj_url:
                verify_links += (f'<a href="{oj_url}" target="_blank" rel="noopener" '
                                 f'class="verify-btn" style="background:#744210;color:#fef3c7;'
                                 f'border:none;font-size:10px">↩Shanghai ${oj_price}</a> ')
            stopover = dr.get('stopover', {})
            if stopover:
                best_key = min(stopover, key=lambda k: stopover[k]['total_outbound_pp'])
                sv = stopover[best_key]
                hub = sv.get('hub', '')
                total = sv.get('total_outbound_pp', 0)
                verify_links += (f'<span style="background:#1e3a5f;color:#bfdbfe;'
                                 f'border-radius:4px;padding:2px 6px;font-size:10px;'
                                 f'margin-right:3px">Stopover {hub} {best_key} ${total}/pp OW</span> ')

    # Trend badge (vs previous run)
    tbadge = fare_trend_badge(origin_city, dest, cabin_label)

    # Row text style for NORMAL fares
    row_style = ' style="color:#a0aec0"' if cls == 'NORMAL' else ''

    return f"""<tr{row_style}>
<td><strong>{origin_city}</strong></td>
<td>{dest}</td>
<td>{cabin_label}</td>
<td class="price {price_class}">${price:.0f}&nbsp;{tbadge}</td>
<td style="color:#718096">${family_price:.0f}</td>
<td>{dates}</td>
<td>{stops}</td>
<td><span style="{type_style}">{type_label}</span></td>
<td>{verify_links}</td>
</tr>
"""

def render_fare_table_header():
    return """<table class="fare-table">
<tr>
<th>Origin</th>
<th>Destination</th>
<th>Cabin</th>
<th>Price (USD)</th>
<th>Family (2A+1C)</th>
<th>Dates</th>
<th>Stops</th>
<th>Classification</th>
<th>Verify</th>
</tr>
"""

# --- Global fare tables sorted by price ---
# Split all fares into affordable (family <= $3000) and expensive (family > $3000)
all_fares_sorted = sorted(all_fares, key=lambda x: x['price_usd'])
affordable_fares = [f for f in all_fares_sorted
                    if f['price_usd'] * 2.75 <= FAMILY_BUDGET
                    and f.get('origin_city') not in EXCLUDE_ORIGINS
                    and f.get('destination') not in EXCLUDE_DESTINATIONS]
expensive_fares  = [f for f in all_fares_sorted
                    if f['price_usd'] * 2.75 > FAMILY_BUDGET
                    and f.get('origin_city') not in EXCLUDE_ORIGINS
                    and f.get('destination') not in EXCLUDE_DESTINATIONS]

# --- Affordable fares table ---
html += f"""
<div class="section">
<div class="section-header">
<h2>All Fares Under $3,000 Family Total ({len(affordable_fares)} fares)</h2>
<span class="badge" style="background:#f0fff4;color:#276749;border:1px solid #9ae6b4">Sorted by price</span>
</div>
"""
html += render_fare_table_header()
for fare in affordable_fares:
    origin_info = ORIGINS.get(fare['origin_city'], {})
    origin_cid = origin_info.get('city_id', '')
    html += render_fare_row(fare, origin_cid, fare['cabin_num'],
                            deep_lookup=deep_verify_lookup, drill_lookup=drill_lookup)
html += """</table>
</div>
"""

# --- Over-budget fares section (show only cheapest per origin+cabin, capped) ---
if expensive_fares:
    # Deduplicate: keep only cheapest per origin+cabin+destination
    seen_exp = set()
    deduped_expensive = []
    for fare in expensive_fares:
        key = (fare['origin_city'], fare['cabin_num'], fare['destination'])
        if key not in seen_exp:
            seen_exp.add(key)
            deduped_expensive.append(fare)
    # Cap at 80 to keep file size reasonable
    capped = deduped_expensive[:80]
    html += f"""
<div class="section" style="opacity:0.7">
<div class="section-header" style="background:#fff5f5">
<h2 style="color:#718096">Over $3,000 Family Total (showing {len(capped)} of {len(deduped_expensive)} fares)</h2>
<span class="badge" style="background:#fed7d7;color:#9b2c2c;border:1px solid #feb2b2">Unlikely to book</span>
</div>
"""
    html += render_fare_table_header()
    for fare in capped:
        origin_info = ORIGINS.get(fare['origin_city'], {})
        origin_cid = origin_info.get('city_id', '')
        html += render_fare_row(fare, origin_cid, fare['cabin_num'])
    html += """</table>
</div>
"""

# --- All cities cheapest fares overview ---
scanned_cities = sorted(set(d['origin_city'] for d in data['destinations']))
all_dests = data['destinations']

# Build cheapest-per-city-per-cabin table
city_cabin_cheapest = {}
for d in all_dests:
    key = (d['origin_city'], d['cabin_num'])
    price = d['price_usd']
    if key not in city_cabin_cheapest or price < city_cabin_cheapest[key]['price_usd']:
        city_cabin_cheapest[key] = d

html += f"""
<div class="section">
<div class="section-header">
<h2>All {len(scanned_cities)} Cities Scanned &mdash; Cheapest Fares Found</h2>
</div>
<table class="fare-table">
<tr>
<th>Origin</th>
<th>Economy</th>
<th>Premium Eco</th>
<th>Business</th>
<th>First</th>
<th>Status</th>
</tr>
"""

for city in scanned_cities:
    origin_info = ORIGINS.get(city, {})
    code = origin_info.get('code', '???')
    cid = origin_info.get('city_id', '')

    cells = []
    has_bug = False
    for cab in [1, 2, 3, 4]:
        key = (city, cab)
        if key in city_cabin_cheapest:
            d = city_cabin_cheapest[key]
            p = d['price_usd']
            fam = p * 2.75
            cls = d.get('classification', 'NORMAL')
            dest = d['destination']
            dates = clean_dates(d.get('dates', ''))
            if cls == 'BUG_FARE':
                color = '#b91c1c'
                weight = '700'
                has_bug = True
            elif cls == 'CHEAP':
                color = '#92400e'
                weight = '600'
            else:
                color = '#718096'
                weight = '400'
            # Build explore link for this city+cabin
            explore_url = build_explore_url(cid, US_CITY_ID, cabin=cab) if cid else ''
            link_open = f'<a href="{explore_url}" target="_blank" rel="noopener" style="text-decoration:none;color:inherit">' if explore_url else ''
            link_close = '</a>' if explore_url else ''
            cells.append(f'<td>{link_open}<span style="color:{color};font-weight:{weight}">${p:,.0f}</span><br><span style="color:#a0aec0;font-size:11px">{dest}</span>{link_close}</td>')
        else:
            cells.append('<td style="color:#cbd5e0">--</td>')

    if has_bug:
        status = '<span style="color:#b91c1c;font-weight:700">BUG FARES</span>'
    elif any(city_cabin_cheapest.get((city, c), {}).get('classification') == 'CHEAP' for c in [1,2,3,4]):
        status = '<span style="color:#92400e;font-weight:600">Cheap</span>'
    else:
        status = '<span style="color:#a0aec0">Normal</span>'

    html += f'<tr><td><strong>{city} ({code})</strong></td>{"".join(cells)}<td>{status}</td></tr>\n'

html += """</table>
</div>
"""

# --- Europe explore links ---
html += """
<div class="section">
<div class="section-header"><h2>Europe Explore Links (Trip 3 Planning)</h2></div>
<div class="explore-links">
"""
GERMANY_ID = '/m/0d060g'
UK_ID = '/m/07ssc'
for city, cid in [('Jakarta', '/m/044rv'), ('Kuala Lumpur', '/m/049d1')]:
    for dest_name, dest_id in [('Germany', GERMANY_ID), ('UK', UK_ID)]:
        for cabin in [3, 4]:
            url = build_explore_url(cid, dest_id, cabin=cabin)
            color = CABIN_COLORS[cabin]
            label = f'{city} > {dest_name} {CABIN_LABELS[cabin]}'
            html += f'<a href="{url}" target="_blank" style="background:{color}11;color:{color};border:1px solid {color}44">{label}</a>\n'

html += """
</div>
</div>
"""

# Footer with archive navigation
archive_dir = 'D:/claude/flights/archive'
archive_links = ''
try:
    import os as _os
    runs = sorted([d for d in _os.listdir(archive_dir)
                   if _os.path.isdir(_os.path.join(archive_dir, d))], reverse=True)
    if runs:
        link_items = []
        for slug in runs:
            # Format slug "20260319_0104" -> "2026-03-19 01:04"
            try:
                label = f"{slug[:4]}-{slug[4:6]}-{slug[6:8]} {slug[9:11]}:{slug[11:13]}"
            except:
                label = slug
            link_items.append(f'<a href="archive/{slug}/bug_fare_verify.html">{label}</a>')
        archive_links = ' &nbsp;|&nbsp; '.join(link_items)
except Exception:
    pass

html += f"""
<p class="timestamp">
Scanner: bug_fare_scanner.py | Data: scanner_results.json | Generated: {timestamp}<br>
Normal price ranges (RT): Economy $800-2000 | Premium Eco $1200-3000 | Business $3000-8000 | First $8000-20000<br>
Bug fare threshold: below 60% of normal minimum
</p>

{f'<div style="margin-top:16px;padding:12px 0;border-top:1px solid #2d3748;font-size:12px;color:#718096"><strong style="color:#a0aec0">Previous runs:</strong> &nbsp; {archive_links} &nbsp;|&nbsp; <a href="index.html" style="color:#68d391">Archive Index</a></div>' if archive_links else ''}

</div>
</div>

<script>
var KEY_HASH = 'bugfare2026';
function checkPass() {{
  var k = document.getElementById('access-key').value;
  if (k === KEY_HASH) {{
    document.getElementById('login-gate').style.display = 'none';
    document.getElementById('main-content').style.display = 'block';
    sessionStorage.setItem('bf_auth', '1');
    return false;
  }}
  document.getElementById('login-error').style.display = 'block';
  return false;
}}
if (sessionStorage.getItem('bf_auth') === '1') {{
  document.getElementById('login-gate').style.display = 'none';
  document.getElementById('main-content').style.display = 'block';
}}
</script>
</body>
</html>
"""

with open('D:/claude/flights/bug_fare_verify.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Generated bug_fare_verify.html ({len(html)} bytes)")
print(f"Total fares: {len(all_fares)} ({len(affordable_fares)} under $3k family, {len(expensive_fares)} over)")
print(f"Bug fares: {bug_count}, Cheap fares: {cheap_count}")
