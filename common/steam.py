import aiohttp
import asyncio
import json
import os
import pandas as pd
import random
import re

from common.constants import IMG_NOT_FOUND, STEAM_API, STEAMFILE
from common.utils import find_true_name, gen_uhtml_img_code

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
        steam_list = pd.read_csv(STEAMFILE)

        existing_user = steam_list[steam_list['user'] == ps_user]
        if existing_user.empty:
            new_user = pd.DataFrame([[ps_user, id64]], columns=['user', 'steam'])
            steam_list = steam_list.append(new_user)
        else:
            steam_list.loc[steam_list['user'] == ps_user, 'steam'] = id64

        steam_list.to_csv(STEAMFILE, index=False)
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
    true_caller = find_true_name(caller)

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
        elif game_info['type'] != 'game':
            games.remove(rand_game)
            await asyncio.sleep(1)
            continue
        else:
            break

    rand_title = game_info['name']
    msg = f'{prefix}{caller} rolled {rand_title}'
    await putter(msg)
