import logging
import aiohttp
import asyncio
import html
import os
import random
import re
import time

import common.constants as const

from common.connections import ApiManager
from common.uhtml import UserInfo
from common.utils import find_true_name, gen_uhtml_img

logger = logging.getLogger(__name__)

# Seconds to wait on MAL before giving up on a request.
MAL_TIMEOUT = 15
# How long a ]mal profile card is reused before its lists are fetched again.
PROFILE_CACHE_TTL = 10 * 60
# MAL usernames are 2-16 letters, digits, underscores or hyphens.
MAL_USERNAME = re.compile(r'^[A-Za-z0-9_-]{2,16}$')
# How often the background task looks for lists to refresh. Lists are
# refreshed once they're a day old.
REFRESH_INTERVAL = 60 * 60
# After a list fails to refresh, don't force another try for this long.
REFRESH_RETRY_DELAY = 10 * 60
# MAL rate limits by redirecting every request to an error page that never
# responds. When that happens, pause background refreshes for this long.
THROTTLE_BACKOFF = 15 * 60
# Seconds between background requests, to stay well under MAL's rate limit.
BACKGROUND_REQUEST_GAP = 2
# Which parts of a user's lists can be rolled from.
LIST_STATUSES = {'anime': ('watching', 'completed'),
                 'manga': ('reading', 'completed')}

MAL_DOWN_MSG = "Couldn't reach MAL right now. Please try again later."
# Fields wanted for every entry when reading a whole list for a profile.
PROFILE_FIELDS = 'list_status,nsfw'


def mal_url_info(url):
    m = re.search(r'myanimelist.net/(?P<medium>[A-Za-z]+)/(?P<id>[0-9]+)', url)
    if m:
        return (m.group('medium'), int(m.group('id')))
    else:
        return


def list_table(mal_user):
    """ Name of the table caching a MAL user's list. """
    return f'mal_list_{find_true_name(mal_user)}'


