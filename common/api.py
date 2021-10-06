import aiohttp
import asyncio

from contextlib import asynccontextmanager

class ApiManager():
    def __init__(self, rate_limit):
        self.api_lock = asyncio.Lock()
        self.rate_limit = rate_limit


    @asynccontextmanager
    async def lock(self):
        await self.api_lock.acquire()
        try:
            yield
        finally:
            await asyncio.sleep(self.rate_limit)
            self.api_lock.release()
