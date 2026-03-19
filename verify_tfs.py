"""Compare: our ?q= URL vs user's proper TFS URL for business class."""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/claude/flights')

import requests
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

# User's actual TFS URL (proper business class with protobuf encoding)
tfs_url = "https://www.google.com/travel/flights/search?tfs=CBwQAhoeEgoyMDI2LTA1LTA4agcIARIDQ0dLcgcIARIDTEFYGh4SCjIwMjYtMDYtMTVqBwgBEgNMQVhyBwgBEgNDR0tAAUgDcAGCAQsI____________AZgBAQ&curr=USD&gl=us&hl=en"

# Our ?q= URL
q_url = "https://www.google.com/travel/flights?q=business%20class%20flights%20from%20CGK%20to%20LAX%20on%20May%208%202026%20round%20trip%20return%20June%2015%202026&curr=USD&hl=en&gl=us"

# Economy ?q= URL for comparison
eco_url = "https://www.google.com/travel/flights?q=flights%20from%20CGK%20to%20LAX%20on%20May%208%202026%20round%20trip%20return%20June%2015%202026&curr=USD&hl=en&gl=us"

def extract_prices(url, label):
    print(f"\n{'='*70}")
    print(f"{label}")
    print(f"URL: {url[:120]}...")
    print(f"{'='*70}")
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        print(f"Status: {resp.status_code}, Length: {len(resp.text)}")

        # Find all dollar prices in the page
        all_prices = re.findall(r'\$(\d[\d,]*)', resp.text)
        prices = sorted(set(int(p.replace(',', '')) for p in all_prices if int(p.replace(',', '')) > 50))
        print(f"All unique prices found: {prices[:30]}")

        # Check for cabin class indicators
        if 'Business' in resp.text or 'business' in resp.text:
            print("'Business/business' found in page text")
        if 'Economy' in resp.text or 'economy' in resp.text:
            print("'Economy/economy' found in page text")
        if 'Premium' in resp.text:
            print("'Premium' found in page text")

        # Check for the TFS parameter in page (what cabin is actually selected)
        cabin_matches = re.findall(r'cabin["\s:=]+(\w+)', resp.text[:5000], re.IGNORECASE)
        if cabin_matches:
            print(f"Cabin references: {cabin_matches[:10]}")

        # Look for ARIA labels with prices
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'html.parser')
        count = 0
        for el in soup.find_all(attrs={"aria-label": True}):
            label_text = el.get("aria-label", "")
            price_match = re.search(r'\$(\d[\d,]*)', label_text)
            if price_match and len(label_text) > 30:
                price = int(price_match.group(1).replace(',', ''))
                if price > 50:
                    count += 1
                    if count <= 10:
                        print(f"  ${price:>5} | {label_text[:120]}")
        print(f"Total ARIA price labels: {count}")

    except Exception as e:
        print(f"ERROR: {e}")

extract_prices(tfs_url, "METHOD 1: User's TFS URL (proper business class protobuf)")
extract_prices(q_url, "METHOD 2: Our ?q= URL (natural language business)")
extract_prices(eco_url, "METHOD 3: Economy ?q= URL (control)")

print("\n\nCONCLUSION:")
print("If TFS shows $3000+ and ?q= shows $900, our scraper is NOT getting real business class prices.")
print("The ?q= method may be defaulting to economy despite 'business class' in the query.")
