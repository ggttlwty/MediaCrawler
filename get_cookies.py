import asyncio
import json
from playwright.async_api import async_playwright
import config
from media_platform.xhs.login import XiaoHongShuLogin
from tools import utils

async def main():
    """
    This script launches a browser, allows the user to log in,
    and then saves the necessary session information to a file.
    """
    platform = config.PLATFORM
    login_type = config.LOGIN_TYPE

    utils.logger.info(f"Starting login process for platform: {platform} using method: {login_type}")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False) # Must not be headless for login
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://www.xiaohongshu.com")

        login_obj = None
        if platform == 'xhs':
            login_obj = XiaoHongShuLogin(
                login_type=login_type,
                browser_context=context,
                context_page=page,
                cookie_str="", # Start fresh
            )
        else:
            utils.logger.error(f"Platform {platform} not supported by this script yet.")
            await browser.close()
            return

        try:
            await login_obj.begin()
            utils.logger.info("Login successful!")

            # Fetch cookies and local storage
            cookies = await context.cookies()
            local_storage = await page.evaluate("() => window.localStorage")

            session_data = {
                "cookies": cookies,
                "local_storage": local_storage
            }

            # Save session data to file
            session_file = f"{platform}_session.json"
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=4)

            utils.logger.info(f"Session data successfully saved to {session_file}")

        except Exception as e:
            utils.logger.error(f"An error occurred during the login process: {e}")
        finally:
            utils.logger.info("Closing browser in 10 seconds...")
            await asyncio.sleep(10)
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
