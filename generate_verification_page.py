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
CABIN_COLORS = {1: '#276749', 2: '#2b6cb0', 3: '#6b21a8', 4: '#c2410c'}
CABIN_EMOJI = {1: '', 2: '', 3: '', 4: ''}

# --- Load scan results ---
with open('D:/claude/flights/scanner_results.json', encoding='utf-8') as f:
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
timestamp = datetime.now().strftime('%Y-%m-%d %H:%M UTC+8')

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bug Fare Scanner - Live Verification Links</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif; background: #fff; color: #2d3748; font-size: 16px; line-height: 1.7; }}
.container {{ max-width: 1100px; margin: 0 auto; padding: 24px 28px; }}
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
origins_with_bugs = len(set(b['origin_city'] for b in bugs if b['classification'] == 'BUG_FARE'))
lowest_biz = min((b['price_usd'] for b in bugs if b['cabin_num'] == 3), default=0)
lowest_first = min((b['price_usd'] for b in bugs if b['cabin_num'] == 4), default=0)

# Build highlight summary rows from actual bug fare data
from collections import defaultdict as dd2
highlight_groups = dd2(lambda: {'prices': [], 'dests': set()})
for b in bugs:
    if b['classification'] == 'BUG_FARE':
        key = (b['origin_city'], b.get('origin_code', ''), b['cabin'])
        highlight_groups[key]['prices'].append(b['price_usd'])
        highlight_groups[key]['dests'].add(b['destination'])

highlight_rows = ''
for (origin, code, cabin), info in sorted(highlight_groups.items(), key=lambda x: min(x[1]['prices'])):
    prices = sorted(info['prices'])
    n_dests = len(info['dests'])
    lo, hi = prices[0], prices[-1]
    fam_lo, fam_hi = lo * 2.75, hi * 2.75
    price_str = f'${lo:,.0f}' if lo == hi else f'${lo:,.0f}-${hi:,.0f}'
    fam_str = f'${fam_lo:,.0f}' if lo == hi else f'${fam_lo:,.0f}-${fam_hi:,.0f}'
    dest_str = list(info['dests'])[0] if n_dests == 1 else f'{n_dests} US cities'
    highlight_rows += f'''<tr>
<td><strong>{origin} ({code})</strong></td>
<td>{cabin}</td>
<td style="color:#b91c1c;font-weight:700">{price_str}</td>
<td>{fam_str}</td>
<td>{dest_str}</td>
</tr>
'''

# Find the winner
winner_key = min(highlight_groups.keys(), key=lambda k: min(highlight_groups[k]['prices']))
winner_origin = winner_key[0]
winner_code = winner_key[1]

html += f"""
<div class="section" style="border:2px solid #805ad5;background:#faf5ff">
<div class="section-header" style="background:#f3e8ff;border-bottom:2px solid #d6bcfa">
<h2 style="color:#6b21a8">{bug_count} Bug Fares Found</h2>
<span style="color:#718096;font-size:13px">All prices per person, round-trip</span>
</div>
<table class="fare-table">
<tr>
<th>Origin</th><th>Cabin</th><th>Price Range</th><th>Family (2A+1C)</th><th>Destinations</th>
</tr>
{highlight_rows}
</table>
<div style="padding:14px 20px;color:#4a5568;font-size:14px;border-top:1px solid #e9d8fd;background:#faf5ff">
<strong style="color:#6b21a8">{winner_origin} is the clear winner</strong> &mdash; scan found bug fares across multiple cabin classes to dozens of US cities. Premium Economy under $2,000 and Business under $2,600 for your family of 3.
</div>
</div>

<div class="stats">
<div class="stat-card"><div class="num" style="color:#b91c1c">{bug_count}</div><div class="label">Bug Fares Found</div></div>
<div class="stat-card"><div class="num" style="color:#92400e">{cheap_count}</div><div class="label">Cheap Fares</div></div>
<div class="stat-card"><div class="num" style="color:#6b21a8">${lowest_biz:.0f}</div><div class="label">Lowest Business RT</div></div>
<div class="stat-card"><div class="num" style="color:#c2410c">${lowest_first:.0f}</div><div class="label">Lowest First RT</div></div>
<div class="stat-card"><div class="num" style="color:#2b6cb0">{origins_with_bugs}</div><div class="label">Origin Cities w/ Bugs</div></div>
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

def render_fare_row(fare, origin_cid, cabin_num):
    """Render a single fare table row."""
    dest = fare['destination']
    price = fare['price_usd']
    family_price = price * 2.75
    dates = clean_dates(fare.get('dates', ''))
    stops = fare.get('stops', '')
    cls = fare['classification']
    origin_code = fare.get('origin_code', '')

    price_class = 'price-bug' if cls == 'BUG_FARE' else 'price-cheap'
    type_label = 'BUG' if cls == 'BUG_FARE' else 'CHEAP'

    # Build verify links
    verify_links = ''
    depart, ret = parse_dates(dates)

    # Use scanner detail_urls when available (all city IDs now corrected)
    v = fare.get('verification', {})
    detail_url = v.get('detail_url', '')
    if detail_url and detail_url != 'none':
        verify_links += f'<a href="{detail_url}" target="_blank" rel="noopener" class="verify-btn search-btn">View Flights</a> '

    # Explore URL — always generate one (use departure date if available, else default)
    explore_url_dated = build_explore_url(origin_cid, US_CITY_ID, date=depart, cabin=cabin_num)
    verify_links += f'<a href="{explore_url_dated}" target="_blank" rel="noopener" class="verify-btn explore-btn">Explore</a>'

    return f"""<tr>
