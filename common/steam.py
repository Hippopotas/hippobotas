import logging
import aiohttp
import asyncio
import json
import os
import pandas as pd
import random
import re

from common.constants import IMG_NOT_FOUND, STEAM_API, STEAMFILE
from common.uhtml import UserInfo
from common.utils import find_true_name, gen_uhtml_img

logger = logging.getLogger(__name__)

# A 64-bit Steam ID, as in steamcommunity.com/profiles/<id>.
STEAM64_ID = re.compile(r'^7656119\d{10}$')


async def steam_api_get(session, path, params, retries=2):
    '''
    Calls the official Steam Web API with the bot's key. Returns the
    'response' object, or None on failure.
    '''
    params = dict(params, key=os.getenv('STEAM_KEY'))
    for attempt in range(retries + 1):
        try:
            async with session.get(STEAM_API + path, params=params) as r:
                if r.status == 200:
                    return (await r.json(content_type=None)).get('response')
                logger.warning(f'Steam API {path.split("/")[1]} returned code {r.status}.')
                # Only rate limits and server errors are worth retrying.
                if r.status != 429 and r.status < 500:
                    return None
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            logger.warning(f'Steam API {path.split("/")[1]} failed: {e!r}')
        if attempt < retries:
            await asyncio.sleep(2 ** attempt)
    return None


async def get_steam_user(username, retries=2):
    '''
    Looks up a Steam account by its 64-bit ID or its custom URL name
    (steamcommunity.com/id/<name>), using only the official Web API. The
    community profile pages used before are heavily rate limited.
    '''
    # Saved IDs are read from the CSV as numbers.
    username = '' if username is None else str(username).strip().strip('/')
    if not username:
        return None

    async with aiohttp.ClientSession(trust_env=True) as session:
        id64 = username if STEAM64_ID.match(username) else None
        if not id64:
            resolved = await steam_api_get(session, 'ISteamUser/ResolveVanityURL/v0001/',
                                           {'vanityurl': username}, retries)
            if resolved and resolved.get('success') == 1:
                id64 = resolved.get('steamid')
        if not id64:
            return None

        summary = await steam_api_get(session, 'ISteamUser/GetPlayerSummaries/v0002/',
                                      {'steamids': id64}, retries)
        players = (summary or {}).get('players') or []
        return players[0] if players else None


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
            steam_list = pd.concat([steam_list, new_user])
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
            if 1 in (game_info.get('content_descriptors', {}).get('ids') or []) and game_info['steam_appid'] not in [1086940, 1687950, 719040]:
                return None

    return game_info


async def gen_uhtml_steam_game(game_id, recent_hours, total_hours):
    game_info = await steam_game_info(game_id)

    if not game_info:
        return None

    game_name = game_info['name']
    img_uhtml = await gen_uhtml_img(game_info['header_image'], height_resize=50)

    game_kwargs = {'img_uhtml': img_uhtml,
                   'url': f'https://store.steampowered.com/app/{game_id}',
                   'name': game_name,
                   'recent_hours': round(recent_hours, 1),
                   'total_hours': round(total_hours, 1)}
    msg = UserInfo.steam_game_uhtml(**game_kwargs)

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
        img_uhtml = await gen_uhtml_img(img_url, height_resize=100, width_resize=125)

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

        user_info = UserInfo(userdata['personaname'], userdata['profileurl'], 'steam')
        kwargs = {'hours': round(total_recent_hours, 1),
                  'img_uhtml': img_uhtml,
                  'game_uhtmls': game_uhtmls}
        steam_uhtml = user_info.steam_user(**kwargs)

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
