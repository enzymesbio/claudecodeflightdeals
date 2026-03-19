#!/usr/bin/env python3
"""
Expedia flight search using Playwright with stealth plugin.
Searches business class flights from Jakarta (CGK) to LHR/LAX.

Strategy: Use Firefox (less detected than Chromium), try multiple OTAs,
and use headed mode with virtual display to appear more human-like.
"""

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import asyncio
import json
import re
import os
import time
import random
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

SCREENSHOT_DIR = "D:/claude/flights"

SEARCHES = [
    {
        "label": "CGK-LHR_OW_May4_Biz",
        "origin": "CGK",
        "dest": "LHR",
        "depart": "2026-05-04",
        "return_date": None,
        "trip_type": "oneway",
    },
    {
        "label": "CGK-LAX_OW_May4_Biz",
        "origin": "CGK",
        "dest": "LAX",
        "depart": "2026-05-04",
        "return_date": None,
        "trip_type": "oneway",
    },
    {
        "label": "CGK-LAX_OW_May8_Biz",
        "origin": "CGK",
        "dest": "LAX",
        "depart": "2026-05-08",
        "return_date": None,
        "trip_type": "oneway",
    },
    {
        "label": "CGK-LAX_RT_May4-Jun15_Biz",
        "origin": "CGK",
        "dest": "LAX",
        "depart": "2026-05-04",
        "return_date": "2026-06-15",
        "trip_type": "roundtrip",
    },
]


def build_urls(search):
    """Build URLs for multiple OTAs."""
    o, d = search["origin"], search["dest"]
    dep = search["depart"]
    dep_compact = dep.replace("-", "")

    urls = []

    # Expedia
    if search["trip_type"] == "oneway":
        urls.append(("expedia",
            f"https://www.expedia.com/Flights-search/{o}-{d}/{dep_compact}/"
            f"?cabinclass=business&passengers=adults:1&trip=oneway"))
    else:
        ret = search["return_date"].replace("-", "")
        urls.append(("expedia",
            f"https://www.expedia.com/Flights-search/{o}-{d}/{dep_compact}/{ret}/"
            f"?cabinclass=business&passengers=adults:1&trip=roundtrip"))

    # Skyscanner
    if search["trip_type"] == "oneway":
        urls.append(("skyscanner",
            f"https://www.skyscanner.com/transport/flights/{o.lower()}/{d.lower()}/{dep_compact}/"
            f"?adultsv2=1&cabinclass=business&rtn=0"))
    else:
        ret_compact = search["return_date"].replace("-", "")
        urls.append(("skyscanner",
            f"https://www.skyscanner.com/transport/flights/{o.lower()}/{d.lower()}/{dep_compact}/{ret_compact}/"
            f"?adultsv2=1&cabinclass=business&rtn=1"))

    # Momondo
    if search["trip_type"] == "oneway":
        urls.append(("momondo",
            f"https://www.momondo.com/flights/{o}-{d}/{dep}?sort=bestflight_a&fs=cabin=b"))
    else:
        ret = search["return_date"]
        urls.append(("momondo",
            f"https://www.momondo.com/flights/{o}-{d}/{dep}/{ret}?sort=bestflight_a&fs=cabin=b"))

    # Trip.com
    if search["trip_type"] == "oneway":
        urls.append(("trip.com",
            f"https://us.trip.com/flights/{o.lower()}-to-{d.lower()}/tickets-{o.lower()}-{d.lower()}?"
            f"dcity={o}&acity={d}&ddate={dep}&rdate=&flighttype=ow&class=c&lowpricesource=searchform"
            f"&quantity=1"))
    else:
        ret = search["return_date"]
        urls.append(("trip.com",
            f"https://us.trip.com/flights/{o.lower()}-to-{d.lower()}/tickets-{o.lower()}-{d.lower()}?"
            f"dcity={o}&acity={d}&ddate={dep}&rdate={ret}&flighttype=rt&class=c&lowpricesource=searchform"
            f"&quantity=1"))

    return urls


