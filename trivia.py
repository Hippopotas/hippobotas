import aiohttp
import asyncio
import json
import math
import pandas as pd
import random
import re
import requests
import time

from peewee import fn

import common.constants as const

from common.qbowl_db import QuestionTable
from common.utils import find_true_name, gen_uhtml_img_code

BASE_DIFF = 3
VG_DIFF_SCALE = 300
UHTML_NAME = 'trivia'
PIC_SIZE = 225


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
        timer = self.scoreboard[self.scoreboard['user'] == const.TIMER_USER]
        # Room that does not support auto-reset
        if timer.empty:
            self.scoreboard = pd.DataFrame(columns=['user', 'score'])
            return
        
        if (time.time() - timer['score'].iloc[0]) > length:
            timer.loc[timer['user'] == const.TIMER_USER, 'score'] = time.time()
            self.scoreboard = timer

    async def start(self, n=10, diff=BASE_DIFF, categories=['all'],
                    excludecats=False, by_rating=False, quizbowl=False, is_dex=False):
        self.active = True
        self.reset_scoreboard()

        if diff > 10:
            diff = 10
        if diff < 1:
            diff = 1
        self.questions.diff = diff
        self.questions.categories = categories
        self.questions.excludecats = excludecats
        self.questions.by_rating = by_rating

        asyncio.create_task(self.questions.gen_list(n=n, quizbowl=quizbowl, is_dex=is_dex),
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
        no_timer = self.scoreboard[self.scoreboard['user'] != const.TIMER_USER]
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
        self.num_qs = 0
        self.questions = asyncio.Queue()
        self.series_exist = True

    async def gen_list(self, n, quizbowl=False, is_dex=False):
        self.num_qs = n
        async with aiohttp.ClientSession() as session:
            if self.room == const.ANIME_ROOM:
                for _ in range(n):
                    if is_dex:
                        await self.gen_mangadex_question(session)
                    elif quizbowl:
                        await self.gen_am_qbowl_question(session)
                    else:
                        await self.gen_am_question(session)

            elif self.room == const.LEAGUE_ROOM:
                for _ in range(n):
                    await self.gen_lol_question(session)

            elif self.room == const.SCHOL_ROOM:
                num_tossups = (QuestionTable.select()
                                            .where(QuestionTable.question_type == 't')
                                            .count())
                num_bonuses = (QuestionTable.select()
                                            .where(QuestionTable.question_type == 'b')
                                            .count()) / 3

                q_types = random.choices(['t', 'b'], weights=[num_tossups, num_bonuses], k=n)
                for qt in q_types:
                    await self.gen_schol_qbowl_question(qt)

            elif self.room == const.VG_ROOM:
                vg_database = json.load(open('data/vg_trivia.json'))
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
                    if c in const.ANIME_TYPES:
                        anime_media.append(('anime', c))
                    if c in const.MANGA_TYPES:
                        manga_media.append(('manga', c))

                for c in self.categories:
                    if c in const.ANIME_GENRES:
                        genres['anime'].append(const.ANIME_GENRES[c])
                    if c in const.MANGA_GENRES:
                        genres['manga'].append(const.MANGA_GENRES[c])

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

            genre = ''
            if genre_code != '':
                if medium == 'anime':
                    for g in const.ANIME_GENRES:
                        if const.ANIME_GENRES[g] == genre_code:
                            genre = g
                            break
                elif medium == 'manga':
                    for g in const.MANGA_GENRES:
                        if const.MANGA_GENRES[g] == genre_code:
                            genre = g
                            break

            # Yes, it's backwards on jikan, idk.
            g_exclude = 1
            if self.excludecats:
                g_exclude = 0

            rank = 0
            max_rank = const.MAL_LAST_PAGES[medium][sub_medium][genre] * 50
            if max_rank == 0:
                self.series_exist = False
                for task in asyncio.all_tasks():
                    if task.get_name() == 'trivia-{}'.format(self.room):
                        task.cancel()
                        break

            diff_scale = max(1.1, math.log(max_rank, 10) / 1.5)
            std_dev_scale = max(10, diff_scale ** 2)

            while rank < 1 or rank > max_rank:
                rank = int(random.gauss(max_rank // ((diff_scale) ** (10 - self.diff)),
                                        (std_dev_scale * self.diff)))

            all_series = {}
            page = (rank - 1) // 50 + 1
            sort_method = 'members'
            if self.by_rating:
                sort_method = 'score'

            url = (f'{const.JIKAN_API}search/{medium}?q=&type={sub_medium}&genre={genre_code}&'
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

            async with session.get(const.JIKAN_API + '{}/{}'.format(medium, series['mal_id'])) as r:
                resp = await r.text()
                series_data = json.loads(resp)

                if r.status == 403:
                    print('Got rate limited by Jikan on {}.'.format())
                    await asyncio.sleep(10)
                    continue

            await asyncio.sleep(2)    # Jikan rate limits to 30 queries/min
            
            valid_series = True

            # Cannot be on banlist.
            bl = json.load(open(const.BANLISTFILE))
            if series['mal_id'] in bl[medium]:
                valid_series = False

            # No H/NSFW.
            for genre in series_data['genres']:
                if genre['mal_id'] == 12:
                    valid_series = False

            # Needs at least 1 picture.
            pics = []
            async with session.get(const.JIKAN_API + '{}/{}/pictures'.format(medium, series['mal_id'])) as r:
                resp = await r.text()
                pics_data = json.loads(resp)

                if r.status == 403:
                    print('Got rate limited by Jikan on {}.'.format())
                    await asyncio.sleep(10)
                    continue
                    
                for p in pics_data['pictures']:
                    pics.append(p['small'])
                if not pics:
                    valid_series = False

            await asyncio.sleep(2)    # Jikan rate limits to 30 queries/min

            # Cannot have banwords in the name.
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

            img_url = random.choice(pics)
            return {'img_url': img_url,
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

    async def gen_mangadex_question(self, session):
        series_id = ''
        cover_id = ''
        answers = []
        while not series_id:
            await asyncio.sleep(0.2)
            async with session.get(f'{const.DEX_API}manga/random') as r:
                rand_series = await r.json()

                if r.status != 200:
                    await asyncio.sleep(3)
                    continue
            
                series_info = rand_series['data']
                if series_info['attributes']['contentRating'] != 'safe':
                    continue

                skip = False
                for tag in series_info['tags']:
                    if tag['attributes']['name'] == 'Doujinshi':
                        skip = True
                        break
                if skip:
                    continue

                if not self.duplicate_check(series_info['id']):
                    series_id = series_info['id']

                    answers = [series_info['attributes']['title']['en']]
                    for title in series_info['attributes']['altTitles']:
                        if len(find_true_name(title['en'])) > 0:
                            answers.append(title['en'])

        async with session.get(f'{const.DEX_API}cover', params={'manga[]': [series_id]}) as r:
            covers = await r.json()

            cover_info = random.choice(covers['results'])
            cover_id = cover_info['data']['attributes']['fileName']

        img_url = f'https://uploads.mangadex.org/covers/{series_id}/{cover_id}.256.jpg'
        img_uhtml = gen_uhtml_img_code(img_url, height_resize=PIC_SIZE)
        await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_uhtml), answers])

    async def gen_lol_base(self, session, data):
        base = {}

        qtypes = []
        if 'all' not in self.categories:
            qtypes = [c for c in const.LEAGUE_CATS if c in self.categories]

        if self.excludecats:
            qtypes = const.LEAGUE_CATS - qtypes

        if len(qtypes) == 0:
            qtypes = const.LEAGUE_CATS
        
        if len(qtypes) == 3:
            data['qtype'] = random.choices(qtypes, weights=[4, 2, 4])[0]
        else:
            data['qtype'] = random.choice(qtypes)

        data['champ'] = random.choice(list(data['all_champs'].keys()))
        data['item'] = random.choice(list(data['all_items'].keys()))

        if data['qtype'] == 'items':
            base = {k:data[k] for k in ('qtype', 'item')}
        else:
            async with session.get(const.DDRAGON_API + 'champion/{}.json'.format(data['champ'])) as r:
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

        async with session.get(const.DDRAGON_API + 'champion.json') as r:
            resp = await r.text()
            data['all_champs'] = json.loads(resp)['data']
        
        async with session.get(const.DDRAGON_API + 'item.json') as r:
            resp = await r.text()
            data['all_items'] = json.loads(resp)['data']
        data, base = await self.gen_lol_base(session, data)
        while self.duplicate_check(base):
            data, base = await self.gen_lol_base(session, data)
        
        self.q_bases.append(base)

        if data['qtype'] == 'items':
            img_url = const.DDRAGON_IMG + 'item/{}.png'.format(data['item'])
            img_url = gen_uhtml_img_code(self.check_for_jpg(img_url))
            await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_url),
                                      [data['all_items'][data['item']]['name']]])
        elif data['qtype'] == 'skins':
            skin_name = ''
            for skin in data['champ_data']['skins']:
                if skin['num'] == data['cval']:
                    skin_name = skin['name'] if skin['name'] != 'default' else data['champ_data']['name']
                    break

            img_url = const.DDRAGON_SPL + '{}_{}.png'.format(data['champ'], data['cval'])
            img_url = gen_uhtml_img_code(self.check_for_jpg(img_url))
            await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_url),
                                      [skin_name]])
        elif data['qtype'] == 'spells':
            ability = {}
            if data['cval'] == 0:
                ability = data['champ_data']['passive']
                img_url = const.DDRAGON_IMG + 'passive/{}'.format(ability['image']['full'])
                img_url = gen_uhtml_img_code(self.check_for_jpg(img_url))
                await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_url),
                                          [ability['name']]])
            else:
                ability = data['champ_data']['spells'][data['cval']-1]
                img_url = const.DDRAGON_IMG + 'spell/{}'.format(ability['image']['full'])
                img_url = gen_uhtml_img_code(self.check_for_jpg(img_url))
                await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_url),
                                          [ability['name']]])

    def gen_schol_base(self, q_type):
        q_row = (QuestionTable.select()
                              .where(QuestionTable.question_type == q_type)
                              .order_by(fn.Random())
                              .limit(1))[0]

        while q_row.prev_b:
            q_row = (QuestionTable.select()
                                  .where(QuestionTable.qid == q_row.prev_b))[0]

        return q_row

    async def gen_schol_qbowl_question(self, q_type):
        question = self.gen_schol_base(q_type)

        while self.duplicate_check(question.qid):
            question = self.gen_schol_base(q_type)

        self.q_bases.append(question.qid)

        await self.questions.put([question.question, json.loads(question.answer)])
        while question.next_b:
            question = (QuestionTable.select()
                                     .where(QuestionTable.qid == question.next_b))[0]
            await self.questions.put([question.question, json.loads(question.answer)])

    def gen_vg_base(self, vg_database):
        rank = -1
        while rank < 0 or rank >= len(vg_database):
            rank = int(random.gauss(VG_DIFF_SCALE * (self.diff - 2),
                                    (VG_DIFF_SCALE * self.diff) // 2))
        vidya = vg_database[rank]

        while vidya['id'] in self.q_bases:
            rank = -1
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

        screenshot_url = 'https:' + random.choice(vidya['screenshots'])['url']
        screenshot_url = screenshot_url.replace('t_thumb', 't_original')
        question = f'/adduhtml {UHTML_NAME}, <center><img src=\'{screenshot_url}\' width=266 height=150></center>'
        await self.questions.put([question, [vidya['name'], vidya['slug']]])