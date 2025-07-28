from typing import Dict, List, Union

from async_db import AsyncMysqlDB
from async_sqlite_db import AsyncSqliteDB
from var import media_crawler_db_var


async def add_new_content(content_item: Dict) -> int:
    """
    新增一条推文记录
    """
    async_db_conn: Union[AsyncMysqlDB, AsyncSqliteDB] = media_crawler_db_var.get()
    last_row_id: int = await async_db_conn.item_to_table("twitter_note", content_item)
    return last_row_id
