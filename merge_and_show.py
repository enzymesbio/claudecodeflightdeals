"""Merge all scan_*.json files and print summary."""
import json, os, glob, time, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

files = sorted(glob.glob('D:/claude/flights/scan_*.json'))
all_destinations = []
all_cities = []
all_cabins = set()

for sf in files:
    with open(sf, encoding='utf-8') as f:
        data = json.load(f)
    all_destinations.extend(data.get('destinations', []))
    all_cities.extend(data.get('cities_scanned', []))
    for c in data.get('cabins_scanned', []):
        all_cabins.add(c)

bug_fares = [d for d in all_destinations if d.get('classification') == 'BUG_FARE']
cheap_fares = [d for d in all_destinations if d.get('classification') == 'CHEAP']

merged = {
    'scan_timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    'cities_scanned': sorted(set(all_cities)),
    'cabins_scanned': sorted(all_cabins),
    'summary': {
        'total_destinations_found': len(all_destinations),
        'total_bug_fares': len(bug_fares),
        'total_cheap_fares': len(cheap_fares),
    },
    'destinations': all_destinations,
    'bug_fares': bug_fares,
    'cheap_fares': cheap_fares,
}

with open('D:/claude/flights/scanner_results.json', 'w', encoding='utf-8') as f:
    json.dump(merged, f, indent=2, ensure_ascii=False)

print(f'Merged {len(files)} city scans: {len(all_destinations)} destinations')
print(f'Bug fares: {len(bug_fares)}, Cheap: {len(cheap_fares)}')
print(f'Cities: {len(set(all_cities))}')
print()

for b in sorted(bug_fares, key=lambda x: x['price_usd']):
    fam = b['price_usd'] * 2.75
    dates = b.get('dates', '').replace('\u2009', ' ').replace('\u2013', '-')
    print(f"  {b['origin_city']:15s} -> {b['destination']:20s} | {b['cabin']:15s} | ${b['price_usd']:.0f} (fam ${fam:.0f}) | {dates}")
