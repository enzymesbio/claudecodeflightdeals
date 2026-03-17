#!/usr/bin/env python3
"""
Massive systematic flight search: Asia -> USA round-trip deals.
Phase 1: Quick scan across origins with a few key dates to LAX.
Phase 2: Deep drill on cheapest origins with ALL date combos and ALL destinations.
Saves results incrementally to massive_search_results.json.
"""

import sys
import os
import json
import time
from datetime import datetime

sys.path.insert(0, 'D:/claude/flights')
from search_flights import FlightSearcher

# --- Configuration ---
SKIP_AIRLINES = {'STARLUX', 'EVA Air', 'China Airlines', 'ZIPAIR'}

ORIGINS = ['ICN', 'NRT', 'HKG', 'PVG', 'CAN', 'KIX']
DESTINATIONS = ['LAX', 'SFO', 'SEA', 'IAH']

# All date combinations
DATE_2WEEK = [
    ('2026-05-01', '2026-05-15'), ('2026-05-05', '2026-05-19'),
    ('2026-05-10', '2026-05-24'), ('2026-05-15', '2026-05-29'),
    ('2026-09-01', '2026-09-15'), ('2026-09-05', '2026-09-19'),
    ('2026-09-10', '2026-09-24'), ('2026-09-15', '2026-09-29'),
]
DATE_3WEEK = [
    ('2026-05-01', '2026-05-22'), ('2026-05-10', '2026-05-31'),
    ('2026-05-15', '2026-06-05'), ('2026-06-01', '2026-06-22'),
    ('2026-09-01', '2026-09-22'), ('2026-09-10', '2026-10-01'),
]
DATE_4WEEK = [
    ('2026-05-01', '2026-05-29'), ('2026-05-10', '2026-06-07'),
    ('2026-05-15', '2026-06-12'), ('2026-05-15', '2026-06-15'),
    ('2026-06-01', '2026-06-29'), ('2026-09-01', '2026-09-29'),
    ('2026-09-10', '2026-10-08'),
]
DATE_5WEEK = [
    ('2026-05-01', '2026-06-05'), ('2026-05-10', '2026-06-14'),
    ('2026-05-15', '2026-06-19'), ('2026-09-01', '2026-10-06'),
]
DATE_6WEEK = [
    ('2026-05-01', '2026-06-12'), ('2026-05-10', '2026-06-21'),
    ('2026-05-15', '2026-06-26'), ('2026-09-01', '2026-10-13'),
]

ALL_DATES = DATE_2WEEK + DATE_3WEEK + DATE_4WEEK + DATE_5WEEK + DATE_6WEEK

# Scan dates: pick a representative from each trip length
SCAN_DATES = [
    ('2026-05-15', '2026-05-29'),   # 2 week
    ('2026-05-15', '2026-06-05'),   # 3 week
    ('2026-09-01', '2026-09-29'),   # 4 week
    ('2026-09-01', '2026-10-06'),   # 5 week
]

RESULTS_FILE = 'D:/claude/flights/massive_search_results.json'

def should_skip(airline_str):
    """Check if any skipped airline name appears in the airline string."""
    for skip in SKIP_AIRLINES:
        if skip.lower() in airline_str.lower():
            return True
    return False

def calc_days(d1, d2):
    """Trip length in days."""
    return (datetime.strptime(d2, '%Y-%m-%d') - datetime.strptime(d1, '%Y-%m-%d')).days

def do_search(searcher, origin, dest, dep, ret, search_count):
    """Execute one search and return filtered flights with metadata."""
    days = calc_days(dep, ret)
    print(f"  [{search_count}] {origin}->{dest}  {dep} to {ret} ({days}d) ...", flush=True)
    try:
        result = searcher.search(origin=origin, destination=dest, date=dep, return_date=ret, adults=1, children=0)
    except Exception as e:
        print(f"    ERROR: {e}", flush=True)
        return []

    if result['status'] != 'success' or not result['flights']:
        print(f"    No flights found.", flush=True)
        return []

    filtered = []
    for f in result['flights']:
        if should_skip(f.get('airline', '')):
            continue
        entry = {
            'origin': origin,
            'destination': dest,
            'depart_date': dep,
            'return_date': ret,
            'trip_days': days,
            'price_pp': f['price'],
            'price_3pax': round(f['price'] * 2.75),
            'airline': f['airline'],
            'stops': f['stops'],
            'duration': f['duration'],
            'dep_time': f['departure']['time'],
            'arr_time': f['arrival']['time'],
            'dep_airport': f['departure'].get('airport', ''),
            'arr_airport': f['arrival'].get('airport', ''),
            'layovers': ', '.join(
                f"{lo['airport']} ({lo['duration']})" for lo in f.get('layovers', [])
            ) if f.get('layovers') else 'Nonstop',
        }
        filtered.append(entry)

    if filtered:
        cheapest = min(f['price_pp'] for f in filtered)
        print(f"    Found {len(filtered)} flights, cheapest ${cheapest}", flush=True)
    else:
        print(f"    All flights filtered out (skipped airlines).", flush=True)
    return filtered

def save_results(all_flights, phase_info):
    """Save current results to JSON."""
    # Sort by price
    all_flights_sorted = sorted(all_flights, key=lambda x: x['price_pp'])
    data = {
        'generated': datetime.utcnow().isoformat() + 'Z',
        'total_flights': len(all_flights_sorted),
        'phase': phase_info,
        'top50': all_flights_sorted[:50],
        'under_2000_3pax': [f for f in all_flights_sorted if f['price_3pax'] < 2000],
        'all_flights': all_flights_sorted,
    }
    with open(RESULTS_FILE, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)
    print(f"  >> Saved {len(all_flights_sorted)} flights to results file.", flush=True)

