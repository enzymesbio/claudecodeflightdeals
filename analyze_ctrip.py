import json
from collections import defaultdict

with open('D:/claude/flights/ctrip_results.json') as f:
    data = json.load(f)

print('Total flights:', data['results_count'])
print('Routes searched:', data['config']['routes_searched'])
print('Dates searched:', data['config']['dates_searched'])

by_route = defaultdict(list)
for f in data['results']:
    by_route[f['search_route']].append(f)

for route, flights in sorted(by_route.items()):
    flights.sort(key=lambda x: x['price'])
    lo = flights[0]['price']
    hi = flights[-1]['price']
    print('\n' + route + ': ' + str(len(flights)) + ' flights')
    print('  CNY ' + str(lo) + ' - ' + str(hi) + ' (~$' + str(round(lo/7.27)) + ' - $' + str(round(hi/7.27)) + ' USD)')
    for f in flights[:8]:
        fn = f.get('flight_number', '') or '??'
        usd = round(f['price'] / 7.27)
        stops = f.get('stops', '?')
        dur = f.get('duration', '') or ''
        dep = f.get('departure_time', '')
        arr = f.get('arrival_time', '')
        date = f.get('search_date', '')
        print('    ' + fn.ljust(14) + str(f['price']).rjust(6) + ' CNY (~$' + str(usd).rjust(4) + ') | ' +
              str(stops) + 'stop | ' + dur.rjust(8) + ' | ' + dep + '->' + arr + ' | ' + date)
