import aiohttp
import asyncio
import json

import common.constants as const

from common.utils import gen_uhtml_img_code

async def display_mtg_card(putter, card):
    msg = ''
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.get(f'{const.MTG_API}{card}') as r:
            resp = await r.text()
            all_cards = json.loads(resp)

            if r.status != 200:
                msg = all_cards['details']

            else:
                card_info = all_cards['data'][0]
                card_name = card_info['name']

                card_img = ''
                if 'card_faces' in card_info and 'image_uris' not in card_info:
                    card_img = card_info['card_faces'][0]['image_uris']['normal']
                else:
                    card_img = card_info['image_uris']['normal']
                card_link = card_info['scryfall_uri']

                img_uhtml = gen_uhtml_img_code(card_img, height_resize=200, alt=card_name)
                msg = f'/adduhtml hippomtg-{card}, <a href=\'{card_link}\'>{img_uhtml}</a>'

    await putter(f'{const.TCG_ROOM}|{msg}')


async def display_ptcg_card(putter, card):
    msg = ''
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.get(f'{const.PTCG_API}{card}') as r:
            resp = await r.text()
            all_cards = json.loads(resp)

            if r.status != 200:
                msg = all_cards['message']

            elif not all_cards['data']:
                msg = 'No cards found with the given name.'

            else:
                card_info = all_cards['data'][0]
                card_name = card_info['name']
                card_img = card_info['images']['small']

                img_uhtml = gen_uhtml_img_code(card_img, height_resize=200, alt=card_name)
                msg = f'/adduhtml hippoptcg-{card}, {img_uhtml}'

    await putter(f'{const.TCG_ROOM}|{msg}')


async def display_ygo_card(putter, card):
    msg = ''
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.get(f'{const.YGO_API}{card}') as r:
            resp = await r.text()
            all_cards = json.loads(resp)

            if r.status != 200:
                msg = all_cards['error']

            else:
                card_info = all_cards['data'][0]
                card_name = card_info['name']
                card_img = card_info['card_images'][0]['image_url']

                img_uhtml = gen_uhtml_img_code(card_img, height_resize=200, alt=card_name)
                msg = f'/adduhtml hippoygo-{card}, {img_uhtml}'

    await putter(f'{const.TCG_ROOM}|{msg}')