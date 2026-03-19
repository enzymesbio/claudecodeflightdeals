import sys, json, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('D:/claude/flights/scanner_results.json', encoding='utf-8') as f:
    data = json.load(f)

jkt = [d for d in data['destinations'] if d['origin_city'] == 'Jakarta']
bugs = [d for d in jkt if d.get('classification') == 'BUG_FARE']
cheaps = [d for d in jkt if d.get('classification') == 'CHEAP']

print(f"Jakarta total fares: {len(jkt)}")
print(f"Jakarta BUG fares: {len(bugs)}")
print(f"Jakarta CHEAP fares: {len(cheaps)}")
print()
print("=== BUG FARES ===")
for d in bugs:
    dates = d.get('dates', '').replace('\u2009', ' ').replace('\u2013', '-')
    print(f"  {d['destination']:20s} | {d['cabin']:20s} | ${d['price_usd']:.0f} | {dates}")

print()
print("=== CHEAP FARES ===")
for d in cheaps:
    dates = d.get('dates', '').replace('\u2009', ' ').replace('\u2013', '-')
    print(f"  {d['destination']:20s} | {d['cabin']:20s} | ${d['price_usd']:.0f} | {dates}")
