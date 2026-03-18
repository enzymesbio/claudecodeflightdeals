"""Generate README.md with bug fare tables and clickable verification links."""
import json
import base64
from datetime import datetime, timedelta
from collections import defaultdict

# --- Protobuf encoding ---
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
    if isinstance(data, str): data = data.encode('utf-8')
    return encode_varint((num << 3) | 2) + encode_varint(len(data)) + data

def build_explore_url(origin_city_id, dest_city_id='/m/09c7w0', date=None, cabin=3):
    if not date:
        date = (datetime.now() + timedelta(days=120)).strftime('%Y-%m-%d')
    origin_msg = field_varint(1, 3) + field_bytes(2, origin_city_id)
    dest_msg = field_varint(1, 4) + field_bytes(2, dest_city_id)
    leg1 = field_bytes(2, date) + field_bytes(13, origin_msg) + field_bytes(14, dest_msg)
    leg2 = field_bytes(13, dest_msg) + field_bytes(14, origin_msg)
    pax_config = b'\x08\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01'
    field22 = field_varint(3, 1) + field_varint(4, 1)
    msg = (field_varint(1, 28) + field_varint(2, 3) + field_bytes(3, leg1) +
           field_bytes(3, leg2) + field_varint(8, 1) + field_varint(9, cabin) +
           field_varint(14, 2) + field_bytes(16, pax_config) + field_varint(19, 1) +
           field_bytes(22, field22))
    tfs = base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')
    return f'https://www.google.com/travel/explore?tfs={tfs}&tfu=GgA&hl=en&gl=hk&curr=USD'

# --- Data ---
ORIGINS = {
    'Jakarta': '/m/044rv', 'Kuala Lumpur': '/m/049d1', 'Bangkok': '/m/0fn2g',
    'Singapore': '/m/06t2t', 'Manila': '/m/0195pd', 'Ho Chi Minh City': '/m/0hn4h',
    'Hong Kong': '/m/03h64', 'Seoul': '/m/0hsqf', 'Tokyo': '/m/07dfk', 'Taipei': '/m/0ftkx',
}
CODES = {
    'Jakarta': 'CGK', 'Kuala Lumpur': 'KUL', 'Bangkok': 'BKK', 'Singapore': 'SIN',
    'Manila': 'MNL', 'Ho Chi Minh City': 'SGN', 'Hong Kong': 'HKG', 'Seoul': 'ICN',
    'Tokyo': 'TYO', 'Taipei': 'TPE',
}
CABIN_LABELS = {1: 'Economy', 2: 'Premium Economy', 3: 'Business', 4: 'First'}
US_CITY_ID = '/m/09c7w0'
GERMANY_ID = '/m/0d060g'
UK_ID = '/m/07ssc'

with open('D:/claude/flights/scanner_results.json', encoding='utf-8') as f:
    data = json.load(f)

bugs = [d for d in data['destinations'] if d['classification'] in ('BUG_FARE', 'CHEAP')]
timestamp = data['scan_timestamp'][:19]
now = datetime.now().strftime('%Y-%m-%d %H:%M')

grouped = defaultdict(list)
for b in bugs:
    grouped[(b['origin_city'], b['cabin_num'])].append(b)
for key in grouped:
    grouped[key].sort(key=lambda x: x['price_usd'])

bug_count = len([b for b in bugs if b['classification'] == 'BUG_FARE'])
cheap_count = len([b for b in bugs if b['classification'] == 'CHEAP'])
lowest_biz = min((b['price_usd'] for b in bugs if b['cabin_num'] == 3), default=0)
lowest_first = min((b['price_usd'] for b in bugs if b['cabin_num'] == 4), default=0)
lowest_prem = min((b['price_usd'] for b in bugs if b['cabin_num'] == 2), default=0)

md = []
md.append('# Bug Fare Scanner - Verification Dashboard')
md.append('')
md.append(f'> **Scan time:** {timestamp} | **Updated:** {now} | All prices USD, round-trip, per person')
md.append('')
md.append('> **Interactive HTML version:** [bug_fare_verify.html](https://enzymesbio.github.io/claudecodeflightdeals/bug_fare_verify.html)')
md.append('')
md.append('---')
md.append('')
md.append('## How to Verify Fares Are LIVE')
md.append('')
md.append('1. **Click an Explore link** below to open Google Flights Explore map')
md.append('2. **Click a city name tab** on the map -- this triggers a FRESH real-time search')
md.append('3. **Wait 3-5 seconds** for the price to reload with live data')
md.append('4. **Click "View flights"** to see actual booking page with specific itineraries')
md.append('5. If the price persists on the booking page, **the fare is confirmed live**')
md.append('6. For 2A+1C pricing: multiply 1-adult price by **2.75**')
md.append('')
md.append('---')
md.append('')
md.append('## Summary')
md.append('')
md.append('| Metric | Value |')
md.append('|--------|-------|')
md.append(f'| Total bug fares | **{bug_count}** |')
md.append(f'| Total cheap fares | **{cheap_count}** |')
md.append(f'| Lowest Business RT | **${lowest_biz:.0f}** (KUL-Denver) |')
md.append(f'| Lowest First RT | **${lowest_first:.0f}** (KUL-Chicago) |')
md.append(f'| Lowest Premium Eco RT | **${lowest_prem:.0f}** (KUL-Denver) |')
md.append('')
md.append('---')
md.append('')
md.append('## Quick Explore Links (Click to Open Map)')
md.append('')
md.append('### Priority Origins (Active Bug Fares)')
md.append('')

