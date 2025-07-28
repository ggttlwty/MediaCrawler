from typing import Dict

from .twitter_store_impl import TwitterCsvStoreImplement, TwitterDbStoreImplement
import config

async def update_twitter_note(note_item: Dict):
    """Update twitter note to db"""
    if config.SAVE_DATA_OPTION == "csv":
        csv_store = TwitterCsvStoreImplement()
        await csv_store.store_content(note_item)
    elif config.SAVE_DATA_OPTION in ["db", "sqlite"]:
        db_store = TwitterDbStoreImplement()
        await db_store.store_content(note_item)
