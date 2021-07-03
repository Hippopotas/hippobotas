import aiohttp
import asyncio
import json
import pandas as pd
import random

import common.constants as const

from common.uhtml import UserInfo, ItemInfo
from common.utils import find_true_name, gen_uhtml_img_code

async def check_mal_nsfw(medium, series):
    bl = json.load(open(const.BANLISTFILE))
    if str(series) in bl[medium]:
        return True

    async with aiohttp.ClientSession(trust_env=True) as session:
        retry = 0
        while retry < 3:
            async with session.get(const.JIKAN_API + '{}/{}'.format(medium, series)) as r:
                resp = await r.text()
                series_data = json.loads(resp)

                if r.status != 200:
                    retry += 1
                    await asyncio.sleep(2)
                    continue

                for genre in series_data['genres']:
                    if genre['mal_id'] == 12:
                        return True

                return False


async def get_mal_user(username, retries=5):
    async with aiohttp.ClientSession(trust_env=True) as session:
        retry = 0
        while retry < retries:
            async with session.get(const.JIKAN_API + 'user/{}'.format(username)) as r:
                resp = await r.text()
                userdata = json.loads(resp)

                if r.status == 404 or r.status == 400:
                    return None
                elif r.status != 200:
                    print('Status {} when getting {} MAL'.format(r.status, username))
                    await asyncio.sleep(10)
                
                    retry += 1
                    continue

                return userdata


async def set_mal_user(putter, ps_user, mal_user, ctx):
    prefix = f'{ctx}|'
    if ctx == 'pm':
        prefix = f'|/w {ps_user},'

    userdata = await get_mal_user(mal_user)
    if userdata:
        mal_list = pd.read_csv(const.MALFILE)

        existing_user = mal_list[mal_list['user'] == ps_user]
        if existing_user.empty:
            new_user = pd.DataFrame([[ps_user, mal_user]], columns=['user', 'mal'])
            mal_list = mal_list.append(new_user)
        else:
            mal_list.loc[mal_list['user'] == ps_user, 'mal'] = mal_user
        
        mal_list.to_csv(const.MALFILE, index=False)
        await putter(f'{prefix} Set {ps_user}\'s MAL to {mal_user}.')
    else:
        await putter(f'{prefix} Could not find MAL user {mal_user}.')


async def show_mal_user(putter, username, true_caller, ctx):
    prefix = f'{ctx}|'
    if ctx == 'pm':
        prefix = f'|/w {true_caller},'

    userdata = await get_mal_user(username)
    if userdata:
        if ctx == 'pm':
            user_url = userdata['url']
            await putter(f'{prefix} {user_url}')
            return

        # Set image
        img_url = const.IMG_NOT_FOUND
        if userdata['image_url']:
            img_url = userdata['image_url']
        img_uhtml = gen_uhtml_img_code(img_url, height_resize=100, width_resize=125)

        # Set favorite series
        top_series_uhtml = {'anime': (), 'manga': ()}
        for medium in top_series_uhtml:
            top_series = 'None'
            top_series_url = ''
            top_series_img = const.IMG_NOT_FOUND

            fav_series = userdata['favorites'][medium]
            while fav_series:
                rand_fav = random.choice(fav_series)
                is_nsfw = await check_mal_nsfw(medium, rand_fav['mal_id'])
                if is_nsfw:
                    fav_series.remove(rand_fav)
                else:
                    top_series = rand_fav['name']
                    top_series_url = rand_fav['url']
                    top_series_img = rand_fav['image_url']
                    break

            top_series_uhtml[medium] = (top_series, top_series_url,
                                        gen_uhtml_img_code(top_series_img, height_resize=64))

        user_info = UserInfo(userdata['username'], userdata['url'], 'mal')
        kwargs = {'profile_pic': img_uhtml,
                  'anime_completed': userdata['anime_stats']['completed'],
                  'anime_watching': userdata['anime_stats']['watching'],
                  'ep_watched': userdata['anime_stats']['episodes_watched'],
                  'anime_score': userdata['anime_stats']['mean_score'],
                  'manga_completed': userdata['manga_stats']['completed'],
                  'manga_reading': userdata['manga_stats']['reading'],
                  'chp_read': userdata['manga_stats']['chapters_read'],
                  'manga_score': userdata['manga_stats']['mean_score'],
                  'anime_img': top_series_uhtml['anime'][2],
                  'manga_img': top_series_uhtml['manga'][2],
                  'anime_link': top_series_uhtml['anime'][1],
                  'anime_title': top_series_uhtml['anime'][0],
                  'manga_link': top_series_uhtml['manga'][1],
                  'manga_title': top_series_uhtml['manga'][0]}

        mal_uhtml = user_info.mal_user(**kwargs)

        await putter(f'{prefix}/adduhtml {username}-mal, {mal_uhtml}')
    else:
        await putter(f'{prefix} Could not find the MAL account {username}. ')


