"""Batch flight search using custom Google Flights scraper"""
import json
import sys
import time
sys.path.insert(0, 'D:/claude/flights')
from search_flights import FlightSearcher

searcher = FlightSearcher(currency='USD')

SKIP_AIRLINES = ['starlux', 'eva air', 'china airlines', 'zipair', 'tigerair']

searches = [
    # Outbound: Asia -> USA (1 adult, multiply by ~2.75 for 2A+1C)
    ('OUT', 'HKG', 'LAX', '2026-06-02'),
    ('OUT', 'HKG', 'LAX', '2026-06-09'),
    ('OUT', 'HKG', 'SFO', '2026-06-02'),
    ('OUT', 'PVG', 'LAX', '2026-05-20'),
    ('OUT', 'PVG', 'LAX', '2026-06-01'),
    ('OUT', 'PVG', 'SFO', '2026-05-15'),
    ('OUT', 'CAN', 'LAX', '2026-05-20'),
    ('OUT', 'ICN', 'LAX', '2026-06-02'),
    ('OUT', 'NRT', 'LAX', '2026-05-15'),
    ('OUT', 'NRT', 'SFO', '2026-05-15'),
    # Return: USA -> Asia
    ('RET', 'LAX', 'HKG', '2026-06-29'),
    ('RET', 'LAX', 'HKG', '2026-06-25'),
    ('RET', 'LAX', 'PVG', '2026-06-29'),
    ('RET', 'SFO', 'HKG', '2026-06-29'),
    ('RET', 'LAX', 'ICN', '2026-06-29'),
    ('RET', 'LAX', 'NRT', '2026-06-29'),
    ('RET', 'SFO', 'PVG', '2026-06-29'),
]

all_outbound = []
all_return = []

for direction, origin, dest, date in searches:
    label = origin + '->' + dest + ' ' + date
    print('Searching: ' + label + '...', flush=True)

    result = searcher.search(origin=origin, destination=dest, date=date, adults=1, children=0)

    if result['status'] == 'success' and result['flights']:
        for f in result['flights']:
            airline = f['airline'].lower()
            if any(s in airline for s in SKIP_AIRLINES):
                continue

            entry = {
                'direction': direction,
                'origin': origin,
                'dest': dest,
                'date': date,
                'price_1pax': f['price'],
                'price_3pax_est': int(f['price'] * 2.75),  # 2 adults + 1 child (~75% adult)
                'airline': f['airline'],
                'stops': f['stops'],
                'duration': f['duration'],
                'dep_time': f['departure']['time'],
                'arr_time': f['arrival']['time'],
                'layovers': [lo['airport'] + ' (' + lo['city'] + ')' for lo in f.get('layovers', [])],
            }

            if direction == 'OUT':
                all_outbound.append(entry)
            else:
                all_return.append(entry)

            print('  $' + str(f['price']) + '/pp (~$' + str(entry['price_3pax_est']) + '/3pax) | ' + f['airline'] + ' | ' + str(f['stops']) + ' stop | ' + f['duration'])
    else:
        print('  No results')

    time.sleep(2)  # Be respectful

# Sort by price
all_outbound.sort(key=lambda x: x['price_1pax'])
all_return.sort(key=lambda x: x['price_1pax'])

print()
print('=' * 70)
print('CHEAPEST OUTBOUND (per person):')
print('=' * 70)
for f in all_outbound[:10]:
    via = ' via ' + ', '.join(f['layovers']) if f['layovers'] else ' nonstop'
    print('  $' + str(f['price_1pax']) + '/pp ($' + str(f['price_3pax_est']) + '/3pax) | ' + f['origin'] + '->' + f['dest'] + ' ' + f['date'] + ' | ' + f['airline'] + ' | ' + f['duration'] + via)

print()
print('CHEAPEST RETURN (per person):')
print('=' * 70)
for f in all_return[:10]:
    via = ' via ' + ', '.join(f['layovers']) if f['layovers'] else ' nonstop'
    print('  $' + str(f['price_1pax']) + '/pp ($' + str(f['price_3pax_est']) + '/3pax) | ' + f['origin'] + '->' + f['dest'] + ' ' + f['date'] + ' | ' + f['airline'] + ' | ' + f['duration'] + via)

# Best combos
print()
print('=' * 70)
print('BEST COMBINATIONS (estimated 3 pax total):')
print('=' * 70)
combos = []
for out in all_outbound[:8]:
    for ret in all_return[:8]:
        total = out['price_3pax_est'] + ret['price_3pax_est']
        combos.append((total, out, ret))
combos.sort(key=lambda x: x[0])

for i, (total, out, ret) in enumerate(combos[:10]):
    marker = ' *** UNDER $2,000! ***' if total < 2000 else ''
    print('  #' + str(i+1) + ': $' + str(total) + ' total' + marker)
    print('    OUT: $' + str(out['price_3pax_est']) + ' | ' + out['origin'] + '->' + out['dest'] + ' ' + out['date'] + ' | ' + out['airline'] + ' | ' + out['duration'])
    print('    RET: $' + str(ret['price_3pax_est']) + ' | ' + ret['origin'] + '->' + ret['dest'] + ' ' + ret['date'] + ' | ' + ret['airline'] + ' | ' + ret['duration'])

# Save all data
with open('D:/claude/flights/custom_search_results.json', 'w') as f:
    json.dump({
        'outbound': all_outbound,
        'return': all_return,
        'best_combos': [{'total': t, 'outbound': o, 'return': r} for t, o, r in combos[:20]]
    }, f, indent=2)

print()
print('Results saved to custom_search_results.json')
