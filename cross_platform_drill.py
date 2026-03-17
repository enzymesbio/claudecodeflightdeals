"""Cross-platform flight price comparison and drill-down.
Aggregates data from Google Flights, ITA Matrix, Ctrip, and produces
a unified best-price comparison."""

import json
from collections import defaultdict

CNY_TO_USD = 7.27

def load_google_flights():
    """Load Google Flights massive search results."""
    with open('D:/claude/flights/massive_search_results.json') as f:
        data = json.load(f)

    deals = []
    for fl in data.get('top50', []):
        deals.append({
            'source': 'Google Flights',
            'origin': fl['origin'],
            'destination': fl['destination'],
            'route': fl['origin'] + '-' + fl['destination'],
            'price_pp': fl['price_pp'],
            'price_3pax': fl['price_3pax'],
            'airline': fl['airline'],
            'stops': fl['stops'],
            'duration': fl.get('duration', ''),
            'depart_date': fl['depart_date'],
            'return_date': fl['return_date'],
            'dep_time': fl.get('dep_time', ''),
            'arr_time': fl.get('arr_time', ''),
            'nonstop': fl['stops'] == 0,
            'currency': 'USD',
        })

    # Also include all under-$2000 flights
    for fl in data.get('under_2000_3pax', []):
        if fl not in data.get('top50', []):
            deals.append({
                'source': 'Google Flights',
                'origin': fl['origin'],
                'destination': fl['destination'],
                'route': fl['origin'] + '-' + fl['destination'],
                'price_pp': fl['price_pp'],
                'price_3pax': fl['price_3pax'],
                'airline': fl['airline'],
                'stops': fl['stops'],
                'duration': fl.get('duration', ''),
                'depart_date': fl['depart_date'],
                'return_date': fl['return_date'],
                'dep_time': fl.get('dep_time', ''),
                'arr_time': fl.get('arr_time', ''),
                'nonstop': fl['stops'] == 0,
                'currency': 'USD',
            })

    return deals


def load_ita_matrix():
    """Load ITA Matrix results from both files."""
    deals = []

    for fname in ['ita_matrix_results.json', 'ita_matrix_chinese_results.json']:
        try:
            with open('D:/claude/flights/' + fname) as f:
                data = json.load(f)
        except FileNotFoundError:
            continue

        for search in data.get('searches', []):
            if not search.get('success'):
                continue
            s = search['search']
            origin = s.get('origin', '')
            dest = s.get('destination', '')
            depart = s.get('depart', '')
            ret = s.get('return', '')

            for fl in search.get('flights', []):
                price_str = fl.get('price', '$0')
                # Skip header rows and garbled entries
                if not price_str or not price_str.startswith('$'):
                    continue
                try:
                    price = int(price_str.replace('$', '').replace(',', ''))
                except ValueError:
                    continue
                if price == 0:
                    continue
                # Skip entries where airline field is just the price repeated
                airline = fl.get('airline', '?')
                if airline.startswith('$'):
                    continue

                deals.append({
                    'source': 'ITA Matrix',
                    'origin': origin,
                    'destination': dest,
                    'route': origin + '-' + dest,
                    'price_pp': price,
                    'price_3pax': round(price * 2.75),
                    'airline': fl.get('airline', '?'),
                    'stops': -1,  # ITA doesn't always give stops
                    'duration': '',
                    'depart_date': depart,
                    'return_date': ret,
                    'dep_time': '',
                    'arr_time': '',
                    'nonstop': False,
                    'is_chinese_airline': fl.get('is_chinese_airline', False),
                    'currency': 'USD',
                })

    return deals


