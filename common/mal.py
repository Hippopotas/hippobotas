import aiohttp
import asyncio
import datetime
import random

import common.constants as const

from common.anilist import check_mal_nsfw
from common.uhtml import UserInfo, ItemInfo
from common.utils import find_true_name, gen_uhtml_img_code


async def mal_of_ps(ps_user, db_man):
    mal_user = await db_man.execute("SELECT mal_username FROM mal_users "
                                       f"WHERE ps_username='{ps_user}'")

    if mal_user:
        return mal_user[0][0]
    else:
        return


async def get_mal_user(username, mal_man):
    async with mal_man.lock():
        async with aiohttp.ClientSession() as session:
            url = f'{const.JIKAN_API}user/{username}'
            async with session.get(url) as r:
                user_data = await r.json()

                if r.status != 200:
                    print(f"Jikan error {r.status} on {url} when "
                          f"fetching {username} profile: {user_data['message']}")
                    return

                return user_data


async def update_mal_user(mal_user, db_man, mal_man):
    table_name = f'mal_list_{find_true_name(mal_user)}'
    table_exists = await db_man.execute("SELECT name FROM sqlite_master "
                                            f"WHERE type='table' AND name='{table_name}'")

    if not table_exists:
        await db_man.execute(f"CREATE TABLE {table_name} (medium VARCHAR NOT NULL, "
                                                         "mal_id INTEGER NOT NULL, "
                                                         "title VARCHAR NOT NULL, "
                                                         "last_updated DATETIME DEFAULT CURRENT_TIMESTAMP, "
                                                         "PRIMARY KEY (medium, mal_id))")

    for medium in ('anime', 'manga'):
        in_progress = 'reading' if medium == 'manga' else 'watching'
        for status in (in_progress, 'completed'):
            series_list = {medium: 'placeholder'}
            page = 0
            while series_list[medium]:
                page += 1
                series_list = await get_mal_user(f'{mal_user}/{medium}list/{status}/{page}', mal_man)

                if series_list and series_list[medium]:
                    values = []
                    for series in series_list[medium]:
                        # Sqlite escape
                        escaped_title = series['title'].replace("'", "''")
                        series_exists = await db_man.execute(f"SELECT COUNT(*) FROM {table_name} "
                                                                f"WHERE medium='{medium}'"
                                                                  f"AND mal_id={series['mal_id']}")

                        if not series_exists[0][0]:
                            values.append(f"('{medium}', '{series['mal_id']}', '{escaped_title}')")

                    if values:
                        await db_man.execute(f"INSERT INTO {table_name} (medium, mal_id, title) "
                                                f"VALUES {', '.join(values)}")
                else:
                    break

    escaped_mal_user = mal_user.replace("'", "''")
    await db_man.execute("UPDATE mal_users SET last_updated=CURRENT_TIMESTAMP "
                            f"WHERE mal_username='{escaped_mal_user}'")


async def set_mal_user(ps_user, mal_user, db_man, mal_man):
    # Sqlite escape
    escaped_mal_user = mal_user.replace("'", "''")

    user_data = await get_mal_user(mal_user, mal_man)

    if user_data:
        current_user = await mal_of_ps(ps_user, db_man)

        if current_user == mal_user:
            return f"{ps_user}'s MAL is already set to {mal_user}."
        # Can change to actual UPSERT when sqlite3 gets updated to have it
        elif current_user:
            await db_man.execute(f"UPDATE mal_users SET mal_username='{escaped_mal_user}', "
                                                       "last_updated=CURRENT_TIMESTAMP "
                                        f"WHERE ps_username='{ps_user}'")

            cu_rows = await db_man.execute("SELECT COUNT(*) FROM mal_users "
                                                f"WHERE mal_username='{current_user}'")
            if cu_rows[0][0] == 0:
                await db_man.execute(f"DROP TABLE mal_{current_user}")
        else:
            await db_man.execute("INSERT INTO mal_users (ps_username, mal_username) "
                                  f"VALUES ('{ps_user}', '{escaped_mal_user}')")

        asyncio.create_task(update_mal_user(mal_user, db_man, mal_man))

        return f"Set {ps_user}'s MAL to {mal_user}."
    else:
        return f'Could not find MAL user {mal_user}.'


