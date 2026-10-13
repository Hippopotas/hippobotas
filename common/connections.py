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


    async def execute(self, query, params=(), allow_drop=False):
        '''
        Runs a query against the database. Pass user-supplied values
        through params (as ? placeholders) rather than formatting them
        into the query string.
        '''
        if 'droptable' in find_true_name(query) and not allow_drop:
            print(f'SOMEONE TRIED TO DROP TABLES WITH: {query}')
            return []

        rows = []
        async with self.db_lock:
            try:
                connection = sqlite3.connect(self.db)
            except sqlite3.Error as e:
                print(f'Could not open {self.db}: {e}')
                return rows

            try:
                with connection:
                    rows = connection.execute(query, params).fetchall()
            except Exception as e:
                print(f'{query} {params} failed on {self.db}: {e}')
            finally:
                connection.close()

        return rows
