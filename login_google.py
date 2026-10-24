"""
One-Time Google Login Helper for NexAgent.
Launches a real Chrome window for manual Google account login and securely saves
the authenticated storage state to ./data/browser_profile/default_storage_state.json
so you NEVER have to log in again during tasks!
"""
import os
import sys
import asyncio
import logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("google_login")

STORAGE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "browser_profile", "default_storage_state.json"))
PROFILE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "browser_profile", "google_chrome_profile"))

async def login():
    os.makedirs(os.path.dirname(STORAGE_PATH), exist_ok=True)
    os.makedirs(PROFILE_DIR, exist_ok=True)

    print("=" * 70)
    print(" NEXAGENT GOOGLE LOGIN HELPER")
    print("=" * 70)
    print("1. A real Google Chrome window will open.")
    print("2. Enter your Google email, password, and complete 2-Step Verification.")
    print("3. Once logged in, your session cookies & credentials will be saved automatically.")
    print("=" * 70)

    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                channel="chrome",
                headless=False,
                viewport={"width": 1280, "height": 800},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-first-run",
                    "--no-service-autorun",
                ],
                ignore_default_args=["--enable-automation"]
            )
        except Exception as e:
            logger.warning("Could not launch with channel='chrome': %s. Retrying with default chromium...", e)
            context = await p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                headless=False,
                viewport={"width": 1280, "height": 800},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-first-run",
                    "--no-service-autorun",
                ],
                ignore_default_args=["--enable-automation"]
            )

        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://accounts.google.com/")

        logger.info("Waiting for you to complete sign-in in the opened Chrome window...")

        # Poll until user has signed in
        for i in range(120): # wait up to 4 minutes
            await asyncio.sleep(2.0)
            try:
                cookies = await context.cookies(["https://accounts.google.com", "https://google.com"])
                has_auth = any(c.get("name") in ("SID", "HSID", "SSID", "__Secure-1PSID", "__Secure-3PSID") for c in cookies)
                current_url = (page.url or "").lower()
                if has_auth or ("myaccount.google.com" in current_url and not any(k in current_url for k in ("signin", "servicelogin"))):
                    logger.info("Google login detected successfully!")
                    break
            except Exception:
                pass
        else:
            logger.warning("Login timeout reached (4 minutes). Saving current state...")

        # Persist storage state
        await context.storage_state(path=STORAGE_PATH)
        print("\n" + "=" * 70)
        print(f" SUCCESS! Google account state saved to:\n {STORAGE_PATH}")
        print(" All future tasks in NexAgent will now stay logged in automatically!")
        print("=" * 70 + "\n")

        await context.close()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(login())
