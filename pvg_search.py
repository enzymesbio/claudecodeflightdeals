"""Comprehensive PVG to USA search: May-Sept 2026, 2-6 week trips"""
import json
import sys
import time
sys.path.insert(0, 'D:/claude/flights')
from search_flights import FlightSearcher

searcher = FlightSearcher(currency='USD')

SKIP = ['starlux', 'eva air', 'china airlines', 'zipair', 'tigerair']

# Outbound dates to search (PVG -> USA)
outbound_dates = [
    '2026-05-10', '2026-05-20', '2026-05-30',
    '2026-06-01', '2026-06-10', '2026-06-20',
    '2026-08-01', '2026-08-15', '2026-08-25',
    '2026-09-01', '2026-09-10', '2026-09-20',
]

# US destinations
destinations = ['LAX', 'SFO']

# Return dates to search (USA -> PVG)
return_dates = [
    '2026-06-01', '2026-06-10', '2026-06-20', '2026-06-29',
    '2026-07-01', '2026-07-10', '2026-07-20',
    '2026-08-01', '2026-08-15', '2026-08-25',
    '2026-09-01', '2026-09-10', '2026-09-20', '2026-09-30',
    '2026-10-10', '2026-10-20', '2026-10-31',
]

all_outbound = []
all_return = []
search_count = 0
errors = 0

# === OUTBOUND: PVG -> LAX/SFO ===
print('=' * 70)
print('OUTBOUND SEARCHES: PVG -> USA')
print('=' * 70)

for dest in destinations:
    for date in outbound_dates:
        label = 'PVG->' + dest + ' ' + date
        print('  ' + label + '...', end=' ', flush=True)
        search_count += 1

        try:
            result = searcher.search(origin='PVG', destination=dest, date=date, adults=1, children=0)

            if result['status'] == 'success' and result['flights']:
                found = 0
                for f in result['flights']:
                    if any(s in f['airline'].lower() for s in SKIP):
                        continue
                    entry = {
                        'origin': 'PVG', 'dest': dest, 'date': date,
                        'price_pp': f['price'],
                        'price_3pax': int(f['price'] * 2.75),
                        'airline': f['airline'], 'stops': f['stops'],
                        'duration': f['duration'],
                        'dep_time': f['departure']['time'],
                        'layovers': [lo['city'] for lo in f.get('layovers', [])],
                    }
                    all_outbound.append(entry)
                    found += 1
                cheapest = min(e['price_pp'] for e in all_outbound if e['date'] == date and e['dest'] == dest) if found else 0
                print(str(found) + ' flights, cheapest $' + str(cheapest) + '/pp')
            else:
                print('no results')
        except Exception as e:
            print('ERROR: ' + str(e))
            errors += 1

        time.sleep(1.5)

# === RETURN: LAX/SFO -> PVG ===
print()
print('=' * 70)
print('RETURN SEARCHES: USA -> PVG')
print('=' * 70)

for orig in destinations:
    for date in return_dates:
        label = orig + '->PVG ' + date
        print('  ' + label + '...', end=' ', flush=True)
        search_count += 1

        try:
            result = searcher.search(origin=orig, destination='PVG', date=date, adults=1, children=0)

            if result['status'] == 'success' and result['flights']:
                found = 0
                for f in result['flights']:
                    if any(s in f['airline'].lower() for s in SKIP):
                        continue
                    entry = {
                        'origin': orig, 'dest': 'PVG', 'date': date,
                        'price_pp': f['price'],
                        'price_3pax': int(f['price'] * 2.75),
                        'airline': f['airline'], 'stops': f['stops'],
                        'duration': f['duration'],
                        'dep_time': f['departure']['time'],
                        'layovers': [lo['city'] for lo in f.get('layovers', [])],
                    }
                    all_return.append(entry)
                    found += 1
                cheapest = min(e['price_pp'] for e in all_return if e['date'] == date and e['origin'] == orig) if found else 0
                print(str(found) + ' flights, cheapest $' + str(cheapest) + '/pp')
            else:
                print('no results')
        except Exception as e:
            print('ERROR: ' + str(e))
            errors += 1

        time.sleep(1.5)

# === ANALYSIS ===
print()
print('=' * 70)
print('ANALYSIS: ' + str(search_count) + ' searches, ' + str(errors) + ' errors')
print('=' * 70)

