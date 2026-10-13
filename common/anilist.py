import aiohttp
import datetime
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
        if r.status != 200:
            return

        resp = await r.json()

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
                resp = await r.json(content_type=None)

                if r.status != 200:
                    err_msg = (resp or {}).get('errors', [{}])[0].get('message', 'unknown error')
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
                    userPreferred
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
            return 'hippoerror, No series found with the given specifications.'

        query_vars['page'] = random.randint(1, num_entries)

        series_data = {}
        while not series_data:
            async with anilist_man.lock():
                async with session.post(const.ANILIST_API, json={'query': query, 'variables': query_vars}) as r:
                    resp = await r.json(content_type=None)

                    if r.status != 200:
                        err_msg = (resp or {}).get('errors', [{}])[0].get('message', 'unknown error')
                        return f'hippoerror, Status code {r.status} when fetching a random {medium}: {err_msg}'

                    media = resp['data']['Page']['media']
                    if media:
                        series_data = media[0]
                    elif query_vars['page'] <= 1:
                        return 'hippoerror, No series found with the given specifications.'
                    else:
                        query_vars['page'] = query_vars['page'] // 2

    mal_url = f'https://myanimelist.net/{medium}/{series_data["idMal"]}'
    img_uhtml = gen_uhtml_img_code(series_data['coverImage']['extraLarge'], dims=(65, 100))
    title = series_data['title']['english']
    if not title:
        title = series_data['title']['userPreferred']

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


async def get_related_series(medium, series, anilist_man):
    related_series = [(medium, series)]
    query = '''
    query ($mal_id: Int) {
        Page (page: 1, perPage: 1) {
            media (type: TYPE_PLACEHOLDER, idMal: $mal_id, isAdult: false) {
                title {
                    userPreferred
                }
                relations {
                    edges {
                        relationType
                        node {
                            idMal
                            type
                        }
                    }
                }
            }
        }
    }
    '''
    title = ''

    for s in related_series:
        async with anilist_man.lock():
            async with aiohttp.ClientSession() as session:
                series_query = query.replace('TYPE_PLACEHOLDER', s[0].upper())
                query_vars = {'mal_id': s[1]}
                async with session.post(const.ANILIST_API, json={'query': series_query, 'variables': query_vars}) as r:
                    resp = await r.json()

                    if r.status != 200:
                        continue

                    if s == (medium, series):
                        title = resp['data']['Page']['media'][0]['title']['userPreferred']

                    for rs in resp['data']['Page']['media'][0]['relations']['edges']:
                        # Not every AniList entry has a MAL counterpart.
                        if rs['node']['idMal'] is None:
                            continue
                        rs_info = (rs['node']['type'].lower(), rs['node']['idMal'])
                        if rs_info not in related_series and rs['relationType'] != 'CHARACTER':
                            related_series.append(rs_info)

    return (related_series, title)


async def add_anotd_bl(medium, series, anilist_man, db_man):
    related_series, title = await get_related_series(medium, series, anilist_man)

    expiration = str(datetime.datetime.now() + datetime.timedelta(days=365))

    await db_man.execute("INSERT INTO anotd_banlist (medium, mal_id, name, expiration) "
                         "VALUES (?, ?, ?, ?)", (medium, series, title, expiration))

    for s in related_series:
        exists = await db_man.execute("SELECT * FROM mal_banlist WHERE medium=? AND mal_id=?", s)

        if not exists:
            await db_man.execute("INSERT INTO mal_banlist (medium, mal_id, anotd_source) "
                                 "VALUES (?, ?, 1)", s)


async def rm_anotd_bl(medium, series, anilist_man, db_man):
    related_series, _ = await get_related_series(medium, series, anilist_man)

    for s in related_series:
        await db_man.execute("DELETE FROM mal_banlist WHERE medium=? AND mal_id=? AND anotd_source=1", s)

    await db_man.execute("DELETE FROM anotd_banlist WHERE medium=? AND mal_id=?", (medium, series))
