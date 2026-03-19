import json, sys

filepath = sys.argv[1]
label = sys.argv[2]

data = json.load(open(filepath))
for item in data:
    for cat in ['best_flights', 'other_flights']:
        if cat in item:
            for f in item[cat]:
                airlines = [leg['airline'] for leg in f['flights']]
                route = ' -> '.join([f['flights'][0]['departure_airport']['id']] + [leg['arrival_airport']['id'] for leg in f['flights']])
                price = f.get('price', 'N/A')
                dur = f.get('total_duration', 'N/A')
                stops = len(f['flights']) - 1
                print(f"{label} | ${price} | {' / '.join(airlines)} | {route} | {dur}min | {stops} stop(s)")