async def extract_prices(page):
    """Extract all price data from any flight results page."""
    return await page.evaluate("""
    () => {
        const results = {
            prices: [],
            cards: [],
            ariaLabels: [],
            allCurrencyAmounts: [],
        };

        const body = document.body?.textContent || '';

        // All currency amounts (USD, GBP, EUR)
        const currencyRe = /(?:\\$|\\xa3|\\u20ac|USD|GBP|EUR)\\s*[\\d,]+(?:\\.\\d{2})?|[\\d,]+(?:\\.\\d{2})?\\s*(?:USD|GBP|EUR)/g;
        const matches = body.match(currencyRe) || [];
        results.allCurrencyAmounts = [...new Set(matches)].slice(0, 30);

        // Dollar amounts specifically
        const dollarRe = /\\$[\\d,]+/g;
        const dollars = body.match(dollarRe) || [];
        results.prices = [...new Set(dollars)].filter(p => {
            const v = parseInt(p.replace(/[$,]/g, ''));
            return v >= 200 && v <= 80000;
        });

        // CNY amounts (for Trip.com)
        const cnyRe = /(?:CNY|\\xa5|RMB)\\s*[\\d,]+/g;
        const cny = body.match(cnyRe) || [];
        if (cny.length > 0) {
            results.cnyPrices = [...new Set(cny)].slice(0, 20);
        }

        // Try to find flight listing cards using generic patterns
        const cardSelectors = [
            '[data-stid="section-results-item-card"]',
            '[class*="FlightCard"]',
            '[class*="flight-card"]',
            '[class*="resultWrapper"]',
            '[class*="listing-item"]',
            '[class*="nrc6"]',
            '[class*="BpkTicket"]',
            '[class*="result-item"]',
            'li[class*="flight"]',
            '[data-testid*="flight"]',
            '[data-testid*="result"]',
            '[class*="itinerary"]',
        ];

        for (const sel of cardSelectors) {
            try {
                const els = document.querySelectorAll(sel);
                if (els.length === 0) continue;
                els.forEach((el, idx) => {
                    if (idx >= 20) return;
                    const text = el.textContent || '';
                    const priceMatch = text.match(/(?:\\$|\\xa3|\\u20ac)[\\d,]+/g) || [];
                    if (priceMatch.length > 0) {
                        const airline = text.match(/(\\w+(?:\\s+\\w+)?\\s*(?:Airlines?|Airways?|Air\\b))/i);
                        const stops = text.match(/((?:Non|Direct|\\d+)\\s*stop)/i);
                        const dur = text.match(/(\\d+h\\s*\\d*m?)/i);
                        const times = text.match(/(\\d{1,2}:\\d{2}\\s*(?:[AaPp][Mm])?)/g);
                        results.cards.push({
                            idx, sel,
                            prices: priceMatch.slice(0, 5),
                            airline: airline?.[1] || null,
                            stops: stops?.[1] || null,
                            duration: dur?.[1] || null,
                            times: times?.slice(0, 4) || null,
                            snippet: text.replace(/\\s+/g, ' ').substring(0, 400),
                        });
                    }
                });
                if (results.cards.length > 0) break;
            } catch(e) {}
        }

        // Also try aria-labels
        document.querySelectorAll('[aria-label]').forEach(el => {
            const label = el.getAttribute('aria-label') || '';
            if (/(?:\\$|\\xa3|\\u20ac)[\\d,]+/.test(label) && label.length > 20 && label.length < 500) {
                results.ariaLabels.push(label.substring(0, 400));
            }
        });

        return results;
    }
    """)


async def check_page(page):
    """Check page status."""
    return await page.evaluate("""
    () => ({
        title: document.title,
        url: location.href,
        bodyLen: (document.body?.innerHTML || '').length,
        isCaptcha: /bot|captcha|human|verify|blocked|access denied|security check|are you a robot/i.test(
            document.title + ' ' +
            (document.querySelector('h1,h2,h3')?.textContent || '') + ' ' +
            (document.querySelector('main,#main,.main')?.textContent?.substring(0,500) || '')
        ),
    })
    """)


async def dismiss_popups(page):
    """Dismiss overlays."""
    for sel in [
        'button[aria-label="Close"]', 'button[aria-label="close"]',
        'button:has-text("Accept")', 'button:has-text("Accept All")',
        'button:has-text("Accept all")',
        'button:has-text("Got it")', 'button:has-text("No thanks")',
        'button:has-text("Close")', 'button:has-text("OK")',
        'button:has-text("Continue")', 'button:has-text("Agree")',
        '[id*="cookie"] button', '[class*="cookie"] button',
        '[class*="consent"] button',
    ]:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=500):
                await el.click(force=True)
                await asyncio.sleep(0.3)
        except:
            pass


