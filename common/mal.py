import aiohttp
import asyncio
import datetime
import os
import random
import re

import common.constants as const

from common.connections import ApiManager
from common.uhtml import UserInfo
from common.utils import find_true_name, gen_uhtml_img_code


async def jikan_user_info(username, jikan_man):
    async with jikan_man.lock():
        async with aiohttp.ClientSession() as session:
            url = f'{const.JIKAN_API}users/{username}/full'
            async with session.get(url) as r:
                user_data = await r.json()

                return user_data['data']


def mal_url_info(url):
    m = re.search(r'myanimelist.net/(?P<medium>[A-Za-z]+)/(?P<id>[0-9]+)', url)
    if m:
        return (m.group('medium'), int(m.group('id')))
    else:
        return


class MalManager(ApiManager):
    def __init__(self, db_man):
        self.db_man = db_man
        super().__init__(0.1)


    async def api_request(self, url, **kwargs):
        async with self.lock():
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers={'X-MAL-CLIENT-ID': os.getenv('MAL_ID')}, **kwargs) as r:
                    request_data = await r.json()

                    return request_data


    async def mal_of_ps(self, ps_user):
        mal_user = await self.db_man.execute("SELECT mal_username FROM mal_users "
                                            f"WHERE ps_username='{ps_user}'")
        if mal_user:
            return mal_user[0][0]
        else:
            return


    async def is_nsfw(self, medium, series_id):
        series_data = await self.api_request(f'{const.MAL_API}{medium}/{series_id}', params={'fields': 'nsfw'})
        if series_data['nsfw'] == 'white':
            return False
        else:
            return True


    async def animelist(self, ps_user):
        """ Gets a list of MAL IDs of completed/watching series. """
        mal_user = await self.mal_of_ps(ps_user)
        full_list = []
        for status in ('watching', 'completed'):
            curr_url = f'{const.MAL_API}users/{mal_user}/animelist?limit=1000&status={status}'
            while curr_url:
                series_data = await self.api_request(curr_url)
                for series in series_data['data']:
                    full_list.append(series['node']['id'])
                if series_data['paging']:
                    curr_url = series_data['paging']['next']
                else:
                    break

        return full_list


    async def mangalist(self, ps_user):
        """ Gets a list of MAL IDs of reading/watching series. """
        mal_user = await self.mal_of_ps(ps_user)
        full_list = []
        for status in ('reading', 'completed'):
            curr_url = f'{const.MAL_API}users/{mal_user}/animelist?limit=1000&status={status}'
            while curr_url:
                series_data = await self.api_request(curr_url)
                for series in series_data['data']:
                    full_list.append(series['node']['id'])
                if series_data['paging']:
                    curr_url = series_data['paging']['next']
                else:
                    break

        return full_list


    async def update_user(self, ps_user, force=False):
        mal_user = await self.mal_of_ps(ps_user)
        table_name = f'mal_list_{find_true_name(mal_user)}'

        table_exists = await self.db_man.execute("SELECT name FROM sqlite_master "
                                                f"WHERE type='table' AND name='{table_name}'")
        if not table_exists:
            await self.db_man.execute(f"CREATE TABLE {table_name} (medium VARCHAR NOT NULL, "
                                                                  "mal_id INTEGER NOT NULL, "
                                                                  "PRIMARY KEY (medium, mal_id))")

        # Do not update if cache is younger than 1 day
        last_updated = await self.db_man.execute("SELECT last_updated FROM mal_users "
                                                f"WHERE mal_username='{mal_user}'")
        update_time = datetime.datetime.strptime(last_updated[0][0], '%Y-%m-%d %H:%M:%S')
        if datetime.datetime.now() - update_time < datetime.timedelta(days=1) and not force:
            return

        animelist = await self.animelist(ps_user)
        mangalist = await self.mangalist(ps_user)

        values = [f"('anime', '{mal_id}')" for mal_id in animelist]
        values += [f"('manga', '{mal_id}')" for mal_id in mangalist]

        if values:
            await self.db_man.execute(f"INSERT OR IGNORE INTO {table_name} (medium, mal_id) "
                                      f"VALUES {', '.join(values)}")

        escaped_mal_user = mal_user.replace("'", "''")
        await self.db_man.execute("UPDATE mal_users SET last_updated=CURRENT_TIMESTAMP "
                                 f"WHERE mal_username='{escaped_mal_user}'")


    async def user_rand_series(self, ps_user, media, anotd=False):
        mal_user = await self.mal_of_ps(ps_user)

        if not mal_user:
            return f'Could not find the MAL account for {ps_user}. They may need to use ]mal_add first.'

        table_name = f'mal_list_{find_true_name(mal_user)}'

        db_query = f"SELECT * FROM {table_name}"
        if len(media) == 1:
            db_query += f" WHERE medium='{media[0]}'"
        all_series = await self.db_man.execute(db_query)

        series = None
        is_nsfw = True
        while is_nsfw and all_series:
            index = random.randrange(len(all_series))
            # series = (medium, mal_id, title, last_updated)
            temp_series = all_series.pop(index)

            is_nsfw = await self.is_nsfw(temp_series[0], temp_series[1])

            # Take out if anotd
            if anotd:
                bl = await self.db_man.execute("SELECT * FROM mal_banlist "
                                              f"WHERE medium='{temp_series[0]}' AND mal_id={temp_series[1]} AND anotd_source=1")
                if bl:
                    is_nsfw = True

            if not is_nsfw:
                series = temp_series

        msg = f'No valid series found for {ps_user}'
        if series:
            series_data = await self.api_request(f'{const.MAL_API}{series[0]}/{series[1]}')
            msg = f"rolled {series_data['title']}"

        asyncio.create_task(self.update_user(ps_user))

        return msg


    async def set_user(self, ps_user, mal_user, jikan_man):
        # Sqlite escape
        escaped_mal_user = mal_user.replace("'", "''")

        try:
            await jikan_user_info(mal_user, jikan_man)
        except:
            return f"Could not find {mal_user} on MAL."

        current_user = await self.mal_of_ps(ps_user)
        if current_user == mal_user:
            return f"{ps_user}'s MAL is already set to {mal_user}."
        # Can change to actual UPSERT when sqlite3 gets updated to have it
        elif current_user:
            await self.db_man.execute(f"UPDATE mal_users SET mal_username='{escaped_mal_user}', "
                                                            "last_updated=CURRENT_TIMESTAMP "
                                      f"WHERE ps_username='{ps_user}'")

            cu_rows = await self.db_man.execute("SELECT COUNT(*) FROM mal_users "
                                               f"WHERE mal_username='{current_user}'")
            if cu_rows[0][0] == 0:
                await self.db_man.execute(f"DROP TABLE mal_{current_user}")
        else:
            await self.db_man.execute("INSERT INTO mal_users (ps_username, mal_username) "
                                     f"VALUES ('{ps_user}', '{escaped_mal_user}')")

        asyncio.create_task(self.update_user(ps_user, force=True))

        return f"Set {ps_user}'s MAL to {mal_user}."


    async def show_user(self, ps_user, jikan_man):
        mal_user = await self.mal_of_ps(ps_user)
        if not mal_user:
            return f"{ps_user} does not have a linked MAL account."

        user_data = await jikan_user_info(mal_user, jikan_man) if mal_user else (None, None)

        # Set image
        img_url = const.IMG_NOT_FOUND
        if user_data['images']:
            img_url = user_data['images']['jpg']['image_url']
        img_uhtml = gen_uhtml_img_code(img_url, height_resize=100, width_resize=125)

        # Set favorite series
        top_series_uhtml = {'anime': (), 'manga': ()}
        for medium in top_series_uhtml:
            top_series = 'None'
            top_series_url = ''
            top_series_img = const.IMG_NOT_FOUND

            fav_series = user_data['favorites'][medium]
            while fav_series:
                rand_fav = random.choice(fav_series)
                is_nsfw = await self.is_nsfw(medium, rand_fav['mal_id'])
                if is_nsfw:
                    fav_series.remove(rand_fav)
                else:
                    top_series = rand_fav['title']
                    top_series_url = rand_fav['url']
                    top_series_img = rand_fav['images']['jpg']['small_image_url']
                    break

            top_series_uhtml[medium] = (top_series, top_series_url,
                                        gen_uhtml_img_code(top_series_img, height_resize=64))

        user_info = UserInfo(user_data['username'], user_data['url'], 'mal')
        kwargs = {'profile_pic': img_uhtml,
                  'anime_completed': user_data['statistics']['anime']['completed'],
                  'anime_watching': user_data['statistics']['anime']['watching'],
                  'ep_watched': user_data['statistics']['anime']['episodes_watched'],
                  'anime_score': user_data['statistics']['anime']['mean_score'],
                  'manga_completed': user_data['statistics']['manga']['completed'],
                  'manga_reading': user_data['statistics']['manga']['reading'],
                  'chp_read': user_data['statistics']['manga']['chapters_read'],
                  'manga_score': user_data['statistics']['manga']['mean_score'],
                  'anime_img': top_series_uhtml['anime'][2],
                  'manga_img': top_series_uhtml['manga'][2],
                  'anime_link': top_series_uhtml['anime'][1],
                  'anime_title': top_series_uhtml['anime'][0],
                  'manga_link': top_series_uhtml['manga'][1],
                  'manga_title': top_series_uhtml['manga'][0]}

        return user_info.mal_user(**kwargs)
