"""Fetch second WeChat article about business class to Europe."""
import asyncio
import os, sys
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def main():
    from playwright.async_api import async_playwright

    url = "https://mp.weixin.qq.com/s/eTkQkpUbtS_3RYU2969NbQ"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36 MicroMessenger/8.0.40",
            locale="zh-CN",
            viewport={"width": 414, "height": 896},
        )
        page = await context.new_page()

        print("Loading second WeChat article...", flush=True)
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        # Scroll to load everything
        for i in range(20):
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(0.5)
        await asyncio.sleep(2)

        title = await page.title()
        print(f"Title: {title}", flush=True)

        await page.screenshot(path="D:/claude/flights/wechat_europe_biz.png", full_page=True)
        print("Saved screenshot", flush=True)

        text = await page.inner_text("body")
        with open("D:/claude/flights/wechat_europe_text.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print(f"\nFull text ({len(text)} chars):", flush=True)
        print(text[:5000], flush=True)

        await browser.close()

asyncio.run(main())
