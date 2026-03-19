import json

with open("D:/claude/flights/ita_matrix_results.json") as f:
    data = json.load(f)

for s in data["searches"]:
    label = s["search"]["label"]
    flights = s["flights"]
    print(f"\n=== {label} ===")
    print(f"Total results: {s['total_results']}")
    print(f"Flights parsed: {len(flights)}")
    print("Matrix summary:")
    for k, v in s["matrix_summary"].get("matrix", {}).items():
        print(f"  {k}: {v}")
    # Show only valid flights (airline != price)
    valid = [f for f in flights if f["airline"] not in [f["price"], "- -", "", "Stops", "2 stops"]]
    print(f"Valid flights: {len(valid)}")
    # Unique airlines
    airlines = sorted(set(f["airline"] for f in valid))
    print(f"Airlines ({len(airlines)}): {airlines}")
    # Price range
    prices = []
    for f in valid:
        p = f["price"].replace("$", "").replace(",", "")
        try:
            prices.append(float(p))
        except:
            pass
    if prices:
        print(f"Price range: ${min(prices):,.0f} - ${max(prices):,.0f}")
    # Top 5 cheapest
    valid_sorted = sorted(
        valid,
        key=lambda x: float(x["price"].replace("$", "").replace(",", ""))
        if x["price"].startswith("$")
        else 999999,
    )
    print("Top 5 cheapest:")
    for f in valid_sorted[:5]:
        out = f["outbound"]
        print(
            f"  {f['price']} {f['airline']} | {out['route']} "
            f"{out['depart']}->{out['arrive']} ({out['duration']})"
        )