priority = [('Kuala Lumpur', '/m/04f_d'), ('Jakarta', '/m/044rv')]
for city, cid in priority:
    links = []
    for cabin in [2, 3, 4]:
        url = build_explore_url(cid, US_CITY_ID, cabin=cabin)
        links.append(f'[{CABIN_LABELS[cabin]}]({url})')
    md.append(f'**{city} ({CODES[city]}):** {" | ".join(links)}')
    md.append('')

md.append('### Other Asian Cities')
md.append('')
other = [('Bangkok', '/m/0fngf'), ('Singapore', '/m/06t2t'), ('Manila', '/m/0195fg'),
         ('Ho Chi Minh City', '/m/0hnp7'), ('Hong Kong', '/m/03h64'),
         ('Seoul', '/m/0hsqf'), ('Tokyo', '/m/07dfk'), ('Taipei', '/m/0ftkx')]
for city, cid in other:
    links = []
    for cabin in [3, 4]:
        url = build_explore_url(cid, US_CITY_ID, cabin=cabin)
        links.append(f'[{CABIN_LABELS[cabin]}]({url})')
    md.append(f'**{city}:** {" | ".join(links)}')

md.append('')
md.append('### Europe (Trip 3 Planning)')
md.append('')
for city, cid in priority:
    links = []
    for dest_name, dest_id in [('Germany', GERMANY_ID), ('UK', UK_ID)]:
        for cabin in [3, 4]:
            url = build_explore_url(cid, dest_id, cabin=cabin)
            links.append(f'[{dest_name} {CABIN_LABELS[cabin]}]({url})')
    md.append(f'**{city}:** {" | ".join(links)}')

md.append('')
md.append('---')
md.append('')

# Fare tables
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
    code = CODES.get(origin, '???')
    cid = ORIGINS.get(origin, '')
    explore_url = build_explore_url(cid, US_CITY_ID, cabin=cabin_num)

    md.append(f'## {origin} ({code}) -- {cabin_label} to USA')
    md.append('')
    md.append(f'[Open Explore Map]({explore_url})')
    md.append('')
    md.append('| Destination | Price | 2A+1C Est. | Dates | Stops | Type | Verify |')
    md.append('|-------------|------:|----------:|-------|-------|------|--------|')

    for fare in fares[:25]:
        dest = fare['destination']
        price = fare['price_usd']
        family = price * 2.75
        dates = fare.get('dates', '')
        stops = fare.get('stops', '')
        cls = fare['classification']
        type_label = 'BUG' if cls == 'BUG_FARE' else 'CHEAP'

        v = fare.get('verification', {})
        detail_url = v.get('detail_url', '')
        verify = f'[Flights]({detail_url})' if detail_url else '--'

        md.append(f'| {dest} | **${price:.0f}** | ${family:.0f} | {dates} | {stops} | {type_label} | {verify} |')

    if len(fares) > 25:
        md.append(f'')
        md.append(f'*...and {len(fares)-25} more. See scanner_results.json for full list.*')
    md.append('')
    md.append('---')
    md.append('')

md.append('## Price Thresholds')
md.append('')
md.append('| Cabin | Normal RT Range | Bug Fare If Below |')
md.append('|-------|---------------:|------------------:|')
md.append('| Economy | $800 -- $2,000 | $480 |')
md.append('| Premium Economy | $1,200 -- $3,000 | $720 |')
md.append('| Business | $3,000 -- $8,000 | $1,800 |')
md.append('| First | $8,000 -- $20,000 | $4,800 |')
md.append('')
md.append('---')
md.append('')
md.append('*Generated by bug_fare_scanner.py | [Full results JSON](scanner_results.json) | [System Design](SYSTEM_DESIGN.md)*')

output = '\n'.join(md)
with open('D:/claude/flights/README.md', 'w', encoding='utf-8') as f:
    f.write(output)

print(f'Generated README.md ({len(output)} bytes, {len(md)} lines)')
