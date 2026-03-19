import json, sys, glob
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

files = glob.glob('D:/claude/flights/tripcom_xhr_data_*.json')
for fpath in sorted(files):
    print(f"\n{'='*60}")
    print(f"File: {fpath}")
    print(f"{'='*60}")
    with open(fpath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Check if this has journeyList (FlightMiddleSearch response)
    jl = data.get('journeyList', [])
    pl = data.get('policyList', [])
    if not jl:
        print("  (No journeyList - skipping)")
        continue

    j0 = jl[0]
    tl = j0.get('transportList', [])
    dur = j0.get('duration', '?')
    print(f"  Journey duration: {dur} min, Segments: {len(tl)}")
    for seg in tl:
        flight = seg.get('flight', {})
        dept = seg.get('departPoint', {})
        arr = seg.get('arrivePoint', {})
        date_info = seg.get('dateInfo', {})
        craft = seg.get('craftInfo', {})
        print(f"    Seg {seg.get('segmentNo','?')}: {flight.get('airlineCode','')} {flight.get('flightNo','')}")
        print(f"      Airline: {flight.get('airlineName','')}")
        print(f"      {dept.get('airportCode','')} ({dept.get('airportName','')}) T{dept.get('terminal','')} -> {arr.get('airportCode','')} ({arr.get('airportName','')}) T{arr.get('terminal','')}")
        print(f"      Depart: {date_info.get('departDate','')} {date_info.get('departTime','')}")
        print(f"      Arrive: {date_info.get('arriveDate','')} {date_info.get('arriveTime','')}")
        print(f"      Duration: {date_info.get('duration','?')} min")
        print(f"      Aircraft: {craft.get('craftName','')} ({craft.get('craftCode','')})")

    print(f"\n  Policies ({len(pl)}):")
    for i, p in enumerate(pl):
        price = p.get('price', {})
        adult = price.get('adult', {})
        grade_list = p.get('gradeInfoList', [])
        cabin = grade_list[0].get('gradeName','') if grade_list else ''
        cabin_code = grade_list[0].get('gradeCode','') if grade_list else ''
        total = price.get('totalPrice', '?')
        fare = adult.get('price', '?')
        tax = adult.get('tax', '?')
        seats = p.get('seatCount', '?')
        print(f"    [{i}] US${total} (fare ${fare} + tax ${tax}) | {cabin} ({cabin_code}) | {seats} seats left")
