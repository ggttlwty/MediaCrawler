import csv
import json
import os
import pathlib
from typing import Dict

import aiofiles

import config
from base.base_crawler import AbstractStore
from tools import utils
from var import crawler_type_var
from . import twitter_store_sql


class TwitterCsvStoreImplement(AbstractStore):
    def __init__(self):
        self.csv_store_path: str = "data/twitter"
        pathlib.Path(self.csv_store_path).mkdir(parents=True, exist_ok=True)

    def _get_save_path(self, store_type: str) -> str:
        return os.path.join(self.csv_store_path, f"{crawler_type_var.get()}_{store_type}.csv")

    async def store_content(self, content_item: Dict):
        save_path = self._get_save_path("contents")
        async with aiofiles.open(save_path, mode='a+', encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if await f.tell() == 0:
                await writer.writerow(content_item.keys())
            await writer.writerow(content_item.values())

    async def store_comment(self, comment_item: Dict):
        pass # Not implemented

    async def store_creator(self, creator: Dict):
        pass # Not implemented


class TwitterDbStoreImplement(AbstractStore):
    async def store_content(self, content_item: Dict):
        await twitter_store_sql.add_new_content(content_item)

    async def store_comment(self, comment_item: Dict):
        pass # Not implemented

    async def store_creator(self, creator: Dict):
        pass # Not implemented
