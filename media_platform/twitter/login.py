import asyncio
from typing import Optional

from playwright.async_api import BrowserContext, Page

from base.base_crawler import AbstractLogin
from tools import utils
import config


class TwitterLogin(AbstractLogin):
    def __init__(self,
                 login_type: str,
                 browser_context: BrowserContext,
                 context_page: Page,
                 cookie_str: str = ""
                 ):
        config.LOGIN_TYPE = login_type
        self.browser_context = browser_context
        self.context_page = context_page
        self.cookie_str = cookie_str

    async def begin(self):
        """Start login twitter"""
        utils.logger.info("[TwitterLogin.begin] Begin login twitter ...")
        if config.LOGIN_TYPE == "cookie":
            await self.login_by_cookies()
        else:
            raise ValueError("[TwitterLogin.begin] Invalid Login Type Currently only supported cookie ...")

    async def login_by_qrcode(self):
        raise NotImplementedError("Twitter does not support QR code login.")

    async def login_by_mobile(self):
        raise NotImplementedError("Twitter mobile login not implemented.")

    async def login_by_cookies(self):
        """login twitter website by cookies"""
        utils.logger.info("[TwitterLogin.login_by_cookies] Begin login twitter by cookie ...")
        if not self.cookie_str:
            raise ValueError("Cookie string is empty, please fill it in config.py")

        cookies = utils.convert_str_cookie_to_dict(self.cookie_str)
        # Add more domains if needed
        for key, value in cookies.items():
            await self.browser_context.add_cookies([{
                'name': key,
                'value': value,
                'domain': ".twitter.com",
                'path': "/"
            }])
        utils.logger.info("[TwitterLogin.login_by_cookies] Successfully added cookies.")