def load_ctrip():
    """Load Ctrip results, converting CNY to USD.
    IMPORTANT: Ctrip prices are ONE-WAY. We double them for RT comparison."""
    with open('D:/claude/flights/ctrip_results.json') as f:
        data = json.load(f)

    deals = []
    for fl in data.get('results', []):
        price_cny_ow = fl['price']
        # Double for round-trip estimate
        price_cny_rt = price_cny_ow * 2
        price_usd_rt = round(price_cny_rt / CNY_TO_USD)
        price_usd_ow = round(price_cny_ow / CNY_TO_USD)

        route = fl.get('search_route', '')
        parts = route.split('-')
        origin = parts[0] if len(parts) >= 2 else ''
        dest = parts[1] if len(parts) >= 2 else ''

        stops = fl.get('stops', '?')
        try:
            stops = int(stops)
        except (ValueError, TypeError):
            stops = -1

        deals.append({
            'source': 'Ctrip (OW x2)',
            'origin': origin,
            'destination': dest,
            'route': route,
            'price_pp': price_usd_rt,  # RT estimate
            'price_pp_ow': price_usd_ow,  # original one-way
            'price_cny_ow': price_cny_ow,
            'price_cny_rt': price_cny_rt,
            'price_3pax': round(price_usd_rt * 2.75),
            'airline': fl.get('flight_number', '?') or '?',
            'stops': stops,
            'duration': fl.get('duration', '') or '',
            'depart_date': fl.get('search_date', ''),
            'return_date': '',
            'dep_time': fl.get('departure_time', ''),
            'arr_time': fl.get('arrival_time', ''),
            'nonstop': stops == 0,
            'currency': 'CNY->USD (OW x2)',
        })

    return deals


def load_sichuan_direct():
    """Load Sichuan Airlines direct results."""
    try:
        with open('D:/claude/flights/sichuan_direct_results.json') as f:
            data = json.load(f)
    except FileNotFoundError:
        return []

    deals = []
    for fl in data.get('results', []):
        price = fl.get('price_usd', 0) or fl.get('price', 0)
        if price == 0:
            continue
        deals.append({
            'source': 'Sichuan Direct',
            'origin': 'TFU',
            'destination': 'LAX',
            'route': 'TFU-LAX',
            'price_pp': price,
            'price_3pax': round(price * 2.75),
            'airline': 'Sichuan Airlines 3U',
            'stops': 0,
            'duration': fl.get('duration', ''),
            'depart_date': fl.get('date', ''),
            'return_date': fl.get('return_date', ''),
            'dep_time': fl.get('dep_time', ''),
            'arr_time': fl.get('arr_time', ''),
            'nonstop': True,
            'currency': 'USD',
        })

    return deals