class MalManager(ApiManager):
    def __init__(self, db_man):
        self.db_man = db_man
        super().__init__(0.1)

        # Background list refreshes get their own, slower lane so they
        # don't hold up commands.
        self.background_api = ApiManager(BACKGROUND_REQUEST_GAP)
        self.throttled_until = 0

        self.tables_ready = False
        self.refreshes = {}
        self.failed_refreshes = {}
        # Lists whose MAL account no longer exists.
        self.missing_accounts = set()
        # Recently built ]mal profile cards: lowercase MAL name -> (time, html).
        self.profile_cache = {}


    async def ensure_tables(self):
        if self.tables_ready:
            return

        # Title and NSFW rating of every series seen in a list, so rolls
        # don't need to ask MAL about each series.
        await self.db_man.execute("CREATE TABLE IF NOT EXISTS mal_series (medium VARCHAR NOT NULL, "
                                  "mal_id INTEGER NOT NULL, title VARCHAR NOT NULL, "
                                  "nsfw VARCHAR NOT NULL, PRIMARY KEY (medium, mal_id))")
        self.tables_ready = True


    async def api_request(self, url, background=False, **kwargs):
        '''
        GETs from the MAL API.

        Returns (status, json), or (None, {}) if MAL couldn't be reached.
        '''
        if background and self.throttled():
            return None, {}

        api = self.background_api if background else self
        # Don't follow redirects: MAL redirects to an error page that hangs.
        kwargs.setdefault('allow_redirects', False)
        async with api.lock():
            try:
                timeout = aiohttp.ClientTimeout(total=MAL_TIMEOUT)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers={'X-MAL-CLIENT-ID': os.getenv('MAL_ID', '')}, **kwargs) as r:
                        if 300 <= r.status < 400:
                            logger.warning(f'MAL redirected {url} to {r.headers.get("Location")} '
                                  '(likely rate limiting); pausing background refreshes.')
                            self.throttled_until = time.time() + THROTTLE_BACKOFF
                            return r.status, {}

                        request_data = await r.json(content_type=None)

                        if r.status != 200:
                            logger.warning(f'MAL API returned {r.status} for {url}: {request_data}')

                        return r.status, request_data or {}
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
                logger.warning(f'MAL API request failed for {url}: {e!r}')
                return None, {}


    async def mal_of_ps(self, ps_user):
        mal_user = await self.db_man.execute("SELECT mal_username FROM mal_users "
                                             "WHERE ps_username=?", (ps_user,))
        if mal_user:
            return mal_user[0][0]
        else:
            return


    async def store_series(self, series):
        """ Saves (medium, mal_id, title, nsfw) rows to mal_series. """
        await self.ensure_tables()
        await self.db_man.transaction([("INSERT OR REPLACE INTO mal_series (medium, mal_id, title, nsfw) "
                                        "VALUES (?, ?, ?, ?)", list(series))])


    async def is_nsfw(self, medium, series_id):
        await self.ensure_tables()
        cached = await self.db_man.execute("SELECT nsfw FROM mal_series WHERE medium=? AND mal_id=?",
                                           (medium, series_id))
        if cached:
            return cached[0][0] != 'white'

        status, series_data = await self.api_request(f'{const.MAL_API}{medium}/{series_id}',
                                                     params={'fields': 'title,nsfw'})
        if status != 200 or 'nsfw' not in series_data:
            return True

        await self.store_series([(medium, series_id, series_data['title'], series_data['nsfw'])])
        return series_data['nsfw'] != 'white'


    async def fetch_list(self, mal_user, medium, background):
        '''
        Gets the rollable part of a user's anime or manga list from MAL.

        Returns a list of (medium, mal_id, title, nsfw), or None if any
        part of the list couldn't be fetched.
        '''
        entries = []
        for status in LIST_STATUSES[medium]:
            url = (f'{const.MAL_API}users/{mal_user}/{medium}list'
                   f'?status={status}&limit=1000&fields=nsfw')
            while url:
                code, list_data = await self.api_request(url, background=background)
                if code == 404:
                    self.missing_accounts.add(list_table(mal_user))
                if code != 200 or 'data' not in list_data:
                    return None

                for item in list_data['data']:
                    node = item['node']
                    entries.append((medium, node['id'], node['title'], node.get('nsfw', 'gray')))

                url = list_data.get('paging', {}).get('next')
                if url and 'fields=' not in url:
                    url += '&fields=nsfw'

        return entries


    async def table_exists(self, table_name):
        return bool(await self.db_man.execute("SELECT name FROM sqlite_master "
                                              "WHERE type='table' AND name=?", (table_name,)))


    async def needs_series_info(self, table_name):
        """ Whether a cached list is missing, or has series without stored info. """
        if not await self.table_exists(table_name):
            return True

        missing = await self.db_man.execute(f"SELECT 1 FROM {table_name} l LEFT JOIN mal_series s "
                                            "ON s.medium=l.medium AND s.mal_id=l.mal_id "
                                            "WHERE s.mal_id IS NULL LIMIT 1")
        return bool(missing)


    async def list_is_stale(self, mal_user):
        await self.ensure_tables()
        # CURRENT_TIMESTAMP and datetime('now') are both UTC. MAL usernames
        # aren't case sensitive, so check every capitalization people linked.
        old = await self.db_man.execute("SELECT MAX(last_updated IS NULL OR "
                                        "last_updated < datetime('now', '-1 day')) "
                                        "FROM mal_users WHERE lower(mal_username)=lower(?)", (mal_user,))
        if old and old[0][0]:
            return True

        return await self.needs_series_info(list_table(mal_user))


    def throttled(self):
        return time.time() < self.throttled_until


    def recently_failed(self, table_name):
        return time.time() - self.failed_refreshes.get(table_name, 0) < REFRESH_RETRY_DELAY


    async def update_user(self, ps_user, force=False, background=True):
        '''
        Refreshes the cached copy of a user's MAL list if it's over a day
        old (or always, with force). Concurrent refreshes of the same list
        share one fetch.

        Returns whether the cached list is now up to date.
        '''
        mal_user = await self.mal_of_ps(ps_user)
        if not mal_user:
            return False
        table_name = list_table(mal_user)

        if table_name not in self.refreshes:
            if not force and not await self.list_is_stale(mal_user):
                return True
            self.refreshes[table_name] = asyncio.ensure_future(self.refresh_list(mal_user, background))

        return await asyncio.shield(self.refreshes[table_name])


    async def refresh_list(self, mal_user, background):
        table_name = list_table(mal_user)
        try:
            await self.ensure_tables()

            entries = []
            for medium in LIST_STATUSES:
                fetched = await self.fetch_list(mal_user, medium, background)
                if fetched is None:
                    self.failed_refreshes[table_name] = time.time()
                    return False
                entries += fetched
            self.missing_accounts.discard(table_name)

            # An empty response is more likely a MAL hiccup than someone
            # clearing their whole list, so don't wipe a list over it.
            if not entries and await self.table_exists(table_name):
                cached = await self.db_man.execute(f"SELECT COUNT(*) FROM {table_name}")
                if cached and cached[0][0]:
                    logger.warning(f'MAL returned an empty list for {mal_user}; keeping the cached one.')
                    self.failed_refreshes[table_name] = time.time()
                    return False

            await self.store_series(entries)

            # Rebuild the cached list in one go, so series dropped from the
            # list stop being rolled. Recreating the table also upgrades
            # lists cached with an older layout, which rejected new entries.
            ok = await self.db_man.transaction([
                (f"DROP TABLE IF EXISTS {table_name}", ()),
                (f"CREATE TABLE {table_name} (medium VARCHAR NOT NULL, "
                 "mal_id INTEGER NOT NULL, PRIMARY KEY (medium, mal_id))", ()),
                (f"INSERT OR IGNORE INTO {table_name} (medium, mal_id) VALUES (?, ?)",
                 [(medium, mal_id) for medium, mal_id, _, _ in entries]),
                ("UPDATE mal_users SET last_updated=CURRENT_TIMESTAMP "
                 "WHERE lower(mal_username)=lower(?)", (mal_user,)),
            ])
            if ok:
                self.failed_refreshes.pop(table_name, None)
            else:
                self.failed_refreshes[table_name] = time.time()
            return ok
        finally:
            self.refreshes.pop(table_name, None)


    async def refresh_repeater(self):
        '''
        Repeating process that keeps every linked MAL list fresh, so rolls
        rarely have to wait on MAL.
        '''
        while True:
            try:
                linked = await self.db_man.execute("SELECT ps_username, mal_username FROM mal_users")
                done = set()
                for ps_user, mal_user in linked:
                    if self.throttled():
                        break
                    table_name = list_table(mal_user)
                    if table_name in done or self.recently_failed(table_name):
                        continue
                    done.add(table_name)
                    await self.update_user(ps_user)
            except Exception:
                logger.exception('MAL list refresh pass failed')

            await asyncio.sleep(REFRESH_INTERVAL)


    async def user_rand_series(self, ps_user, media, anotd=False):
        mal_user = await self.mal_of_ps(ps_user)

        if not mal_user:
            return f'Could not find the MAL account for {ps_user}. They may need to use ]mal_add first.'

        await self.ensure_tables()
        table_name = list_table(mal_user)

        # Lists that haven't been fetched since series info started being
        # stored need one refresh before they can be rolled from.
        refreshed = False
        if await self.needs_series_info(table_name) and not self.recently_failed(table_name):
            await self.update_user(ps_user, force=True, background=False)
            refreshed = True

        if not await self.table_exists(table_name):
            return self.unavailable_msg(ps_user, mal_user)

        db_query = (f"SELECT s.medium, s.mal_id, s.title FROM {table_name} l "
                    "JOIN mal_series s ON s.medium=l.medium AND s.mal_id=l.mal_id "
                    "WHERE s.nsfw='white'")
        db_params = []
        if len(media) == 1:
            db_query += " AND l.medium=?"
            db_params.append(media[0])
        # Take out if anotd
        if anotd:
            db_query += (" AND NOT EXISTS (SELECT 1 FROM mal_banlist b WHERE b.medium=l.medium "
                         "AND b.mal_id=l.mal_id AND b.anotd_source=1)")
        db_query += " ORDER BY RANDOM() LIMIT 1"
        series = await self.db_man.execute(db_query, tuple(db_params))

        # Nothing to roll from an out-of-date list: refresh before saying so.
        if (not series and not refreshed and not self.recently_failed(table_name)
                and await self.list_is_stale(mal_user)):
            await self.update_user(ps_user, force=True, background=False)
            series = await self.db_man.execute(db_query, tuple(db_params))

        # Refreshes in the background if the cached list is over a day old.
        asyncio.create_task(self.update_user(ps_user))

        if not series:
            if self.recently_failed(table_name):
                return self.unavailable_msg(ps_user, mal_user)
            return f'No valid series found for {ps_user}'

        return f'rolled {series[0][2]}'


    def unavailable_msg(self, ps_user, mal_user):
        if list_table(mal_user) in self.missing_accounts:
            return (f"The MAL account {mal_user} doesn't exist anymore. "
                    f"{ps_user} may need to update it with ]mal_add.")
        return f"Couldn't load {ps_user}'s MAL list right now. Please try again later."


    async def set_user(self, ps_user, mal_user):
        if not mal_user:
            return 'Usage: ]mal_add [MAL username]'
        if not MAL_USERNAME.match(mal_user):
            return f"{mal_user} isn't a valid MAL username."

        # MAL's API has no public profile lookup, but a user's list answers
        # 404 if the account doesn't exist and 403 if the list is private.
        code, _ = await self.api_request(f'{const.MAL_API}users/{mal_user}/animelist',
                                         params={'limit': 1})
        if code == 404:
            return f"Could not find {mal_user} on MAL."
        if code not in (200, 403):
            return MAL_DOWN_MSG
        private_note = ''
        if code == 403:
            private_note = (f" Their anime list is private, so ]mal and rolls won't work "
                            f"until it's made public.")

        current_user = await self.mal_of_ps(ps_user)
        if current_user == mal_user:
            return f"{ps_user}'s MAL is already set to {mal_user}."
        # Can change to actual UPSERT when sqlite3 gets updated to have it
        elif current_user:
            await self.db_man.execute("UPDATE mal_users SET mal_username=?, "
                                      "last_updated=CURRENT_TIMESTAMP WHERE ps_username=?",
                                      (mal_user, ps_user))

            cu_rows = await self.db_man.execute("SELECT COUNT(*) FROM mal_users "
                                                "WHERE mal_username=?", (current_user,))
            if cu_rows[0][0] == 0:
                await self.db_man.execute(f"DROP TABLE IF EXISTS mal_list_{find_true_name(current_user)}",
                                          allow_drop=True)
        else:
            await self.db_man.execute("INSERT INTO mal_users (ps_username, mal_username) "
                                      "VALUES (?, ?)", (ps_user, mal_user))

        asyncio.create_task(self.update_user(ps_user, force=True, background=False))
        self.missing_accounts.discard(list_table(mal_user))

        return f"Set {ps_user}'s MAL to {mal_user}.{private_note}"


    async def fetch_full_list(self, mal_user, medium):
        '''
        Every entry of a user's anime or manga list, with their status,
        score and progress.

        Returns (status code, entries); entries is None on failure.
        '''
        url = f'{const.MAL_API}users/{mal_user}/{medium}list?limit=1000&fields={PROFILE_FIELDS}'
        entries = []
        while url:
            code, list_data = await self.api_request(url)
            if code != 200 or 'data' not in list_data:
                return code, None
            entries.extend(list_data['data'])

            url = list_data.get('paging', {}).get('next')
            if url and 'fields=' not in url:
                url += f'&fields={PROFILE_FIELDS}'
        return 200, entries


    @staticmethod
    def list_stats(entries, medium):
        ''' The profile card's numbers, worked out from a list. '''
        current, progress = (('watching', 'num_episodes_watched') if medium == 'anime'
                             else ('reading', 'num_chapters_read'))
        statuses = [e.get('list_status', {}) for e in entries]
        scores = [s.get('score', 0) for s in statuses if s.get('score')]
        return {'completed': sum(s.get('status') == 'completed' for s in statuses),
                'current': sum(s.get('status') == current for s in statuses),
                'progress': sum(s.get(progress) or 0 for s in statuses),
                'mean': f'{sum(scores) / len(scores):.2f}' if scores else 'N/A'}


    @staticmethod
    def top_rated(entries):
        ''' A random pick among the user's highest-scored SFW series. '''
        sfw = [e for e in entries if e['node'].get('nsfw') == 'white']
        scored = [e for e in sfw if e.get('list_status', {}).get('score')]
        if scored:
            best = max(e['list_status']['score'] for e in scored)
            return random.choice([e for e in scored if e['list_status']['score'] == best])
        completed = [e for e in sfw if e.get('list_status', {}).get('status') == 'completed']
        return random.choice(completed or sfw) if (completed or sfw) else None


    async def series_cell(self, entry, medium, height):
        ''' (title, link, image html) for a list entry, or placeholders. '''
        if entry is None:
            return 'None', '', await gen_uhtml_img(const.IMG_NOT_FOUND, height_resize=height)
        node = entry['node']
        img = (node.get('main_picture') or {}).get('medium') or const.IMG_NOT_FOUND
        return (html.escape(node['title']), f'https://myanimelist.net/{medium}/{node["id"]}',
                await gen_uhtml_img(img, height_resize=height))


    async def show_user(self, ps_user):
        mal_user = await self.mal_of_ps(ps_user)
        if not mal_user:
            return f"{ps_user} does not have a linked MAL account."

        cached = self.profile_cache.get(mal_user.lower())
        if cached and time.time() - cached[0] < PROFILE_CACHE_TTL:
            return cached[1]

        # MAL's API can't look up other users' profiles, so the card is
        # built from their lists: stats, top-rated picks, latest update.
        lists = {}
        for medium in ('anime', 'manga'):
            code, entries = await self.fetch_full_list(mal_user, medium)
            if code == 404:
                self.missing_accounts.add(list_table(mal_user))
                return (f"{mal_user} wasn't found on MAL. "
                        f"They may need to update their account with ]mal_add.")
            if code == 403:
                lists[medium] = None    # This list is private.
            elif entries is None:
                return MAL_DOWN_MSG
            else:
                lists[medium] = entries

        if lists['anime'] is None and lists['manga'] is None:
            return f"{mal_user}'s MAL lists are private, so their profile can't be shown."

        # Remember the NSFW ratings seen, which rolls and trivia also use.
        seen = [(medium, e['node']['id'], e['node']['title'], e['node'].get('nsfw', 'gray'))
                for medium, entries in lists.items() if entries for e in entries]
        if seen:
            await self.store_series(seen)

        kwargs = {}
        for medium, prefix in (('anime', 'anime'), ('manga', 'manga')):
            entries = lists[medium]
            if entries is None:
                stats = dict.fromkeys(('completed', 'current', 'progress', 'mean'), 'Private')
            else:
                stats = self.list_stats(entries, medium)
            title, link, img = await self.series_cell(self.top_rated(entries or []), medium, 64)
            kwargs.update({f'{prefix}_completed': stats['completed'],
                           f'{prefix}_title': title, f'{prefix}_link': link, f'{prefix}_img': img})
            if medium == 'anime':
                kwargs.update(anime_watching=stats['current'], ep_watched=stats['progress'],
                              anime_score=stats['mean'])
            else:
                kwargs.update(manga_reading=stats['current'], chp_read=stats['progress'],
                              manga_score=stats['mean'])

        # In place of the avatar (which the API doesn't give): the SFW
        # series they most recently updated.
        recent = [(e.get('list_status', {}).get('updated_at', ''), medium, e)
                  for medium, entries in lists.items() if entries for e in entries
                  if e['node'].get('nsfw') == 'white']
        if recent:
            _, medium, entry = max(recent, key=lambda r: r[0])
            title, link, img = await self.series_cell(entry, medium, 100)
            kwargs['profile_pic'] = (f'{img}<br><span style="font-size:9px">Latest: '
                                     f'<a href="{link}" style="color:#8311a6">{title}</a></span>')
        else:
            kwargs['profile_pic'] = await gen_uhtml_img(const.IMG_NOT_FOUND, height_resize=100)
        kwargs['fav_label'] = 'Top Rated'

        user_info = UserInfo(mal_user, f'https://myanimelist.net/profile/{mal_user}', 'mal')
        card = user_info.mal_user(**kwargs)
        self.profile_cache[mal_user.lower()] = (time.time(), card)
        return card
