"""Generate an HTML page with clickable Google Flights verification links for all bug fares found."""
import json
import base64
from datetime import datetime, timedelta

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
    'Kuala Lumpur': {'city_id': '/m/04f_d', 'code': 'KUL'},
    'Bangkok': {'city_id': '/m/0fngf', 'code': 'BKK'},
    'Singapore': {'city_id': '/m/06t2t', 'code': 'SIN'},
    'Manila': {'city_id': '/m/0195fg', 'code': 'MNL'},
    'Ho Chi Minh City': {'city_id': '/m/0hnp7', 'code': 'SGN'},
    'Hong Kong': {'city_id': '/m/03h64', 'code': 'HKG'},
    'Seoul': {'city_id': '/m/0hsqf', 'code': 'ICN'},
    'Tokyo': {'city_id': '/m/07dfk', 'code': 'TYO'},
    'Taipei': {'city_id': '/m/0ftkx', 'code': 'TPE'},
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
    'Portland': '/m/0fwwg',
    'San Diego': '/m/0d6lp',
    'Philadelphia': '/m/0k_q',
    'Orlando': '/m/0fhp9',
    'Fort Lauderdale': '/m/0fvyg',
    'Charlotte': '/m/0fttg',
    'Nashville': '/m/05jbn',
    'Phoenix': '/m/0dc_v',
    'Minneapolis': '/m/0fpzwf',
    'Detroit': '/m/02dtg',
    'Baltimore': '/m/0k_p0',
    'Pittsburgh': '/m/068p2',
    'New Orleans': '/m/0f8l9c',
    'Salt Lake City': '/m/0f2nf',
    'Honolulu': '/m/02hrh0_',
    'San Antonio': '/m/0f2v0',
}

US_CITY_ID = '/m/09c7w0'

CABIN_LABELS = {1: 'Economy', 2: 'Premium Economy', 3: 'Business', 4: 'First'}
CABIN_COLORS = {1: '#4CAF50', 2: '#2196F3', 3: '#9C27B0', 4: '#FF9800'}
CABIN_EMOJI = {1: '', 2: '', 3: '', 4: ''}

# --- Load scan results ---
with open('D:/claude/flights/scanner_results.json') as f:
    data = json.load(f)

bugs = [d for d in data['destinations'] if d['classification'] in ('BUG_FARE', 'CHEAP')]

