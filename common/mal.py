import aiohttp
import random
import datetime

import common.constants as const

from common.uhtml import UserInfo, ItemInfo
from common.utils import find_true_name, gen_uhtml_img_code


async def check_mal_nsfw(medium, series, db_man, mal_man):
    bl = await db_man.execute(f"SELECT mal_id FROM mal_banlist WHERE medium = '{medium}'")

    for mal_id in bl:
        if series == mal_id[0]:
            return True

    series_data = None
    async with mal_man.lock():
        async with aiohttp.ClientSession() as session:
            url = f'{const.JIKAN_API}{medium}/{series}'
            async with session.get(url) as r:
                series_data = await r.json()

                if r.status != 200:
                    print(f"Jikan error {r.status} on {url} in "
                          f"check_mal_nsfw: {series_data['message']}")
                    return False

    for genre in series_data['genres']:
        # H
        if genre['mal_id'] == 12:
            await db_man.execute("INSERT INTO mal_banlist (medium, mal_id, manual) "
                                  f"VALUES ('{medium}', {series_data['mal_id']}, 0)")
            return True

    return False


async def mal_of_ps(ps_user, db_man):
    mal_user = await db_man.execute("SELECT mal_username FROM mal_users "
                                       f"WHERE ps_username = '{ps_user}'")

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
                    return None

                return user_data


async def set_mal_user(ps_user, mal_user, db_man, mal_man):
    user_data = await get_mal_user(mal_user, mal_man)

    if user_data:
        # Can change to actual UPSERT when sqlite3 gets updated to have it
        current_user = await mal_of_ps(ps_user, db_man)

        if current_user:
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await db_man.execute(f"UPDATE mal_users SET mal_username = {mal_user}, "
                                                      f"last_updated = {current_time}")
        else:
            await db_man.execute("INSERT INTO mal_users (ps_username, mal_username) "
                                  f"VALUES ('{ps_user}', '{mal_user}')")

        return f"Set {ps_user}'s MAL to {mal_user}."
    else:
        return f'Could not find MAL user {mal_user}.'


async def show_mal_user(ps_user, db_man, mal_man):
    mal_user = await mal_of_ps(ps_user, db_man)
    user_data = await get_mal_user(mal_user, mal_man)

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
                is_nsfw = await check_mal_nsfw(medium, rand_fav['mal_id'], db_man, mal_man)
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
        return f'Could not find the MAL account {ps_user}. They may need to use ]mal_add first.'
