import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import asyncio
import json
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

SEARCHES = [
    {
        "label": "CGK-LHR OW May4 Business",
        "url": "https://www.skyscanner.com/transport/flights/cgk/lhr/260504/?adultsv2=1&cabinclass=business&rtn=0",
        "screenshot": "D:/claude/flights/sky_CGK-LHR_OW_May4.png",
    },
    {
        "label": "CGK-LAX OW May4 Business",
        "url": "https://www.skyscanner.com/transport/flights/cgk/lax/260504/?adultsv2=1&cabinclass=business&rtn=0",
        "screenshot": "D:/claude/flights/sky_CGK-LAX_OW_May4.png",
    },
    {
        "label": "CGK-LAX OW May8 Business",
        "url": "https://www.skyscanner.com/transport/flights/cgk/lax/260508/?adultsv2=1&cabinclass=business&rtn=0",
        "screenshot": "D:/claude/flights/sky_CGK-LAX_OW_May8.png",
    },
]

stealth = Stealth()


async def extract_prices(page):
    """Extract all price-like elements from the page using multiple selectors."""
    prices = await page.evaluate("""
    () => {
        const results = [];

        // Strategy 1: Look for elements with price-related attributes
        const priceEls = document.querySelectorAll('[class*="rice"], [class*="cost"], [class*="fare"], [class*="amount"], [class*="Price"], [class*="Fare"]');
        priceEls.forEach(el => {
            const text = el.textContent.trim();
            if (text && /[\\$\\u00A3\\u20AC]|\\d/.test(text) && text.length < 100) {
                results.push({source: 'class-match', text: text});
            }
        });

        // Strategy 2: Look for spans/divs containing currency symbols or price patterns
        const allEls = document.querySelectorAll('span, div, a, p, strong, b');
        allEls.forEach(el => {
            const text = el.textContent.trim();
            if (/^[\\$\\u00A3\\u20AC\\u00A5]\\s?[\\d,]+/.test(text) ||
                /^[\\d,]+\\s?[\\$\\u00A3\\u20AC\\u00A5]/.test(text) ||
                /^(USD|GBP|EUR|IDR|CNY)\\s?[\\d,]+/.test(text) ||
                /^[\\d,]+\\s?(USD|GBP|EUR|IDR|CNY)/.test(text)) {
                if (text.length < 50) {
                    results.push({source: 'currency-pattern', text: text});
                }
            }
        });

        // Strategy 3: Look for aria-label containing price
        const ariaEls = document.querySelectorAll('[aria-label*="price"], [aria-label*="Price"], [aria-label*="cost"], [aria-label*="fare"]');
        ariaEls.forEach(el => {
            results.push({source: 'aria-label', text: el.getAttribute('aria-label'), innerText: el.textContent.trim()});
        });

        // Strategy 4: data-testid or data-e2e containing price
        const dataEls = document.querySelectorAll('[data-testid*="price"], [data-testid*="Price"], [data-e2e*="price"], [data-e2e*="Price"]');
        dataEls.forEach(el => {
            results.push({source: 'data-attr', text: el.textContent.trim()});
        });

        // Strategy 5: Look for structured itinerary/result items
        const itinEls = document.querySelectorAll('[class*="tinerary"], [class*="esult"], [class*="TicketBody"], [class*="FlightCard"]');
        itinEls.forEach(el => {
            const text = el.textContent.trim().substring(0, 300);
            if (/[\\$\\u00A3\\u20AC]\\s?[\\d,]+/.test(text) || /[\\d,]+\\s?(USD|GBP|EUR)/.test(text)) {
                results.push({source: 'itinerary-block', text: text});
            }
        });

        // Deduplicate
        const seen = new Set();
        return results.filter(r => {
            const key = r.text;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    }
    """)
    return prices


async def get_page_info(page):
    """Get page title and basic structure info."""
    info = await page.evaluate("""
    () => {
        const title = document.title;
        const bodyText = document.body ? document.body.innerText.substring(0, 3000) : 'NO BODY';
        const h1s = Array.from(document.querySelectorAll('h1')).map(e => e.textContent.trim());
        const h2s = Array.from(document.querySelectorAll('h2')).map(e => e.textContent.trim());
        return {title, h1s, h2s, bodyTextPreview: bodyText};
    }
    """)
    return info


async def solve_press_hold(page):
    """Try to solve the PerimeterX PRESS & HOLD captcha."""
    try:
        # Look for the press & hold button
        button = page.locator('#px-captcha, button:has-text("PRESS & HOLD")')
        if await button.count() > 0:
            print("  Found PRESS & HOLD button, attempting to solve...")
            box = await button.first.bounding_box()
            if box:
                x = box['x'] + box['width'] / 2
                y = box['y'] + box['height'] / 2

                # Simulate human-like mouse movement
                import random
                start_x = random.randint(100, 400)
                start_y = random.randint(600, 800)
                await page.mouse.move(start_x, start_y)
                await asyncio.sleep(0.3)

                # Move to button in steps
                steps = 15
                for i in range(steps):
                    cx = start_x + (x - start_x) * (i + 1) / steps + random.uniform(-3, 3)
                    cy = start_y + (y - start_y) * (i + 1) / steps + random.uniform(-3, 3)
                    await page.mouse.move(cx, cy)
                    await asyncio.sleep(random.uniform(0.02, 0.08))

                await asyncio.sleep(random.uniform(0.1, 0.3))
                await page.mouse.down()
                print("  Mouse down, holding for 12s...")
                await asyncio.sleep(12)
                await page.mouse.up()
                print("  Mouse released. Waiting 5s...")
                await asyncio.sleep(5)
                return True
        else:
            print("  No PRESS & HOLD button found.")
        return False
    except Exception as e:
        print(f"  Error during press-hold: {e}")
        return False


