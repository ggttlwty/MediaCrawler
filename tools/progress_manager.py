import asyncio
import json
import os
from typing import Dict, Any

import aiofiles

from . import utils

PROGRESS_FILE = "progress.json"
lock = asyncio.Lock()

async def load_progress() -> Dict[str, Any]:
    """Load progress from the progress file."""
    async with lock:
        if not os.path.exists(PROGRESS_FILE):
            return {}
        try:
            async with aiofiles.open(PROGRESS_FILE, mode='r', encoding='utf-8') as f:
                content = await f.read()
                if not content:
                    return {}
                return json.loads(content)
        except (IOError, json.JSONDecodeError) as e:
            utils.logger.error(f"Error loading progress file: {e}")
            return {}

async def save_progress(progress_data: Dict[str, Any]):
    """Save progress to the progress file."""
    async with lock:
        try:
            async with aiofiles.open(PROGRESS_FILE, mode='w', encoding='utf-8') as f:
                await f.write(json.dumps(progress_data, indent=4))
        except IOError as e:
            utils.logger.error(f"Error saving progress file: {e}")
