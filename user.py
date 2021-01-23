import aiohttp
import asyncio
import json
import os
import pandas as pd
import random
import re

from constants import ANIME_ROOM
from constants import JIKAN_API, IMG_NOT_FOUND, STEAM_API
from constants import ANIME_TYPES, MANGA_TYPES
from trivia import gen_uhtml_img_code


async def check_mal_nsfw(medium, series):
    async with aiohttp.ClientSession(trust_env=True) as session:
        retry = 0
        while retry < 3:
            async with session.get(JIKAN_API + '{}/{}'.format(medium, series)) as r:
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

    while all_series_list:
        rand_series = random.choice(all_series_list)

        medium = 'manga'
        if User.find_true_name(rand_series['type']) in ANIME_TYPES:
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


async def get_steam_user(username, retries=2):
    async with aiohttp.ClientSession(trust_env=True) as session:
        id64 = None
        url_vers = 'profiles'
        for i in range(retries):
            async with session.get(f'https://steamcommunity.com/{url_vers}/{username}/?xml=1') as r:
                resp = await r.text()

                if r.status != 200:
                    print(f'Steam prelim check returned code {r.status}.')
                    await asyncio.sleep(0.5)
                    continue

                # If user has set steam ID, check if they gave that instead of steam64 ID.
                if 'The specified profile could not be found.' in resp:
                    url_vers = 'id'
                    continue

                m = re.search(r'<steamID64>(?P<id>\w+)</steamID64>', resp)
                if m:
                    id64 = m.group('id')
                    break
                else:
                    return None

        if id64:
            steam_key = os.getenv('STEAM_KEY')
            for i in range(retries):
                async with session.get(f'{STEAM_API}ISteamUser/GetPlayerSummaries/V0002/?key={steam_key}&steamids={id64}') as r:
                    resp = await r.text()
                    userdata = json.loads(resp)

                    if r.status != 200:
                        print(f' Steam prelim check returned code {r.status}.')
                        await asyncio.sleep(0.5)
                        continue

                    return userdata['response']['players'][0]

        return None


async def set_steam_user(putter, ps_user, steam_user, ctx):
    prefix = f'{ctx}|'
    if ctx == 'pm':
        prefix = f'|/w {ps_user},'

    userdata = await get_steam_user(steam_user)
    if userdata:
        persona_name = userdata['personaname']
        id64 = userdata['steamid']
        steam_list = pd.read_csv('steam.txt')

        existing_user = steam_list[steam_list['user'] == ps_user]
        if existing_user.empty:
            new_user = pd.DataFrame([[ps_user, id64]], columns=['user', 'steam'])
            steam_list = steam_list.append(new_user)
        else:
            steam_list.loc[steam_list['user'] == ps_user, 'steam'] = id64

        steam_list.to_csv('steam.txt', index=False)
        await putter(f'{prefix} Set {ps_user}\'s Steam to {persona_name}.')
    else:
        await putter(f'{prefix} Could not find steam user {steam_user}. Make sure to use the ID in the URL!')


async def steam_game_info(game_id):
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.get(f'https://store.steampowered.com/api/appdetails/?appids={game_id}') as r:
            resp = await r.text()
            if r.status != 200:
                return None

            temp_json = json.loads(resp)[str(game_id)]
            if not temp_json['success']:
                return None

            game_info = temp_json['data']

            # NSFW games
            if 1 in game_info['content_descriptors']['ids']:
                return None

    return game_info


async def gen_uhtml_steam_game(game_id, recent_hours, total_hours):
    game_info = await steam_game_info(game_id)

    if not game_info:
        return None

    game_name = game_info['name']
    img_uhtml = gen_uhtml_img_code(game_info['header_image'], height_resize=50)
    msg = (f'<tr><td style=\'padding: 0px 5px 5px 5px\'>{img_uhtml}</td>'
            '<td align=left style=\'vertical-align:top; font-size:10px\'>'
           f'<a href=\'https://store.steampowered.com/app/{game_id}\' style=\'color:#FFF\'>'
           f'{game_name}</a></td>'
            '<td align=right style=\'vertical-align:bottom; font-size:10px; color:#FFF; padding: 0px 5px 5px 0px\'>'
           f'{recent_hours:.1f} hrs last two weeks<br>{total_hours:.1f} hrs total playtime</td></tr>')
    
    return msg


