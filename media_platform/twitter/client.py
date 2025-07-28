import json
from typing import Any, Dict

import httpx
from playwright.async_api import BrowserContext

from base.base_crawler import AbstractApiClient
from tools import utils
from .field import BEARER_TOKEN, USER_TWEETS_URL


class TwitterClient(AbstractApiClient):
    def __init__(self, proxies=None, cookie_dict: Dict = None):
        self.proxies = proxies
        self.cookie_dict = cookie_dict or {}
        self.headers = self._get_headers()

    def _get_headers(self) -> Dict:
        # Default headers for Twitter API requests
        headers = {
            "Authorization": f"Bearer {BEARER_TOKEN}",
            "Content-Type": "application/json",
            "Referer": "https://twitter.com/",
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "en",
        }
        # Add CSRF token if available from cookies
        if "ct0" in self.cookie_dict:
            headers["x-csrf-token"] = self.cookie_dict["ct0"]
        return headers

    async def request(self, method, url, **kwargs) -> dict:
        async with httpx.AsyncClient(proxies=self.proxies, headers=self.headers) as client:
            response = await client.request(method, url, **kwargs)
            if response.status_code == 200:
                return response.json()
            else:
                utils.logger.error(f"[TwitterClient.request] Request failed with status {response.status_code}: {response.text}")
                return {}

    async def get_tweets_by_user(self, user_id: str, count: int = 20, cursor: str = None) -> Dict:
        """Fetch tweets for a given user ID."""
        variables = {
            "userId": user_id,
            "count": count,
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True
        }
        if cursor:
            variables["cursor"] = cursor

        features = {
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "tweetypie_unmention_optimization_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": False,
            "tweet_awards_web_tipping_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
g            "responsive_web_media_download_video_enabled": False,
            "responsive_web_enhance_cards_enabled": False
        }

        params = {
            "variables": json.dumps(variables),
            "features": json.dumps(features)
        }
        return await self.request("GET", USER_TWEETS_URL, params=params)


    async def update_cookies(self, browser_context: BrowserContext):
        cookies = await browser_context.cookies()
        _, self.cookie_dict = utils.convert_cookies(cookies)
        self.headers = self._get_headers()
        utils.logger.info("[TwitterClient.update_cookies] Cookies updated.")
