"""Fetch WeChat article with Playwright and screenshot it."""
import asyncio
import sys
import os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def main():
    from playwright.async_api import async_playwright

    url = "https://mp.weixin.qq.com/s/ZswJbH2VlbJc_CqwpLm2-A"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781",
            locale="zh-CN",
            viewport={"width": 414, "height": 896},  # mobile viewport
        )
        page = await context.new_page()

        print("Loading WeChat article...", flush=True)
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        # Get page title
        title = await page.title()
        print(f"Title: {title}", flush=True)

        # Full page screenshot
        await page.screenshot(path="D:/claude/flights/wechat_article_full.png", full_page=True)
        print("Saved full page screenshot: wechat_article_full.png", flush=True)

        # Also get text content
        text = await page.inner_text("body")
        with open("D:/claude/flights/wechat_article_text.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Saved text ({len(text)} chars): wechat_article_text.txt", flush=True)

        # Try to get the article content specifically
        try:
            content = await page.inner_text("#js_content")
            print(f"\nArticle content ({len(content)} chars):")
            print(content[:3000])
        except:
            print("Could not find #js_content, printing body text:")
            print(text[:3000])

        await browser.close()

asyncio.run(main())
