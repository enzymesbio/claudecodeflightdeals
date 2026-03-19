"""Fetch WeChat article comments by scrolling down."""
import asyncio
import os, sys
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def main():
    from playwright.async_api import async_playwright

    url = "https://mp.weixin.qq.com/s/ZswJbH2VlbJc_CqwpLm2-A"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36 MicroMessenger/8.0.40",
            locale="zh-CN",
            viewport={"width": 414, "height": 896},
        )
        page = await context.new_page()

        print("Loading WeChat article...", flush=True)
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        # Scroll to bottom to load comments
        for i in range(15):
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(0.5)

        await asyncio.sleep(2)

        # Screenshot the full page including comments
        await page.screenshot(path="D:/claude/flights/wechat_with_comments.png", full_page=True)
        print("Saved full screenshot with comments", flush=True)

        # Get all text
        text = await page.inner_text("body")
        with open("D:/claude/flights/wechat_full_text.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Full text ({len(text)} chars):", flush=True)
        print(text, flush=True)

        await browser.close()

asyncio.run(main())
