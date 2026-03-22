#!/usr/bin/env python3
"""
Playwright script to:
1. Visit 3 Google Flights URLs and take screenshots
2. Send screenshots + message to ChatGPT and capture the response
"""

import time
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

# Directories
SCREENSHOT_DIR = Path("D:/claude/flights/stopover_screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

OUTPUT_FILE = Path("D:/claude/flights/chatgpt_stopover_guidance.txt")

URLS = [
    (
        "url1_4leg_booking.png",
        "4-leg booking with ICN stopover stays",
        "https://www.google.com/travel/flights/booking?tfs=CBwQAhpFEgoyMDI2LTA1LTA0Ih8KA0hHSBIKMjAyNi0wNS0wNBoDSUNOKgJPWjIDMzYwag0IAxIJL20vMDE0dm00cgcIARIDSUNOGj8SCjIwMjYtMDUtMDciHwoDSUNOEgoyMDI2LTA1LTA3GgNTRk8qAk9aMgMyMTJqBwgBEgNJQ05yBwgBEgNTRk8aRBIKMjAyNi0wNS0xMiIfCgNTRk8SCjIwMjYtMDUtMTIaA0lDTioCT1oyAzIxMWoHCAESA1NGT3IMCAMSCC9tLzBoc3FmGkoSCjIwMjYtMDUtMTQiHwoDSUNOEgoyMDI2LTA1LTE0GgNIR0gqAk9aMgMzNTlqDAgDEggvbS8waHNxZnINCAMSCS9tLzAxNHZtNEABSAFwAYIBCwj___________8BmAED&tfu=CmxDalJJVFRWTmVGbEJhR0ZGWkdkQlJGWnNUV2RDUnkwdExTMHRMUzB0TFhSaVkyZHNOVUZCUVVGQlIyMDVZVXR2U2xGU2FFbEJFZ1ZQV2pNMU9Sb0xDSUQvQkJBQ0dnTlZVMFE0SEhDQS93UT0SAggAIgYKATAKATM&hl=en&gl=hk&curr=USD"
    ),
    (
        "url2_explore_hgh_usa.png",
        "Explore HGH to USA business class",
        "https://www.google.com/travel/explore?tfs=CBwQAxoqEgoyMDI2LTA1LTA0ag0IAxIJL20vMDE0dm00cg0IBBIJL20vMDljN3cwGh5qDQgEEgkvbS8wOWM3dzByDQgDEgkvbS8wMTR2bTRAAUgBcAKCAQsI____________AZgBAbIBBBgBIAE&tfu=GgA&hl=en&gl=hk&curr=USD"
    ),
    (
        "url3_roundtrip_hgh_sfo.png",
        "Round-trip HGH to SFO original $722",
        "https://www.google.com/travel/flights?tfs=CBsQAhopEgoyMDI2LTA1LTA0ag0IAxIJL20vMDE0dm00cgwIAhIIL20vMGQ2bHAaKRIKMjAyNi0wNS0xMGoMCAISCC9tLzBkNmxwcg0IAxIJL20vMDE0dm00QAFIAVIDVVNEcAF6dENqUklZalZsUkRWZk9VcFhha1ZCUkZWSWNXZENSeTB0TFMwdExTMHRMWFJzYVcweE1FRkJRVUZCUjIwNVlWcDNRMlIyTkhWQkVndFBXak0yTUh4UFdqSXhNaG9MQ1BpekJCQUNHZ05WVTBRNEhIRDRzd1E9mAEBsgESGAEgASoMCAISCC9tLzBkNmxw&tfu=GgA&hl=en&gl=hk&curr=USD"
    ),
]

CHATGPT_URL = "https://chatgpt.com/c/69bc7912-c0b8-8331-9b73-f0ba91466ee2"

CHATGPT_MESSAGE = """I want to implement a "stopover stay" feature in my Google Flights bug fare scanner. Here's what I discovered manually:

**The opportunity:** When a round-trip fare from China (e.g. Hangzhou HGH) to the USA has 1 stopover in Korea (ICN/Seoul) or Japan (NRT/TYO/Tokyo), I can convert that into a proper stopover with 2-3 night stays instead of just a connection — at very similar total price.

**Example I found manually:**
- Original: HGH→SFO round trip via ICN, ~$722/pp (screenshot 3)
- Modified 4-leg version: HGH→ICN (stay 3 nights), ICN→SFO, SFO→ICN (stay 2 nights), ICN→HGH — slightly more but still excellent value (screenshot 1)
- I built this by changing the round-trip to multi-city in Google Flights and adjusting dates

**What I want the scanner to do automatically:**
When scanning China mainland departure cities and finding cheap round trips with 1 stopover in Seoul/ICN or Tokyo/NRT:
1. Detect the stopover city from the fare data
2. Auto-build a 4-leg multi-city Google Flights URL with:
   - Leg 1: Origin → Stopover (original departure date)
   - Leg 2: Stopover → USA dest (departure date + 2 or 3 days)
   - Leg 3: USA dest → Stopover (original return date)
   - Leg 4: Stopover → Origin (return date + 2 days)
3. Check this price — if it's within 25% of the original round-trip price, flag it as a "stopover stay bonus"
4. Show it in the HTML output with the suggested dates and total price

**Scope:** Only for China mainland departures (not SEA cities), only when stopover is ICN or NRT/TYO, only for fares already in the top affordable list.

**My TFS URL format:** I use protobuf-encoded tfs params. The 4-leg booking URL above uses the `/travel/flights/booking` endpoint.

Please analyze my 3 screenshots and guide me on:
1. How to decode/build the 4-leg multi-city tfs URL in my existing protobuf encoder
2. Where in my pipeline (drill_promising.py?) to add this check
3. The exact Python code to build the 4-leg URL given: origin_cid, stopover_cid, dest_cid, depart_date, nights_at_stopover_out=3, nights_at_stopover_ret=2, return_date

My current protobuf builder for 2-leg round trips:
```python
def build_rt_url(origin_cid, dest_cid, depart, ret_date, cabin=1):
    o = field_bytes(13, origin_cid)
    d = field_bytes(14, dest_cid)
    l1 = field_bytes(2, depart) + field_bytes(13, ...) + field_bytes(14, ...)  # leg 1
    l2 = field_bytes(2, ret_date) + ...  # leg 2
    # encode as protobuf, base64url encode → tfs param
```"""


def take_screenshots(page):
    """Visit each URL and take a full-page screenshot."""
    screenshot_paths = []

    for filename, label, url in URLS:
        print(f"\n[SCREENSHOT] Loading: {label}")
        print(f"  URL: {url[:80]}...")

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            print(f"  Page loaded (domcontentloaded). Waiting 15 seconds for content...")
            time.sleep(15)

            # Try to wait for network idle too
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
                print("  Network idle reached.")
            except Exception:
                print("  Network idle timeout (OK, continuing).")

            save_path = str(SCREENSHOT_DIR / filename)
            page.screenshot(path=save_path, full_page=True)
            print(f"  Saved screenshot: {save_path}")
            screenshot_paths.append(save_path)

        except Exception as e:
            print(f"  ERROR taking screenshot for {label}: {e}")
            # Try to save whatever we have
            try:
                save_path = str(SCREENSHOT_DIR / filename)
                page.screenshot(path=save_path, full_page=True)
                print(f"  Saved partial screenshot: {save_path}")
                screenshot_paths.append(save_path)
            except Exception as e2:
                print(f"  Could not save screenshot: {e2}")

    return screenshot_paths


def upload_files_and_send_message(page, screenshot_paths):
    """Upload screenshots and send message to ChatGPT."""
    print(f"\n[CHATGPT] Navigating to conversation: {CHATGPT_URL}")
    page.goto(CHATGPT_URL, wait_until="domcontentloaded", timeout=60000)
    print("  Waiting 5 seconds for ChatGPT to load...")
    time.sleep(5)

    # Wait for the page to be ready
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
        print("  Network idle.")
    except Exception:
        print("  Network idle timeout (OK).")

    time.sleep(3)

    # Take a screenshot to see current state
    page.screenshot(path=str(SCREENSHOT_DIR / "chatgpt_01_loaded.png"))
    print("  Saved initial ChatGPT screenshot.")

    # Find file upload button
    print("\n[CHATGPT] Looking for file upload button...")

    # Try multiple selectors for the upload button
    upload_selectors = [
        "button[aria-label*='ttach']",
        "button[aria-label*='pload']",
        "button[aria-label*='ile']",
        "input[type='file']",
        "[data-testid*='attach']",
        "[data-testid*='upload']",
        "button[aria-label*='Add']",
        "button.text-token-text-primary",  # common ChatGPT button class
        "label[for*='file']",
        "label[for*='upload']",
    ]

    upload_button = None
    for sel in upload_selectors:
        try:
            elements = page.query_selector_all(sel)
            if elements:
                print(f"  Found element with selector: {sel} ({len(elements)} elements)")
                # For input[type='file'], we use it directly
                if sel == "input[type='file']":
                    upload_button = elements[0]
                    break
                else:
                    upload_button = elements[0]
                    break
        except Exception as e:
            pass

    # Try to find file input directly
    file_input = page.query_selector("input[type='file']")

    if file_input:
        print("  Found direct file input element.")
        # Upload all files
        file_input.set_input_files(screenshot_paths)
        print(f"  Uploaded {len(screenshot_paths)} files via file input.")
        time.sleep(3)
    elif upload_button:
        print(f"  Clicking upload button...")
        upload_button.click()
        time.sleep(2)

        # After click, look for file input
        file_input = page.query_selector("input[type='file']")
        if file_input:
            file_input.set_input_files(screenshot_paths)
            print(f"  Uploaded {len(screenshot_paths)} files.")
            time.sleep(3)
        else:
            print("  No file input found after clicking button.")
    else:
        print("  Could not find upload button. Trying to use page evaluate to find it...")
        # Try using JS to find and interact with file input
        file_input_handle = page.evaluate_handle("""
            () => {
                return document.querySelector('input[type="file"]');
            }
        """)
        print(f"  JS file input handle: {file_input_handle}")

    page.screenshot(path=str(SCREENSHOT_DIR / "chatgpt_02_after_upload_attempt.png"))

    # Now find the message input area
    print("\n[CHATGPT] Looking for message input...")

    message_selectors = [
        "#prompt-textarea",
        "div[contenteditable='true']",
        "textarea[placeholder*='Message']",
        "textarea[placeholder*='message']",
        "div[role='textbox']",
        "textarea",
        "[data-testid='text-input']",
        "p[data-placeholder]",
    ]

    message_input = None
    for sel in message_selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                print(f"  Found message input with selector: {sel}")
                message_input = el
                break
        except Exception as e:
            pass

    if not message_input:
        print("  Could not find message input! Taking debug screenshot...")
        page.screenshot(path=str(SCREENSHOT_DIR / "chatgpt_debug_no_input.png"))
        # Try to get page content for debugging
        content = page.content()
        with open(str(SCREENSHOT_DIR / "chatgpt_debug_content.html"), "w", encoding="utf-8") as f:
            f.write(content[:50000])
        raise Exception("Could not find ChatGPT message input")

    # Click the message input and type
    print("  Clicking message input...")
    message_input.click()
    time.sleep(1)

    # Clear any existing content
    message_input.press("Control+a")
    time.sleep(0.5)

    # Type the message (use keyboard for contenteditable)
    print("  Typing message...")
    # Use fill for textarea, or type for contenteditable
    tag_name = page.evaluate("el => el.tagName.toLowerCase()", message_input)
    print(f"  Input element tag: {tag_name}")

    if tag_name == "textarea":
        message_input.fill(CHATGPT_MESSAGE)
    else:
        # For contenteditable divs, use clipboard paste to avoid typing timeout
        # Set the clipboard content via JS and paste
        page.evaluate("""(text) => {
            navigator.clipboard.writeText(text).catch(() => {
                // Fallback: use execCommand
                const el = document.createElement('textarea');
                el.value = text;
                document.body.appendChild(el);
                el.select();
                document.execCommand('copy');
                document.body.removeChild(el);
            });
        }""", CHATGPT_MESSAGE)
        time.sleep(0.5)
        # Paste into the focused element
        message_input.press("Control+v")
        time.sleep(2)

    print("  Message typed. Waiting 2 seconds...")
    time.sleep(2)

    page.screenshot(path=str(SCREENSHOT_DIR / "chatgpt_03_message_typed.png"))

    # Send the message
    print("\n[CHATGPT] Sending message...")

    # Try to find and click send button
    send_selectors = [
        "button[data-testid='send-button']",
        "button[aria-label='Send message']",
        "button[aria-label='Send prompt']",
        "button[type='submit']",
        "button.bg-black",  # ChatGPT send button styling
        "button[aria-label*='Send']",
        "[data-testid='fruitjuice-send-button']",
    ]

    sent = False
    for sel in send_selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible() and btn.is_enabled():
                print(f"  Clicking send button: {sel}")
                btn.click()
                sent = True
                break
        except Exception as e:
            pass

    if not sent:
        # Try pressing Enter
        print("  No send button found, pressing Enter...")
        message_input.press("Enter")
        sent = True

    print("  Message sent! Waiting for response...")
    page.screenshot(path=str(SCREENSHOT_DIR / "chatgpt_04_sent.png"))

    # Wait for response - ChatGPT with thinking mode can take 60-90 seconds
    # Wait for the stop button to appear (indicates generating)
    print("  Waiting for stop button to appear (generation started)...")
    try:
        page.wait_for_selector(
            "button[aria-label='Stop streaming'], button[aria-label='Stop generating'], [data-testid='stop-button']",
            timeout=30000,
            state="visible"
        )
        print("  Stop button appeared - response is being generated.")
    except Exception:
        print("  Stop button not found within 30s, waiting anyway...")

    # Now wait for the stop button to disappear (generation finished)
    print("  Waiting for generation to complete (stop button to disappear)...")
    max_wait = 180  # 3 minutes max
    check_interval = 5
    elapsed = 0

    while elapsed < max_wait:
        time.sleep(check_interval)
        elapsed += check_interval

        # Check if stop button is still visible
        stop_btn = None
        for stop_sel in ["button[aria-label='Stop streaming']", "button[aria-label='Stop generating']", "[data-testid='stop-button']"]:
            try:
                el = page.query_selector(stop_sel)
                if el and el.is_visible():
                    stop_btn = el
                    break
            except Exception:
                pass

        if stop_btn is None:
            print(f"  Stop button gone after {elapsed}s - response complete!")
            break
        else:
            print(f"  Still generating... ({elapsed}s elapsed)")

    # Extra wait to ensure everything is rendered
    time.sleep(5)

    page.screenshot(path=str(SCREENSHOT_DIR / "chatgpt_05_response_complete.png"), full_page=True)
    print("  Saved response screenshot.")

    # Extract the response text
    print("\n[CHATGPT] Extracting response text...")

    response_text = ""

    # Try multiple selectors for the response
    response_selectors = [
        "div[data-message-author-role='assistant']",
        "div.agent-turn",
        "[data-testid='conversation-turn-3']",  # might be 3rd turn
        "div.markdown",
        "div.prose",
    ]

    for sel in response_selectors:
        try:
            elements = page.query_selector_all(sel)
            if elements:
                # Get the last assistant message
                last_el = elements[-1]
                text = last_el.inner_text()
                if len(text) > 100:  # Must have substantial content
                    response_text = text
                    print(f"  Got response text using selector: {sel} ({len(text)} chars)")
                    break
        except Exception as e:
            pass

    if not response_text:
        # Try getting all conversation turns
        try:
            turns = page.query_selector_all("[data-testid^='conversation-turn']")
            if turns:
                last_turn = turns[-1]
                response_text = last_turn.inner_text()
                print(f"  Got response from conversation turns ({len(response_text)} chars)")
        except Exception as e:
            print(f"  Error getting conversation turns: {e}")

    if not response_text:
        # Last resort: get all text from main content area
        try:
            main = page.query_selector("main")
            if main:
                response_text = main.inner_text()
                print(f"  Got text from main element ({len(response_text)} chars)")
        except Exception as e:
            print(f"  Error getting main content: {e}")

    return response_text


def main():
    print("=" * 60)
    print("STOPOVER STAY CHATGPT CONSULTATION SCRIPT")
    print("=" * 60)

    with sync_playwright() as p:
        print("\n[CONNECT] Connecting to Chrome via CDP at http://127.0.0.1:9222...")
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        print(f"  Connected! Browser version: {browser.version}")

        # Use existing context or create new one
        contexts = browser.contexts
        if contexts:
            context = contexts[0]
            print(f"  Using existing context with {len(context.pages)} pages.")
        else:
            context = browser.new_context()
            print("  Created new context.")

        # Create a new page for our work
        page = context.new_page()

        # Set viewport
        page.set_viewport_size({"width": 1400, "height": 900})

        # Phase 1: Take screenshots of all 3 URLs
        print("\n" + "=" * 60)
        print("PHASE 1: TAKING GOOGLE FLIGHTS SCREENSHOTS")
        print("=" * 60)

        screenshot_paths = take_screenshots(page)

        print(f"\n  Captured {len(screenshot_paths)} screenshots:")
        for p_path in screenshot_paths:
            print(f"    - {p_path}")

        if len(screenshot_paths) < 3:
            print("  WARNING: Not all screenshots captured!")

        # Phase 2: ChatGPT consultation
        print("\n" + "=" * 60)
        print("PHASE 2: CHATGPT CONSULTATION")
        print("=" * 60)

        response_text = upload_files_and_send_message(page, screenshot_paths)

        # Save the response
        if response_text:
            with open(str(OUTPUT_FILE), "w", encoding="utf-8") as f:
                f.write("ChatGPT Response - Stopover Stay Feature Guidance\n")
                f.write("=" * 60 + "\n")
                f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")
                f.write(response_text)

            print(f"\n[DONE] Response saved to: {OUTPUT_FILE}")
            print(f"  Response length: {len(response_text)} characters")
        else:
            print("\n[WARNING] No response text extracted!")
            # Save debug info
            with open(str(OUTPUT_FILE), "w", encoding="utf-8") as f:
                f.write("ERROR: Could not extract ChatGPT response text.\n")
                f.write("Please check screenshots in stopover_screenshots/ for debugging.\n")

        print("\n[DONE] Script complete!")
        print(f"  Screenshots: {SCREENSHOT_DIR}")
        print(f"  Response: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