async def show_steam_user(putter, username, true_caller, ctx):
    prefix = f'{ctx}|'
    if ctx == 'pm':
        prefix = f'|/w {true_caller},'

    userdata = await get_steam_user(username)
    if userdata:
        if ctx == 'pm':
            user_url = userdata['profileurl']
            await putter(f'{prefix} {user_url}')
            return

        # Set image
        img_url = IMG_NOT_FOUND
        if userdata['avatarfull']:
            img_url = userdata['avatarfull']
        img_uhtml = gen_uhtml_img_code(img_url, height_resize=100, width_resize=125)

        # Generate recently played uhtml
        id64 = userdata['steamid']
        steam_key = os.getenv('STEAM_KEY')

        recent_games = []

        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.get(f'{STEAM_API}IPlayerService/GetRecentlyPlayedGames/v0001/?key={steam_key}&steamid={id64}&count=all') as r:
                resp = await r.text()

                temp_json = json.loads(resp)
                if temp_json['response']:
                    if 'games' in temp_json['response']:
                        recent_games = temp_json['response']['games']

        game_uhtmls = []
        for game in recent_games:
            recent_hours = game['playtime_2weeks'] / 60
            total_hours = game['playtime_forever'] / 60
            game_uhtml = await gen_uhtml_steam_game(game['appid'], recent_hours, total_hours)

            if game_uhtml:
                game_uhtmls.append(game_uhtml)

            if len(game_uhtmls) >= 2:
                break

        # Fix spacing issues by appending blank game entry.
        if len(game_uhtmls) == 1:
            game_uhtmls.append('<tr><td style=\'padding: 0px 5px 5px 5px\'><div style=\'min-height:50px\'></div></td></tr>')

        total_recent_hours = 0
        for game in recent_games:
            total_recent_hours += game['playtime_2weeks']
        total_recent_hours /= 60

        profile_url = userdata['profileurl']
        persona_name = userdata['personaname']
        all_game_uhtml = ''.join(game_uhtmls)

        steam_uhtml = ('<table style=\'border:3px solid #858585; border-spacing:0px; border-radius:10px; '
                       'background-image:url(https://i.imgur.com/c68ilQW.png); background-size:cover\'>'
                       '<thead><tr><th width=96 style=\'font-size:14px; padding:5px; border-right:3px solid #858585\'>'
                      f'<a href=\'{profile_url}\' style=\'color:#FFF\'>{persona_name}</a></th>'
                       '<th align=left style=\'font-weight:normal; color:#858585; padding-left:5px\' colspan=2>Recent Activity</th>'
                       '<th align=right style=\'font-weight:normal; color:#858585; padding-left:30px; padding-right: 5px\'>'
                      f'{total_recent_hours:.1f} hours past 2 weeks</th></tr></thead><tbody>'
                      f'<td rowspan=6 style=\'border-right:3px solid #858585; padding:5px\'>{img_uhtml}</td></tr>'
                      f'{all_game_uhtml}</tbody></table>')
        
        await putter(f'{prefix}/adduhtml {username}-steam, {steam_uhtml}')
    else:
        await putter(f'{prefix} Could not find the Steam account {username}. ')


async def steam_user_rand_series(putter, id64, username, caller, ctx):
    true_caller = User.find_true_name(caller)

    prefix = f'{ctx}|'
    if ctx == 'pm':
        prefix = f'|/w {true_caller},'

    games = []
    async with aiohttp.ClientSession(trust_env=True) as session:
        steam_key = os.getenv('STEAM_KEY')
        async with session.get(f'{STEAM_API}IPlayerService/GetOwnedGames/v0001/?key={steam_key}&steamid={id64}') as r:
            resp = await r.text()

            try:
                games = json.loads(resp)['response']['games']
            except:
                await putter(f'{prefix} No games found for {username} with the given specifications.')
                return                

    game_info = None
    while True:
        if len(games) == 0:
            await putter(f'{prefix} No games found for {username} with the given specifications.')
            return                

        rand_game = random.choice(games)

        game_id = rand_game['appid']
        game_info = await steam_game_info(game_id)

        if not game_info:
            games.remove(rand_game)
            await asyncio.sleep(1)
            continue
        else:
            break

    rand_title = game_info['name']
    msg = f'{prefix}{caller} rolled {rand_title}'
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