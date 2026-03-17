"""
Compare round-trip (same airline) vs one-way combo pricing.
Also explores: different return destinations, various date combos.
Explorer showed PVG->SFO RT at $720/pp and PVG->LAX RT at $879/pp!
"""
import json
import sys
import time
sys.path.insert(0, 'D:/claude/flights')
from search_flights import FlightSearcher

searcher = FlightSearcher(currency='USD')
SKIP = ['starlux', 'eva air', 'china airlines', 'zipair', 'tigerair']


def parse_results(result):
    """Extract clean flight list from search result"""
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
            'dep_time': f['departure']['time'],
            'arr_time': f['arrival']['time'],
            'layovers': [lo['city'] for lo in f.get('layovers', [])],
        })
    return flights


# =============================================
# PART 1: ROUND-TRIP SEARCHES (same airline both ways)
# Explorer found: PVG->SFO $720/pp RT, PVG->LAX $879/pp RT
# Let's verify with our dates (May-Jun, 2-6 weeks)
# =============================================
print('=' * 70)
print('PART 1: ROUND-TRIP SEARCHES (same airline, both directions)')
print('=' * 70)

rt_searches = [
    # PVG round trips (Explorer's best dates and our target dates)
    ('PVG', 'SFO', '2026-05-04', '2026-05-18'),   # Explorer found $720
    ('PVG', 'SFO', '2026-05-20', '2026-06-20'),   # 4 weeks, May-Jun
    ('PVG', 'SFO', '2026-06-01', '2026-06-29'),   # 4 weeks, Jun
    ('PVG', 'LAX', '2026-05-20', '2026-06-20'),   # 4 weeks
    ('PVG', 'LAX', '2026-06-01', '2026-06-29'),   # 4 weeks
    ('PVG', 'LAX', '2026-06-12', '2026-06-25'),   # Explorer found $879
    ('PVG', 'LAX', '2026-09-10', '2026-09-30'),   # Sep (cheapest month)
    ('PVG', 'SFO', '2026-09-10', '2026-09-30'),   # Sep
    # HKG round trips
    ('HKG', 'LAX', '2026-06-02', '2026-06-29'),
    ('HKG', 'SFO', '2026-06-02', '2026-06-29'),
    ('HKG', 'LAX', '2026-06-09', '2026-06-29'),
    # NRT round trips (Tokyo)
    ('NRT', 'LAX', '2026-05-15', '2026-06-15'),
    ('NRT', 'SFO', '2026-05-15', '2026-06-15'),
    # ICN round trips (Seoul)
    ('ICN', 'LAX', '2026-06-02', '2026-06-29'),
    ('ICN', 'SFO', '2026-06-02', '2026-06-29'),
]

rt_results = []
for origin, dest, dep_date, ret_date in rt_searches:
    label = origin + '->' + dest + ' ' + dep_date + ' RT ' + ret_date
    print('\n  ' + label + '...', flush=True)

    result = searcher.search(
        origin=origin, destination=dest,
        date=dep_date, return_date=ret_date,
        adults=1, children=0
    )

    flights = parse_results(result)
    if flights:
        # These are round-trip prices per person
        for f in flights[:5]:
            via = ' via ' + ','.join(f['layovers']) if f['layovers'] else ' nonstop'
            print('    $' + str(f['price_pp']) + '/pp RT ($' + str(f['price_3pax']) + '/3pax) | ' +
                  f['airline'] + ' | ' + str(f['stops']) + 'stop | ' + f['duration'] + via)
        rt_results.append({
            'origin': origin, 'dest': dest,
            'dep_date': dep_date, 'ret_date': ret_date,
            'type': 'round_trip',
            'cheapest_pp': flights[0]['price_pp'],
            'cheapest_3pax': flights[0]['price_3pax'],
            'cheapest_airline': flights[0]['airline'],
            'all_flights': flights[:8],
        })
    else:
        print('    No results')

    time.sleep(1.5)


# =============================================
# PART 2: OPEN-JAW / DIFFERENT RETURN CITY
# Fly INTO one city, fly OUT from another
# e.g., PVG->SFO, LAX->PVG (explore California, no inter-city flight cost)
# =============================================
print('\n' + '=' * 70)
print('PART 2: OPEN-JAW (arrive one city, depart another)')
print('=' * 70)

# For open-jaw, we search as one-way legs
oj_combos = [
    # PVG -> SFO (arrive) + LAX -> PVG (depart)
    ('PVG', 'SFO', '2026-05-20', 'LAX', 'PVG', '2026-06-20'),
    ('PVG', 'SFO', '2026-06-01', 'LAX', 'PVG', '2026-06-29'),
    ('PVG', 'SFO', '2026-09-10', 'LAX', 'PVG', '2026-09-30'),
    # PVG -> LAX (arrive) + SFO -> PVG (depart)
    ('PVG', 'LAX', '2026-05-20', 'SFO', 'PVG', '2026-06-20'),
    ('PVG', 'LAX', '2026-06-01', 'SFO', 'PVG', '2026-06-29'),
    # HKG -> LAX + SFO -> HKG
    ('HKG', 'LAX', '2026-06-09', 'SFO', 'HKG', '2026-06-29'),
    # NRT -> LAX + SFO -> NRT
    ('NRT', 'LAX', '2026-05-15', 'SFO', 'NRT', '2026-06-15'),
    # ICN -> LAX + SFO -> ICN
    ('ICN', 'LAX', '2026-06-02', 'SFO', 'ICN', '2026-06-29'),
]

