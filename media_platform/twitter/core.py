import asyncio
import os
from typing import Optional

from playwright.async_api import BrowserContext, BrowserType, Playwright, async_playwright

import config
from base.base_crawler import AbstractCrawler
from tools import utils
from .client import TwitterClient
from .login import TwitterLogin


class TwitterCrawler(AbstractCrawler):
    def __init__(self):
        super().__init__()
        self.index_url = "https://x.com"
        self.client: Optional[TwitterClient] = None

    async def start(self):
        utils.logger.info("[TwitterCrawler.start] Start Twitter crawler ...")
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=config.HEADLESS)
            self.browser_context = await browser.new_context(storage_state=config.COOKIES if config.SAVE_LOGIN_STATE else None)
            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url)

            # Login
            login_obj = TwitterLogin(
                login_type=config.LOGIN_TYPE,
                browser_context=self.browser_context,
                context_page=self.context_page,
                cookie_str=config.COOKIES,
            )
            await login_obj.begin()

            # Create client
            cookies = await self.browser_context.cookies()
            _, cookie_dict = utils.convert_cookies(cookies)
            self.client = TwitterClient(cookie_dict=cookie_dict)

            if config.CRAWLER_TYPE == "creator":
                await self.get_creators_and_notes()
            else:
                utils.logger.warning(f"Twitter crawler currently only supports 'creator' type, but got '{config.CRAWLER_TYPE}'")

            utils.logger.info("[TwitterCrawler.start] Twitter crawler finished.")

    async def get_creators_and_notes(self):
        """Fetch tweets for creators specified in config."""
        from store.twitter import update_twitter_note
        from model.m_twitter import TwitterNote
        utils.logger.info("[TwitterCrawler.get_creators_and_notes] Start fetching tweets for creators...")
        for user_id in config.TWITTER_CREATOR_ID_LIST:
            utils.logger.info(f"[TwitterCrawler.get_creators_and_notes] Fetching tweets for user ID: {user_id}")
            tweets_data = await self.client.get_tweets_by_user(user_id=user_id)
            if not tweets_data:
                continue

            # For now, we only process the first timeline instruction
            instructions = tweets_data.get("data", {}).get("user", {}).get("result", {}).get("timeline_v2", {}).get("timeline", {}).get("instructions", [])
            for instruction in instructions:
                if instruction.get("type") == "TimelineAddEntries":
                    entries = instruction.get("entries", [])
                    for entry in entries:
                        content = entry.get("content", {})
                        if content.get("entryType") == "TimelineTimelineItem":
                            item_content = content.get("itemContent", {})
                            tweet_results = item_content.get("tweet_results", {})
                            result = tweet_results.get("result", {})
                            legacy = result.get("legacy", {})
                            if legacy:
                                note = TwitterNote(
                                    tweet_id=legacy.get("id_str"),
                                    user_id=legacy.get("user_id_str"),
                                    text=legacy.get("full_text"),
                                    created_at=legacy.get("created_at"),
                                )
                                await update_twitter_note(note.model_dump())
                    break # only process first batch of tweets

    async def search(self):
        utils.logger.info("[TwitterCrawler.search] Twitter search not implemented yet")
        pass

    async def launch_browser(self, chromium: BrowserType, playwright_proxy: Optional[dict], user_agent: Optional[str],
                             headless: bool = True) -> BrowserContext:
        """Launch browser and create browser context"""
        utils.logger.info(
            "[TwitterCrawler.launch_browser] Begin create browser context ..."
        )
        if config.SAVE_LOGIN_STATE:
            user_data_dir = os.path.join(
                os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM
            )
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
            )
            return browser_context
        else:
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy)
            browser_context = await browser.new_context(
                viewport={"width": 1920, "height": 1080}, user_agent=user_agent
            )
            return browser_context
