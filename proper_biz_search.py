"""Build PROPER TFS URLs with business class cabin encoded in protobuf, like user's URL."""
import sys, os, base64
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/claude/flights')

import re
import time

# First, decode the user's URL to understand the structure
user_tfs = "CBwQAhoeEgoyMDI2LTA1LTA4agcIARIDQ0dLcgcIARIDTEFYGh4SCjIwMjYtMDYtMTVqBwgBEgNMQVhyBwgBEgNDR0tAAUgDcAGCAQsI____________AZgBAQ"

# Add padding
padded = user_tfs + "=" * (4 - len(user_tfs) % 4) if len(user_tfs) % 4 else user_tfs
decoded = base64.urlsafe_b64decode(padded)
print("User's TFS decoded bytes:")
print(" ".join(f"{b:02x}" for b in decoded))
print()

# Parse protobuf manually
def parse_protobuf(data, indent=0):
    i = 0
    prefix = "  " * indent
    while i < len(data):
        # Read tag
        tag_byte = data[i]
        field_num = tag_byte >> 3
        wire_type = tag_byte & 0x07
        i += 1

        # Handle multi-byte tags
        if tag_byte & 0x80:
            tag_val = tag_byte & 0x7f
            shift = 7
            while i < len(data) and data[i] & 0x80:
                tag_val |= (data[i] & 0x7f) << shift
                shift += 7
                i += 1
            if i < len(data):
                tag_val |= (data[i] & 0x7f) << shift
                i += 1
            field_num = tag_val >> 3
            wire_type = tag_val & 0x07

        if wire_type == 0:  # varint
            val = 0
            shift = 0
            while i < len(data) and data[i] & 0x80:
                val |= (data[i] & 0x7f) << shift
                shift += 7
                i += 1
            if i < len(data):
                val |= (data[i] & 0x7f) << shift
                i += 1
            print(f"{prefix}field {field_num} (varint): {val}")
        elif wire_type == 2:  # length-delimited
            length = 0
            shift = 0
            while i < len(data) and data[i] & 0x80:
                length |= (data[i] & 0x7f) << shift
                shift += 7
                i += 1
            if i < len(data):
                length |= (data[i] & 0x7f) << shift
                i += 1
            content = data[i:i+length]
            i += length
            # Try to interpret as string
            try:
                s = content.decode('utf-8')
                if all(32 <= ord(c) < 127 for c in s):
                    print(f"{prefix}field {field_num} (string): \"{s}\"")
                else:
                    print(f"{prefix}field {field_num} (bytes, len={length}): {' '.join(f'{b:02x}' for b in content)}")
                    print(f"{prefix}  sub-message:")
                    parse_protobuf(content, indent+2)
            except:
                print(f"{prefix}field {field_num} (bytes, len={length}): {' '.join(f'{b:02x}' for b in content)}")
                print(f"{prefix}  sub-message:")
                parse_protobuf(content, indent+2)
        else:
            print(f"{prefix}field {field_num} (wire_type={wire_type}): ???")
            break

print("Parsed protobuf structure:")
parse_protobuf(decoded)


# Now build proper TFS with business class
def encode_varint(value):
    result = b''
    while value > 0x7f:
        result += bytes([(value & 0x7f) | 0x80])
        value >>= 7
    result += bytes([value])
    return result

def field_varint(num, val):
    return encode_varint((num << 3) | 0) + encode_varint(val)