async def mal_user_rand_series(putter, username, caller, media, ctx):
    true_caller = find_true_name(caller)

    prefix = f'{ctx}|'
    if ctx == 'pm':
        prefix = f'|/w {true_caller},'

    all_series_list = []
    for medium in media:
        # Different terms for anime vs manga
        in_progress = 'reading'
        if medium == 'anime':
            in_progress = 'watching'

        for status in (in_progress, 'completed'):
            series_list = {medium: 'placeholder'}
            page = 1
            while series_list[medium]:
                series_list = await get_mal_user('{}/{}list/{}/{}'.format(username,
                                                                          medium,
                                                                          status,
                                                                          page))

                if series_list:
                    all_series_list += series_list[medium]
                else:
                    break
                
                page += 1
                await asyncio.sleep(0.5)    # Jikan rate-limits to 2 requests/second.

    while all_series_list:
        rand_series = random.choice(all_series_list)

        medium = 'manga'
        if find_true_name(rand_series['type']) in const.ANIME_TYPES:
            medium = 'anime'
        is_nsfw = await check_mal_nsfw(medium, rand_series['mal_id'])
        if is_nsfw:
            all_series_list.remove(rand_series)
        else:
            rand_title = rand_series['title']
            break

    if not all_series_list:
        await putter(f'{prefix} No series found for {username} with the given specifications.')
        return

    msg = f'{prefix} {caller} rolled {rand_title}'
    await putter(msg)


async def mal_search(putter, ctx, medium, query):
    msg_body = ''
    results = []
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.get(const.JIKAN_SEARCH_API + f'{medium}?q={query}') as r:
            resp = await r.json()

            if r.status != 200:
                err_msg = resp.get('message', '[No error message]')
                msg_body = f'{r.status} - {err_msg}'

            results = resp.get('results', [])

    if results:
        for r in results:
            is_nsfw = await check_mal_nsfw(medium, r['mal_id'])
            if not is_nsfw:
                name = r['title'] if 'title' in r else r['name']
                img_uhtml = gen_uhtml_img_code(r['image_url'], height_resize=100)

                ongoing = 'Ongoing' if r.get('airing', r.get('publishing', False)) else 'Completed'
                parts = 'Episodes' if 'episodes' in r else 'Chapters'

                item_info = ItemInfo(name, r['url'], 'mal')

                kwargs = {'img_uhtml': img_uhtml,
                          'ongoing': ongoing,
                          'parts': f'{parts}: {r[parts.lower()]}',
                          'score': f"""Score: {r['score']}""",
                          'synopsis': r['synopsis']}

                uhtml = item_info.animanga(**kwargs)

                msg_body = f"""/adduhtml hippo{medium}{r['mal_id']}, {uhtml}"""
                break

            await asyncio.sleep(0.2)
        else:
            msg_body = 'No valid series found.'

    msg = f'{ctx}|{msg_body}'
    await putter(msg)