import aiohttp
import asyncio
import json
import math
import pandas as pd
import random
import re
import requests
import time

from PIL import ImageFile
from urllib import request as ulreq

from constants import ANIME_ROOM, LEAGUE_ROOM, VG_ROOM
from constants import ANIME_GENRES, MANGA_GENRES, ANIME_TYPES, MANGA_TYPES, LEAGUE_CATS
from constants import JIKAN_API, DDRAGON_API, DDRAGON_IMG, DDRAGON_SPL
from constants import TIMER_USER

BASE_DIFF = 3
AN_DIFF_SCALE = 475
MA_DIFF_SCALE = 275
VG_DIFF_SCALE = 300
UHTML_NAME = 'trivia'
PIC_SIZE = 225


def img_dims_from_uri(uri):
    # Returns width, height
    dims = (0, 0)
    data = None
    retry = 0
    with ulreq.urlopen(uri) as f:
        while retry < 1000:
            p = ImageFile.Parser()

            if not data:
                data = f.read(1024)
            else:
                data += f.read(1024)

            p.feed(data)

            try:
                dims = p.image.size
            except AttributeError:
                retry += 1
                continue
            else:
                break

    return dims


def gen_uhtml_img_code(url, height_resize=300, width_resize=None):
    w, h = img_dims_from_uri(url)
    if h > height_resize:
        w = w * height_resize // h
        h = height_resize
    
    if width_resize:
        if w > width_resize:
            h = h * width_resize // w
            w = width_resize

    return '<center><img src=\'{}\' width={} height={}></center>'.format(url, w, h)


CENSOR_WHITELIST = ['the', 'and']
def censor_quizbowl(title, question):
    to_replace = list(map(lambda x: re.sub(r'[^a-zA-Z0-9]', '', x).lower(), title.split()))
    split_question = question.split()
    for i, word in enumerate(split_question):
        raw_word = re.sub(r'[^a-zA-Z0-9]', '', word).lower()
        if (len(word) > 2 and raw_word in to_replace
                          and raw_word not in CENSOR_WHITELIST):
            split_question[i] = '____'
    return ' '.join(split_question)


class TriviaGame:
    def __init__(self, room):
        self.active = False
        self.q_active = asyncio.Event()
        self.correct = asyncio.Event()
        self.answers = []

        self.room = room
        self.questions = QuestionList(self.room)

        try:
            self.scoreboard = pd.read_csv('trivia/{}.txt'.format(self.room))
        except FileNotFoundError:
            self.scoreboard = pd.DataFrame(columns=['user', 'score'])
        self.reset_scoreboard()

    async def autoskip(self, skip_time, putter):
        answer = self.answers[0]
        while self.active and self.answers[0] == answer:
            await self.q_active.wait()
            self.q_active.clear()

            await asyncio.sleep(skip_time)

            if len(self.answers) == 0:
                break

            curr_time = int(time.time())
            await putter(f'>{self.room}\n'
                         f'|c:|{curr_time}|*hippobotas|{answer}')

    async def quizbowl_question(self, question, skip_time, putter, i_putter):
        answer = self.answers[0]
        curr_output = []
        remaining = iter(question.split(' '))
        done = False
        while self.active and self.answers[0] == answer:
            for _ in range(1):
                try:
                    word = next(remaining)
                    curr_output.append(word)
                    if word.endswith('.') or word.endswith(',') or word.endswith(';'):
                        break
                except StopIteration:
                    done = True
                    break
            curr_str = ' '.join(curr_output)
            await putter(f'{self.room}|/adduhtml {UHTML_NAME}, {curr_str}')

            if done:
                asyncio.create_task(self.autoskip(skip_time, i_putter))
                return
            await asyncio.sleep(0.3)

    def reset_scoreboard(self, length=60*60*24*3):
        timer = self.scoreboard[self.scoreboard['user'] == TIMER_USER]
        # Room that does not support auto-reset
        if timer.empty:
            self.scoreboard = pd.DataFrame(columns=['user', 'score'])
            return
        
        if (time.time() - timer['score'].iloc[0]) > length:
            timer.loc[timer['user'] == TIMER_USER, 'score'] = time.time()
            self.scoreboard = timer

    async def start(self, n=10, diff=BASE_DIFF, categories=['all'],
                    excludecats=False, by_rating=False, quizbowl=False):
        self.active = True
        self.reset_scoreboard()

        if diff > 15:
            diff = 15
        if diff < 1:
            diff = 1
        self.questions.diff = diff
        self.questions.categories = categories
        self.questions.excludecats = excludecats
        self.questions.by_rating = by_rating

        asyncio.create_task(self.questions.gen_list(n=n, quizbowl=quizbowl),
                            name='tquestions-{}'.format(self.room))

    def update_scores(self, user):
        user_pts = self.scoreboard[self.scoreboard['user'] == user]

        if user_pts.empty:
            new_user = pd.DataFrame([[user, 1]], columns=['user', 'score'])
            self.scoreboard = self.scoreboard.append(new_user)
        else:
            self.scoreboard.loc[self.scoreboard['user'] == user, 'score'] += 1

    async def end(self, putter):
        self.scoreboard = self.scoreboard.sort_values('score', ascending=False)
        self.scoreboard.to_csv('trivia/{}.txt'.format(self.room), index=False)
        self.active = False
        self.questions = QuestionList(self.room)

        endtext = 'This trivia game has ended. See below for results.'
        await putter(self.room + '|' + '/adduhtml {}, {}'.format(UHTML_NAME, endtext))

    async def skip(self, putter):
        await putter(self.room + '|' + '/adduhtml {}, <center>Question skipped.</center>'.format(UHTML_NAME))

    def leaderboard(self, n=5):
        if n > 10:
            n = 10
        self.scoreboard = self.scoreboard.sort_values('score', ascending=False)
        no_timer = self.scoreboard[self.scoreboard['user'] != TIMER_USER]
        return no_timer.head(n=n).values.tolist()
    
    def userscore(self, user):
        user_pts = self.scoreboard[self.scoreboard['user'] == user]
        
        if user_pts.empty:
            return [None, None]
        else:
            return user_pts.values.tolist()[0]


