"""Verify Philippine Airlines HKG-LAX/SFO deal on Ctrip and ITA Matrix."""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/claude/flights')

import asyncio
import json
import time
from datetime import datetime

async def search_ctrip_philippine():
    """Search Ctrip for the exact Philippine Airlines open-jaw routes."""
    from playwright.async_api import async_playwright

    routes = [
        # Exact article routes (open-jaw as one-way legs)
        ("hkg", "sfo", "2026-09-25", "HKG-SFO Sep25 OW"),
        ("lax", "pvg", "2026-10-04", "LAX-PVG Oct4 OW"),
        ("hkg", "lax", "2026-09-25", "HKG-LAX Sep25 OW"),
        ("lax", "pek", "2026-10-05", "LAX-PEK Oct5 OW"),
        ("lax", "hkg", "2026-10-04", "LAX-HKG Oct4 OW"),
        # Also PVG origins for user
        ("pvg", "lax", "2026-09-25", "PVG-LAX Sep25 OW"),
        ("pvg", "sfo", "2026-09-25", "PVG-SFO Sep25 OW"),
        # User preferred dates
        ("pvg", "lax", "2026-05-15", "PVG-LAX May15 OW"),
        ("pvg", "sfo", "2026-05-15", "PVG-SFO May15 OW"),
        ("hkg", "lax", "2026-05-15", "HKG-LAX May15 OW"),
        ("hkg", "sfo", "2026-05-15", "HKG-SFO May15 OW"),
    ]

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="zh-CN",
        )

        for origin, dest, date, label in routes:
            url = f"https://flights.ctrip.com/international/search/oneway-{origin}-{dest}?depdate={date}&cabin=y&adult=1&child=0&infant=0"
            print(f"Ctrip: {label}...", end=' ', flush=True)

            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(5)

                # Try to find Philippine Airlines flights
                content = await page.content()
                text = await page.inner_text("body")

                # Look for Philippine Airlines mentions
                if 'Philippine' in text or 'PR' in text or '菲律宾' in text:
                    print("FOUND Philippine Airlines!", flush=True)
                    # Take screenshot
                    fname = f"ctrip_pr_{origin}_{dest}_{date}.png"
                    await page.screenshot(path=f"D:/claude/flights/{fname}", full_page=True)
                    print(f"  Screenshot: {fname}")
                else:
                    print(f"no PR found ({len(text)} chars)", flush=True)

                # Extract any prices from the page
                # Look for price elements
                price_elements = await page.query_selector_all('[class*="price"], [class*="Price"]')
                for pe in price_elements[:5]:
                    try:
                        ptxt = await pe.inner_text()
                        if ptxt.strip():
                            print(f"  Price element: {ptxt.strip()[:60]}")
                    except:
                        pass

                results.append({
                    'source': 'Ctrip',
                    'route': f"{origin.upper()}-{dest.upper()}",
                    'date': date,
                    'label': label,
                    'has_philippine': 'Philippine' in text or '菲律宾' in text,
                    'page_length': len(text),
                })

            except Exception as e:
                print(f"ERROR: {e}", flush=True)
                results.append({'source': 'Ctrip', 'route': f"{origin.upper()}-{dest.upper()}", 'date': date, 'error': str(e)})
            finally:
                await page.close()

            await asyncio.sleep(2)

        await browser.close()

    return results


async def search_ita_philippine():
    """Search ITA Matrix for Philippine Airlines open-jaw routes."""
    from playwright.async_api import async_playwright

    searches = [
        {"origin": "HKG", "destination": "SFO", "depart": "9/25/2026", "return": "10/4/2026", "label": "HKG-SFO RT"},
        {"origin": "HKG", "destination": "LAX", "depart": "9/25/2026", "return": "10/5/2026", "label": "HKG-LAX RT"},
        {"origin": "PVG", "destination": "LAX", "depart": "9/25/2026", "return": "10/4/2026", "label": "PVG-LAX RT"},
        {"origin": "PVG", "destination": "SFO", "depart": "9/25/2026", "return": "10/4/2026", "label": "PVG-SFO RT"},
        {"origin": "PVG", "destination": "LAX", "depart": "5/15/2026", "return": "6/12/2026", "label": "PVG-LAX May RT"},
    ]

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for s in searches:
            print(f"ITA Matrix: {s['label']}...", end=' ', flush=True)
            try:
                url = f"https://matrix.itasoftware.com/search"
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(3)

                # Fill in search form
                # Origin
                origin_input = await page.query_selector('input[aria-label="Origin"]')
                if origin_input:
                    await origin_input.fill(s['origin'])
                    await asyncio.sleep(1)
                    await page.keyboard.press('Tab')

                # Destination
                dest_input = await page.query_selector('input[aria-label="Destination"]')
                if dest_input:
                    await dest_input.fill(s['destination'])
                    await asyncio.sleep(1)
                    await page.keyboard.press('Tab')

                await asyncio.sleep(1)

                # For now just note that ITA Matrix was attempted
                print("form loaded", flush=True)
                results.append({'source': 'ITA Matrix', 'label': s['label'], 'status': 'form_loaded'})

            except Exception as e:
                print(f"ERROR: {e}", flush=True)
                results.append({'source': 'ITA Matrix', 'label': s['label'], 'error': str(e)})

            await asyncio.sleep(2)

        await browser.close()

    return results


async def main():
    print("=" * 80)
    print("VERIFYING PHILIPPINE AIRLINES DEALS ON CTRIP")
    print("=" * 80)

    ctrip_results = await search_ctrip_philippine()

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for r in ctrip_results:
        has_pr = r.get('has_philippine', False)
        tag = ' >>> PHILIPPINE AIRLINES FOUND!' if has_pr else ''
        print(f"  {r.get('label', r['route'])}: {'OK' if not r.get('error') else 'ERROR'} (page: {r.get('page_length', 0)} chars){tag}")

    with open('D:/claude/flights/philippine_ctrip_verification.json', 'w') as f:
        json.dump({'timestamp': datetime.now().isoformat(), 'results': ctrip_results}, f, indent=2, default=str)

asyncio.run(main())