async def show_mal_user(ps_user, anilist_man, db_man, mal_man):
    mal_user = await mal_of_ps(ps_user, db_man)
    user_data = await get_mal_user(mal_user, mal_man) if mal_user else None

    if user_data:
        # Set image
        img_url = const.IMG_NOT_FOUND
        if user_data['image_url']:
            img_url = user_data['image_url']
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
                is_nsfw = await check_mal_nsfw(medium, rand_fav['mal_id'], anilist_man, db_man)
                if is_nsfw:
                    fav_series.remove(rand_fav)
                else:
                    top_series = rand_fav['name']
                    top_series_url = rand_fav['url']
                    top_series_img = rand_fav['image_url']
                    break

            top_series_uhtml[medium] = (top_series, top_series_url,
                                        gen_uhtml_img_code(top_series_img, height_resize=64))

        user_info = UserInfo(user_data['username'], user_data['url'], 'mal')
        kwargs = {'profile_pic': img_uhtml,
                  'anime_completed': user_data['anime_stats']['completed'],
                  'anime_watching': user_data['anime_stats']['watching'],
                  'ep_watched': user_data['anime_stats']['episodes_watched'],
                  'anime_score': user_data['anime_stats']['mean_score'],
                  'manga_completed': user_data['manga_stats']['completed'],
                  'manga_reading': user_data['manga_stats']['reading'],
                  'chp_read': user_data['manga_stats']['chapters_read'],
                  'manga_score': user_data['manga_stats']['mean_score'],
                  'anime_img': top_series_uhtml['anime'][2],
                  'manga_img': top_series_uhtml['manga'][2],
                  'anime_link': top_series_uhtml['anime'][1],
                  'anime_title': top_series_uhtml['anime'][0],
                  'manga_link': top_series_uhtml['manga'][1],
                  'manga_title': top_series_uhtml['manga'][0]}

        return user_info.mal_user(**kwargs)

    else:
        return f'Could not find the MAL account for {ps_user}. They may need to use ]mal_add first.'


async def mal_user_rand_series(ps_user, anilist_man, db_man, mal_man):
    mal_user = await mal_of_ps(ps_user, db_man)

    if not mal_user:
        return f'Could not find the MAL account for {ps_user}. They may need to use ]mal_add first.'

    table_name = f'mal_list_{find_true_name(mal_user)}'

    msg = f"Loading {ps_user}'s list for the first time. This may take several minutes. Please try again later."
    table_exists = await db_man.execute("SELECT name FROM sqlite_master "
                                            f"WHERE type='table' AND name='{table_name}'")
    if table_exists:
        all_series = await db_man.execute(f"SELECT * FROM {table_name}")

        series = None
        is_nsfw = True
        while is_nsfw and all_series:
            index = random.randrange(len(all_series))
            # series = (medium, mal_id, title, last_updated)
            series = all_series.pop(index)

            is_nsfw = await check_mal_nsfw(series[0], series[1], anilist_man, db_man)

        msg = f'No valid series found for {ps_user}'
        if series:
            msg = f'rolled {series[2]}'

    # Update cache
    last_updated = await db_man.execute("SELECT last_updated FROM mal_users "
                                            f"WHERE mal_username='{mal_user}'")

    update_list = False
    for row in last_updated:
        update_time = datetime.datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
        if datetime.datetime.now() - update_time > datetime.timedelta(days=2):
            update_list = True
            break

    if update_list:
        asyncio.create_task(update_mal_user(mal_user, db_man, mal_man))

    return msg