def main():
    searcher = FlightSearcher(currency='USD')
    all_flights = []
    search_count = 0

    # ==================== PHASE 1: Quick scan ====================
    print("=" * 70)
    print("PHASE 1: Quick scan - all origins to LAX, 4 date combos")
    print("=" * 70)

    origin_cheapest = {}  # origin -> cheapest price seen

    for origin in ORIGINS:
        print(f"\n--- Origin: {origin} ---", flush=True)
        for dep, ret in SCAN_DATES:
            search_count += 1
            flights = do_search(searcher, origin, 'LAX', dep, ret, search_count)
            all_flights.extend(flights)
            if flights:
                cp = min(f['price_pp'] for f in flights)
                if origin not in origin_cheapest or cp < origin_cheapest[origin]:
                    origin_cheapest[origin] = cp
            time.sleep(1.2)

        save_results(all_flights, f"Phase 1 - scanned {origin}")

    # Rank origins
    print("\n" + "=" * 70)
    print("PHASE 1 RESULTS - Origin rankings (cheapest RT price to LAX):")
    for orig, price in sorted(origin_cheapest.items(), key=lambda x: x[1]):
        print(f"  {orig}: ${price}")
    print("=" * 70)

    # Pick top 4 origins for deep drill (or all if fewer)
    ranked_origins = sorted(origin_cheapest.keys(), key=lambda x: origin_cheapest[x])
    deep_origins = ranked_origins[:4]
    remaining_origins = ranked_origins[4:]
    print(f"Deep drill origins: {deep_origins}")
    print(f"Light scan origins: {remaining_origins}")

    # ==================== PHASE 2: Deep drill ====================
    print("\n" + "=" * 70)
    print("PHASE 2: Deep drill - top origins x ALL destinations x ALL dates")
    print("=" * 70)

    # For top origins: all destinations x all dates
    for origin in deep_origins:
        for dest in DESTINATIONS:
            print(f"\n--- {origin} -> {dest} (deep) ---", flush=True)
            for dep, ret in ALL_DATES:
                # Skip if we already searched this exact combo in phase 1
                if dest == 'LAX' and (dep, ret) in SCAN_DATES:
                    continue
                search_count += 1
                flights = do_search(searcher, origin, dest, dep, ret, search_count)
                all_flights.extend(flights)
                time.sleep(1.2)

            save_results(all_flights, f"Phase 2 - deep {origin}->{dest}")

    # ==================== PHASE 3: Remaining origins, lighter scan ====================
    print("\n" + "=" * 70)
    print("PHASE 3: Remaining origins - all destinations, subset of dates")
    print("=" * 70)

    # For remaining origins: all destinations x subset of dates (every other date combo)
    light_dates = ALL_DATES[::2]  # every other date

    for origin in remaining_origins:
        for dest in DESTINATIONS:
            print(f"\n--- {origin} -> {dest} (light) ---", flush=True)
            for dep, ret in light_dates:
                if dest == 'LAX' and (dep, ret) in SCAN_DATES:
                    continue
                search_count += 1
                flights = do_search(searcher, origin, dest, dep, ret, search_count)
                all_flights.extend(flights)
                time.sleep(1.2)

            save_results(all_flights, f"Phase 3 - light {origin}->{dest}")

    # ==================== FINAL REPORT ====================
    save_results(all_flights, "COMPLETE")

    all_sorted = sorted(all_flights, key=lambda x: x['price_pp'])

    print("\n" + "=" * 90)
    print("FINAL RESULTS - TOP 50 CHEAPEST ROUND-TRIP FLIGHTS (per person)")
    print("=" * 90)
    print(f"{'#':>3} {'Price':>7} {'3pax':>7} {'Route':<12} {'Dates':<25} {'Days':>4} {'Airline':<30} {'Stops':>5} {'Duration':<14} {'Layovers'}")
    print("-" * 160)

    for i, f in enumerate(all_sorted[:50], 1):
        route = f"{f['origin']}-{f['destination']}"
        dates = f"{f['depart_date']} -> {f['return_date']}"
        flag = " ***" if f['price_3pax'] < 2000 else ""
        print(f"{i:>3} ${f['price_pp']:>6,} ${f['price_3pax']:>6,} {route:<12} {dates:<25} {f['trip_days']:>4}d {f['airline']:<30} {f['stops']:>5} {f['duration']:<14} {f['layovers'][:50]}{flag}")

    # Under $2000 for 3 pax
    under_2k = [f for f in all_sorted if f['price_3pax'] < 2000]
    print(f"\n{'=' * 90}")
    print(f"DEALS UNDER $2,000 FOR 3 PAX (2 adults + 1 child): {len(under_2k)} found")
    print(f"{'=' * 90}")
    if under_2k:
        for i, f in enumerate(under_2k, 1):
            route = f"{f['origin']}-{f['destination']}"
            dates = f"{f['depart_date']} -> {f['return_date']}"
            print(f"  {i:>3}. ${f['price_pp']:>6,}/pp (${f['price_3pax']:>6,} 3pax) {route} {dates} {f['trip_days']}d | {f['airline']} | {f['stops']} stop(s) | {f['layovers'][:60]}")
    else:
        print("  None found.")

    # Summary stats
    print(f"\nTotal searches performed: {search_count}")
    print(f"Total flights recorded (after airline filter): {len(all_sorted)}")
    if all_sorted:
        print(f"Absolute cheapest per-person: ${all_sorted[0]['price_pp']:,} ({all_sorted[0]['origin']}-{all_sorted[0]['destination']} {all_sorted[0]['airline']})")
        print(f"Cheapest 3-pax estimate: ${all_sorted[0]['price_3pax']:,}")

if __name__ == '__main__':
    main()
