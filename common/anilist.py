import aiohttp
import asyncio
import json
import random

import common.constants as const

from common.uhtml import ItemInfo
from common.utils import gen_uhtml_img_code


async def anilist_num_entries(query, query_vars, session):
    '''
    Oneshot query to determine the total number of entries
    in an anilist query. Requires the query to have pageInfo.

    Does not have the anilist context manager lock.
    '''
    async with session.post(const.ANILIST_API, json={'query': query, 'variables': query_vars}) as r:
        resp = await r.json()

        if r.status != 200:
            return

    return resp['data']['Page']['pageInfo']['total']


async def anilist_search(medium, search, anilist_man):
    query = '''
    query ($search: String) {
        Page (page: 1, perPage: 1) {
            media (MEDIUM_PLACEHOLDER, search: $search, isAdult: false) {
                id
                idMal
                title {
                    english
                    romaji
                }
                coverImage {
                    extraLarge
                }
                status
                episodes
                chapters
                description
                averageScore
            }
        }
    }
    '''

    mq = 'type: ANIME' if medium == 'anime' else 'type: MANGA'
    query = query.replace('MEDIUM_PLACEHOLDER', mq)
    query_vars = {
        'search': search
    }

    series_data = {}

    async with anilist_man.lock():
        async with aiohttp.ClientSession() as session:
            async with session.post(const.ANILIST_API, json={'query': query, 'variables': query_vars}) as r:
                resp = await r.json()

                if r.status != 200:
                    err_msg = resp['errors'][0]['message']
                    return f'hippoerror, Status code {r.status} when fetching {search}: {err_msg}'

                series_list = resp['data']['Page']['media']
                if not series_list:
                    return f'hippoerror, No {medium} found for {search}.'

                series_data = series_list[0]

    mal_url = f'https://myanimelist.net/{medium}/{series_data["idMal"]}'
    img_uhtml = gen_uhtml_img_code(series_data['coverImage']['extraLarge'], dims=(65, 100))
    title = series_data['title']['english']
    if not title:
        title = series_data['title']['romaji']

    parts = 'Episodes' if medium == 'anime' else 'Chapters'
    score = f'{series_data["averageScore"]}%' if series_data['averageScore'] else 'N/A'

    item_info = ItemInfo(title, mal_url, 'mal')

    kwargs = {'img_uhtml': img_uhtml,
              'al_link': f'https://anilist.co/{medium}/{series_data["id"]}',
              'ongoing': series_data['status'],
              'parts': f'{parts}: {series_data[parts.lower()]}',
              'score': score,
              'synopsis': series_data['description']}

    uhtml = item_info.animanga(**kwargs)

    return f'hippo{medium}{series_data["idMal"]}, {uhtml}'


async def anilist_rand_series(medium, anilist_man, genres=[], tags=[]):
    query = '''
    query ($page: Int) {
        Page (page: $page, perPage: 1) {
            pageInfo {
                total
            }
            media (CATEGORIES_PLACEHOLDER minimumTagRank: 50, type: TYPE_PLACEHOLDER, isAdult: false) {
                id
                idMal
                title {
                    english
                    romaji
                }
                coverImage {
                    extraLarge
                }
                status
                episodes
                chapters
                description
                averageScore
            }
        }
    }
    '''

    category_params = []
    if genres:
        category_params.append(f'genre_in: {json.dumps(genres)}')
    if tags:
        category_params.append(f'tag_in: {json.dumps(tags)}')

    category_params_str = ','.join(category_params)
    if category_params_str:
        category_params_str += ','

    query = query.replace('CATEGORIES_PLACEHOLDER', category_params_str)
    query = query.replace('TYPE_PLACEHOLDER', medium.upper())
    query_vars = {'page': 1}

    num_entries = 0
    async with aiohttp.ClientSession() as session:
        async with anilist_man.lock():
            num_entries = await anilist_num_entries(query, query_vars, session)

        if not num_entries:
            return 'No series found with the given specifications.'

        query_vars['page'] = random.randint(1, num_entries)

        series_data = {}
        async with anilist_man.lock():
            async with session.post(const.ANILIST_API, json={'query': query, 'variables': query_vars}) as r:
                resp = await r.json()

                if r.status != 200:
                    err_msg = resp['errors'][0]['message']
                    return f'Status code {r.status} when fetching {query}: {err_msg}'
            
                series_data = resp['data']['Page']['media'][0]

    mal_url = f'https://myanimelist.net/{medium}/{series_data["idMal"]}'
    img_uhtml = gen_uhtml_img_code(series_data['coverImage']['extraLarge'], dims=(65, 100))
    title = series_data['title']['english']
    if not title:
        title = series_data['title']['romaji']

    parts = 'Episodes' if medium == 'anime' else 'Chapters'
    score = f'{series_data["averageScore"]}%' if series_data['averageScore'] else 'N/A'

    item_info = ItemInfo(title, mal_url, 'mal')

    kwargs = {'img_uhtml': img_uhtml,
              'al_link': f'https://anilist.co/{medium}/{series_data["id"]}',
              'ongoing': series_data['status'],
              'parts': f'{parts}: {series_data[parts.lower()]}',
              'score': score,
              'synopsis': series_data['description']}

    uhtml = item_info.animanga(**kwargs)

    return f'hippo{medium}{series_data["idMal"]}, {uhtml}'


async def check_mal_nsfw(medium, series, anilist_man, db_man):
    bl = await db_man.execute(f"SELECT mal_id FROM mal_banlist WHERE medium = '{medium}'")

    for mal_id in bl:
        if series == mal_id[0]:
            return True

    query = '''
    query ($mal_id: Int) {
        Page (page: 1, perPage: 1) {
            pageInfo {
                total
            }
            media (MEDIUM_PLACEHOLDER, idMal: $mal_id, isAdult: false) {
                id
            }
        }
    }
    '''
    query_vars = {'mal_id': series}

    is_safe = None
    async with anilist_man.lock():
        async with aiohttp.ClientSession() as session:
            # There will exist a series if isAdult is false and the series exists.
            # This does bl any series that have a MAL ID and are not on AL.
            is_safe = anilist_num_entries(query, query_vars, session)

    if not is_safe:
        await db_man.execute("INSERT INTO mal_banlist (medium, mal_id, manual) "
                            f"VALUES ('{medium}', {series}, 0)")
        return True
    else:
        return False
