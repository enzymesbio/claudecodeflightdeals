"""Deep drill: granular date search on top 5 routes from Jiaxing."""
import sys
sys.path.insert(0, 'D:/claude/flights')

import json
import time
from datetime import datetime, timedelta
from search_flights import FlightSearcher

ROUTES = [
    ('PVG', 'SFO'),
    ('PVG', 'LAX'),
    ('ICN', 'SFO'),
    ('ICN', 'LAX'),
    ('HKG', 'SFO'),
]

DEPART_DATES = [
    '2026-05-01', '2026-05-08', '2026-05-15', '2026-05-22', '2026-05-29',
    '2026-06-01', '2026-06-08', '2026-06-15',
    '2026-09-01', '2026-09-08', '2026-09-15', '2026-09-22',
]

RETURN_WEEKS = [2, 3, 4, 6]

def main():
    searcher = FlightSearcher(currency='USD')
    all_results = []
    searches_done = 0
    total = len(ROUTES) * len(DEPART_DATES) * len(RETURN_WEEKS)

    print(f"Starting deep drill: {total} searches across {len(ROUTES)} routes")

    for origin, dest in ROUTES:
        for dep_date in DEPART_DATES:
            for weeks in RETURN_WEEKS:
                dep_dt = datetime.strptime(dep_date, '%Y-%m-%d')
                ret_dt = dep_dt + timedelta(weeks=weeks)
                ret_date = ret_dt.strftime('%Y-%m-%d')

                searches_done += 1
                print(f"[{searches_done}/{total}] {origin}-{dest} {dep_date} RT {ret_date} ({weeks}w)...", end=' ', flush=True)

                try:
                    result = searcher.search(
                        origin=origin,
                        destination=dest,
                        date=dep_date,
                        return_date=ret_date,
                        adults=2,
                        children=1,
                    )

                    flights = result.get('flights', [])
                    print(f"{len(flights)} flights", flush=True)

                    for fl in flights[:10]:  # top 10 per search
                        price = fl.get('price', 0)
                        if price == 0:
                            continue
                        all_results.append({
                            'origin': origin,
                            'destination': dest,
                            'route': f"{origin}-{dest}",
                            'depart_date': dep_date,
                            'return_date': ret_date,
                            'trip_weeks': weeks,
                            'price_pp': price,
                            'price_3pax': round(price * 2.75),
                            'airline': fl.get('airline', '?'),
                            'stops': fl.get('stops', -1),
                            'duration': fl.get('duration', ''),
                            'nonstop': fl.get('stops', -1) == 0,
                            'dep_time': fl.get('dep_time', ''),
                            'arr_time': fl.get('arr_time', ''),
                        })
                except Exception as e:
                    print(f"ERROR: {e}", flush=True)

                time.sleep(1.5)

                # Save progress every 20 searches
                if searches_done % 20 == 0:
                    _save(all_results, searches_done)

    _save(all_results, searches_done)

    # Print top 20
    all_results.sort(key=lambda x: x['price_pp'])
    print("\n" + "=" * 80)
    print("TOP 20 CHEAPEST DEALS (deep drill)")
    print("=" * 80)
    seen = set()
    rank = 0
    for r in all_results:
        key = (r['route'], r['airline'], r['price_pp'])
        if key in seen:
            continue
        seen.add(key)
        rank += 1
        if rank > 20:
            break
        ns = ' NONSTOP' if r['nonstop'] else ''
        print(f"  {rank:>2}. ${r['price_pp']:>4}/pp (${r['price_3pax']:>5}/3pax) | "
              f"{r['route']:<8} | {r['airline'][:22]:<22} | "
              f"{r['stops']}stop{ns} | {r['depart_date']} RT {r['return_date']}")


def _save(results, n):
    results_sorted = sorted(results, key=lambda x: x['price_pp'])
    output = {
        'timestamp': datetime.now().isoformat(),
        'searches_completed': n,
        'total_flights': len(results_sorted),
        'results': results_sorted,
    }
    with open('D:/claude/flights/deep_drill_results.json', 'w') as f:
        json.dump(output, f, indent=2)
    print(f"  [saved {len(results_sorted)} flights after {n} searches]", flush=True)


if __name__ == '__main__':
    main()