async def try_search(browser_type, pw, search, site_name, url, label):
    """Try a single search on a single site."""
    print(f"\n  [{site_name}] Trying: {url}")

    # Use Firefox for better stealth
    browser = await pw.firefox.launch(
        headless=True,
        args=[],
    )

    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) "
            "Gecko/20100101 Firefox/134.0"
        ),
        locale="en-US",
        timezone_id="America/New_York",
        extra_http_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        },
    )

    page = await context.new_page()
    result = None

    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        status = resp.status if resp else "N/A"
        print(f"  [{site_name}] HTTP {status}")

        await asyncio.sleep(random.uniform(5, 8))
        await dismiss_popups(page)

        st = await check_page(page)
        print(f"  [{site_name}] Title: {st['title']}")
        print(f"  [{site_name}] CAPTCHA: {st['isCaptcha']}, Body: {st['bodyLen']}")

        if st["isCaptcha"]:
            print(f"  [{site_name}] Blocked! Waiting 20s to see if it clears...")
            await asyncio.sleep(20)
            st2 = await check_page(page)
            if st2["isCaptcha"]:
                ss = os.path.join(SCREENSHOT_DIR, f"expedia_{label}_{site_name}_blocked.png")
                await page.screenshot(path=ss, full_page=False)
                print(f"  [{site_name}] Still blocked. Screenshot: {ss}")
                await context.close()
                await browser.close()
                return None

        # Wait for flight content to load
        print(f"  [{site_name}] Waiting for results...")
        await asyncio.sleep(12)
        await dismiss_popups(page)

        # Scroll
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(1)
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(2)

        # Screenshots
        ss1 = os.path.join(SCREENSHOT_DIR, f"expedia_{label}_{site_name}_results.png")
        await page.screenshot(path=ss1, full_page=False)
        print(f"  [{site_name}] Screenshot: {ss1}")

        ss2 = os.path.join(SCREENSHOT_DIR, f"expedia_{label}_{site_name}_full.png")
        try:
            await page.screenshot(path=ss2, full_page=True)
        except:
            await page.screenshot(path=ss2, full_page=False)

        # Extract
        data = await extract_prices(page)
        prices = data.get("prices", [])
        cards = data.get("cards", [])
        aria = data.get("ariaLabels", [])
        all_cur = data.get("allCurrencyAmounts", [])
        cny = data.get("cnyPrices", [])

        print(f"  [{site_name}] Dollar prices: {prices[:15]}")
        print(f"  [{site_name}] Cards: {len(cards)}")
        print(f"  [{site_name}] Aria labels: {len(aria)}")
        if all_cur:
            print(f"  [{site_name}] All currency amounts: {all_cur[:15]}")
        if cny:
            print(f"  [{site_name}] CNY prices: {cny[:15]}")

        if cards:
            print(f"\n  [{site_name}] FLIGHT LISTINGS:")
            for c in cards[:15]:
                a = c.get("airline", "?")
                p = c.get("prices", [])
                s = c.get("stops", "")
                d = c.get("duration", "")
                t = c.get("times", [])
                tstr = " -> ".join(t[:2]) if t else ""
                print(f"    {a}: {', '.join(p)} | {s} | {d} | {tstr}")

        if aria:
            print(f"\n  [{site_name}] ARIA DETAILS:")
            for a_item in aria[:8]:
                print(f"    {a_item}")

        if prices or cards or all_cur:
            result = {
                "source": site_name,
                "prices": prices,
                "cards": cards,
                "aria": aria[:10],
                "all_currency": all_cur,
                "cny": cny,
            }

    except Exception as e:
        print(f"  [{site_name}] Error: {e}")
        try:
            ss = os.path.join(SCREENSHOT_DIR, f"expedia_{label}_{site_name}_error.png")
            await page.screenshot(path=ss, full_page=False)
        except:
            pass

    await context.close()
    await browser.close()
    return result


async def run_search(pw, search, search_num):
    """Run a single search across multiple OTAs."""
    label = search["label"]
    print(f"\n{'='*60}")
    print(f"Search {search_num}: {label}")
    print(f"{'='*60}")

    urls = build_urls(search)
    result = {"search": label, "flights": [], "prices": [], "source": None}

    for site_name, url in urls:
        data = await try_search("firefox", pw, search, site_name, url, label)
        if data and (data.get("prices") or data.get("cards")):
            result["source"] = data["source"]
            result["prices"] = data.get("prices", [])
            result["flights"] = data.get("cards", [])
            result["aria"] = data.get("aria", [])
            result["all_currency"] = data.get("all_currency", [])
            result["cny"] = data.get("cny", [])
            break
        # Even if no structured prices, save currency amounts if found
        if data and data.get("all_currency"):
            result["source"] = data["source"]
            result["all_currency"] = data.get("all_currency", [])
            result["cny"] = data.get("cny", [])
            # Don't break - try next site for better results

        await asyncio.sleep(random.uniform(2, 4))

    return result


async def main():
    print("=" * 60)
    print("EXPEDIA BUSINESS CLASS FLIGHT SEARCH")
    print("Playwright + Firefox + Stealth")
    print("Fallbacks: Skyscanner, Momondo, Trip.com")
    print("=" * 60)

    all_results = []

    async with async_playwright() as pw:
        for i, search in enumerate(SEARCHES, 1):
            result = await run_search(pw, search, i)
            all_results.append(result)
            if i < len(SEARCHES):
                await asyncio.sleep(random.uniform(3, 5))

    # Save
    out_file = os.path.join(SCREENSHOT_DIR, "expedia_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults saved to: {out_file}")

    # Summary
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    for r in all_results:
        src = r.get("source", "none")
        print(f"\n{r['search']} (source: {src}):")
        if r.get("prices"):
            print(f"  Prices: {r['prices'][:15]}")
        if r.get("flights"):
            print(f"  Flights: {len(r['flights'])}")
            for fl in r["flights"][:8]:
                a = fl.get("airline", "?")
                p = fl.get("prices", [])
                s = fl.get("stops", "")
                d = fl.get("duration", "")
                print(f"    {a}: {', '.join(p)} ({s}, {d})")
        if r.get("cny"):
            print(f"  CNY prices: {r['cny'][:10]}")
        if r.get("all_currency") and not r.get("prices") and not r.get("flights"):
            print(f"  Currency amounts: {r['all_currency'][:15]}")
        if r.get("aria"):
            for ad in r["aria"][:3]:
                print(f"    Detail: {ad}")
        if not r.get("prices") and not r.get("flights") and not r.get("all_currency"):
            print("  No results obtained (all sites blocked)")


if __name__ == "__main__":
    asyncio.run(main())