# Group by origin + cabin
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
timestamp = datetime.now().strftime('%Y-%m-%d %H:%M UTC+8')

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bug Fare Scanner - Live Verification Links</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #c9d1d9; padding: 20px; }}
h1 {{ color: #58a6ff; margin-bottom: 5px; font-size: 1.8em; }}
.subtitle {{ color: #8b949e; margin-bottom: 20px; font-size: 0.9em; }}
.alert {{ background: #1a0a0a; border: 1px solid #f85149; border-radius: 8px; padding: 15px; margin-bottom: 20px; }}
.alert h3 {{ color: #f85149; margin-bottom: 8px; }}
.alert p {{ color: #f0aaaa; font-size: 0.9em; }}
.section {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; margin-bottom: 20px; overflow: hidden; }}
.section-header {{ padding: 15px 20px; border-bottom: 1px solid #30363d; display: flex; align-items: center; gap: 12px; cursor: pointer; }}
.section-header h2 {{ font-size: 1.2em; }}
.section-header .badge {{ padding: 2px 10px; border-radius: 12px; font-size: 0.8em; font-weight: 600; }}
.explore-links {{ padding: 15px 20px; border-bottom: 1px solid #21262d; background: #0d1117; }}
.explore-links a {{ display: inline-block; padding: 6px 14px; margin: 4px; border-radius: 6px; text-decoration: none; font-weight: 500; font-size: 0.85em; transition: opacity 0.2s; }}
.explore-links a:hover {{ opacity: 0.8; }}
.fare-table {{ width: 100%; border-collapse: collapse; }}
.fare-table th {{ text-align: left; padding: 10px 15px; background: #0d1117; color: #8b949e; font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #30363d; }}
.fare-table td {{ padding: 10px 15px; border-bottom: 1px solid #21262d; font-size: 0.9em; }}
.fare-table tr:hover {{ background: #1c2128; }}
.price {{ font-weight: 700; font-size: 1.1em; }}
.price-bug {{ color: #f85149; }}
.price-cheap {{ color: #d29922; }}
.cabin-eco {{ color: #4CAF50; }}
.cabin-premeco {{ color: #2196F3; }}
.cabin-biz {{ color: #9C27B0; }}
.cabin-first {{ color: #FF9800; }}
a.verify-btn {{ display: inline-block; padding: 4px 12px; border-radius: 4px; text-decoration: none; font-size: 0.8em; font-weight: 600; }}
a.explore-btn {{ background: #1f6feb33; color: #58a6ff; border: 1px solid #1f6feb; }}
a.search-btn {{ background: #23862633; color: #3fb950; border: 1px solid #238636; }}
a.verify-btn:hover {{ opacity: 0.85; }}
.instructions {{ background: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 15px 20px; margin-bottom: 20px; }}
.instructions h3 {{ color: #58a6ff; margin-bottom: 10px; }}
.instructions ol {{ padding-left: 20px; }}
.instructions li {{ margin-bottom: 6px; color: #8b949e; font-size: 0.9em; }}
.instructions li strong {{ color: #c9d1d9; }}
.stats {{ display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap; }}
.stat-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px 20px; flex: 1; min-width: 150px; }}
.stat-card .num {{ font-size: 2em; font-weight: 700; }}
.stat-card .label {{ color: #8b949e; font-size: 0.85em; }}
.top-deal {{ background: #1a0a2e; border: 2px solid #9C27B0; }}
.timestamp {{ color: #484f58; font-size: 0.8em; text-align: right; margin-top: 20px; }}
</style>
</head>
<body>

<h1>Bug Fare Scanner - Verification Dashboard</h1>
<p class="subtitle">Scan timestamp: {data['scan_timestamp'][:19]} | Generated: {timestamp} | All prices USD, round-trip, per person</p>

<div class="alert">
<h3>IMPORTANT: How to verify these fares are LIVE</h3>
<p>The Explore overview prices may be cached. To get <strong>real-time prices</strong>:</p>
</div>

<div class="instructions">
<h3>Verification Steps</h3>
<ol>
<li><strong>Click an "Explore" link below</strong> to open Google Flights Explore map</li>
<li><strong>Click a city name tab</strong> on the map -- this triggers a FRESH real-time search</li>
<li><strong>Wait 3-5 seconds</strong> for the price panel to reload with live data</li>
<li><strong>Click "View flights"</strong> to go to the actual booking page with specific itineraries</li>
<li>If the price persists on the booking page, <strong>the fare is confirmed live</strong></li>
<li>For 2A+1C pricing, multiply the 1-adult price by 2.75</li>
</ol>
</div>
"""

# Stats
bug_count = len([b for b in bugs if b['classification'] == 'BUG_FARE'])
cheap_count = len([b for b in bugs if b['classification'] == 'CHEAP'])
origins_with_bugs = len(set(b['origin_city'] for b in bugs if b['classification'] == 'BUG_FARE'))
lowest_biz = min((b['price_usd'] for b in bugs if b['cabin_num'] == 3), default=0)
lowest_first = min((b['price_usd'] for b in bugs if b['cabin_num'] == 4), default=0)

html += f"""
<div class="stats">
<div class="stat-card"><div class="num" style="color:#f85149">{bug_count}</div><div class="label">Bug Fares Found</div></div>
<div class="stat-card"><div class="num" style="color:#d29922">{cheap_count}</div><div class="label">Cheap Fares</div></div>
<div class="stat-card"><div class="num" style="color:#9C27B0">${lowest_biz:.0f}</div><div class="label">Lowest Business RT</div></div>
<div class="stat-card"><div class="num" style="color:#FF9800">${lowest_first:.0f}</div><div class="label">Lowest First RT</div></div>
<div class="stat-card"><div class="num" style="color:#58a6ff">{origins_with_bugs}</div><div class="label">Origin Cities w/ Bugs</div></div>
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
    ('Kuala Lumpur', '/m/04f_d', 2, '#2196F3'),
    ('Kuala Lumpur', '/m/04f_d', 3, '#9C27B0'),
    ('Kuala Lumpur', '/m/04f_d', 4, '#FF9800'),
    ('Bangkok', '/m/0fngf', 3, '#9C27B0'),
    ('Bangkok', '/m/0fngf', 4, '#FF9800'),
    ('Singapore', '/m/06t2t', 3, '#9C27B0'),
    ('Singapore', '/m/06t2t', 4, '#FF9800'),
    ('Manila', '/m/0195fg', 3, '#9C27B0'),
    ('Ho Chi Minh City', '/m/0hnp7', 3, '#9C27B0'),
    ('Hong Kong', '/m/03h64', 3, '#9C27B0'),
    ('Seoul', '/m/0hsqf', 3, '#9C27B0'),
    ('Tokyo', '/m/07dfk', 3, '#9C27B0'),
]

for city, cid, cabin, color in explore_combos:
    url = build_explore_url(cid, US_CITY_ID, cabin=cabin)
    label = f'{city} {CABIN_LABELS[cabin]}'
    html += f'<a href="{url}" target="_blank" style="background:{color}22;color:{color};border:1px solid {color}">{label}</a>\n'

html += """
</div>
</div>
"""

# --- Per-origin sections with fare tables ---
section_order = [
    ('Kuala Lumpur', 4), ('Kuala Lumpur', 3), ('Kuala Lumpur', 2),
    ('Jakarta', 3), ('Jakarta', 2), ('Jakarta', 4),
    ('Bangkok', 4), ('Singapore', 4),
]

for origin, cabin_num in section_order:
    key = (origin, cabin_num)
    if key not in grouped:
        continue
    fares = grouped[key]
    cabin_label = CABIN_LABELS[cabin_num]
    cabin_color = CABIN_COLORS[cabin_num]
    origin_info = ORIGINS.get(origin, {})
    origin_code = origin_info.get('code', '???')
    origin_cid = origin_info.get('city_id', '')

    # Determine if this is a top deal section
    is_top = origin in ('Kuala Lumpur',) and cabin_num in (3, 4)
    section_class = 'section top-deal' if is_top else 'section'

    explore_url = build_explore_url(origin_cid, US_CITY_ID, cabin=cabin_num)

    html += f"""
<div class="{section_class}">
<div class="section-header">
<h2 style="color:{cabin_color}">{origin} ({origin_code}) - {cabin_label} to USA</h2>
<span class="badge" style="background:{cabin_color}33;color:{cabin_color}">{len(fares)} fares</span>
<a href="{explore_url}" target="_blank" class="verify-btn explore-btn">Open Explore Map</a>
</div>
<table class="fare-table">
<tr>
<th>Destination</th>
<th>Price (USD)</th>
<th>2A+1C Est.</th>
<th>Dates</th>
<th>Stops</th>
<th>Type</th>
<th>Verify</th>
</tr>
"""

    for fare in fares:
        dest = fare['destination']
        price = fare['price_usd']
        family_price = price * 2.75
        dates = fare.get('dates', '')
        stops = fare.get('stops', '')
        cls = fare['classification']

        price_class = 'price-bug' if cls == 'BUG_FARE' else 'price-cheap'
        type_label = 'BUG' if cls == 'BUG_FARE' else 'CHEAP'

        # Build verify links
        verify_links = ''

        # If we have a verified detail_url from the scan, use it
        v = fare.get('verification', {})
        detail_url = v.get('detail_url', '')
        if detail_url and detail_url != 'none':
            verify_links += f'<a href="{detail_url}" target="_blank" class="verify-btn search-btn">Flights</a> '

        # Also try to build a direct search URL
        depart, ret = parse_dates(dates)
        if depart and ret and dest in US_DEST:
            search_url = build_search_url(origin_cid, US_DEST[dest], depart, ret, cabin=cabin_num)
            verify_links += f'<a href="{search_url}" target="_blank" class="verify-btn search-btn">Search</a> '

        # Build explore URL for this specific route (with date)
        if depart:
            explore_url_dated = build_explore_url(origin_cid, US_CITY_ID, date=depart, cabin=cabin_num)
            verify_links += f'<a href="{explore_url_dated}" target="_blank" class="verify-btn explore-btn">Explore</a>'

        html += f"""<tr>
<td><strong>{dest}</strong></td>
<td class="price {price_class}">${price:.0f}</td>
<td style="color:#8b949e">${family_price:.0f}</td>
<td>{dates}</td>
<td>{stops}</td>
<td><span style="color:{'#f85149' if cls=='BUG_FARE' else '#d29922'};font-weight:600">{type_label}</span></td>
<td>{verify_links}</td>
</tr>
"""

    html += """</table>
</div>
"""

# --- Additional explore links for cities not in scan results yet ---
html += """
<div class="section">
<div class="section-header"><h2>Scan More Cities (Not Yet Scanned or Partial)</h2></div>
<div class="explore-links">
"""

extra_cities = [
    ('Taipei', '/m/0ftkx'),
    ('Seoul', '/m/0hsqf'),
    ('Tokyo', '/m/07dfk'),
    ('Ho Chi Minh City', '/m/0hnp7'),
]

for city, cid in extra_cities:
    for cabin in [2, 3, 4]:
        url = build_explore_url(cid, US_CITY_ID, cabin=cabin)
        color = CABIN_COLORS[cabin]
        label = f'{city} {CABIN_LABELS[cabin]}'
        html += f'<a href="{url}" target="_blank" style="background:{color}22;color:{color};border:1px solid {color}">{label}</a>\n'

# Also add Europe destinations
html += """
<br><br><strong style="color:#8b949e;font-size:0.85em">Europe destinations (for Trip 3 planning):</strong><br>
"""
GERMANY_ID = '/m/0d060g'
UK_ID = '/m/07ssc'
for city, cid in [('Jakarta', '/m/044rv'), ('Kuala Lumpur', '/m/04f_d')]:
    for dest_name, dest_id in [('Germany', GERMANY_ID), ('UK', UK_ID)]:
        for cabin in [3, 4]:
            url = build_explore_url(cid, dest_id, cabin=cabin)
            color = CABIN_COLORS[cabin]
            label = f'{city} > {dest_name} {CABIN_LABELS[cabin]}'
            html += f'<a href="{url}" target="_blank" style="background:{color}22;color:{color};border:1px solid {color}">{label}</a>\n'

html += """
</div>
</div>
"""

# Footer
html += f"""
<p class="timestamp">
Scanner: bug_fare_scanner.py | Data: scanner_results.json | Generated: {timestamp}<br>
Normal price ranges (RT): Economy $800-2000 | Premium Eco $1200-3000 | Business $3000-8000 | First $8000-20000<br>
Bug fare threshold: below 60% of normal minimum
</p>

</body>
</html>
"""

with open('D:/claude/flights/bug_fare_verify.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Generated bug_fare_verify.html ({len(html)} bytes)")
print(f"Sections: {len(section_order)} origin+cabin groups")
print(f"Total fares listed: {len(bugs)}")