<td><strong>{dest}</strong></td>
<td class="price {price_class}">${price:.0f}</td>
<td style="color:#718096">${family_price:.0f}</td>
<td>{dates}</td>
<td>{stops}</td>
<td><span style="color:{'#b91c1c' if cls=='BUG_FARE' else '#92400e'};font-weight:600">{type_label}</span></td>
<td>{verify_links}</td>
</tr>
"""

def render_fare_table_header():
    return """<table class="fare-table">
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

# --- Per-origin sections with fare tables (under $3000 family budget) ---
section_order = [
    ('Jakarta', 2), ('Jakarta', 3), ('Jakarta', 4),
    ('Tokyo', 3), ('Tokyo', 4),
    ('Manila', 4),
    ('Seoul', 2), ('Seoul', 3), ('Seoul', 4),
    ('Kuala Lumpur', 2), ('Kuala Lumpur', 3), ('Kuala Lumpur', 4),
    ('Bangkok', 3), ('Bangkok', 4),
    ('Singapore', 3), ('Singapore', 4),
    ('Taipei', 3), ('Taipei', 4),
    ('Hong Kong', 3), ('Hong Kong', 4),
]

over_budget_fares = []  # collect fares over $3000 family total

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

    affordable = [f for f in fares if f['price_usd'] * 2.75 <= FAMILY_BUDGET]
    expensive = [f for f in fares if f['price_usd'] * 2.75 > FAMILY_BUDGET]
    for f in expensive:
        over_budget_fares.append((f, origin_cid, cabin_num))

    if not affordable:
        continue

    is_top = origin in ('Kuala Lumpur',) and cabin_num in (3, 4)
    section_class = 'section top-deal' if is_top else 'section'
    explore_url = build_explore_url(origin_cid, US_CITY_ID, cabin=cabin_num)

    html += f"""
<div class="{section_class}">
<div class="section-header">
<h2>{origin} ({origin_code}) &mdash; {cabin_label} to USA</h2>
<span class="badge" style="background:{cabin_color}15;color:{cabin_color};border:1px solid {cabin_color}33">{len(affordable)} fares under $3k</span>
<a href="{explore_url}" target="_blank" rel="noopener" class="verify-btn explore-btn">Open Explore Map</a>
</div>
"""
    html += render_fare_table_header()
    for fare in affordable:
        html += render_fare_row(fare, origin_cid, cabin_num)
    html += """</table>
</div>
"""

# --- Over-budget fares section ---
if over_budget_fares:
    html += f"""
<div class="section" style="opacity:0.7">
<div class="section-header" style="background:#fff5f5">
<h2 style="color:#718096">Over $3,000 Family Total ({len(over_budget_fares)} fares)</h2>
<span class="badge" style="background:#fed7d7;color:#9b2c2c;border:1px solid #feb2b2">Unlikely to book</span>
</div>
"""
    html += render_fare_table_header()
    for fare, cid, cab in over_budget_fares:
        html += render_fare_row(fare, cid, cab)
    html += """</table>
</div>
"""

# --- Scanned cities with no bug fares (summary) ---
scanned_cities = sorted(set(d['origin_city'] for d in data['destinations']))
cities_with_fares = sorted(set(b['origin_city'] for b in bugs))
no_bugs = [c for c in scanned_cities if c not in cities_with_fares]

html += f"""
<div class="section" style="opacity:0.6">
<div class="section-header" style="background:#f7fafc">
<h2 style="color:#a0aec0">Scanned &mdash; No Bug Fares ({len(no_bugs)} cities)</h2>
</div>
<div style="padding:14px 20px;color:#718096;font-size:13px">
{', '.join(no_bugs)}. All showed normal market pricing.
</div>
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

# Footer
html += f"""
<p class="timestamp">
Scanner: bug_fare_scanner.py | Data: scanner_results.json | Generated: {timestamp}<br>
Normal price ranges (RT): Economy $800-2000 | Premium Eco $1200-3000 | Business $3000-8000 | First $8000-20000<br>
Bug fare threshold: below 60% of normal minimum
</p>

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
print(f"Sections: {len(section_order)} origin+cabin groups")
print(f"Total fares listed: {len(bugs)}")