async def main():
    all_results = {}

    async with stealth.use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=True,
            channel="chrome",
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        )

        for search in SEARCHES:
            label = search["label"]
            url = search["url"]
            screenshot_path = search["screenshot"]

            print(f"\n{'='*60}")
            print(f"SEARCH: {label}")
            print(f"URL: {url}")
            print(f"{'='*60}")

            page = await context.new_page()

            # Capture API responses
            api_data = []
            async def on_response(response):
                resp_url = response.url
                try:
                    ct = response.headers.get('content-type', '')
                    if 'json' in ct and response.status == 200:
                        body = await response.text()
                        if len(body) > 200:
                            has_flight = any(kw in body.lower() for kw in ['itinerary', 'carrier', 'airline', 'departure', 'arrival'])
                            if has_flight:
                                api_data.append({
                                    'url': resp_url[:300],
                                    'size': len(body),
                                    'body': body[:3000],
                                })
                except:
                    pass
            page.on("response", on_response)

            try:
                print("Navigating...")
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                print("DOM loaded. Waiting 10s for page to render...")
                await asyncio.sleep(10)

                # Check for bot detection
                info = await get_page_info(page)
                body_text = info.get('bodyTextPreview', '')
                is_blocked = 'robot' in body_text.lower()

                if is_blocked:
                    print("Bot detection page shown. Attempting PRESS & HOLD solve...")
                    solved = await solve_press_hold(page)

                    if solved:
                        info = await get_page_info(page)
                        body_text = info.get('bodyTextPreview', '')
                        is_blocked = 'robot' in body_text.lower()
                        print(f"After solve: blocked={is_blocked}, title={info['title']}")

                        if is_blocked:
                            # Second attempt
                            print("Retrying PRESS & HOLD...")
                            await solve_press_hold(page)
                            await asyncio.sleep(3)
                            info = await get_page_info(page)
                            body_text = info.get('bodyTextPreview', '')
                            is_blocked = 'robot' in body_text.lower()
                            print(f"After retry: blocked={is_blocked}")

                if not is_blocked:
                    print("Past bot detection! Waiting for results...")
                    await asyncio.sleep(15)

                    # Scroll to load all results
                    for y in [300, 800, 1500, 2500, 4000]:
                        await page.evaluate(f"window.scrollTo(0, {y})")
                        await asyncio.sleep(1.5)
                    await page.evaluate("window.scrollTo(0, 0)")
                    await asyncio.sleep(2)

                    info = await get_page_info(page)

                # Take screenshot
                await page.screenshot(path=screenshot_path, full_page=True)
                print(f"Screenshot saved: {screenshot_path}")

                # Extract prices
                prices = await extract_prices(page)
                print(f"\nExtracted {len(prices)} price elements:")
                for i, price in enumerate(prices[:30]):
                    print(f"  [{i+1}] ({price['source']}): {price['text']}")
                    if 'innerText' in price:
                        print(f"       innerText: {price['innerText']}")

                # Print captured flight API data
                if api_data:
                    print(f"\nFlight API responses captured: {len(api_data)}")
                    for i, d in enumerate(api_data[:5]):
                        print(f"  [{i+1}] {d['url']}")
                        print(f"    Preview: {d['body'][:500]}")

                # Print page text
                print(f"\n--- Page text (first 2000 chars) ---")
                print(body_text[:2000])

                all_results[label] = {
                    "url": url,
                    "title": info.get('title', ''),
                    "prices": prices,
                    "screenshot": screenshot_path,
                    "blocked": is_blocked,
                }

            except Exception as e:
                print(f"ERROR: {e}")
                try:
                    await page.screenshot(path=screenshot_path, full_page=True)
                except:
                    pass
                all_results[label] = {"url": url, "error": str(e)}
            finally:
                await page.close()

            await asyncio.sleep(5)

        await browser.close()

    # Save results
    output_path = "D:/claude/flights/skyscanner_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n\nAll results saved to {output_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for label, result in all_results.items():
        blocked = result.get('blocked', True)
        prices = result.get('prices', [])
        print(f"\n{label}:")
        print(f"  URL: {result.get('url', 'N/A')}")
        print(f"  Blocked: {blocked}")
        print(f"  Prices found: {len(prices)}")
        if prices:
            for p in prices[:5]:
                print(f"    - {p.get('text', 'N/A')}")
        print(f"  Screenshot: {result.get('screenshot', 'N/A')}")


if __name__ == "__main__":
    asyncio.run(main())
