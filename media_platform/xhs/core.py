# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。


import asyncio
import os
import random
import time
from asyncio import Task
from typing import Dict, List, Optional, Tuple

from playwright.async_api import (
    BrowserContext,
    BrowserType,
    Page,
    Playwright,
    async_playwright,
)
from tenacity import RetryError

import config
from base.base_crawler import AbstractCrawler
from config import CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES
from model.m_xiaohongshu import NoteUrlInfo
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import xhs as xhs_store
from tools import utils
from tools.cdp_browser import CDPBrowserManager
from var import crawler_type_var, source_keyword_var

from .client import XiaoHongShuClient
from .exception import DataFetchError
from .field import SearchSortType
from .help import parse_note_info_from_note_url, get_search_id
from .login import XiaoHongShuLogin


from tools.account_manager import AccountManager, Account


class XiaoHongShuCrawler(AbstractCrawler):
    def __init__(self) -> None:
        self.index_url = "https://www.xiaohongshu.com"
        self.account_manager = AccountManager(platform=config.PLATFORM)

    async def start(self) -> None:
        """
        Start the crawler, this method will create a worker for each concurrent task.
        """
        utils.logger.info(f"[XiaoHongShuCrawler.start] Begin start xiaohongshu crawler, CRAWLER_TYPE={config.CRAWLER_TYPE}")

        # Create a semaphore to control the number of concurrent workers
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)

        # Create a task queue
        task_queue = asyncio.Queue()

        # Add tasks to the queue
        if config.CRAWLER_TYPE == "search":
            for keyword in config.KEYWORDS.split(","):
                await task_queue.put(("search", keyword))
        elif config.CRAWLER_TYPE == "creator":
            for user_id in config.XHS_CREATOR_ID_LIST:
                await task_queue.put(("creator", user_id))
        elif config.CRAWLER_TYPE == "detail":
             for note_url in config.XHS_SPECIFIED_NOTE_URL_LIST:
                 await task_queue.put(("detail", note_url))

        # Create worker tasks
        workers = [
            asyncio.create_task(self.worker(f"worker-{i}", task_queue, semaphore))
            for i in range(config.MAX_CONCURRENCY_NUM)
        ]

        # Wait for all tasks in the queue to be processed
        await task_queue.join()

        # Cancel worker tasks
        for worker in workers:
            worker.cancel()

        await asyncio.gather(*workers, return_exceptions=True)
        utils.logger.info("[XiaoHongShuCrawler.start] Xhs Crawler finished ...")

    async def worker(self, name: str, queue: asyncio.Queue, semaphore: asyncio.Semaphore):
        """
        A worker that fetches tasks from the queue and processes them.
        """
        while True:
            try:
                async with semaphore:
                    task_type, task_value = await queue.get()
                    utils.logger.info(f"[{name}] Got task: {task_type} - {task_value}")

                    account = await self.account_manager.get_account()
                    if not account:
                        utils.logger.error(f"[{name}] No available accounts, stopping worker.")
                        break

                    try:
                        await self.process_task(account, task_type, task_value)
                        await self.account_manager.release_account(account)
                    except Exception as e:
                        utils.logger.error(f"[{name}] Error processing task {task_type} - {task_value} with account {account.id}: {e}")
                        # Mark account as banned if a specific exception occurs, otherwise just release it
                        await self.account_manager.release_account(account, is_banned=isinstance(e, DataFetchError))

                    queue.task_done()
            except asyncio.CancelledError:
                break

    async def process_task(self, account: Account, task_type: str, task_value: str):
        """
        Process a single task (e.g., search for a keyword, fetch a creator's notes).
        """
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            if account.proxy:
                # Use account-specific proxy
                ip_proxy_info = utils.parse_proxy_url(account.proxy)
            else:
                # Use global proxy pool
                ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=True)
                ip_proxy_info = await ip_proxy_pool.get_proxy()

            playwright_proxy_format, httpx_proxy_format = self.format_proxy_info(ip_proxy_info)

        user_agent = account.user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"

        async with async_playwright() as playwright:
            browser_context = await self.launch_browser(
                playwright.chromium,
                playwright_proxy_format,
                user_agent,
                headless=config.HEADLESS,
                user_data_dir_suffix=account.id  # Use account id for separate sessions
            )
            context_page = await browser_context.new_page()
            await context_page.goto(self.index_url)

            xhs_client = await self.create_xhs_client(httpx_proxy_format, context_page, account.cookies)
            if not await xhs_client.pong():
                login_obj = XiaoHongShuLogin(
                    login_type="cookie", # Force cookie login for workers
                    browser_context=browser_context,
                    context_page=context_page,
                    cookie_str=account.cookies,
                )
                await login_obj.begin()
                await xhs_client.update_cookies(browser_context)

            if task_type == "search":
                await self.search(keyword=task_value, xhs_client=xhs_client)
            elif task_type == "creator":
                await self.get_creators_and_notes(user_id=task_value, xhs_client=xhs_client)
            elif task_type == "detail":
                await self.get_specified_notes(note_url=task_value, xhs_client=xhs_client)

            await browser_context.close()

    async def search(self) -> None:
        """Search for notes and retrieve their comment information."""
        from tools.progress_manager import load_progress, save_progress
        progress = await load_progress()
        if "search" not in progress:
            progress["search"] = {}

        utils.logger.info(
            "[XiaoHongShuCrawler.search] Begin search xiaohongshu keywords"
        )
        xhs_limit_count = 20
        if config.CRAWLER_MAX_NOTES_COUNT < xhs_limit_count:
            config.CRAWLER_MAX_NOTES_COUNT = xhs_limit_count

        for keyword in config.KEYWORDS.split(","):
            source_keyword_var.set(keyword)
            if keyword not in progress["search"]:
                progress["search"][keyword] = {"page": 1, "note_ids": []}

            start_page = progress["search"][keyword]["page"]
            page = start_page

            utils.logger.info(
                f"[XiaoHongShuCrawler.search] Current search keyword: {keyword}, start page: {start_page}"
            )
            search_id = get_search_id()
            while (
                    page - start_page + 1
            ) * xhs_limit_count <= config.CRAWLER_MAX_NOTES_COUNT:
                try:
                    utils.logger.info(
                        f"[XiaoHongShuCrawler.search] search xhs keyword: {keyword}, page: {page}"
                    )
                    note_ids: List[str] = []
                    xsec_tokens: List[str] = []
                    notes_res = await self.xhs_client.get_note_by_keyword(
                        keyword=keyword,
                        search_id=search_id,
                        page=page,
                        sort=(
                            SearchSortType(config.SORT_TYPE)
                            if config.SORT_TYPE != ""
                            else SearchSortType.GENERAL
                        ),
                    )
                    utils.logger.info(
                        f"[XiaoHongShuCrawler.search] Search notes res:{notes_res}"
                    )
                    if not notes_res or not notes_res.get("has_more", False):
                        utils.logger.info("No more content!")
                        break
                    semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
                    task_list = [
                        self.get_note_detail_async_task(
                            note_id=post_item.get("id"),
                            xsec_source=post_item.get("xsec_source"),
                            xsec_token=post_item.get("xsec_token"),
                            semaphore=semaphore,
                        )
                        for post_item in notes_res.get("items", {})
                        if post_item.get("model_type") not in ("rec_query", "hot_query") and post_item.get("id") not in progress["search"][keyword]["note_ids"]
                    ]
                    note_details = await asyncio.gather(*task_list)
                    for note_detail in note_details:
                        if note_detail:
                            await xhs_store.update_xhs_note(note_detail)
                            await self.get_notice_media(note_detail)
                            note_id = note_detail.get("note_id")
                            note_ids.append(note_id)
                            progress["search"][keyword]["note_ids"].append(note_id)
                            xsec_tokens.append(note_detail.get("xsec_token"))

                    page += 1
                    progress["search"][keyword]["page"] = page
                    await save_progress(progress)

                    utils.logger.info(
                        f"[XiaoHongShuCrawler.search] Note details: {note_details}"
                    )
                    await self.batch_get_note_comments(note_ids, xsec_tokens)
                except DataFetchError:
                    utils.logger.error(
                        "[XiaoHongShuCrawler.search] Get note detail error"
                    )
                    break

    async def get_creators_and_notes(self) -> None:
        """Get creator's notes and retrieve their comment information."""
        from tools.progress_manager import load_progress, save_progress
        progress = await load_progress()
        if "creator" not in progress:
            progress["creator"] = {}

        utils.logger.info(
            "[XiaoHongShuCrawler.get_creators_and_notes] Begin get xiaohongshu creators"
        )
        for user_id in config.XHS_CREATOR_ID_LIST:
            if user_id not in progress["creator"]:
                progress["creator"][user_id] = {"cursor": "", "note_ids": []}

            start_cursor = progress["creator"][user_id]["cursor"]

            # get creator detail info from web html content
            createor_info: Dict = await self.xhs_client.get_creator_info(
                user_id=user_id
            )
            if createor_info:
                await xhs_store.save_creator(user_id, creator=createor_info)

            # When proxy is not enabled, increase the crawling interval
            if config.ENABLE_IP_PROXY:
                crawl_interval = random.random()
            else:
                crawl_interval = random.uniform(1, config.CRAWLER_MAX_SLEEP_SEC)

            async def save_creator_progress_callback(notes: List[Dict]):
                new_cursor = notes[-1].get("cursor") if notes else ""
                if new_cursor:
                    progress["creator"][user_id]["cursor"] = new_cursor
                    await save_progress(progress)
                await self.fetch_creator_notes_detail(notes)

            # Get all note information of the creator
            all_notes_list = await self.xhs_client.get_all_notes_by_creator(
                user_id=user_id,
                crawl_interval=crawl_interval,
                callback=save_creator_progress_callback,
                start_cursor=start_cursor
            )

            note_ids = []
            xsec_tokens = []
            for note_item in all_notes_list:
                note_ids.append(note_item.get("note_id"))
                xsec_tokens.append(note_item.get("xsec_token"))
            await self.batch_get_note_comments(note_ids, xsec_tokens)

    async def fetch_creator_notes_detail(self, note_list: List[Dict]):
        """
        Concurrently obtain the specified post list and save the data
        """
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = [
            self.get_note_detail_async_task(
                note_id=post_item.get("note_id"),
                xsec_source=post_item.get("xsec_source"),
                xsec_token=post_item.get("xsec_token"),
                semaphore=semaphore,
            )
            for post_item in note_list
        ]

        note_details = await asyncio.gather(*task_list)
        for note_detail in note_details:
            if note_detail:
                await xhs_store.update_xhs_note(note_detail)

    async def get_specified_notes(self):
        """
        Get the information and comments of the specified post
        must be specified note_id, xsec_source, xsec_token⚠️⚠️⚠️
        Returns:

        """
        get_note_detail_task_list = []
        for full_note_url in config.XHS_SPECIFIED_NOTE_URL_LIST:
            note_url_info: NoteUrlInfo = parse_note_info_from_note_url(full_note_url)
            utils.logger.info(
                f"[XiaoHongShuCrawler.get_specified_notes] Parse note url info: {note_url_info}"
            )
            crawler_task = self.get_note_detail_async_task(
                note_id=note_url_info.note_id,
                xsec_source=note_url_info.xsec_source,
                xsec_token=note_url_info.xsec_token,
                semaphore=asyncio.Semaphore(config.MAX_CONCURRENCY_NUM),
            )
            get_note_detail_task_list.append(crawler_task)

        need_get_comment_note_ids = []
        xsec_tokens = []
        note_details = await asyncio.gather(*get_note_detail_task_list)
        for note_detail in note_details:
            if note_detail:
                need_get_comment_note_ids.append(note_detail.get("note_id", ""))
                xsec_tokens.append(note_detail.get("xsec_token", ""))
                await xhs_store.update_xhs_note(note_detail)
        await self.batch_get_note_comments(need_get_comment_note_ids, xsec_tokens)

    async def get_note_detail_async_task(
            self,
            note_id: str,
            xsec_source: str,
            xsec_token: str,
            semaphore: asyncio.Semaphore,
    ) -> Optional[Dict]:
        """Get note detail

        Args:
            note_id:
            xsec_source:
            xsec_token:
            semaphore:

        Returns:
            Dict: note detail
        """
        note_detail = None
        async with semaphore:
            try:
                utils.logger.info(
                    f"[get_note_detail_async_task] Begin get note detail, note_id: {note_id}"
                )

                try:
                    note_detail = await self.xhs_client.get_note_by_id(
                        note_id, xsec_source, xsec_token
                    )
                except RetryError as e:
                    pass

                if not note_detail:
                    note_detail = await self.xhs_client.get_note_by_id_from_html(note_id, xsec_source, xsec_token,
                                                                                 enable_cookie=False)
                    if not note_detail:
                        raise Exception(f"[get_note_detail_async_task] Failed to get note detail, Id: {note_id}")

                note_detail.update(
                    {"xsec_token": xsec_token, "xsec_source": xsec_source}
                )
                return note_detail

            except DataFetchError as ex:
                utils.logger.error(
                    f"[XiaoHongShuCrawler.get_note_detail_async_task] Get note detail error: {ex}"
                )
                return None
            except KeyError as ex:
                utils.logger.error(
                    f"[XiaoHongShuCrawler.get_note_detail_async_task] have not fund note detail note_id:{note_id}, err: {ex}"
                )
                return None

    async def batch_get_note_comments(
            self, note_list: List[str], xsec_tokens: List[str]
    ):
        """Batch get note comments"""
        if not config.ENABLE_GET_COMMENTS:
            utils.logger.info(
                f"[XiaoHongShuCrawler.batch_get_note_comments] Crawling comment mode is not enabled"
            )
            return

        utils.logger.info(
            f"[XiaoHongShuCrawler.batch_get_note_comments] Begin batch get note comments, note list: {note_list}"
        )
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list: List[Task] = []
        for index, note_id in enumerate(note_list):
            task = asyncio.create_task(
                self.get_comments(
                    note_id=note_id, xsec_token=xsec_tokens[index], semaphore=semaphore
                ),
                name=note_id,
            )
            task_list.append(task)
        await asyncio.gather(*task_list)

    async def get_comments(
            self, note_id: str, xsec_token: str, semaphore: asyncio.Semaphore
    ):
        """Get note comments with keyword filtering and quantity limitation"""
        async with semaphore:
            utils.logger.info(
                f"[XiaoHongShuCrawler.get_comments] Begin get note id comments {note_id}"
            )
            # When proxy is not enabled, increase the crawling interval
            if config.ENABLE_IP_PROXY:
                crawl_interval = random.random()
            else:
                crawl_interval = random.uniform(1, config.CRAWLER_MAX_SLEEP_SEC)
            await self.xhs_client.get_note_all_comments(
                note_id=note_id,
                xsec_token=xsec_token,
                crawl_interval=crawl_interval,
                callback=xhs_store.batch_update_xhs_note_comments,
                max_count=CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
            )

    @staticmethod
    def format_proxy_info(
            ip_proxy_info: IpInfoModel,
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        """format proxy info for playwright and httpx"""
        playwright_proxy = {
            "server": f"{ip_proxy_info.protocol}{ip_proxy_info.ip}:{ip_proxy_info.port}",
            "username": ip_proxy_info.user,
            "password": ip_proxy_info.password,
        }
        httpx_proxy = {
            f"{ip_proxy_info.protocol}": f"http://{ip_proxy_info.user}:{ip_proxy_info.password}@{ip_proxy_info.ip}:{ip_proxy_info.port}"
        }
        return playwright_proxy, httpx_proxy

    async def create_xhs_client(self, httpx_proxy: Optional[str]) -> XiaoHongShuClient:
        """Create xhs client"""
        utils.logger.info(
            "[XiaoHongShuCrawler.create_xhs_client] Begin create xiaohongshu API client ..."
        )
        cookie_str, cookie_dict = utils.convert_cookies(
            await self.browser_context.cookies()
        )
        xhs_client_obj = XiaoHongShuClient(
            proxies=httpx_proxy,
            headers={
                "accept": "application/json, text/plain, */*",
                "accept-language": "zh-CN,zh;q=0.9",
                "cache-control": "no-cache",
                "content-type": "application/json;charset=UTF-8",
                "origin": "https://www.xiaohongshu.com",
                "pragma": "no-cache",
                "priority": "u=1, i",
                "referer": "https://www.xiaohongshu.com/",
                "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                "Cookie": cookie_str,
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
        )
        return xhs_client_obj

    async def launch_browser(
            self,
            chromium: BrowserType,
            playwright_proxy: Optional[Dict],
            user_agent: Optional[str],
            headless: bool = True,
            user_data_dir_suffix: str = ""
    ) -> BrowserContext:
        """Launch browser and create browser context"""
        utils.logger.info(
            "[XiaoHongShuCrawler.launch_browser] Begin create browser context ..."
        )
        if config.SAVE_LOGIN_STATE:
            user_data_dir = os.path.join(
                os.getcwd(), "browser_data", f"{config.PLATFORM}_{user_data_dir_suffix}"
            )
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,  # type: ignore
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
            )
            return browser_context
        else:
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy)  # type: ignore
            browser_context = await browser.new_context(
                viewport={"width": 1920, "height": 1080}, user_agent=user_agent
            )
            return browser_context

    async def launch_browser_with_cdp(
            self,
            playwright: Playwright,
            playwright_proxy: Optional[Dict],
            user_agent: Optional[str],
            headless: bool = True,
    ) -> BrowserContext:
        """
        使用CDP模式启动浏览器
        """
        try:
            self.cdp_manager = CDPBrowserManager()
            browser_context = await self.cdp_manager.launch_and_connect(
                playwright=playwright,
                playwright_proxy=playwright_proxy,
                user_agent=user_agent,
                headless=headless,
            )

            # 显示浏览器信息
            browser_info = await self.cdp_manager.get_browser_info()
            utils.logger.info(f"[XiaoHongShuCrawler] CDP浏览器信息: {browser_info}")

            return browser_context

        except Exception as e:
            utils.logger.error(
                f"[XiaoHongShuCrawler] CDP模式启动失败，回退到标准模式: {e}"
            )
            # 回退到标准模式
            chromium = playwright.chromium
            return await self.launch_browser(
                chromium, playwright_proxy, user_agent, headless
            )

    async def close(self):
        """Close browser context"""
        # 如果使用CDP模式，需要特殊处理
        if self.cdp_manager:
            await self.cdp_manager.cleanup()
            self.cdp_manager = None
        else:
            await self.browser_context.close()
        utils.logger.info("[XiaoHongShuCrawler.close] Browser context closed ...")

    async def get_notice_media(self, note_detail: Dict):
        if not config.ENABLE_GET_IMAGES:
            utils.logger.info(
                f"[XiaoHongShuCrawler.get_notice_media] Crawling image mode is not enabled"
            )
            return
        await self.get_note_images(note_detail)
        await self.get_notice_video(note_detail)

    async def get_note_images(self, note_item: Dict):
        """
        get note images. please use get_notice_media
        :param note_item:
        :return:
        """
        if not config.ENABLE_GET_IMAGES:
            return
        note_id = note_item.get("note_id")
        image_list: List[Dict] = note_item.get("image_list", [])

        for img in image_list:
            if img.get("url_default") != "":
                img.update({"url": img.get("url_default")})

        if not image_list:
            return
        picNum = 0
        for pic in image_list:
            url = pic.get("url")
            if not url:
                continue
            content = await self.xhs_client.get_note_media(url)
            if content is None:
                continue
            extension_file_name = f"{picNum}.jpg"
            picNum += 1
            await xhs_store.update_xhs_note_image(note_id, content, extension_file_name)

    async def get_notice_video(self, note_item: Dict):
        """
        get note images. please use get_notice_media
        :param note_item:
        :return:
        """
        if not config.ENABLE_GET_IMAGES:
            return
        note_id = note_item.get("note_id")

        videos = xhs_store.get_video_url_arr(note_item)

        if not videos:
            return
        videoNum = 0
        for url in videos:
            content = await self.xhs_client.get_note_media(url)
            if content is None:
                continue
            extension_file_name = f"{videoNum}.mp4"
            videoNum += 1
            await xhs_store.update_xhs_note_image(note_id, content, extension_file_name)
