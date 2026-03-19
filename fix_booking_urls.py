"""Replace the hardcoded CONFIRMED BOOKABLE section with dynamic loading from verify JSONs."""
import json, re

with open('D:/claude/flights/generate_verification_page.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the section to replace
start_marker = '# --- VERIFIED BOOKABLE DEALS (from deep verification) ---'
end_marker = '</div>"""'  # The closing of the confirmed bookable section

start_idx = content.index(start_marker)

# Find the specific end: the closing </div>""" after the "Best family deals" line
# We need to find the end_marker that comes after "legitimate low-cost carrier fares"
search_from = start_idx
marker_text = 'not pricing errors.'
marker_idx = content.index(marker_text, search_from)
# Find the next """  after that
end_idx = content.index('"""', marker_idx) + 3

old_section = content[start_idx:end_idx]
print(f"Found section: {len(old_section)} chars, lines {content[:start_idx].count(chr(10))+1} to {content[:end_idx].count(chr(10))+1}")

new_section = '''# --- VERIFIED BOOKABLE DEALS (from deep verification JSON files) ---
# Load real booking URLs from deep verify results
verified_deals = []

# Tokyo results
try:
    with open('D:/claude/flights/deep_verify_tokyo_results.json', encoding='utf-8') as f:
        tokyo_data = json.load(f)
    for r in tokyo_data.get('results', []):
        if r.get('booking_url') and r.get('status') in ('BOOKABLE', 'BOOKABLE_NO_PRICE'):
            btext = r.get('booking_section_text', '')
            airline = ''
            if 'Book with ' in btext:
                airline = btext.split('Book with ')[1].split('Airline')[0].strip()
            cabin = 'Business' if 'Business' in r.get('route', '') else 'Economy'
            if 'Economy' in r.get('route', ''):
                cabin = 'Economy'
            booking_price = None
            if btext and 'Book with' in btext:
                price_match = re.search(r'\\$([\d,]+)', btext.split('Book with')[1])
                if price_match:
                    booking_price = int(price_match.group(1).replace(',', ''))
            verified_deals.append({
                'origin': 'Tokyo',
                'dest': r['city'],
                'cabin': cabin,
                'price': booking_price or r.get('search_price', 0),
                'airline': airline or 'Unknown',
                'booking_url': r['booking_url'],
                'has_booking': r.get('has_book_with_links', False),
            })
except Exception as e:
    print(f"Warning: could not load Tokyo verify results: {e}")

# Seoul results
try:
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
                price_match = re.search(r'\\$([\d,]+)', btext.split('Book with')[1])
                if price_match:
                    booking_price = int(price_match.group(1).replace(',', ''))
            cabin_raw = r.get('cabin', 'BIZ')
            cabin = {'PE': 'Premium Eco', 'BIZ': 'Business', 'ECO': 'Economy'}.get(cabin_raw, cabin_raw)
            verified_deals.append({
                'origin': 'Seoul',
                'dest': r['city'],
                'cabin': cabin,
                'price': booking_price or r.get('search_price', 0),
                'airline': airline or 'Unknown',
                'booking_url': r['booking_url'],
                'has_booking': 'Book with' in btext,
            })
except Exception as e:
    print(f"Warning: could not load Seoul verify results: {e}")

# Sort by price
verified_deals.sort(key=lambda x: x['price'])

html += """
<div class="section" style="border:2px solid #276749;background:#f0fff4">
<div class="section-header" style="background:#c6f6d5;border-bottom:2px solid #9ae6b4">
<h2 style="color:#276749">CONFIRMED BOOKABLE \\u2014 Deep Verified</h2>
<span style="color:#276749;font-size:13px">Clicked through Google Flights booking page \\u2014 real "Book with" links extracted</span>
</div>
<table class="fare-table">
<tr><th>Route</th><th>Cabin</th><th>Price</th><th>Family (2A+1C)</th><th>Book With</th><th>Verified Booking Link</th></tr>
"""

for deal in verified_deals:
    fam = deal['price'] * 2.75
    bg = ' style="background:#f0fff4"' if fam <= 3000 else ''
    html += f"""<tr{bg}>
<td><strong>{deal['origin']} &rarr; {deal['dest']}</strong></td><td>{deal['cabin']}</td>
<td class="price" style="color:#276749">${deal['price']:,}</td><td>${fam:,.0f}</td>
<td>{deal['airline']}</td>
<td><a href="{deal['booking_url']}" target="_blank" rel="noopener" class="verify-btn" style="background:#276749;color:#fff;border:none">Google Booking Page</a></td>
</tr>
"""

html += """</table>
<div style="padding:14px 20px;color:#276749;font-size:14px;border-top:1px solid #9ae6b4;background:#f0fff4">
<strong>All "Google Booking Page" links go to the real Google Flights booking page with live prices.</strong> These URLs were extracted by clicking through the full Explore &rarr; View Flights &rarr; Select Flights &rarr; Booking flow. Links may expire after ~24 hours.
</div>
</div>\\n"""'''

content = content[:start_idx] + new_section + content[end_idx:]

with open('D:/claude/flights/generate_verification_page.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done! Replaced hardcoded section with dynamic loading from verify JSONs")
