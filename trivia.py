import aiohttp
import asyncio
import json
import pandas as pd
import random
import requests
import time

from PIL import ImageFile
from urllib import request as ulreq

from constants import ANIME_ROOM, LEAGUE_ROOM, VG_ROOM
from constants import JIKAN_API, DDRAGON_API, DDRAGON_IMG, DDRAGON_SPL
from constants import VG_QUESTION_LEN, TIMER_USER

BASE_DIFF = 3
AN_DIFF_SCALE = 475
MA_DIFF_SCALE = 275
VG_DIFF_SCALE = 300
UHTML_NAME = 'trivia'
PIC_SIZE = 225


def img_dims_from_uri(uri):
    # Returns width, height
    dims = (0, 0)
    with ulreq.urlopen(uri) as f:
        p = ImageFile.Parser()
        data = f.read(1024)

        p.feed(data)
        if not p.image.size:
            print(uri)
        dims = p.image.size

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


class TriviaGame:
    def __init__(self, room):
        self.active = False
        self.q_active = asyncio.Event()
        self.correct = asyncio.Event()
        self.answers = []

        self.room = room
        self.questions = QuestionList(self.room)

        self.scoreboard = pd.read_csv('trivia/{}.txt'.format(self.room))
        if self.room == ANIME_ROOM or self.room == VG_ROOM:
            self.scoreboard = pd.DataFrame(columns=['user', 'score'])

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

    def reset_scoreboard(self, length=60*60*24*3):
        timer = self.scoreboard[self.scoreboard['user'] == TIMER_USER]
        # Room that does not support auto-reset
        if timer.empty:
            return
        
        if (time.time() - timer['score'][0]) > length:
            timer.loc[timer['user'] == TIMER_USER, 'score'] = time.time()
            self.scoreboard = timer

    async def start(self, n=10, diff=BASE_DIFF, categories=['all'],
                    by_rating=False):
        self.active = True

        if diff > 10:
            diff = 10
        if diff < 1:
            diff = 1
        self.questions.diff = diff
        self.questions.categories = categories
        self.questions.by_rating = by_rating

        asyncio.create_task(self.questions.gen_list(n=n),
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
        self.by_rating = False
        self.room = room
        self.q_bases = []
        self.questions = asyncio.Queue()

    async def gen_list(self, n):
        async with aiohttp.ClientSession() as session:
            if self.room == ANIME_ROOM:
                for _ in range(n):
                    print(self.q_bases)
                    await self.gen_am_question(session)

            elif self.room == LEAGUE_ROOM:
                for _ in range(n):
                    await self.gen_lol_question(session)
            
            elif self.room == VG_ROOM:
                vg_database = None
                with open('data/vg_trivia.json') as f:
                    vg_database = json.load(f)
                for _ in range(n):
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
        while True:
            media = ['anime', 'manga']
            if 'all' not in self.categories:
                media = [c for c in ('anime', 'manga') if c in self.categories]
            if len(media) == 0:
                media = ['anime', 'manga']
            medium = ''
            rank = 0

            medium = random.choice(media)

            diff_scale = 0
            if medium == 'anime':
                diff_scale = AN_DIFF_SCALE
            elif medium == 'manga':
                diff_scale = MA_DIFF_SCALE

            while rank < 1:
                rank = int(random.gauss(diff_scale * (self.diff - 2),
                                        (diff_scale * self.diff) // 2))

            all_series = {}
            page = (rank - 1) // 50 + 1
            sort_method = 'bypopularity'
            if self.by_rating:
                sort_method = ''

            async with session.get(JIKAN_API + '{}/{}/{}/{}'.format('top', medium, page, sort_method)) as r:
                resp = await r.text()

                if r.status == 403:
                    print('Got rate limited by Jikan on top {}.'.format(medium))
                    await asyncio.sleep(10)
                    continue

                all_series = json.loads(resp)['top']

            await asyncio.sleep(2)    # Jikan rate limits to 30 queries/min

            series_data = {}
            series = all_series[(rank%50)-1]
            async with session.get(JIKAN_API + '{}/{}'.format(medium, series['mal_id'])) as r:
                resp = await r.text()
                series_data = json.loads(resp)

                if r.status == 403:
                    print('Got rate limited by Jikan on {}.'.format())
                    await asyncio.sleep(10)
                    continue

            await asyncio.sleep(2)    # Jikan rate limits to 30 queries/min
            
            valid_series = True

            # Exclude non-manga manga for now.
            if medium == 'manga' and series_data['type'] != 'Manga':
                print(series_data['title'])
                print(series_data['type'])
                valid_series = False

            # No H.
            for genre in series_data['genres']:
                if genre['mal_id'] == 12:
                    valid_series = False

            if not valid_series:
                continue

            aliases = []
            if series_data['title']:
                aliases.append(series_data['title'])
            if series_data['title_english']:
                aliases.append(series_data['title_english'])
            aliases += series_data['title_synonyms']

            return {'img_url': series_data['image_url'],
                    'answers': aliases,
                    'medium': medium,
                    'rank': rank}

    async def gen_am_question(self, session):
        base = await self.gen_am_base(session)
        while self.duplicate_check({k:base[k] for k in ('medium', 'rank') if k in base}):
            base = await self.gen_am_base(session)
        
        self.q_bases.append({k:base[k] for k in ('medium', 'rank') if k in base})

        img_url = gen_uhtml_img_code(base['img_url'], height_resize=PIC_SIZE)
        
        await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_url),
                                  base['answers']])

    async def gen_lol_base(self, session, data):
        base = {}

        qtypes = ['skins', 'spells', 'items']
        if 'all' not in self.categories:
            qtypes = [c for c in ('skins', 'spells', 'items') if c in self.categories]
        if len(qtypes) == 0:
            qtypes = ['skins', 'spells', 'items']
        
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

    async def gen_vg_question(self, vg_database):
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

        question = vidya['summary'].replace('\\n', '<br>')

        to_replace = vidya['name'].lower().split()
        split_question = question.split()
        for i, word in enumerate(split_question):
            if len(word) > 3 and word.lower() in to_replace:
                split_question[i] = '[GAME]'
        question = ' '.join(split_question)

        if len(question) > VG_QUESTION_LEN:
            question = question[:VG_QUESTION_LEN]
            for i in range(1, VG_QUESTION_LEN+1):
                if question[-1] == ' ':
                    break
                else:
                    question = question[:-1]

            question += '...'

        await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, question),
                                  [vidya['name'], vidya['slug']]])
