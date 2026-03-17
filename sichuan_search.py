#!/usr/bin/env python3
"""
Sichuan Airlines Flight Search: CTU/TFU -> LAX/SFO
Searches round-trip and one-way flights, no airline filtering.
"""

import json
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, r'D:\claude\flights')
from search_flights import FlightSearcher, format_results_table

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

searcher = FlightSearcher(currency='USD')

# ---- Define all searches ----
# Round-trip searches: CTU -> LAX with various date ranges (2-6 weeks)
round_trip_searches = [
    # May 2026 departures, 2-week trips
    {"origin": "CTU", "dest": "LAX", "depart": "2026-05-01", "return": "2026-05-15", "label": "CTU-LAX RT May 1-15 (2wk)"},
    {"origin": "CTU", "dest": "LAX", "depart": "2026-05-15", "return": "2026-05-29", "label": "CTU-LAX RT May 15-29 (2wk)"},
    # May departure, 4-week trip
    {"origin": "CTU", "dest": "LAX", "depart": "2026-05-10", "return": "2026-06-07", "label": "CTU-LAX RT May 10-Jun 7 (4wk)"},
    # June 2026, 3-week trip
    {"origin": "CTU", "dest": "LAX", "depart": "2026-06-01", "return": "2026-06-22", "label": "CTU-LAX RT Jun 1-22 (3wk)"},
    # June 2026, 6-week trip
    {"origin": "CTU", "dest": "LAX", "depart": "2026-06-15", "return": "2026-07-27", "label": "CTU-LAX RT Jun 15-Jul 27 (6wk)"},
    # September 2026
    {"origin": "CTU", "dest": "LAX", "depart": "2026-09-01", "return": "2026-09-15", "label": "CTU-LAX RT Sep 1-15 (2wk)"},
    {"origin": "CTU", "dest": "LAX", "depart": "2026-09-10", "return": "2026-10-08", "label": "CTU-LAX RT Sep 10-Oct 8 (4wk)"},
    # CTU -> SFO round trips
    {"origin": "CTU", "dest": "SFO", "depart": "2026-05-15", "return": "2026-05-29", "label": "CTU-SFO RT May 15-29 (2wk)"},
    {"origin": "CTU", "dest": "SFO", "depart": "2026-06-01", "return": "2026-06-22", "label": "CTU-SFO RT Jun 1-22 (3wk)"},
    {"origin": "CTU", "dest": "SFO", "depart": "2026-09-01", "return": "2026-09-15", "label": "CTU-SFO RT Sep 1-15 (2wk)"},
]

# One-way searches
one_way_searches = [
    {"origin": "CTU", "dest": "LAX", "depart": "2026-05-01", "label": "CTU-LAX OW May 1"},
    {"origin": "CTU", "dest": "LAX", "depart": "2026-05-15", "label": "CTU-LAX OW May 15"},
    {"origin": "CTU", "dest": "LAX", "depart": "2026-06-01", "label": "CTU-LAX OW Jun 1"},
    {"origin": "CTU", "dest": "LAX", "depart": "2026-06-15", "label": "CTU-LAX OW Jun 15"},
    {"origin": "CTU", "dest": "LAX", "depart": "2026-09-01", "label": "CTU-LAX OW Sep 1"},
    {"origin": "CTU", "dest": "LAX", "depart": "2026-09-15", "label": "CTU-LAX OW Sep 15"},
    # One-way SFO
    {"origin": "CTU", "dest": "SFO", "depart": "2026-05-15", "label": "CTU-SFO OW May 15"},
    {"origin": "CTU", "dest": "SFO", "depart": "2026-06-01", "label": "CTU-SFO OW Jun 1"},
    {"origin": "CTU", "dest": "SFO", "depart": "2026-09-01", "label": "CTU-SFO OW Sep 1"},
]

all_search_results = []
total_searches = len(round_trip_searches) + len(one_way_searches)
search_num = 0

print(f"=== Sichuan Airlines Flight Search ===", flush=True)
print(f"Total searches to run: {total_searches}", flush=True)
print(f"NO airline filtering - showing ALL airlines (especially Sichuan Airlines)", flush=True)
print("=" * 60, flush=True)

# ---- Run round-trip searches ----
print("\n--- ROUND-TRIP SEARCHES ---", flush=True)
for s in round_trip_searches:
    search_num += 1
    print(f"\n[{search_num}/{total_searches}] {s['label']}...", flush=True)

    result = searcher.search(
        origin=s['origin'],
        destination=s['dest'],
        date=s['depart'],
        return_date=s['return'],
    )

    entry = {
        "label": s['label'],
        "trip_type": "round_trip",
        "origin": s['origin'],
        "destination": s['dest'],
        "depart_date": s['depart'],
        "return_date": s['return'],
        "status": result['status'],
        "results_count": result.get('results_count', 0),
        "flights": [],
        "sichuan_flights": [],
    }

    if result['status'] == 'success' and result.get('flights'):
        for f in result['flights']:
            flight_entry = {
                "price": f['price'],
                "airline": f['airline'],
                "stops": f['stops'],
                "duration": f['duration'],
                "dep_time": f['departure']['time'],
                "dep_airport": f['departure']['airport'],
                "arr_time": f['arrival']['time'],
                "arr_airport": f['arrival']['airport'],
                "layovers": f.get('layovers', []),
            }
            entry["flights"].append(flight_entry)
            # Flag Sichuan Airlines flights
            if 'sichuan' in f['airline'].lower():
                entry["sichuan_flights"].append(flight_entry)

        # Print summary
        cheapest = min(f['price'] for f in result['flights'])
        sichuan_count = len(entry["sichuan_flights"])
        print(f"  Found {len(result['flights'])} flights, cheapest ${cheapest:,}", flush=True)
        if sichuan_count:
            sichuan_cheapest = min(f['price'] for f in entry["sichuan_flights"])
            print(f"  ** {sichuan_count} Sichuan Airlines flight(s), cheapest ${sichuan_cheapest:,} **", flush=True)
        else:
            print(f"  (No Sichuan Airlines flights in results)", flush=True)

        # Print table
        print(format_results_table(result), flush=True)
    else:
        print(f"  No flights found or error: {result.get('error', 'unknown')}", flush=True)

    all_search_results.append(entry)
    time.sleep(3)  # Rate limiting