def main():
    print("=" * 80)
    print("CROSS-PLATFORM FLIGHT PRICE COMPARISON")
    print("Family of 3: 2 adults + 1 child (price x 2.75)")
    print("=" * 80)

    # Load all sources
    gf_deals = load_google_flights()
    ita_deals = load_ita_matrix()
    ctrip_deals = load_ctrip()
    sc_deals = load_sichuan_direct()

    all_deals = gf_deals + ita_deals + ctrip_deals + sc_deals

    print(f"\nData loaded:")
    print(f"  Google Flights: {len(gf_deals)} deals")
    print(f"  ITA Matrix:     {len(ita_deals)} deals")
    print(f"  Ctrip:          {len(ctrip_deals)} deals")
    print(f"  Sichuan Direct: {len(sc_deals)} deals")
    print(f"  TOTAL:          {len(all_deals)} deals")

    # === BEST PRICE PER ROUTE PER PLATFORM ===
    print("\n" + "=" * 80)
    print("BEST PRICE PER ROUTE BY PLATFORM (per person, round-trip)")
    print("=" * 80)

    routes = sorted(set(d['route'] for d in all_deals))
    sources = ['Google Flights', 'ITA Matrix', 'Ctrip', 'Sichuan Direct']

    # Header
    print(f"\n{'Route':<12}", end='')
    for s in sources:
        print(f"{'  ' + s:<18}", end='')
    print(f"  {'BEST':>10}")
    print("-" * 90)

    best_by_route = {}
    for route in routes:
        route_deals = [d for d in all_deals if d['route'] == route]
        print(f"{route:<12}", end='')

        best_price = 99999
        best_source = ''

        for src in sources:
            src_deals = [d for d in route_deals if d['source'] == src]
            if src_deals:
                cheapest = min(src_deals, key=lambda x: x['price_pp'])
                price = cheapest['price_pp']
                print(f"  ${price:<16}", end='')
                if price < best_price:
                    best_price = price
                    best_source = src
            else:
                print(f"  {'---':<16}", end='')

        if best_price < 99999:
            print(f"  ${best_price} ({best_source})")
            best_by_route[route] = {'price': best_price, 'source': best_source}
        else:
            print()

    # === TOP 20 CHEAPEST DEALS ACROSS ALL PLATFORMS ===
    print("\n" + "=" * 80)
    print("TOP 20 CHEAPEST DEALS ACROSS ALL PLATFORMS")
    print("=" * 80)

    all_sorted = sorted(all_deals, key=lambda x: x['price_pp'])
    seen = set()
    rank = 0

    for d in all_sorted:
        key = (d['route'], d['airline'], d['price_pp'])
        if key in seen:
            continue
        seen.add(key)
        rank += 1
        if rank > 20:
            break

        three_pax = round(d['price_pp'] * 2.75)
        stops_str = str(d['stops']) + 'stop' if d['stops'] >= 0 else '?stop'
        nonstop = ' NONSTOP' if d['nonstop'] else ''

        print(f"  {rank:>2}. ${d['price_pp']:>4}/pp (${three_pax:>5}/3pax) | "
              f"{d['route']:<8} | {d['airline'][:20]:<20} | "
              f"{stops_str}{nonstop} | {d['depart_date']} | [{d['source']}]")

    # === CHINESE AIRLINE SPOTLIGHT ===
    print("\n" + "=" * 80)
    print("CHINESE AIRLINE DEALS (all platforms)")
    print("=" * 80)

    # Use airline names (not IATA codes) to avoid false matches like "Air CAnada"
    chinese_kws = ['china southern', 'china eastern', 'air china', 'sichuan',
                   'hainan', 'xiamen', 'juneyao', 'spring air', 'shenzhen']
    # IATA codes must match as standalone flight number prefixes
    chinese_codes = ['CZ', 'MU', '3U', 'CA', 'HU', 'MF']

    chinese_deals = []
    for d in all_deals:
        airline_lower = d['airline'].lower()
        is_chinese = False
        for kw in chinese_kws:
            if kw in airline_lower:
                is_chinese = True
                break
        if not is_chinese:
            # Check if flight number starts with a Chinese IATA code
            for code in chinese_codes:
                if d['airline'].startswith(code) and len(d['airline']) > len(code) and d['airline'][len(code):len(code)+1].isdigit():
                    is_chinese = True
                    break
        if d.get('is_chinese_airline'):
            is_chinese = True
        if is_chinese:
            chinese_deals.append(d)

    chinese_sorted = sorted(chinese_deals, key=lambda x: x['price_pp'])
    seen = set()
    for d in chinese_sorted[:15]:
        key = (d['route'], d['airline'], d['price_pp'])
        if key in seen:
            continue
        seen.add(key)
        three_pax = round(d['price_pp'] * 2.75)
        print(f"  ${d['price_pp']:>4}/pp (${three_pax:>5}/3pax) | "
              f"{d['route']:<8} | {d['airline'][:25]:<25} | "
              f"{d['depart_date']} | [{d['source']}]")

    # === SEASONAL COMPARISON ===
    print("\n" + "=" * 80)
    print("SEASONAL COMPARISON: MAY-JUNE vs SEPTEMBER")
    print("=" * 80)

    may_jun = [d for d in all_deals if d['depart_date'] and
               (d['depart_date'].startswith('2026-05') or
                d['depart_date'].startswith('2026-06') or
                d['depart_date'].startswith('5/') or
                d['depart_date'].startswith('6/'))]
    sep = [d for d in all_deals if d['depart_date'] and
           (d['depart_date'].startswith('2026-09') or
            d['depart_date'].startswith('9/'))]

    if may_jun:
        best_mj = min(may_jun, key=lambda x: x['price_pp'])
        print(f"\n  MAY-JUNE best:  ${best_mj['price_pp']}/pp (${round(best_mj['price_pp']*2.75)}/3pax)")
        print(f"    {best_mj['route']} | {best_mj['airline']} | {best_mj['depart_date']} | [{best_mj['source']}]")

    if sep:
        best_sep = min(sep, key=lambda x: x['price_pp'])
        print(f"\n  SEPTEMBER best: ${best_sep['price_pp']}/pp (${round(best_sep['price_pp']*2.75)}/3pax)")
        print(f"    {best_sep['route']} | {best_sep['airline']} | {best_sep['depart_date']} | [{best_sep['source']}]")

    if may_jun and sep:
        savings = round((1 - min(d['price_pp'] for d in sep) / min(d['price_pp'] for d in may_jun)) * 100)
        print(f"\n  September savings: ~{savings}% cheaper")

    # === CONVENIENCE FROM JIAXING ===
    print("\n" + "=" * 80)
    print("TRUE COST FROM JIAXING (with positioning)")
    print("=" * 80)

    positioning = {
        'PVG': ('1.5h train, ~$15', 15),
        'HGH': ('1h train, ~$10', 10),
        'CAN': ('2h flight, ~$80', 80),
        'CTU': ('3h flight, ~$100', 100),
        'TFU': ('3h flight, ~$100', 100),
        'PEK': ('2h flight, ~$80', 80),
        'ICN': ('2h flight, ~$150', 150),
        'NRT': ('2.5h flight, ~$150', 150),
        'XMN': ('1.5h flight, ~$60', 60),
        'HKG': ('2h flight, ~$120', 120),
        'KIX': ('2.5h flight, ~$150', 150),
    }

    print(f"\n  {'Route':<12} {'Best/pp':<10} {'+ Position':<12} {'True/pp':<10} {'True/3pax':<12} {'Source':<16} {'Airline'}")
    print("  " + "-" * 90)

    true_costs = []
    for route in routes:
        route_deals = [d for d in all_deals if d['route'] == route]
        if not route_deals:
            continue
        cheapest = min(route_deals, key=lambda x: x['price_pp'])
        origin = cheapest['origin']
        pos_info = positioning.get(origin, ('?', 0))
        pos_cost = pos_info[1]
        true_pp = cheapest['price_pp'] + pos_cost
        true_3pax = round(true_pp * 2.75)

        true_costs.append({
            'route': route,
            'true_pp': true_pp,
            'true_3pax': true_3pax,
            'base_pp': cheapest['price_pp'],
            'positioning': pos_info[0],
            'source': cheapest['source'],
            'airline': cheapest['airline'],
            'depart': cheapest['depart_date'],
        })

        print(f"  {route:<12} ${cheapest['price_pp']:<9} +${pos_cost:<10} ${true_pp:<9} ${true_3pax:<11} {cheapest['source']:<16} {cheapest['airline'][:20]}")

    true_costs.sort(key=lambda x: x['true_pp'])

    print(f"\n  BEST TRUE COST FROM JIAXING:")
    for i, tc in enumerate(true_costs[:5], 1):
        budget_ok = "UNDER $2000!" if tc['true_3pax'] < 2000 else "over budget"
        print(f"    {i}. {tc['route']}: ${tc['true_pp']}/pp (${tc['true_3pax']}/3pax) [{tc['source']}] {tc['airline'][:20]} - {budget_ok}")

    # === FINAL VERDICT ===
    print("\n" + "=" * 80)
    print("FINAL VERDICT - RECOMMENDED BOOKING OPTIONS")
    print("=" * 80)

    under_budget = [tc for tc in true_costs if tc['true_3pax'] < 2000]
    if under_budget:
        print(f"\n  OPTIONS UNDER $2,000 FOR FAMILY OF 3:")
        for tc in under_budget:
            print(f"    >>> {tc['route']}: ${tc['true_3pax']}/3pax via {tc['airline'][:25]} [{tc['source']}] {tc['depart']}")

    print(f"\n  ALL TOP OPTIONS:")
    for i, tc in enumerate(true_costs[:8], 1):
        print(f"    {i}. {tc['route']}: ${tc['true_3pax']}/3pax | {tc['airline'][:25]} | {tc['positioning']} to airport | {tc['depart']} | [{tc['source']}]")

    # Save unified data for HTML report
    output = {
        'generated': str(__import__('datetime').datetime.now().isoformat()),
        'sources': {
            'google_flights': len(gf_deals),
            'ita_matrix': len(ita_deals),
            'ctrip': len(ctrip_deals),
            'sichuan_direct': len(sc_deals),
        },
        'total_deals': len(all_deals),
        'top20': [],
        'best_by_route': best_by_route,
        'true_costs_from_jiaxing': true_costs[:10],
        'under_budget': under_budget,
    }

    seen = set()
    rank = 0
    for d in all_sorted:
        key = (d['route'], d['airline'], d['price_pp'])
        if key in seen:
            continue
        seen.add(key)
        rank += 1
        if rank > 20:
            break
        output['top20'].append({
            'rank': rank,
            'route': d['route'],
            'airline': d['airline'],
            'price_pp': d['price_pp'],
            'price_3pax': round(d['price_pp'] * 2.75),
            'stops': d['stops'],
            'nonstop': d['nonstop'],
            'depart_date': d['depart_date'],
            'source': d['source'],
        })

    with open('D:/claude/flights/cross_platform_comparison.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n\nSaved cross-platform comparison to cross_platform_comparison.json")


if __name__ == '__main__':
    main()
