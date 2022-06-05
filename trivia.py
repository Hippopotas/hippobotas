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

from common.anilist import anilist_num_entries
from common.qbowl_db import QuestionTable
from common.utils import find_true_name, gen_uhtml_img_code, trivia_leaderboard_msg

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


def anagram_scramble(answer):
    to_scramble = answer.split()
    for i, word in enumerate(to_scramble):
        sw = list(word.lower())
        while ''.join(sw) == word.lower():
            random.shuffle(sw)
            if len(set(sw)) <= 1:
                break
        to_scramble[i] = ''.join(sw)

    return ' '.join(to_scramble)


def check_answer(guess, answers, exact=False):
    '''
    Checks if a guess is correct for a trivia question.

    Args:
        guess (str): The raw guess
        answers (str list): Base list of acceptable answers 
    
    Returns:
        An empty string if the guess is incorrect, else the matching answer
        from answers.
    '''
    t_guess = find_true_name(guess)

    for answer in answers:
        t_answer = find_true_name(answer)
        if (t_guess == t_answer):
            return answer
        elif exact:
            continue
        elif t_answer in t_guess:
            return answer

        # The heuristic for generating aliases for the answers is as follows -
        # given an answer, valid prefixes consist of whole alphanumeric chunks
        # (separated by non-alphanumeric chars), starting from the beginning of
        # the answer. If the guess matches any of these prefixes, and is at least
        # 8 characters long, it is counted as correct.
        answer_parts = re.findall('([a-zA-Z0-9]+)', answer)
        acceptable = []
        total=''
        for part in answer_parts:
            total += part.lower()
            if len(total) >= 8:
                acceptable.append(total)
        
        if ":" in answer:
            prefix = answer.split(':')[0]
            acceptable.append(find_true_name(prefix))

        if t_guess in acceptable:
            return answer

    return ''


