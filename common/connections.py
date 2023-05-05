import aiohttp
import asyncio
import sqlite3

from contextlib import asynccontextmanager
from common.utils import find_true_name


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


class DatabaseManager():
    def __init__(self, db_file):
        self.db_lock = asyncio.Lock()
        self.db = db_file


    async def execute(self, query):
        if 'droptable' in find_true_name(query):
            print(f'SOMEONE TRIED TO DROP TABLES WITH: {query}')
            return
        await self.db_lock.acquire()

        rows = []

        connection = sqlite3.connect(self.db)

        try:
            with connection:
                rows = connection.execute(query).fetchall()
        except Exception as e:
            print(f'{query} failed on {self.db}: {e}')
        finally:
            connection.close()

        self.db_lock.release()

        return rows
