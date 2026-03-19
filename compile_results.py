import json
import os
import glob

SKIP_AIRLINES = {'EVA Air', 'China Airlines', 'STARLUX Airlines', 'ZIPAIR'}

all_results = {
    "search_summary": [],
    "outbound_flights": [],
    "return_flights": [],
    "best_combinations": []
}

base = "D:/claude/flights"
search_files = {
    "CAN->LAX May15": (f"{base}/search1_CAN_LAX.json", "outbound"),
    "CTU->LAX May20": (f"{base}/search2_CTU_LAX.json", "outbound"),
    "PVG->LAX May15": (f"{base}/search3_PVG_LAX.json", "outbound"),
    "CKG->LAX May20": (f"{base}/search4_CKG_LAX.json", "outbound"),
    "XIY->LAX May20": (f"{base}/search5_XIY_LAX.json", "outbound"),
    "KMG->LAX Jun01": (f"{base}/search6_KMG_LAX.json", "outbound"),
    "HKG->SFO Jun02": (f"{base}/search7_HKG_SFO.json", "outbound"),
    "LAX->CAN Jun25": (f"{base}/search8_LAX_CAN.json", "return"),
    "LAX->CTU Jun25": (f"{base}/search9_LAX_CTU.json", "return"),
    "LAX->PVG Jun29": (f"{base}/search10_LAX_PVG.json", "return"),
    "LAX->HKG Jun29": (f"{base}/search11_LAX_HKG.json", "return"),
    "SFO->PVG Jun25": (f"{base}/search12_SFO_PVG.json", "return"),
    "LAX->CAN Jun29": (f"{base}/search13_LAX_CAN29.json", "return"),
    "SFO->HKG Jun29": (f"{base}/search14_SFO_HKG.json", "return"),
    "SFO->CAN Jun29": (f"{base}/search15_SFO_CAN.json", "return"),
}

outbound_options = []
return_options = []

for label, (filepath, direction) in search_files.items():
    if not os.path.exists(filepath):
        all_results["search_summary"].append({"search": label, "status": "file_not_found"})
        continue

    try:
        data = json.load(open(filepath))
    except:
        all_results["search_summary"].append({"search": label, "status": "parse_error"})
        continue

    if not data:
        all_results["search_summary"].append({"search": label, "status": "empty_results"})
        continue

    flight_count = 0
    for item in data:
        for cat in ['best_flights', 'other_flights']:
            if cat not in item:
                continue
            for f in item[cat]:
                price = f.get('price')
                if price is None:
                    continue

                airlines = [leg['airline'] for leg in f['flights']]
                airline_set = set(airlines)

                # Check if any airline in the flight is in the skip list
                skip = bool(airline_set & SKIP_AIRLINES)

                dep = f['flights'][0]['departure_airport']
                arr = f['flights'][-1]['arrival_airport']
                route = ' -> '.join([f['flights'][0]['departure_airport']['id']] +
                                   [leg['arrival_airport']['id'] for leg in f['flights']])

                flight_info = {
                    "search": label,
                    "direction": direction,
                    "price": price,
                    "airlines": ' / '.join(airlines),
                    "route": route,
                    "departure_airport": dep['name'],
                    "departure_id": dep['id'],
                    "arrival_airport": arr['name'],
                    "arrival_id": arr['id'],
                    "total_duration_min": f.get('total_duration'),
                    "stops": len(f['flights']) - 1,
                    "category": cat,
                    "skipped_airline": skip,
                    "flight_details": [{
                        "airline": leg['airline'],
                        "flight_number": leg.get('flight_number', 'N/A'),
                        "from": leg['departure_airport']['id'],
                        "to": leg['arrival_airport']['id'],
                        "depart": leg['departure_airport'].get('time', ''),
                        "arrive": leg['arrival_airport'].get('time', ''),
                        "duration_min": leg.get('duration'),
                    } for leg in f['flights']]
                }

                if direction == "outbound":
                    all_results["outbound_flights"].append(flight_info)
                    if not skip:
                        outbound_options.append(flight_info)
                else:
                    all_results["return_flights"].append(flight_info)
                    if not skip:
                        return_options.append(flight_info)

                flight_count += 1

    all_results["search_summary"].append({"search": label, "status": "ok", "flights_found": flight_count})

