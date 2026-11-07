import aiohttp
import asyncio
import datetime
import json
import logging
import random
import time

import common.constants as const

from common.uhtml import ItemInfo
from common.utils import img_tag

logger = logging.getLogger(__name__)

# AniList allows 30 requests a minute; when it says to wait, wait at most this long.
MAX_RATE_LIMIT_WAIT = 65


def anilist_wait_time(status, headers):
    '''
    How long to wait before the next AniList request: as long as it asks
    after a 429, or until the limit resets if no requests are left.
    '''
    try:
        if status == 429:
            wait = float(headers.get('Retry-After', 60))
        elif int(headers.get('X-RateLimit-Remaining', 1)) <= 0 and headers.get('X-RateLimit-Reset'):
            wait = float(headers['X-RateLimit-Reset']) - time.time() + 1
        else:
            return 0
    except (TypeError, ValueError):
        wait = 60 if status == 429 else 0
    return min(max(wait, 1), MAX_RATE_LIMIT_WAIT)


async def anilist_post(session, query, query_vars, anilist_man, attempts=4):
    '''
    Sends an AniList query, waiting out its rate limit (and retrying
    briefly on server errors) instead of failing. Waits happen while
    holding the AniList lock, so every other AniList request waits too.
    When AniList says no requests are left, this result is returned right
    away and the next request waits for the limit to reset.

    Returns:
        (status, json): status is None if AniList couldn't be reached.
    '''
    status, resp = None, None
    for _ in range(attempts):
        headers = {}
        async with anilist_man.lock():
            resume_in = getattr(anilist_man, 'anilist_resume_at', 0) - time.monotonic()
            if resume_in > 0:
                logger.info(f'Waiting {resume_in:.0f}s for the AniList rate limit to reset.')
                await asyncio.sleep(resume_in)
            try:
                async with session.post(const.ANILIST_API,
                                        json={'query': query, 'variables': query_vars}) as r:
                    status, headers = r.status, r.headers
                    try:
                        resp = await r.json(content_type=None)
                    except ValueError:
                        resp = None
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f'AniList request failed: {e!r}')
                status, resp = None, None

            wait = anilist_wait_time(status, headers)
            if wait:
                logger.info(f'AniList rate limit reached; pausing AniList requests for {wait:.0f}s.')
                anilist_man.anilist_resume_at = time.monotonic() + wait

        if status == 200:
            return status, resp
        if status is not None and status != 429 and status < 500:
            return status, resp    # A real error; retrying won't help.
        if status != 429:
            await asyncio.sleep(2)
    return status, resp


async def anilist_num_entries(query, query_vars, session, anilist_man):
    '''
    Oneshot query to determine the total number of entries
    in an anilist query. Requires the query to have pageInfo.

    Returns None if AniList couldn't answer.
    '''
    status, resp = await anilist_post(session, query, query_vars, anilist_man)
    if status != 200 or not resp:
        return None
    try:
        return resp['data']['Page']['pageInfo']['total']
    except (KeyError, TypeError):
        return None


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
    img_uhtml = img_tag(series_data['coverImage']['extraLarge'], (65, 100))
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
        num_entries = await anilist_num_entries(query, query_vars, session, anilist_man)

        if not num_entries:
            return 'hippoerror, No series found with the given specifications.'

        query_vars['page'] = random.randint(1, num_entries)

        series_data = {}
        while not series_data:
            status, resp = await anilist_post(session, query, query_vars, anilist_man)

            if status != 200 or not resp:
                err_msg = (resp or {}).get('errors', [{}])[0].get('message', 'unknown error')
                return f'hippoerror, Status code {status} when fetching a random {medium}: {err_msg}'

            media = resp['data']['Page']['media']
            if media:
                series_data = media[0]
            elif query_vars['page'] <= 1:
                return 'hippoerror, No series found with the given specifications.'
            else:
                query_vars['page'] = query_vars['page'] // 2

    mal_url = f'https://myanimelist.net/{medium}/{series_data["idMal"]}'
    img_uhtml = img_tag(series_data['coverImage']['extraLarge'], (65, 100))
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
