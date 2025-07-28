import asyncio
import random
from enum import Enum
from typing import Dict, List, Optional, Any

from . import utils
import config
from config.account_pool_config import XHS_ACCOUNT_POOL, DY_ACCOUNT_POOL # Import other pools as needed

class AccountStatus(Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    BANNED = "banned"

class Account:
    def __init__(self, account_info: Dict[str, Any]):
        self.id = account_info.get("id")
        self.cookies = account_info.get("cookies")
        self.proxy = account_info.get("proxy")
        self.user_agent = account_info.get("user_agent")
        self.status = AccountStatus.AVAILABLE
        self.lock = asyncio.Lock()

    def is_available(self) -> bool:
        return self.status == AccountStatus.AVAILABLE

    async def set_busy(self):
        async with self.lock:
            if self.status == AccountStatus.AVAILABLE:
                self.status = AccountStatus.BUSY
                return True
            return False

    async def set_available(self):
        async with self.lock:
            self.status = AccountStatus.AVAILABLE

    async def set_banned(self):
        async with self.lock:
            self.status = AccountStatus.BANNED

class AccountManager:
    def __init__(self, platform: str):
        self.platform = platform
        self.accounts: List[Account] = self._load_accounts()
        if not self.accounts:
            raise ValueError(f"No accounts configured for platform: {platform}")
        self.available_accounts = asyncio.Queue()
        for acc in self.accounts:
            self.available_accounts.put_nowait(acc)

    def _load_accounts(self) -> List[Account]:
        """Load accounts from the config file for the specified platform."""
        pool_name = f"{self.platform.upper()}_ACCOUNT_POOL"
        # Dynamically get the account pool from the config module
        account_list = getattr(config.account_pool_config, pool_name, [])
        return [Account(acc_info) for acc_info in account_list]

    async def get_account(self) -> Optional[Account]:
        """Get an available account from the pool. This will block until one is available."""
        utils.logger.info(f"[AccountManager] Waiting for an available {self.platform.upper()} account...")
        account = await self.available_accounts.get()
        await account.set_busy()
        utils.logger.info(f"[AccountManager] Acquired account: {account.id}")
        return account

    async def release_account(self, account: Account, is_banned: bool = False):
        """Release an account back to the pool."""
        if is_banned:
            await account.set_banned()
            utils.logger.warning(f"[AccountManager] Account {account.id} has been marked as banned.")
        else:
            await account.set_available()
            await self.available_accounts.put(account)
            utils.logger.info(f"[AccountManager] Account {account.id} released back to the pool.")

    def get_total_accounts(self) -> int:
        return len(self.accounts)

    def get_available_accounts_count(self) -> int:
        return self.available_accounts.qsize()
