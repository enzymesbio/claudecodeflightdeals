import json, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
with open('D:/claude/flights/scanner_results.json', encoding='utf-8') as f:
    data = json.load(f)
hk = [d for d in data['destinations'] if d['origin_city'] == 'Hong Kong' and d['cabin'] != 'Economy']
hk.sort(key=lambda x: x['price_usd'])
print(f'HK non-economy fares: {len(hk)}')
for d in hk[:20]:
    fam = d['price_usd'] * 2.75
    dates = d.get('dates', '').replace('\u2009', ' ').replace('\u2013', '-')
    print(f"  {d['cabin']:15s} | ${d['price_usd']:>6.0f} (fam ${fam:>7.0f}) | {d['destination']:20s} | {d['classification']:10s} | {dates}")
