import aiohttp
import asyncio

import common.constants as const

from common.uhtml import ItemInfo
from common.utils import gen_uhtml_img_code


async def anilist_search(medium, search, anilist_man):
    msg_body = ''
    results = []

    query = '''
    query ($search: String) {
        Page (page: 1, perPage: 1) {
            media (MEDIUM_PLACEHOLDER, search: $search, isAdult: false) {
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
                meanScore
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

    async with aiohttp.ClientSession() as session:
        async with anilist_man.lock():
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

    item_info = ItemInfo(title, mal_url, 'mal')

    kwargs = {'img_uhtml': img_uhtml,
              'ongoing': series_data['status'],
              'parts': f'{parts}: {series_data[parts.lower()]}',
              'score': series_data['meanScore'],
              'synopsis': series_data['description']}

    uhtml = item_info.animanga(**kwargs)

    return f'hippo{medium}{series_data["idMal"]}, {uhtml}'
