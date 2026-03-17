"""Check which airlines Google Flights actually shows - NO filtering"""
import sys
import time
sys.path.insert(0, 'D:/claude/flights')
from search_flights import FlightSearcher

searcher = FlightSearcher(currency='USD')

routes = [
    ('PVG', 'LAX', '2026-05-15', '2026-06-15'),
    ('PVG', 'SFO', '2026-05-15', '2026-06-15'),
    ('CAN', 'LAX', '2026-05-15', '2026-06-15'),
    ('XMN', 'LAX', '2026-05-15', '2026-06-15'),
    ('HGH', 'LAX', '2026-05-15', '2026-06-15'),
    ('PVG', 'LAX', '2026-09-01', '2026-09-29'),
    ('PVG', 'SFO', '2026-09-01', '2026-09-29'),
]

all_airlines = set()

for origin, dest, dep, ret in routes:
    print('\n=== ' + origin + ' -> ' + dest + ' (' + dep + ' RT ' + ret + ') ===')
    result = searcher.search(origin=origin, destination=dest, date=dep, return_date=ret, adults=1, children=0)
    if result['status'] == 'success':
        for f in result.get('flights', []):
            airline = f['airline']
            all_airlines.add(airline)
            price = f['price']
            stops = f['stops']
            dur = f['duration']
            print('  $' + str(price) + '/pp | ' + airline + ' | ' + str(stops) + 'stop | ' + dur)
    else:
        print('  Error: ' + str(result.get('error', 'unknown')))
    time.sleep(1.5)

print('\n\n=== ALL AIRLINES FOUND ===')
for a in sorted(all_airlines):
    is_chinese = False
    for kw in ['china', 'southern', 'eastern', 'xiamen', 'hainan', 'sichuan', 'juneyao', 'spring', 'lucky', 'shenzhen', 'air china']:
        if kw in a.lower():
            is_chinese = True
    marker = ' *** CHINESE ***' if is_chinese else ''
    print('  ' + a + marker)