# Sort by price
outbound_options.sort(key=lambda x: x['price'])
return_options.sort(key=lambda x: x['price'])

# Find best combinations
combos = []
for ob in outbound_options[:15]:  # top 15 cheapest outbound
    for ret in return_options[:15]:  # top 15 cheapest return
        total = ob['price'] + ret['price']
        combos.append({
            "total_price": total,
            "outbound": {
                "price": ob['price'],
                "airlines": ob['airlines'],
                "route": ob['route'],
                "date": ob['search'],
                "duration_min": ob['total_duration_min'],
                "stops": ob['stops'],
                "flight_details": ob['flight_details']
            },
            "return": {
                "price": ret['price'],
                "airlines": ret['airlines'],
                "route": ret['route'],
                "date": ret['search'],
                "duration_min": ret['total_duration_min'],
                "stops": ret['stops'],
                "flight_details": ret['flight_details']
            }
        })

combos.sort(key=lambda x: x['total_price'])
all_results["best_combinations"] = combos[:30]  # top 30

# Print summary
print("=" * 80)
print("SEARCH SUMMARY")
print("=" * 80)
for s in all_results["search_summary"]:
    print(f"  {s['search']}: {s['status']} ({s.get('flights_found', 0)} flights)")

print("\n" + "=" * 80)
print("TOP 10 CHEAPEST OUTBOUND (excluding EVA Air, China Airlines, STARLUX, ZIPAIR)")
print("=" * 80)
for i, f in enumerate(outbound_options[:10]):
    dur_hrs = f['total_duration_min'] / 60 if f['total_duration_min'] else 0
    print(f"  {i+1}. ${f['price']} | {f['airlines']} | {f['route']} | {dur_hrs:.1f}h | {f['stops']} stop(s)")

print("\n" + "=" * 80)
print("TOP 10 CHEAPEST RETURN (excluding EVA Air, China Airlines, STARLUX, ZIPAIR)")
print("=" * 80)
for i, f in enumerate(return_options[:10]):
    dur_hrs = f['total_duration_min'] / 60 if f['total_duration_min'] else 0
    print(f"  {i+1}. ${f['price']} | {f['airlines']} | {f['route']} | {dur_hrs:.1f}h | {f['stops']} stop(s)")

print("\n" + "=" * 80)
print("TOP 15 CHEAPEST ROUND-TRIP COMBINATIONS (outbound + return)")
print("=" * 80)
for i, c in enumerate(combos[:15]):
    ob = c['outbound']
    ret = c['return']
    under = "UNDER $2000!" if c['total_price'] < 2000 else ""
    at = "AT $2000!" if c['total_price'] == 2000 else ""
    marker = under or at or ""
    print(f"\n  #{i+1} TOTAL: ${c['total_price']} {marker}")
    print(f"    OUT: ${ob['price']} | {ob['airlines']} | {ob['route']} | {ob['date']}")
    for fd in ob['flight_details']:
        print(f"         {fd['flight_number']}: {fd['from']}->{fd['to']} dep {fd['depart']} arr {fd['arrive']}")
    print(f"    RET: ${ret['price']} | {ret['airlines']} | {ret['route']} | {ret['date']}")
    for fd in ret['flight_details']:
        print(f"         {fd['flight_number']}: {fd['from']}->{fd['to']} dep {fd['depart']} arr {fd['arrive']}")

# Save to file
with open("D:/claude/flights/apify_final_results.json", "w") as fp:
    json.dump(all_results, fp, indent=2)

print(f"\n\nResults saved to D:/claude/flights/apify_final_results.json")
print(f"Total outbound flights found (after filtering): {len(outbound_options)}")
print(f"Total return flights found (after filtering): {len(return_options)}")
print(f"Total combinations evaluated: {len(combos)}")
