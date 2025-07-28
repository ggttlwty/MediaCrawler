"""
Account Pool Configuration
Each account dictionary can have the following keys:
- 'id': A unique identifier for the account (e.g., username or a number).
- 'cookies': The cookie string for this account.
- 'proxy': (Optional) A specific proxy to use for this account, in the format "http://user:pass@host:port".
           If not provided, a proxy will be drawn from the global IP pool if ENABLE_IP_PROXY is True.
- 'user_agent': (Optional) A specific user agent for this account.
"""

XHS_ACCOUNT_POOL = [
    {
        "id": "user_1",
        "cookies": "your_cookie_string_for_user_1",
        "proxy": None,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    },
    # {
    #     "id": "user_2",
    #     "cookies": "your_cookie_string_for_user_2",
    #     "proxy": "http://user2:pass2@proxy.example.com:8080",
    #     "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36",
    # },
    # Add more accounts as needed
]

DY_ACCOUNT_POOL = []
WEIBO_ACCOUNT_POOL = []
# ... add pools for other platforms as needed