def field_bytes(num, data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return encode_varint((num << 3) | 2) + encode_varint(len(data)) + data


def build_biz_tfs(legs, adults=1, children=0, cabin=3):
    """Build TFS matching user's URL format. cabin: 1=eco, 2=prem eco, 3=biz, 4=first"""
    legs_data = b''
    for leg in legs:
        origin_msg = field_varint(1, 1) + field_bytes(2, leg['origin'])
        dest_msg = field_varint(1, 1) + field_bytes(2, leg['destination'])
        leg_msg = (
            field_bytes(2, leg['date']) +
            field_bytes(13, origin_msg) +
            field_bytes(14, dest_msg)
        )
        legs_data += field_bytes(3, leg_msg)

    trip_type = 2 if len(legs) > 1 else 1

    # Passenger config (field 16) - matching user's format
    pax_config = (
        b'\x08' + b'\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01'  # field 1, varint -1
    )
    if children > 0:
        pax_config += field_varint(8, 1) + field_varint(9, 1)
    else:
        pax_config += field_varint(8, 1) + field_varint(9, 1)

    msg = (
        field_varint(1, 28) +
        field_varint(2, trip_type) +
        legs_data +
        field_varint(8, adults) +       # adults at top level
        field_varint(9, cabin) +         # CABIN CLASS: 3=business
        field_varint(14, 1) +
        field_bytes(16, pax_config) +
        field_varint(19, 1)
    )

    return base64.urlsafe_b64encode(msg).rstrip(b'=').decode('ascii')


# Build URLs
print("\n" + "=" * 70)
print("BUILDING PROPER BUSINESS CLASS TFS URLS")
print("=" * 70)

searches = [
    # RT
    {
        'label': 'CGK-LAX BIZ RT May8-Jun15',
        'legs': [
            {'origin': 'CGK', 'destination': 'LAX', 'date': '2026-05-08'},
            {'origin': 'LAX', 'destination': 'CGK', 'date': '2026-06-15'},
        ],
    },
    # OW
    {
        'label': 'CGK-LAX BIZ OW May4',
        'legs': [{'origin': 'CGK', 'destination': 'LAX', 'date': '2026-05-04'}],
    },
    {
        'label': 'CGK-LAX BIZ OW May8',
        'legs': [{'origin': 'CGK', 'destination': 'LAX', 'date': '2026-05-08'}],
    },
    {
        'label': 'CGK-LHR BIZ OW May4',
        'legs': [{'origin': 'CGK', 'destination': 'LHR', 'date': '2026-05-04'}],
    },
    # RT Apr 21
    {
        'label': 'CGK-LAX BIZ RT Apr21-May25',
        'legs': [
            {'origin': 'CGK', 'destination': 'LAX', 'date': '2026-04-21'},
            {'origin': 'LAX', 'destination': 'CGK', 'date': '2026-05-25'},
        ],
    },
]

urls = []
for s in searches:
    tfs = build_biz_tfs(s['legs'], cabin=3)
    url = f"https://www.google.com/travel/flights/search?tfs={tfs}&curr=USD"
    urls.append((s['label'], url))
    print(f"\n{s['label']}:")
    print(f"  {url}")

# Verify our TFS matches user's format
print("\n" + "=" * 70)
print("COMPARING OUR TFS vs USER'S TFS")
print("=" * 70)
our_rt = build_biz_tfs([
    {'origin': 'CGK', 'destination': 'LAX', 'date': '2026-05-08'},
    {'origin': 'LAX', 'destination': 'CGK', 'date': '2026-06-15'},
], cabin=3)
print(f"User: {user_tfs}")
print(f"Ours: {our_rt}")

our_decoded = base64.urlsafe_b64decode(our_rt + "=" * (4 - len(our_rt) % 4) if len(our_rt) % 4 else our_rt)
print(f"\nUser bytes: {' '.join(f'{b:02x}' for b in decoded)}")
print(f"Ours bytes: {' '.join(f'{b:02x}' for b in our_decoded)}")

# Now use Playwright to search with proper URLs
print("\n" + "=" * 70)
print("PLAYWRIGHT SEARCH WITH PROPER BIZ TFS")
print("=" * 70)

try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            extra_http_headers={'Accept-Language': 'en-US,en;q=0.9'},
        )
        page = context.new_page()

        for label, url in urls:
            print(f"\n  {label}...")
            try:
                page.goto(url, wait_until='networkidle', timeout=60000)
                time.sleep(5)  # wait longer for results

                # Accept cookies/consent
                for selector in ['button:has-text("Accept")', 'button:has-text("Reject")', 'button:has-text("I agree")']:
                    try:
                        page.click(selector, timeout=2000)
                        time.sleep(2)
                    except:
                        pass

                # Check what cabin class is shown
                page_text = page.inner_text('body')
                if 'Business' in page_text:
                    print("    ✓ 'Business' found on page")
                if 'Economy' in page_text:
                    print("    'Economy' found on page")

                # Extract prices from ARIA labels
                prices_found = []
                elements = page.query_selector_all('[aria-label]')
                for el in elements:
                    aria = el.get_attribute('aria-label') or ''
                    price_match = re.search(r'(\d[\d,]*)\s*(?:US\s*)?dollars?', aria)
                    if price_match and len(aria) > 30:
                        price = int(price_match.group(1).replace(',', ''))
                        if price > 50:
                            airline_match = re.search(r'flight with ([^.]+)', aria)
                            airline = airline_match.group(1) if airline_match else '?'
                            stops_match = re.search(r'(Nonstop|\d+ stops?)', aria)
                            stops = stops_match.group(1) if stops_match else '?'
                            dur_match = re.search(r'(\d+ hr\s*(?:\d+ min)?)', aria)
                            dur = dur_match.group(1) if dur_match else '?'
                            prices_found.append((price, airline, stops, dur))

                if prices_found:
                    prices_found.sort()
                    for price, airline, stops, dur in prices_found[:10]:
                        print(f"    ${price:>5} | {airline[:45]} | {stops} | {dur}")
                    print(f"    Total: {len(prices_found)} options, range ${prices_found[0][0]}-${prices_found[-1][0]}")
                else:
                    print("    NO prices found")

                # Screenshot
                safe_label = label.replace(' ', '_').replace('/', '-')
                page.screenshot(path=f'D:/claude/flights/biz_proper_{safe_label}.png')
                print(f"    Screenshot saved: biz_proper_{safe_label}.png")

            except Exception as e:
                print(f"    ERROR: {e}")

        browser.close()

except ImportError:
    print("Playwright not installed")
except Exception as e:
    print(f"Playwright error: {e}")

print("\nDONE")