class QuestionList:

    def __init__(self, room):
        self.diff = BASE_DIFF
        self.categories = ['all']
        self.excludecats = False
        self.by_rating = False
        self.room = room
        self.q_bases = []
        self.questions = asyncio.Queue()
        self.series_exist = True

    async def gen_list(self, n, quizbowl=False):
        async with aiohttp.ClientSession() as session:
            if self.room == ANIME_ROOM:
                for _ in range(n):
                    if quizbowl:
                        await self.gen_am_qbowl_question(session)
                    else:
                        await self.gen_am_question(session)

            elif self.room == LEAGUE_ROOM:
                for _ in range(n):
                    await self.gen_lol_question(session)
            
            elif self.room == VG_ROOM:
                vg_database = None
                with open('data/vg_trivia.json') as f:
                    vg_database = json.load(f)
                for _ in range(n):
                    if quizbowl:
                        await self.gen_vg_qbowl_question(vg_database)
                    else:
                        await self.gen_vg_question(vg_database)

    def duplicate_check(self, d):
        for base in self.q_bases:
            if d == base:
                return True
        return False

    def check_for_jpg(self, url):
        r = requests.get(url)
        if r.status_code != 200:
            return url[:-3] + 'jpg'
        return url

    async def gen_am_base(self, session):
        while self.series_exist:
            media = []
            anime_media = []
            manga_media = []
            genres = {'anime': [], 'manga': []}

            if 'all' not in self.categories:
                for c in self.categories:
                    if c in ANIME_TYPES:
                        anime_media.append(('anime', c))
                    if c in MANGA_TYPES:
                        manga_media.append(('manga', c))

                for c in self.categories:
                    if c in ANIME_GENRES:
                        genres['anime'].append(ANIME_GENRES[c])
                        if len(anime_media) == 0:
                            anime_media = [('anime', '')]
                    if c in MANGA_GENRES:
                        genres['manga'].append(MANGA_GENRES[c])
                        if len(manga_media) == 0:
                            manga_media = [('manga', '')]

            media = anime_media + manga_media
            if len(media) == 0:
                media = [('anime', ''), ('manga', '')]

            exclude_media = []
            if self.excludecats:
                exclude_media = [p[1] for p in media]
                media = [('anime', ''), ('manga', '')]

            medium, sub_medium = random.choice(media)
            # Handle 'anime'/'manga' exclusion here
            if medium in exclude_media:
                continue

            if len(genres[medium]) == 0:
                genres[medium] = ['']
            genre_code = random.choice(genres[medium])
            if self.excludecats:
                genre_code = ','.join(map(str, genres[medium]))

            # Yes, it's backwards on jikan, idk.
            g_exclude = 1
            if self.excludecats:
                g_exclude = 0

            rank = 0
            diff_scale = 0
            if medium == 'anime':
                diff_scale = AN_DIFF_SCALE
            elif medium == 'manga':
                diff_scale = MA_DIFF_SCALE

            while rank < 1:
                rank = int(random.gauss(diff_scale * (self.diff - 2),
                                        (diff_scale * self.diff) // 2))
            # Adjust rank for smaller categories
            if (sub_medium and sub_medium != 'anime' and sub_medium != 'manga') or genre_code:
                rank = math.ceil(rank / 8)

            all_series = {}
            page = (rank - 1) // 50 + 1
            sort_method = 'members'
            if self.by_rating:
                sort_method = 'score'

            url = (f'{JIKAN_API}search/{medium}?q=&type={sub_medium}&genre={genre_code}&'
                   f'genre_exclude={g_exclude}&page=1&order_by={sort_method}&sort=desc')

            async with session.get(url) as r:
                resp = await r.text()

                if r.status == 404:
                    self.series_exist = False
                    for task in asyncio.all_tasks():
                        if task.get_name() == 'trivia-{}'.format(self.room):
                            task.cancel()
                            break
                elif resp:
                    if len(json.loads(resp)['results']) == 0:
                        self.series_exist = False
                        for task in asyncio.all_tasks():
                            if task.get_name() == 'trivia-{}'.format(self.room):
                                task.cancel()
                                break

                await asyncio.sleep(2)

            async with session.get(url.replace('page=1', f'page={page}')) as r:
                resp = await r.text()

                if r.status == 403:
                    print('Got rate limited by Jikan on top {}.'.format(medium))
                    await asyncio.sleep(10)
                    continue
                # Page number/rank is too large, reroll
                elif r.status == 404:
                    await asyncio.sleep(2)
                    continue

                all_series = json.loads(resp)['results']

            await asyncio.sleep(2)    # Jikan rate limits to 30 queries/min

            series_data = {}

            try:
                series = all_series[(rank%50)-1]
            except IndexError:
                series = random.choice(all_series)

            # Reroll on hitting excluded medium
            if self.excludecats and re.sub(r'[^a-zA-Z0-9]', '', series['type']).lower() in exclude_media:
                continue

            async with session.get(JIKAN_API + '{}/{}'.format(medium, series['mal_id'])) as r:
                resp = await r.text()
                series_data = json.loads(resp)

                if r.status == 403:
                    print('Got rate limited by Jikan on {}.'.format())
                    await asyncio.sleep(10)
                    continue

            await asyncio.sleep(2)    # Jikan rate limits to 30 queries/min
            
            valid_series = True

            # No H/NSFW.
            for genre in series_data['genres']:
                if genre['mal_id'] == 12:
                    valid_series = False

            aliases = []
            if series_data['title']:
                aliases.append(series_data['title'])
            if series_data['title_english']:
                aliases.append(series_data['title_english'])
            aliases += series_data['title_synonyms']

            for alias in aliases:
                if 'hentai' in alias.lower():
                    valid_series = False
                    break

            if not valid_series:
                continue

            return {'img_url': series_data['image_url'],
                    'synopsis': series_data['synopsis'],
                    'answers': aliases,
                    'medium': medium,
                    'sub_medium': sub_medium,
                    'genre': genre_code,
                    'rank': rank}

    async def gen_am_question(self, session):
        base = await self.gen_am_base(session)
        while self.duplicate_check({k:base[k] for k in ('medium', 'sub_medium', 'genre', 'rank') if k in base}):
            base = await self.gen_am_base(session)
        
        self.q_bases.append({k:base[k] for k in ('medium', 'sub_medium', 'genre', 'rank') if k in base})

        img_url = gen_uhtml_img_code(base['img_url'], height_resize=PIC_SIZE)
        
        await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_url),
                                  base['answers']])

    async def gen_am_qbowl_question(self, session):
        base = await self.gen_am_base(session)
        while self.duplicate_check({k:base[k] for k in ('medium', 'sub_medium', 'genre', 'rank') if k in base}) or not base['synopsis']:
            base = await self.gen_am_base(session)

        self.q_bases.append({k:base[k] for k in ('medium', 'sub_medium', 'genre', 'rank') if k in base})

        question = base['synopsis']
        for title in base['answers']:
            question = censor_quizbowl(title, question)

        await self.questions.put([question, base['answers']])

    async def gen_lol_base(self, session, data):
        base = {}

        qtypes = []
        if 'all' not in self.categories:
            qtypes = [c for c in LEAGUE_CATS if c in self.categories]

        if self.excludecats:
            qtypes = LEAGUE_CATS - qtypes

        if len(qtypes) == 0:
            qtypes = LEAGUE_CATS
        
        if len(qtypes) == 3:
            data['qtype'] = random.choices(qtypes, weights=[4, 2, 4])[0]
        else:
            data['qtype'] = random.choice(qtypes)

        data['champ'] = random.choice(list(data['all_champs'].keys()))
        data['item'] = random.choice(list(data['all_items'].keys()))

        if data['qtype'] == 'items':
            base = {k:data[k] for k in ('qtype', 'item')}
        else:
            async with session.get(DDRAGON_API + 'champion/{}.json'.format(data['champ'])) as r:
                resp = await r.text()
                data['champ_data'] = json.loads(resp)['data'][data['champ']]

                if data['qtype'] == 'skins':
                    skin = random.choice(data['champ_data']['skins'])
                    data['cval'] = skin['num']
                elif data['qtype'] == 'spells':
                    data['cval'] = random.randint(0, 4)

                base = {k:data[k] for k in ('qtype', 'champ', 'cval')}

        return data, base
        
    async def gen_lol_question(self, session):
        data = {'all_champs': {}, 'champ': '', 'champ_data': {}, 'all_items': {}, 'item': {}}

        async with session.get(DDRAGON_API + 'champion.json') as r:
            resp = await r.text()
            data['all_champs'] = json.loads(resp)['data']
        
        async with session.get(DDRAGON_API + 'item.json') as r:
            resp = await r.text()
            data['all_items'] = json.loads(resp)['data']
        data, base = await self.gen_lol_base(session, data)
        while self.duplicate_check(base):
            data, base = await self.gen_lol_base(session, data)
        
        self.q_bases.append(base)

        if data['qtype'] == 'items':
            img_url = DDRAGON_IMG + 'item/{}.png'.format(data['item'])
            img_url = gen_uhtml_img_code(self.check_for_jpg(img_url))
            await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_url),
                                      [data['all_items'][data['item']]['name']]])
        elif data['qtype'] == 'skins':
            skin_name = ''
            for skin in data['champ_data']['skins']:
                if skin['num'] == data['cval']:
                    skin_name = skin['name'] if skin['name'] != 'default' else data['champ_data']['name']
                    break

            img_url = DDRAGON_SPL + '{}_{}.png'.format(data['champ'], data['cval'])
            img_url = gen_uhtml_img_code(self.check_for_jpg(img_url))
            await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_url),
                                      [skin_name]])
        elif data['qtype'] == 'spells':
            ability = {}
            if data['cval'] == 0:
                ability = data['champ_data']['passive']
                img_url = DDRAGON_IMG + 'passive/{}'.format(ability['image']['full'])
                img_url = gen_uhtml_img_code(self.check_for_jpg(img_url))
                await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_url),
                                          [ability['name']]])
            else:
                ability = data['champ_data']['spells'][data['cval']-1]
                img_url = DDRAGON_IMG + 'spell/{}'.format(ability['image']['full'])
                img_url = gen_uhtml_img_code(self.check_for_jpg(img_url))
                await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_url),
                                          [ability['name']]])

    def gen_vg_base(self, vg_database):
        rank = -1
        while rank < 0 or rank >= len(vg_database):
            rank = int(random.gauss(VG_DIFF_SCALE * (self.diff - 2),
                                    (VG_DIFF_SCALE * self.diff) // 2))
        vidya = vg_database[rank]

        while vidya['id'] in self.q_bases:
            while rank < 0 or rank >= len(vg_database):
                rank = int(random.gauss(VG_DIFF_SCALE * (self.diff - 2),
                                        (VG_DIFF_SCALE * self.diff) // 2))
            vidya = vg_database[rank]

        self.q_bases.append(vidya['id'])
        return vidya

    async def gen_vg_qbowl_question(self, vg_database):
        vidya = self.gen_vg_base(vg_database)

        question = vidya['summary']
        question = censor_quizbowl(vidya['name'], question)

        await self.questions.put([question, [vidya['name'], vidya['slug']]])

    async def gen_vg_question(self, vg_database):
        vidya = self.gen_vg_base(vg_database)

        cover_url = 'https:' + vidya['cover']['url']
        question = f'/adduhtml {UHTML_NAME}, <center><img src=\'{cover_url}\' width=90 height=90></center>'
        await self.questions.put([question, [vidya['name'], vidya['slug']]])