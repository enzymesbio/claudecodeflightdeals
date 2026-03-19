import json, sys, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

EXCLUDE_DESTINATIONS = ['Honolulu', 'Kauai']
EXCLUDE_AIRLINES = ['ZIPAIR', 'Philippine Airlines', 'Malaysia Airlines', 'Cebu Pacific']
verified_deals = []

# Seoul
with open('D:/claude/flights/deep_verify_seoul_results.json', encoding='utf-8') as f:
    seoul_data = json.load(f)
for r in seoul_data.get('results', []):
    if r.get('booking_url') and r.get('has_booking_page'):
        btext = r.get('booking_text', '')
        airline = ''
        if 'Book with ' in btext:
            airline = btext.split('Book with ')[1].split('Airline')[0].strip()
        booking_price = None
        if btext and 'Book with' in btext:
            price_match = re.search(r'\$([\d,]+)', btext.split('Book with')[1])
            if price_match:
                booking_price = int(price_match.group(1).replace(',', ''))
        cabin_raw = r.get('cabin', 'BIZ')
        cabin = {'PE': 'Premium Eco', 'BIZ': 'Business', 'ECO': 'Economy'}.get(cabin_raw, cabin_raw)
        dest = r['city']
        if dest in EXCLUDE_DESTINATIONS:
            print(f'  SKIP (dest): {dest}')
            continue
        is_excluded = any(excl.lower() in (airline or '').lower() for excl in EXCLUDE_AIRLINES)
        if is_excluded:
            print(f'  SKIP (airline): {dest} {airline}')
            continue
        print(f'  ADD: {dest:15s} | {cabin:15s} | {airline:20s} | ${booking_price}')
        verified_deals.append({'dest': dest, 'cabin': cabin, 'airline': airline, 'price': booking_price})

print(f'\nTotal Seoul deals: {len(verified_deals)}')
