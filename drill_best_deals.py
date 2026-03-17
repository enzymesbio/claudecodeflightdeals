"""
Drill into the best deals found:
1. ICN->LAX Air Premia RT $675/pp - verify with more dates
2. NRT->LAX RT - search more date combos
3. PVG->SFO RT - the $720 Korean Air deal
4. Try longer trip durations (3-6 weeks)
"""
import json
import sys
import time
sys.path.insert(0, 'D:/claude/flights')
from search_flights import FlightSearcher

searcher = FlightSearcher(currency='USD')
SKIP = ['starlux', 'eva air', 'china airlines', 'zipair', 'tigerair']


def parse(result):
    flights = []
    if result['status'] != 'success':
        return flights
    for f in result.get('flights', []):
        if any(s in f['airline'].lower() for s in SKIP):
            continue
        flights.append({
            'price_pp': f['price'],
            'price_3pax': int(f['price'] * 2.75),
            'airline': f['airline'],
            'stops': f['stops'],
            'duration': f['duration'],
            'layovers': [lo['city'] for lo in f.get('layovers', [])],
        })
    return flights


# All round-trip searches to run
searches = [
    # === ICN (Seoul) - THE WINNER ===
    # Air Premia nonstop LAX was $675/pp! Verify with different dates/durations
    ('ICN', 'LAX', '2026-05-15', '2026-06-15'),  # May-Jun, 4 wks
    ('ICN', 'LAX', '2026-05-20', '2026-06-20'),  # May-Jun, 4 wks
    ('ICN', 'LAX', '2026-06-01', '2026-07-01'),  # Jun-Jul, 4 wks
    ('ICN', 'LAX', '2026-06-09', '2026-06-29'),  # Jun, 3 wks
    ('ICN', 'LAX', '2026-05-20', '2026-07-01'),  # 6 wks
    ('ICN', 'LAX', '2026-09-01', '2026-09-30'),  # Sep
    ('ICN', 'LAX', '2026-09-10', '2026-10-10'),  # Sep-Oct
    # ICN -> SFO
    ('ICN', 'SFO', '2026-05-15', '2026-06-15'),
    ('ICN', 'SFO', '2026-06-01', '2026-07-01'),
    ('ICN', 'SFO', '2026-09-01', '2026-09-30'),
    # === NRT (Tokyo) ===
    ('NRT', 'LAX', '2026-05-10', '2026-06-10'),
    ('NRT', 'LAX', '2026-06-01', '2026-06-29'),
    ('NRT', 'LAX', '2026-09-01', '2026-09-30'),
    ('NRT', 'SFO', '2026-05-10', '2026-06-10'),
    ('NRT', 'SFO', '2026-09-01', '2026-09-30'),
    # === PVG (Shanghai) - verify the $720 deal ===
    ('PVG', 'SFO', '2026-05-10', '2026-05-24'),  # 2 wks
    ('PVG', 'SFO', '2026-05-15', '2026-06-15'),  # 4 wks
    ('PVG', 'LAX', '2026-05-10', '2026-05-24'),  # 2 wks
    ('PVG', 'LAX', '2026-09-01', '2026-09-15'),  # 2 wks Sep
    # === HKG (Hong Kong) ===
    ('HKG', 'LAX', '2026-05-15', '2026-06-15'),
    ('HKG', 'LAX', '2026-09-01', '2026-09-30'),
    ('HKG', 'SFO', '2026-09-01', '2026-09-30'),
]

all_results = []

for origin, dest, dep, ret in searches:
    from datetime import datetime
    d1 = datetime.strptime(dep, '%Y-%m-%d')
    d2 = datetime.strptime(ret, '%Y-%m-%d')
    weeks = round((d2 - d1).days / 7, 1)

    label = origin + '->' + dest + ' ' + dep + ' RT ' + ret + ' (' + str(weeks) + 'wk)'
    print(label + '...', end=' ', flush=True)

    result = searcher.search(origin=origin, destination=dest, date=dep, return_date=ret, adults=1, children=0)
    flights = parse(result)

    if flights:
        best = flights[0]
        via = ' via ' + ','.join(best['layovers']) if best['layovers'] else ' nonstop'
        marker = ' *** UNDER $2K! ***' if best['price_3pax'] < 2000 else ''
        print('$' + str(best['price_pp']) + '/pp ($' + str(best['price_3pax']) + '/3pax) | ' +
              best['airline'] + ' | ' + best['duration'] + via + marker)

        all_results.append({
            'origin': origin, 'dest': dest,
            'dep': dep, 'ret': ret, 'weeks': weeks,
            'cheapest_pp': best['price_pp'],
            'cheapest_3pax': best['price_3pax'],
            'airline': best['airline'],
            'stops': best['stops'],
            'duration': best['duration'],
            'top_5': flights[:5],
        })
    else:
        print('no results')

    time.sleep(1.5)

# Sort by price
all_results.sort(key=lambda x: x['cheapest_pp'])

# Summary
print('\n' + '=' * 70)
print('ALL DEALS RANKED (cheapest round-trip per person):')
print('=' * 70)
print('{:>4} {:>8} {:>10} {:<20} {:<12} {:<25} {:>6}'.format(
    '#', '$/pp', '$/3pax', 'Route', 'Dates', 'Airline', 'Weeks'))
print('-' * 95)
for i, r in enumerate(all_results):
    marker = ' ***' if r['cheapest_3pax'] < 2000 else ''
    dates = r['dep'][5:] + '-' + r['ret'][5:]
    print('{:>4} {:>8} {:>10} {:<20} {:<12} {:<25} {:>5}{}'.format(
        i+1, '$' + str(r['cheapest_pp']), '$' + str(r['cheapest_3pax']),
        r['origin'] + '->' + r['dest'] + '->' + r['origin'],
        dates, r['airline'][:25], str(r['weeks']) + 'wk', marker))

# Separate: deals under $2500 for 3 pax
print('\n' + '=' * 70)
print('DEALS UNDER $2,500 FOR FAMILY OF 3:')
print('=' * 70)
for r in all_results:
    if r['cheapest_3pax'] < 2500:
        via = ' via ' + ','.join(r['top_5'][0]['layovers']) if r['top_5'][0]['layovers'] else ' nonstop'
        print('  $' + str(r['cheapest_3pax']) + ' | ' + r['origin'] + '->' + r['dest'] + '->' + r['origin'] +
              ' | ' + r['dep'] + ' to ' + r['ret'] + ' (' + str(r['weeks']) + 'wk) | ' +
              r['airline'] + via)
        # Also show alternatives
        for alt in r['top_5'][1:3]:
            alt_via = ' via ' + ','.join(alt['layovers']) if alt['layovers'] else ' nonstop'
            print('    alt: $' + str(alt['price_3pax']) + ' | ' + alt['airline'] + alt_via)

# Save
with open('D:/claude/flights/best_deals_drilldown.json', 'w') as f:
    json.dump(all_results, f, indent=2)

print('\nSaved to best_deals_drilldown.json')