# ---- Run one-way searches ----
print("\n\n--- ONE-WAY SEARCHES ---", flush=True)
for s in one_way_searches:
    search_num += 1
    print(f"\n[{search_num}/{total_searches}] {s['label']}...", flush=True)

    result = searcher.search(
        origin=s['origin'],
        destination=s['dest'],
        date=s['depart'],
    )

    entry = {
        "label": s['label'],
        "trip_type": "one_way",
        "origin": s['origin'],
        "destination": s['dest'],
        "depart_date": s['depart'],
        "return_date": None,
        "status": result['status'],
        "results_count": result.get('results_count', 0),
        "flights": [],
        "sichuan_flights": [],
    }

    if result['status'] == 'success' and result.get('flights'):
        for f in result['flights']:
            flight_entry = {
                "price": f['price'],
                "airline": f['airline'],
                "stops": f['stops'],
                "duration": f['duration'],
                "dep_time": f['departure']['time'],
                "dep_airport": f['departure']['airport'],
                "arr_time": f['arrival']['time'],
                "arr_airport": f['arrival']['airport'],
                "layovers": f.get('layovers', []),
            }
            entry["flights"].append(flight_entry)
            if 'sichuan' in f['airline'].lower():
                entry["sichuan_flights"].append(flight_entry)

        cheapest = min(f['price'] for f in result['flights'])
        sichuan_count = len(entry["sichuan_flights"])
        print(f"  Found {len(result['flights'])} flights, cheapest ${cheapest:,}", flush=True)
        if sichuan_count:
            sichuan_cheapest = min(f['price'] for f in entry["sichuan_flights"])
            print(f"  ** {sichuan_count} Sichuan Airlines flight(s), cheapest ${sichuan_cheapest:,} **", flush=True)
        else:
            print(f"  (No Sichuan Airlines flights in results)", flush=True)

        print(format_results_table(result), flush=True)
    else:
        print(f"  No flights found or error: {result.get('error', 'unknown')}", flush=True)

    all_search_results.append(entry)
    time.sleep(3)

# ---- Build summary ----
print("\n\n" + "=" * 80, flush=True)
print("SUMMARY", flush=True)
print("=" * 80, flush=True)

all_sichuan = []
all_flights_flat = []
for entry in all_search_results:
    for f in entry["flights"]:
        f_full = {**f, "search_label": entry["label"], "trip_type": entry["trip_type"]}
        all_flights_flat.append(f_full)
    for f in entry["sichuan_flights"]:
        f_full = {**f, "search_label": entry["label"], "trip_type": entry["trip_type"]}
        all_sichuan.append(f_full)

# Sichuan Airlines summary
if all_sichuan:
    print(f"\nSICHUAN AIRLINES FLIGHTS FOUND: {len(all_sichuan)}", flush=True)
    print("-" * 60, flush=True)
    for f in sorted(all_sichuan, key=lambda x: x['price']):
        print(f"  ${f['price']:>6,}  {f['trip_type']:>10}  {f['search_label']}", flush=True)
        print(f"          {f['stops']} stop(s), {f['duration']}, {f['dep_time']} -> {f['arr_time']}", flush=True)
else:
    print("\nNo Sichuan Airlines flights found in any search.", flush=True)
    print("(Sichuan Airlines may not appear on Google Flights for these routes/dates,", flush=True)
    print(" or results may be codeshare under a different airline name.)", flush=True)

# Overall cheapest flights
if all_flights_flat:
    print(f"\nALL CHEAPEST FLIGHTS (top 15):", flush=True)
    print("-" * 60, flush=True)
    for f in sorted(all_flights_flat, key=lambda x: x['price'])[:15]:
        print(f"  ${f['price']:>6,}  {f['airline']:<35}  {f['trip_type']:>10}  {f['search_label']}", flush=True)

# Save results
output = {
    "search_timestamp": datetime.now(timezone.utc).isoformat(),
    "total_searches": total_searches,
    "searches": all_search_results,
    "sichuan_flights_summary": all_sichuan,
    "all_flights_count": len(all_flights_flat),
    "sichuan_flights_count": len(all_sichuan),
}

output_path = r'D:\claude\flights\sichuan_results.json'
with open(output_path, 'w', encoding='utf-8') as fp:
    json.dump(output, fp, indent=2, ensure_ascii=False)
print(f"\nResults saved to: {output_path}", flush=True)
