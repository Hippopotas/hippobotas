import aiohttp
import asyncio
import json
import pandas as pd
import random
import re

from constants import ANIME_ROOM
from constants import JIKAN_API, IMG_NOT_FOUND
from trivia import gen_uhtml_img_code


async def get_mal_user(username, retries=5):
    async with aiohttp.ClientSession(trust_env=True) as session:
        retry = 0
        while retry < retries:
            async with session.get(JIKAN_API + 'user/{}'.format(username)) as r:
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
        mal_list = pd.read_csv('mal.txt')

        existing_user = mal_list[mal_list['user'] == ps_user]
        if existing_user.empty:
            new_user = pd.DataFrame([[ps_user, mal_user]], columns=['user', 'mal'])
            mal_list = mal_list.append(new_user)
        else:
            mal_list.loc[mal_list['user'] == ps_user, 'mal'] = mal_user
        
        mal_list.to_csv('mal.txt', index=False)
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
        img_url = IMG_NOT_FOUND
        if userdata['image_url']:
            img_url = userdata['image_url']
        img_uhtml = gen_uhtml_img_code(img_url, height_resize=100, width_resize=125)

        # Set favorite series
        top_series_uhtml = {'anime': (), 'manga': ()}
        for medium in top_series_uhtml:
            top_series = 'None'
            top_series_url = ''
            top_series_img = IMG_NOT_FOUND

            fav_series = userdata['favorites'][medium]
            if fav_series:
                rand_fav = random.choice(fav_series)
                top_series = rand_fav['name']
                top_series_url = rand_fav['url']
                top_series_img = rand_fav['image_url']

            top_series_uhtml[medium] = (top_series, top_series_url,
                                        gen_uhtml_img_code(top_series_img, height_resize=64))

        mal_uhtml = ('<table style=\'border:3px solid #0088cc; border-spacing:0px; border-radius:10px; '
                     'background-image:url(https://i.imgur.com/l8iJKoX.png); background-size:cover\'>'
                     '<thead><tr><th width=96 style=\'font-size:14px; padding:5px; '
                     'border-right:3px solid #0088cc\'>'
                     '<a href=\'{}\' style=\'color:#8311a6\'>{}</a>'
                     '</th><th colspan=2>Anime</th>'
                     '<th colspan=2>Manga</th></tr></thead>'
                     '<tbody><tr><td rowspan=3 style='
                     '\'border-right:3px solid #0088cc; padding:5px\'>{}</td>'
                     '<td style=\'text-align:center\'>Rand Fav</td>'
                     '<td style=\'font-size:10px; vertical-align:middle\' rowspan=3>'
                     'Completed: {}<br><br>Watching: {}<br><br>'
                     'Episodes Watched: {}<br><br>Mean Score: {}</td>'
                     '<td style=\'text-align:center\'>Rand Fav</td>'
                     '<td style=\'font-size:10px; vertical-align:middle; padding-right:5px\' rowspan=3>'
                     'Completed: {}<br><br>Reading: {}<br><br>'
                     'Chapters Read: {}<br><br>Mean Score: {}</td></tr>'
                     '<tr><td>{}</td><td>{}</td></tr>'
                     '<tr><td width=80 style=\'font-size:10px; font-style:italic; '
                     'text-align:center; vertical-align:top; padding-bottom:5px\'>'
                     '<a href=\'{}\' style=\'text-decoration:none; color:#8311a6\'>{}</a></td>'
                     '<td width=80 style=\'font-size:10px; font-style:italic; '
                     'text-align:center; vertical-align:top; padding-bottom:5px\'>'
                     '<a href=\'{}\' style=\'text-decoration:none; color:#8311a6\'>{}</a></td>'
                     '</tr></tbody></table>'.format(
                            userdata['url'], userdata['username'], img_uhtml,
                            userdata['anime_stats']['completed'],
                            userdata['anime_stats']['watching'],
                            userdata['anime_stats']['episodes_watched'],
                            userdata['anime_stats']['mean_score'],
                            userdata['manga_stats']['completed'],
                            userdata['manga_stats']['reading'],
                            userdata['manga_stats']['chapters_read'],
                            userdata['manga_stats']['mean_score'],
                            top_series_uhtml['anime'][2],
                            top_series_uhtml['manga'][2],
                            top_series_uhtml['anime'][1],
                            top_series_uhtml['anime'][0],
                            top_series_uhtml['manga'][1],
                            top_series_uhtml['manga'][0]))

        await putter(f'{prefix}/adduhtml {username}-mal, {mal_uhtml}')
    else:
        await putter(f'{prefix} Could not find the MAL account {username}. ')


async def mal_user_rand_series(putter, username, caller, media, ctx):
    true_caller = User.find_true_name(caller)

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

    if not all_series_list:
        await putter(f'{prefix} No series found for {username} with the given specifications.')
        return

    rand_series = random.choice(all_series_list)
    rand_title = rand_series['title']

    msg = f'{prefix} {caller} rolled {rand_title}'
    await putter(msg)


class User:
    Groups = {'‽': -1, '!': -1, ' ': 0, '^': 0.1, '+': 1, '*': 1.5, '★': 2, '%': 2, '@': 3, '&': 4, '#': 5, '＋': 6, '~': 6}

    @staticmethod
    def compare_ranks(rank1, rank2):
        try:
            return User.Groups[rank1] >= User.Groups[rank2]
        except KeyError:
            if rank1 not in User.Groups:
                print('{rank} is not a supported usergroup'.format(rank = rank1))
            if rank2 not in User.Groups:
                print('{rank} is not a supported usergroup'.format(rank = rank2))
            return False

    @staticmethod
    def find_true_name(username):
        return re.sub(r'[^a-zA-Z0-9]', '', username).lower()

    def __init__(self, username, rank=' '):
        self.name = username
        self.true_name = self.find_true_name(self.name)
        self.rank = rank