class TriviaGame:
    def __init__(self, room, bot):
        self.active = False
        self.q_active = asyncio.Event()
        self.correct = asyncio.Event()
        self.answers = []

        self.bot = bot
        self.room = room
        self.questions = QuestionList(self.room, self.bot)

        try:
            self.scoreboard = pd.read_csv('trivia/{}.txt'.format(self.room))
        except FileNotFoundError:
            self.scoreboard = pd.DataFrame(columns=['user', 'score'])
        self.reset_scoreboard()

    async def autoskip(self, skip_time):
        answer = self.answers[0]
        while self.active and self.answers[0] == answer:
            await self.q_active.wait()
            self.q_active.clear()

            await asyncio.sleep(skip_time)

            if len(self.answers) == 0:
                break

            curr_time = int(time.time())
            await self.bot.incoming.put(f'>{self.room}\n'
                                        f'|c:|{curr_time}|*hippobotas|{answer}')

    async def quizbowl_question(self, question, skip_time):
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
            await self.bot.outgoing.put(f'{self.room}|/adduhtml {UHTML_NAME}, {curr_str}')

            if done:
                asyncio.create_task(self.autoskip(skip_time))
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

    async def run(self, n=10, diff=BASE_DIFF, categories=['all'],
                  excludecats=None, by_rating=False, autoskip=20,
                  quizbowl=False, is_dex=False, anagrams=False):
        if self.active:
            await self.bot.outgoing.put(self.room + '|There is already a running trivia!')
            return

        self.active = True
        self.anagrams = anagrams
        self.quizbowl = quizbowl
        self.reset_scoreboard()

        if diff > 10:
            diff = 10
        if diff < 1:
            diff = 1
        self.questions.diff = diff
        self.questions.categories = categories
        self.questions.excludecats = excludecats
        self.questions.by_rating = by_rating

        asyncio.create_task(self.questions.gen_list(n, self.bot, quizbowl=quizbowl, is_dex=is_dex, anagrams=anagrams),
                            name='tquestions-{}'.format(self.room))

        for _ in range(n):
            await asyncio.sleep(5)

            curr_question = await self.questions.questions.get()
            self.answers = curr_question[1]

            if quizbowl:
                asyncio.create_task(self.quizbowl_question(curr_question[0], autoskip))
            else:
                if autoskip:
                    asyncio.create_task(self.autoskip(autoskip))

                await self.bot.outgoing.put(f'{self.room}|{curr_question[0]}')

            self.q_active.set()

            await self.correct.wait()
            self.correct.clear()

        await self.end()

    def update_scores(self, user):
        user_pts = self.scoreboard[self.scoreboard['user'] == user]

        if user_pts.empty:
            new_user = pd.DataFrame([[user, 1]], columns=['user', 'score'])
            self.scoreboard = self.scoreboard.append(new_user)
        else:
            self.scoreboard.loc[self.scoreboard['user'] == user, 'score'] += 1

    async def end(self):
        self.scoreboard = self.scoreboard.sort_values('score', ascending=False)
        self.scoreboard.to_csv('trivia/{}.txt'.format(self.room), index=False)

        self.questions.ended = True
        while not self.questions.ending_acknowledged:
            await asyncio.sleep(0.1)
        self.questions = QuestionList(self.room, self.bot)

        endtext = 'This trivia game has ended. See below for results.'
        await self.bot.outgoing.put(f'{self.room}|/adduhtml {UHTML_NAME}, {endtext}')
        await asyncio.sleep(1)
        t_title = 'Quizbowl Leaderboard' if self.quizbowl else 'Trivia Leaderboard'
        await self.bot.outgoing.put(f"{self.room}|{trivia_leaderboard_msg(self.leaderboard(), t_title)}")

        self.active = False

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

    def __init__(self, room, bot):
        self.diff = BASE_DIFF
        self.categories = ['all']
        self.excludecats = None
        self.by_rating = False
        self.room = room
        self.bot = bot
        self.q_bases = []
        self.num_qs = 0
        self.questions = asyncio.Queue()
        self.series_exist = True
        self.category_params = []
        self.max_rank = 0
        self.ended = False
        self.ending_acknowledged = True

    async def gen_list(self, n, bot, quizbowl=False, is_dex=False, anagrams=False):
        self.num_qs = n
        async with aiohttp.ClientSession() as session:
            if self.room == const.ANIME_ROOM:
                for _ in range(n):
                    if self.ended:
                        self.ending_acknowledged = True
                        break

                    if is_dex:
                        await self.gen_mangadex_question(session)
                    elif quizbowl:
                        await self.gen_am_qbowl_question(session, bot.anilist_man)
                    else:
                        await self.gen_am_question(session, bot.anilist_man, anagrams=anagrams)

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

            elif self.room == const.SPORTS_ROOM:
                await self.gen_sports_questions(session)

            elif self.room == const.VG_ROOM:
                vg_database = json.load(open('data/vg_trivia.json'))
                for _ in range(n):
                    if quizbowl:
                        await self.gen_vg_qbowl_question(vg_database)
                    else:
                        await self.gen_vg_question(vg_database, anagrams=anagrams)

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

    async def gen_am_base(self, session, anilist_man):
        query = '''
        query ($page: Int, $perpage: Int) {
            Page (page: $page, perPage: $perpage) {
                pageInfo {
                    total
                }
                media (CATEGORIES_PLACEHOLDER minimumTagRank: 50, isAdult: false, sort: SORT_PLACEHOLDER) {
                    id
                    idMal
                    type
                    description
                    title {
                        english
                        userPreferred
                        romaji
                    }
                    coverImage {
                        large
                    }
                    bannerImage
                }
            }
        }
        '''

        if not self.category_params:
            if 'all' not in self.categories:
                media = []
                genres = []
                tags = []
                for c in self.categories:
                    true_c = find_true_name(c)

                    for m in const.ANILIST_MEDIA:
                        if true_c == find_true_name(m):
                            media.append(m)
                            break

                    for g in const.ANILIST_GENRES:
                        if true_c == find_true_name(g):
                            genres.append(g)
                            break

                    for t in const.ANILIST_TAGS:
                        if true_c == find_true_name(t):
                            tags.append(t)
                            break

                if media:
                    self.category_params.append(f'format_in: {", ".join(media)}')
                if genres:
                    self.category_params.append(f'genre_in: {json.dumps(genres)}')
                if tags:
                    self.category_params.append(f'tag_in: {json.dumps(tags)}')

                if self.excludecats:
                    media = []
                    genres = []
                    tags = []
                    for c in self.excludecats:
                        true_c = find_true_name(c)

                        for m in const.ANILIST_MEDIA:
                            if true_c == find_true_name(m):
                                media.append(m)
                                break

                        for g in const.ANILIST_GENRES:
                            if true_c == find_true_name(g):
                                genres.append(g)
                                break

                        for t in const.ANILIST_TAGS:
                            if true_c == find_true_name(t):
                                tags.append(t)
                                break

                    if media:
                        self.category_params.append(f'format_not_in: {json.dumps(media)}')
                    if genres:
                        self.category_params.append(f'genre_not_in: {json.dumps(genres)}')
                    if tags:
                        self.category_params.append(f'tag_not_in: {json.dumps(tags)}')

        category_params_str = ','.join(self.category_params)
        if category_params_str:
            category_params_str += ','
        query = query.replace('CATEGORIES_PLACEHOLDER', category_params_str)

        sort = 'SCORE_DESC' if self.by_rating else 'POPULARITY_DESC'
        query = query.replace('SORT_PLACEHOLDER', sort)

        # Get max_rank
        if not self.max_rank:
            query_vars = {
                'page': 1,
                'perpage': 1
            }

            async with anilist_man.lock():
                self.max_rank = await anilist_num_entries(query, query_vars, session)

            if not self.max_rank:
                for task in asyncio.all_tasks():
                    if task.get_name() == 'trivia-{}'.format(self.room):
                        task.cancel()
                        return

        rank = 0
        if self.max_rank < self.num_qs:
            self.series_exist = False
            for task in asyncio.all_tasks():
                if task.get_name() == 'trivia-{}'.format(self.room):
                    task.cancel()
                    return

        diff_scale = max(1.1, math.log(self.max_rank, 10) / 1.5)
        std_dev_scale = max(10, diff_scale ** 2)

        while rank < 1 or rank > self.max_rank:
            rank = int(random.gauss(self.max_rank // ((diff_scale) ** (10 - self.diff)),
                                    (std_dev_scale * self.diff / 2)))

        all_series = []
        roll_query_vars = {
            'page': rank,
            'perpage': 1
        }
        # Anilist pageInfo is flaky, resulting in the possibility of overshooting the upper bound at higher diffs
        while not all_series:
            async with anilist_man.lock():
                async with session.post(const.ANILIST_API, json={'query': query, 'variables': roll_query_vars}) as r:
                    resp = await r.json()

                    if r.status != 200:
                        for task in asyncio.all_tasks():
                            if task.get_name() == 'trivia-{}'.format(self.room):
                                task.cancel()
                                return

                    all_series = resp['data']['Page']['media']

            roll_query_vars['page'] = math.floor(roll_query_vars['page'] * 0.8)

        series_data = all_series[0]

        aliases = []
        for title in series_data['title'].values():
            if title:
                aliases.append(title)

        slug = {'img_url': series_data['coverImage']['large'],
                'description': series_data['description'],
                'answers': aliases,
                'rank': rank,
                'id': series_data['id']}

        is_nsfw = await self.bot.mal_man.is_nsfw(series_data['type'].lower(), series_data['idMal'])
        if is_nsfw:
            slug = slug.fromkeys(slug, None)
        return slug

    async def gen_am_question(self, session, anilist_man, anagrams=False):
        base = await self.gen_am_base(session, anilist_man)

        while self.duplicate_check(base['id']) or not base['img_url']:
            base = await self.gen_am_base(session, anilist_man)

        self.q_bases.append(base['id'])

        if anagrams:
            answer = random.choice(base['answers'])
            scrambled = anagram_scramble(answer)

            await self.questions.put([f'/announce Unscramble this: **{scrambled}**', [answer]])
            return

        img_url = gen_uhtml_img_code(base['img_url'], dims=(140, 210))

        await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_url),
                                  base['answers']])

    async def gen_am_qbowl_question(self, session, anilist_man):
        base = await self.gen_am_base(session, anilist_man)
        while self.duplicate_check(base['id']) or not base['description']:
            base = await self.gen_am_base(session, anilist_man)

        self.q_bases.append(base['id'])

        question = base['description']
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
                for tag in series_info['attributes']['tags']:
                    if tag['attributes']['name']['en'] in ['Doujinshi', 'Oneshot']:
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

            cover_info = random.choice(covers['data'])
            cover_id = cover_info['attributes']['fileName']

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

    async def gen_sports_questions(self, session):
        payload = {'amount': min(self.num_qs, 50),
                   'category': 21,
                   'type': 'multiple'}

        questions = None
        async with session.get(const.OPENTDB_API, params=payload) as r:
            questions = await r.json()

        for q in questions['results']:
            formatted = f"""/announce {q['question']}"""
            await self.questions.put([formatted, [q['correct_answer']]])

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

    async def gen_vg_question(self, vg_database, anagrams=False):
        vidya = self.gen_vg_base(vg_database)

        if anagrams:
            answer = vidya['name']
            scrambled = anagram_scramble(answer)

            await self.questions.put([f'/announce Unscramble this: **{scrambled}**', [answer]])
            return

        screenshot_url = 'https:' + random.choice(vidya['screenshots'])['url']
        screenshot_url = screenshot_url.replace('t_thumb', 't_original')
        question = f'/adduhtml {UHTML_NAME}, <center><img src=\'{screenshot_url}\' width=266 height=150></center>'
        await self.questions.put([question, [vidya['name'], vidya['slug']]])