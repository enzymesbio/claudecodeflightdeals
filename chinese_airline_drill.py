"""Search specifically for Chinese airline routes with 2A+1C pricing."""
import sys
sys.path.insert(0, 'D:/claude/flights')

import json
import time
from datetime import datetime
from search_flights import FlightSearcher

# Chinese airline hub routes
ROUTES = [
    # China Southern hub
    ('CAN', 'LAX', 'China Southern hub'),
    ('CAN', 'SFO', 'China Southern hub'),
    # China Eastern hub
    ('PVG', 'LAX', 'China Eastern hub'),
    ('PVG', 'SFO', 'China Eastern hub'),
    # Sichuan Airlines
    ('CTU', 'LAX', 'Sichuan/China Eastern'),
    ('TFU', 'LAX', 'Sichuan Airlines nonstop'),
    # Air China
    ('PEK', 'LAX', 'Air China hub'),
    ('PEK', 'SFO', 'Air China hub'),
    # XiamenAir
    ('XMN', 'LAX', 'XiamenAir hub'),
    # Hainan Airlines
    ('PEK', 'SEA', 'Hainan Airlines route'),
    # HGH direct
    ('HGH', 'LAX', 'Hangzhou direct'),
]

# Dates that showed results before
DATES = [
    ('2026-05-22', '2026-06-19'),
    ('2026-06-01', '2026-06-29'),
    ('2026-06-15', '2026-07-13'),
    ('2026-09-01', '2026-09-29'),
    ('2026-09-15', '2026-10-13'),
]

def main():
    searcher = FlightSearcher(currency='USD')
    all_results = []
    total = len(ROUTES) * len(DATES)
    n = 0

    print(f"Chinese airline deep drill: {total} searches")
    print("="*80)

    for origin, dest, note in ROUTES:
        print(f"\n--- {origin}-{dest} ({note}) ---")
        for dep, ret in DATES:
            n += 1
            print(f"[{n}/{total}] {origin}-{dest} {dep} RT {ret}...", end=' ', flush=True)

            try:
                # Search with 2 adults + 1 child
                result = searcher.search(
                    origin=origin,
                    destination=dest,
                    date=dep,
                    return_date=ret,
                    adults=2,
                    children=1,
                )

                flights = result.get('flights', [])
                print(f"{len(flights)} flights", flush=True)

                for fl in flights:
                    total_price = fl.get('price', 0)
                    if total_price == 0:
                        continue
                    airline = fl.get('airline', '?')
                    print(f"    ${total_price:>5} | {airline[:40]} | {fl.get('stops','')} stop | {fl.get('duration','')}")
                    all_results.append({
                        'origin': origin,
                        'destination': dest,
                        'route': f"{origin}-{dest}",
                        'note': note,
                        'depart_date': dep,
                        'return_date': ret,
                        'total_3pax': total_price,
                        'pp': round(total_price / 3),
                        'airline': airline,
                        'stops': fl.get('stops', -1),
                        'duration': fl.get('duration', ''),
                        'nonstop': fl.get('stops', -1) == 0,
                        'dep_time': fl.get('dep_time', ''),
                        'arr_time': fl.get('arr_time', ''),
                    })

            except Exception as e:
                print(f"ERROR: {e}", flush=True)

            time.sleep(1.5)

    # Sort and save
    all_results.sort(key=lambda x: x['total_3pax'])

    output = {
        'timestamp': datetime.now().isoformat(),
        'searches': n,
        'total_flights': len(all_results),
        'results': all_results,
    }

    with open('D:/claude/flights/chinese_airline_drill_results.json', 'w') as f:
        json.dump(output, f, indent=2)

    # Print results
    print("\n" + "="*80)
    print(f"RESULTS: {len(all_results)} flights from {n} searches")
    print("="*80)

    if not all_results:
        print("  NO FLIGHTS FOUND from any Chinese airline hub!")
        print("  Google Flights may not return Chinese airline results with 2A+1C search.")
        return

    # Chinese airline filter
    chinese_kws = ['china southern', 'china eastern', 'air china', 'sichuan',
                   'hainan', 'xiamen', 'juneyao', 'spring air', 'shenzhen',
                   'cathay']
    chinese_codes = ['CZ', 'MU', '3U', 'CA', 'HU', 'MF']

    print("\nALL RESULTS (sorted by price):")
    for r in all_results[:30]:
        airline_lower = r['airline'].lower()
        is_cn = any(kw in airline_lower for kw in chinese_kws)
        if not is_cn:
            is_cn = any(r['airline'].startswith(c) and len(r['airline']) > len(c) and r['airline'][len(c)].isdigit() for c in chinese_codes)
        tag = ' [CHINESE]' if is_cn else ''
        ns = ' NONSTOP' if r['nonstop'] else ''
        print(f"  ${r['total_3pax']:>5} total (${r['pp']}/pp) | {r['route']:<8} | {r['airline'][:35]:<35} | {r['stops']}stop{ns}{tag}")

    chinese_only = [r for r in all_results if any(kw in r['airline'].lower() for kw in chinese_kws)]
    if chinese_only:
        print(f"\nCHINESE AIRLINES ONLY ({len(chinese_only)} flights):")
        for r in chinese_only[:15]:
            ns = ' NONSTOP' if r['nonstop'] else ''
            print(f"  ${r['total_3pax']:>5} total (${r['pp']}/pp) | {r['route']:<8} | {r['airline'][:35]:<35} | {r['depart_date']}{ns}")
    else:
        print("\nNO Chinese airline flights found in results!")


if __name__ == '__main__':
    main()