# Cheapest outbound by date
print()
print('CHEAPEST OUTBOUND PVG->USA BY DATE (per person):')
print('-' * 70)
seen_dates = sorted(set(e['date'] for e in all_outbound))
for date in seen_dates:
    flights = [e for e in all_outbound if e['date'] == date]
    if flights:
        best = min(flights, key=lambda x: x['price_pp'])
        via = ' via ' + ','.join(best['layovers']) if best['layovers'] else ' nonstop'
        print('  ' + date + ': $' + str(best['price_pp']) + '/pp ($' + str(best['price_3pax']) + '/3pax) | ' +
              best['dest'] + ' | ' + best['airline'] + ' | ' + best['duration'] + via)

print()
print('CHEAPEST RETURN USA->PVG BY DATE (per person):')
print('-' * 70)
seen_dates = sorted(set(e['date'] for e in all_return))
for date in seen_dates:
    flights = [e for e in all_return if e['date'] == date]
    if flights:
        best = min(flights, key=lambda x: x['price_pp'])
        via = ' via ' + ','.join(best['layovers']) if best['layovers'] else ' nonstop'
        print('  ' + date + ': $' + str(best['price_pp']) + '/pp ($' + str(best['price_3pax']) + '/3pax) | from ' +
              best['origin'] + ' | ' + best['airline'] + ' | ' + best['duration'] + via)

# Best combos (2-6 week trips)
print()
print('=' * 70)
print('BEST ROUND-TRIP COMBOS (2-6 weeks, est. 3 pax):')
print('=' * 70)

from datetime import datetime

combos = []
for out in all_outbound:
    out_date = datetime.strptime(out['date'], '%Y-%m-%d')
    for ret in all_return:
        ret_date = datetime.strptime(ret['date'], '%Y-%m-%d')
        days = (ret_date - out_date).days
        if days < 14 or days > 42:  # 2-6 weeks
            continue
        # Match destinations (out to LAX, return from LAX; or SFO-SFO)
        # Allow LAX<->SFO mix too since they're close
        total = out['price_3pax'] + ret['price_3pax']
        weeks = round(days / 7, 1)
        combos.append({
            'total': total,
            'pp': round(total / 3),
            'out': out,
            'ret': ret,
            'days': days,
            'weeks': weeks,
        })

combos.sort(key=lambda x: x['total'])

# Show top 20
for i, c in enumerate(combos[:20]):
    out = c['out']
    ret = c['ret']
    marker = ' *** UNDER $2,000! ***' if c['total'] < 2000 else ''
    print('  #' + str(i+1) + ': $' + str(c['total']) + ' total ($' + str(c['pp']) + '/pp) | ' +
          str(c['weeks']) + ' weeks' + marker)
    out_via = ' via ' + ','.join(out['layovers']) if out['layovers'] else ' nonstop'
    ret_via = ' via ' + ','.join(ret['layovers']) if ret['layovers'] else ' nonstop'
    print('    OUT: PVG->' + out['dest'] + ' ' + out['date'] + ' $' + str(out['price_pp']) + '/pp | ' +
          out['airline'] + ' | ' + out['duration'] + out_via)
    print('    RET: ' + ret['origin'] + '->PVG ' + ret['date'] + ' $' + str(ret['price_pp']) + '/pp | ' +
          ret['airline'] + ' | ' + ret['duration'] + ret_via)

# Monthly price heatmap
print()
print('=' * 70)
print('MONTHLY PRICE HEATMAP (cheapest per-person one-way):')
print('=' * 70)
months = ['May', 'Jun', 'Aug', 'Sep', 'Oct']
month_nums = {'May': '05', 'Jun': '06', 'Aug': '08', 'Sep': '09', 'Oct': '10'}

print('{:>12} {:>12} {:>12}'.format('Month', 'PVG->USA', 'USA->PVG'))
print('-' * 40)
for month in months:
    mn = month_nums[month]
    out_prices = [e['price_pp'] for e in all_outbound if e['date'][5:7] == mn]
    ret_prices = [e['price_pp'] for e in all_return if e['date'][5:7] == mn]
    out_min = '$' + str(min(out_prices)) if out_prices else 'N/A'
    ret_min = '$' + str(min(ret_prices)) if ret_prices else 'N/A'
    print('{:>12} {:>12} {:>12}'.format(month, out_min, ret_min))

# Save everything
with open('D:/claude/flights/pvg_comprehensive_results.json', 'w') as f:
    json.dump({
        'outbound': all_outbound,
        'return': all_return,
        'best_combos': combos[:30],
        'search_count': search_count,
        'errors': errors,
    }, f, indent=2)

print()
print('All data saved to pvg_comprehensive_results.json')
print('Total: ' + str(len(all_outbound)) + ' outbound + ' + str(len(all_return)) + ' return flights found')