oj_results = []
for o1, d1, date1, o2, d2, date2 in oj_combos:
    label = o1 + '->' + d1 + ' ' + date1 + ' + ' + o2 + '->' + d2 + ' ' + date2
    print('\n  ' + label)

    # Search outbound
    r1 = searcher.search(origin=o1, destination=d1, date=date1, adults=1, children=0)
    f1 = parse_results(r1)
    time.sleep(1.5)

    # Search return
    r2 = searcher.search(origin=o2, destination=d2, date=date2, adults=1, children=0)
    f2 = parse_results(r2)
    time.sleep(1.5)

    if f1 and f2:
        best_out = f1[0]
        best_ret = f2[0]
        total_pp = best_out['price_pp'] + best_ret['price_pp']
        total_3pax = best_out['price_3pax'] + best_ret['price_3pax']

        out_via = ' via ' + ','.join(best_out['layovers']) if best_out['layovers'] else ' nonstop'
        ret_via = ' via ' + ','.join(best_ret['layovers']) if best_ret['layovers'] else ' nonstop'

        print('    OUT: $' + str(best_out['price_pp']) + '/pp | ' + best_out['airline'] + out_via)
        print('    RET: $' + str(best_ret['price_pp']) + '/pp | ' + best_ret['airline'] + ret_via)
        print('    TOTAL: $' + str(total_pp) + '/pp ($' + str(total_3pax) + '/3pax)')

        oj_results.append({
            'out_origin': o1, 'out_dest': d1, 'out_date': date1,
            'ret_origin': o2, 'ret_dest': d2, 'ret_date': date2,
            'type': 'open_jaw',
            'out_price_pp': best_out['price_pp'],
            'out_airline': best_out['airline'],
            'ret_price_pp': best_ret['price_pp'],
            'ret_airline': best_ret['airline'],
            'total_pp': total_pp,
            'total_3pax': total_3pax,
            'out_flights': f1[:5],
            'ret_flights': f2[:5],
        })
    else:
        print('    Incomplete results')


# =============================================
# PART 3: COMPARISON SUMMARY
# =============================================
print('\n' + '=' * 70)
print('COMPARISON: ROUND-TRIP vs ONE-WAY COMBO vs OPEN-JAW')
print('=' * 70)

# Organize by origin/date range
all_deals = []

for rt in rt_results:
    all_deals.append({
        'type': 'Round Trip',
        'route': rt['origin'] + '->' + rt['dest'] + '->' + rt['origin'],
        'dates': rt['dep_date'] + ' to ' + rt['ret_date'],
        'price_pp': rt['cheapest_pp'],
        'price_3pax': rt['cheapest_3pax'],
        'airline': rt['cheapest_airline'],
        'note': 'Same airline both ways',
    })

for oj in oj_results:
    all_deals.append({
        'type': 'Open Jaw',
        'route': oj['out_origin'] + '->' + oj['out_dest'] + ' + ' + oj['ret_origin'] + '->' + oj['ret_dest'],
        'dates': oj['out_date'] + ' to ' + oj['ret_date'],
        'price_pp': oj['total_pp'],
        'price_3pax': oj['total_3pax'],
        'airline': oj['out_airline'] + ' + ' + oj['ret_airline'],
        'note': 'Arrive/depart different cities',
    })

all_deals.sort(key=lambda x: x['price_pp'])

print('\n{:<12} {:<35} {:<25} {:>8} {:>10} {}'.format(
    'Type', 'Route', 'Dates', '$/pp', '$/3pax', 'Airlines'))
print('-' * 120)
for d in all_deals[:25]:
    marker = ' ***' if d['price_3pax'] < 2000 else ''
    print('{:<12} {:<35} {:<25} {:>8} {:>10} {}{}'.format(
        d['type'], d['route'][:35], d['dates'][:25],
        '$' + str(d['price_pp']), '$' + str(d['price_3pax']),
        d['airline'][:40], marker))

# Save everything
with open('D:/claude/flights/rt_vs_ow_comparison.json', 'w') as f:
    json.dump({
        'round_trips': rt_results,
        'open_jaws': oj_results,
        'all_deals_sorted': all_deals,
    }, f, indent=2)

print('\n\nAll data saved to rt_vs_ow_comparison.json')
print('Total: ' + str(len(rt_results)) + ' round-trip + ' + str(len(oj_results)) + ' open-jaw searches')
