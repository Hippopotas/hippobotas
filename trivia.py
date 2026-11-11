import logging
import aiohttp
import asyncio
import discord
import html
import io
import json
import math
import os
import pandas as pd
import random
import re
import time

from peewee import fn

import common.constants as const

from common.anilist import anilist_num_entries, anilist_post
from common.qbowl_db import QuestionTable
from common.utils import find_true_name, gen_uhtml_img, img_tag, leaderboard_uhtml

logger = logging.getLogger(__name__)

BASE_DIFF = 3
# Anime/manga questions are picked from pages of this many series, fetched
# once per game and reused, so skipping duplicates, NSFW series or ones
# without a cover doesn't cost another AniList request.
AM_PAGE_SIZE = 50
# Rolls to try before giving up on a question (e.g. a small category that
# has run out of usable series).
AM_MAX_ROLLS = 10
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
        elif exact == "league":
            if t_guess == re.sub(r"prestige|\d{4}", "", t_answer):
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
        self.stopping = False
        self.run_task = None
        self.ending = False
        self.q_active = asyncio.Event()
        self.correct = asyncio.Event()
        self.answers = []
        # Increases with every question (and when a game ends), so timers
        # and reveals left over from an earlier question know to stop.
        self.q_id = 0
        self.tasks = set()

        self.bot = bot
        self.room = room
        self.questions = QuestionList(self.room, self.bot)

        self.score_file = 'trivia/{}.txt'.format(self.room)
        self.scoreboard = self.load_scores()
        self.reset_scoreboard()

    def load_scores(self):
        '''
        Reads the saved scores. A damaged file is set aside (as .corrupt)
        rather than stopping the room from loading.
        '''
        try:
            scoreboard = pd.read_csv(self.score_file)
            if list(scoreboard.columns[:2]) != ['user', 'score']:
                raise ValueError(f'unexpected columns {list(scoreboard.columns)}')
            scoreboard = scoreboard[['user', 'score']].copy()
            scoreboard['score'] = pd.to_numeric(scoreboard['score'], errors='coerce').fillna(0)
            return scoreboard
        except FileNotFoundError:
            pass
        except (pd.errors.EmptyDataError, pd.errors.ParserError, ValueError, UnicodeDecodeError) as e:
            logger.warning(f'Trivia scores in {self.score_file} are unreadable ({e!r}); starting fresh.')
            try:
                os.replace(self.score_file, self.score_file + '.corrupt')
            except OSError:
                pass
        return pd.DataFrame(columns=['user', 'score'])

    def spawn(self, coro):
        ''' Starts a background task, keeping a reference so it isn't lost. '''
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    def question_live(self, q_id):
        return self.active and self.q_id == q_id and bool(self.answers)

    async def autoskip(self, skip_time, q_id):
        # Wait until the question is actually shown, then start the clock.
        await self.q_active.wait()
        await asyncio.sleep(skip_time)
        if self.question_live(q_id):
            await self.time_up(self.answers[0])

    async def time_up(self, answer):
        '''
        Ends the current question unanswered. On Showdown this is done by
        having the bot "answer" it, which the guess handler treats as a skip.
        '''
        curr_time = int(time.time())
        await self.bot.incoming.put(f'>{self.room}\n'
                                    f'|c:|{curr_time}|*hippobotas|{answer}')

    async def say(self, text):
        await self.bot.outgoing.put(f'{self.room}|{text}')

    async def show_question(self, question):
        await self.bot.outgoing.put(f'{self.room}|{question[0]}')

    async def show_results(self):
        endtext = 'This trivia game has ended. See below for results.'
        await self.bot.outgoing.put(f'{self.room}|/adduhtml {UHTML_NAME}, {endtext}')
        await asyncio.sleep(1)
        t_title = 'Quizbowl Leaderboard' if self.quizbowl else 'Trivia Leaderboard'
        await self.bot.outgoing.put(f"{self.room}|/adduhtml {leaderboard_uhtml(self.leaderboard(), t_title)}")

    async def quizbowl_question(self, question, skip_time, q_id):
        curr_output = []
        remaining = iter(question.split(' '))
        done = False
        while self.question_live(q_id):
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
                if skip_time:
                    self.spawn(self.autoskip(skip_time, q_id))
                return
            await asyncio.sleep(0.3)

    def reset_scoreboard(self, length=60*60*24*3):
        timer = self.scoreboard[self.scoreboard['user'] == const.TIMER_USER]
        # Room that does not support auto-reset
        if timer.empty:
            self.scoreboard = pd.DataFrame(columns=['user', 'score'])
            return
        
        if (time.time() - timer['score'].iloc[0]) > length:
            timer = timer.copy()
            timer['score'] = time.time()
            self.scoreboard = timer

    async def run(self, n=10, diff=BASE_DIFF, categories=['all'],
                  excludecats=None, by_rating=False, autoskip=20,
                  quizbowl=False, is_dex=False, anagrams=False):
        if self.active:
            await self.say('There is already a running trivia!')
            return

        self.active = True
        self.run_task = asyncio.current_task()
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

        gen_task = asyncio.create_task(self.questions.gen_list(n, self.bot, quizbowl=quizbowl,
                                                               is_dex=is_dex, anagrams=anagrams),
                                       name='tquestions-{}'.format(self.room))

        try:
            for _ in range(n):
                await asyncio.sleep(5)

                # Waits here, without starting any timer, while questions are
                # still being fetched (e.g. when AniList asks us to slow down).
                curr_question = await self.next_question(gen_task)
                if curr_question is None:
                    await self.say('Could not generate any more questions.')
                    break
                self.q_id += 1
                q_id = self.q_id
                self.answers = curr_question[1]
                self.correct.clear()
                self.q_active.clear()

                if quizbowl:
                    self.spawn(self.quizbowl_question(curr_question[0], autoskip, q_id))
                else:
                    if autoskip:
                        self.spawn(self.autoskip(autoskip, q_id))

                    await self.show_question(curr_question)

                self.q_active.set()

                await self.correct.wait()
                self.correct.clear()
        except asyncio.CancelledError:
            gen_task.cancel()
            if not self.stopping:
                reason = self.questions.error or 'Trivia could not be run with those settings.'
                self.reset_game()
                await self.say(reason)
            raise
        except Exception:
            # Without this, an unexpected error would leave the game marked as
            # running, blocking new games until a restart.
            logger.exception(f'Trivia game in {self.room} failed')
            gen_task.cancel()
            self.reset_game()
            try:
                await self.say('Trivia stopped because of an error.')
            except Exception:
                pass
            return

        gen_task.cancel()
        await self.end()

    def reset_game(self):
        self.questions = QuestionList(self.room, self.bot)
        self.answers = []
        self.q_id += 1
        self.active = False

    async def next_question(self, gen_task):
        '''
        Waits for the next question, or returns None if the generator
        finished (or crashed) without producing one.
        '''
        get_task = asyncio.ensure_future(self.questions.questions.get())
        done, _ = await asyncio.wait([get_task, gen_task], return_when=asyncio.FIRST_COMPLETED)
        if get_task in done:
            return get_task.result()

        if not gen_task.cancelled() and gen_task.exception():
            logger.warning(f'Trivia question generation failed in {self.room}: {gen_task.exception()!r}')

        # The generator may have queued a final question as it finished.
        if not self.questions.questions.empty():
            get_task.cancel()
            return self.questions.questions.get_nowait()

        get_task.cancel()
        return None

    def update_scores(self, user):
        user_pts = self.scoreboard[self.scoreboard['user'] == user]

        if user_pts.empty:
            new_user = pd.DataFrame([[user, 1]], columns=['user', 'score'])
            self.scoreboard = pd.concat([self.scoreboard, new_user], ignore_index=True)
        else:
            self.scoreboard.loc[self.scoreboard['user'] == user, 'score'] += 1

    def save_scores(self):
        self.scoreboard = self.scoreboard.sort_values('score', ascending=False)
        # Write to a temporary file and swap it in, so a crash mid-save
        # can't leave a half-written score file.
        tmp = self.score_file + '.tmp'
        try:
            self.scoreboard.to_csv(tmp, index=False)
            os.replace(tmp, self.score_file)
        except OSError as e:
            logger.warning(f'Could not save trivia scores to {self.score_file}: {e!r}')

    async def end(self):
        if self.ending:
            return
        self.ending = True
        try:
            self.save_scores()

            self.questions.ended = True
            while not self.questions.ending_acknowledged:
                await asyncio.sleep(0.1)
            self.questions = QuestionList(self.room, self.bot)

            await self.show_results()
        except Exception:
            logger.exception(f'Could not finish the trivia game in {self.room}')
        finally:
            # However the ending went, the game is over.
            self.answers = []
            self.q_id += 1
            self.active = False
            self.ending = False

    async def stop(self):
        '''
        Ends a running game early. The run loop is cancelled so that it
        doesn't keep consuming questions meant for the next game.
        '''
        if self.ending:
            return
        self.stopping = True
        try:
            if (self.run_task and not self.run_task.done()
                    and self.run_task is not asyncio.current_task()):
                self.run_task.cancel()
                # Let it finish unwinding while stopping is still set.
                await asyncio.wait([self.run_task], timeout=5)
            self.answers = []
            await self.end()
        finally:
            self.stopping = False

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
        self.am_pages = {}
        self.ended = False
        self.ending_acknowledged = True
        # Why generation gave up, shown to the room instead of the default.
        self.error = None

    def abort(self, reason=None):
        ''' Gives up on the game, cancelling its run task with a reason. '''
        self.error = reason
        for task in asyncio.all_tasks():
            if task.get_name() == 'trivia-{}'.format(self.room):
                task.cancel()

    async def gen_list(self, n, bot, quizbowl=False, is_dex=False, anagrams=False):
        self.num_qs = n
        async with aiohttp.ClientSession() as session:
            if (self.room in [const.ANIME_ROOM, const.HINDISUB_ROOM] or
                self.room.startswith(const.DISCORD_TRIVIA_PREFIX)):
                for _ in range(n):
                    if self.ended:
                        self.ending_acknowledged = True
                        break

                    made = None
                    if is_dex:
                        await self.gen_mangadex_question(session)
                    elif quizbowl:
                        made = await self.gen_am_qbowl_question(session, bot.anilist_man)
                    else:
                        made = await self.gen_am_question(session, bot.anilist_man, anagrams=anagrams)

                    # Out of usable series: later questions would fail the
                    # same way, so finish with the questions already made.
                    if made is False:
                        break

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

    async def check_for_jpg(self, session, url):
        async with session.head(url) as r:
            if r.status != 200:
                return url[:-3] + 'jpg'
        return url

    async def gen_am_base(self, session, anilist_man, need):
        '''
        Picks an unused, SFW series with the field `need` (img_url or
        description) at around the game's difficulty.

        Returns None if no such series turned up within AM_MAX_ROLLS rolls,
        or if the game had to be aborted.
        '''
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
                    self.category_params.append(f'format_in: [{", ".join(media)}]')
                if genres:
                    self.category_params.append(f'genre_in: {json.dumps(genres)}')
                if tags:
                    self.category_params.append(f'tag_in: {json.dumps(tags)}')

            # Exclusions apply whether or not categories were chosen.
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
                    self.category_params.append(f'format_not_in: [{", ".join(media)}]')
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

            max_rank = await anilist_num_entries(query, query_vars, session, anilist_man)

            if max_rank is None:
                self.abort('AniList is not responding right now, so trivia could not start.')
                return
            if not max_rank:
                self.abort('No series match those settings.')
                return
            self.max_rank = max_rank

        if self.max_rank < self.num_qs:
            self.series_exist = False
            self.abort(f'Only {self.max_rank} series match those settings, '
                       f'not enough for {self.num_qs} questions.')
            return

        for _ in range(AM_MAX_ROLLS):
            rank = self.roll_rank()
            media = await self.am_page(session, anilist_man, query, (rank - 1) // AM_PAGE_SIZE + 1)
            if media is None:
                return None

            # Prefer the rolled series; otherwise others on the same page,
            # which are about as popular.
            idx = (rank - 1) % AM_PAGE_SIZE
            preferred = [media[idx]] if idx < len(media) else []
            others = [s for s in media if not preferred or s is not preferred[0]]
            random.shuffle(others)

            for series_data in preferred + others:
                slug = self.am_slug(series_data, rank)
                if not slug['id'] or self.duplicate_check(slug['id']) or not slug[need]:
                    continue
                if await self.bot.mal_man.is_nsfw(series_data['type'].lower(), series_data['idMal']):
                    continue
                return slug

        logger.warning(f'No usable series for a trivia question in {self.room} '
                       f'after {AM_MAX_ROLLS} rolls.')
        return None

    def roll_rank(self):
        ''' A popularity (or score) rank, more obscure at higher difficulty. '''
        diff_scale = max(1.1, math.log(self.max_rank, 10) / 1.5)
        std_dev_scale = max(10, diff_scale ** 2)

        rank = 0
        while rank < 1 or rank > self.max_rank:
            rank = int(random.gauss(self.max_rank // ((diff_scale) ** (10 - self.diff)),
                                    (std_dev_scale * self.diff / 2)))
        return rank

    async def am_page(self, session, anilist_man, query, page):
        '''
        One page of AM_PAGE_SIZE series, fetched once per game. Returns
        None (after aborting the game) if AniList fails or nothing matches.
        '''
        # AniList's total is sometimes larger than the real number of
        # series, so a page past the end can come back empty; step back.
        while page >= 1:
            if page in self.am_pages:
                return self.am_pages[page]

            # Waits out AniList's rate limit rather than failing.
            status, resp = await anilist_post(session, query, {'page': page, 'perpage': AM_PAGE_SIZE},
                                              anilist_man)
            if status != 200 or not resp:
                self.abort('AniList is not responding right now, so trivia had to stop.')
                return None

            media = ((resp.get('data') or {}).get('Page') or {}).get('media') or []
            if media:
                self.am_pages[page] = media
                return media
            page = math.floor(page * 0.8) if page > 1 else 0

        self.abort('No series match those settings.')
        return None

    def am_slug(self, series_data, rank):
        aliases = [title for title in series_data['title'].values() if title]
        return {'img_url': (series_data.get('coverImage') or {}).get('large'),
                'description': series_data.get('description'),
                'answers': aliases,
                'rank': rank,
                'id': series_data.get('id')}

    async def gen_am_question(self, session, anilist_man, anagrams=False):
        ''' Returns False if no question could be made. '''
        base = await self.gen_am_base(session, anilist_man, 'img_url')
        if base is None:
            return False

        self.q_bases.append(base['id'])

        if anagrams:
            answer = random.choice(base['answers'])
            scrambled = anagram_scramble(answer)

            await self.questions.put([f'/announce Unscramble this: **{scrambled}**', [answer],
                                      {'text': f'Unscramble this: **{scrambled}**'}])
            return True

        img_url = img_tag(base['img_url'], (140, 210))

        await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_url),
                                  base['answers'], {'image': base['img_url']}])
        return True

    async def gen_am_qbowl_question(self, session, anilist_man):
        ''' Returns False if no question could be made. '''
        base = await self.gen_am_base(session, anilist_man, 'description')
        if base is None:
            return False

        self.q_bases.append(base['id'])

        question = base['description']
        for title in base['answers']:
            question = censor_quizbowl(title, question)

        await self.questions.put([question, base['answers']])
        return True

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

                    answers = list(series_info['attributes']['title'].values())
                    for title in series_info['attributes']['altTitles']:
                        for lang in ('en', 'ja-ro'):
                            if len(find_true_name(title.get(lang, ''))) > 0:
                                answers.append(title[lang])

                    if not answers:
                        series_id = ''

            if not series_id:
                continue

            async with session.get(f'{const.DEX_API}cover', params=[('manga[]', series_id)]) as r:
                covers = await r.json()

                if r.status != 200 or not covers.get('data'):
                    series_id = ''
                    continue

                cover_info = random.choice(covers['data'])
                cover_id = cover_info['attributes']['fileName']

        self.q_bases.append(series_id)

        img_url = f'https://uploads.mangadex.org/covers/{series_id}/{cover_id}.256.jpg'
        img_uhtml = await gen_uhtml_img(img_url, height_resize=PIC_SIZE)
        await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_uhtml), answers,
                                  {'image': img_url}])

    async def gen_lol_base(self, session, data):
        base = {}

        qtypes = []
        if 'all' not in self.categories:
            qtypes = [c for c in const.LEAGUE_CATS if c in self.categories]

        if self.excludecats:
            qtypes = [c for c in (qtypes or const.LEAGUE_CATS) if c not in self.excludecats]

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
            async with session.get(data['api'] + 'champion/{}.json'.format(data['champ'])) as r:
                resp = await r.text()
                data['champ_data'] = json.loads(resp)['data'][data['champ']]

                if data['qtype'] == 'skins':
                    # Chromas are listed as skins but have no art of their own.
                    skins = [s for s in data['champ_data']['skins'] if 'parentSkin' not in s]
                    skin = random.choice(skins)
                    data['cval'] = skin['num']
                elif data['qtype'] == 'spells':
                    data['cval'] = random.randint(0, 4)

                base = {k:data[k] for k in ('qtype', 'champ', 'cval')}

        return data, base
        
    async def gen_lol_question(self, session):
        data = {'all_champs': {}, 'champ': '', 'champ_data': {}, 'all_items': {}, 'item': {},
                'api': const.DDRAGON_API, 'img': const.DDRAGON_IMG}

        # Use the current patch so new champions/items are included.
        try:
            async with session.get(const.DDRAGON_VERSIONS) as r:
                version = (await r.json())[0]
            data['api'] = data['api'].replace(const.DDRAGON_VERSION, version)
            data['img'] = data['img'].replace(const.DDRAGON_VERSION, version)
        except Exception as e:
            logger.warning(f'Could not get latest Data Dragon version: {e!r}')

        async with session.get(data['api'] + 'champion.json') as r:
            resp = await r.text()
            data['all_champs'] = json.loads(resp)['data']
        
        async with session.get(data['api'] + 'item.json') as r:
            resp = await r.text()
            data['all_items'] = {k: v for k, v in json.loads(resp)['data'].items()
                                 if lol_name(v.get('name'))}
        data, base = await self.gen_lol_base(session, data)
        while self.duplicate_check(base):
            data, base = await self.gen_lol_base(session, data)
        
        self.q_bases.append(base)

        if data['qtype'] == 'items':
            img_url = data['img'] + 'item/{}.png'.format(data['item'])
            img_url = await gen_uhtml_img(await self.check_for_jpg(session, img_url))
            await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_url),
                                      [lol_name(data['all_items'][data['item']]['name'])]])
        elif data['qtype'] == 'skins':
            skin_name = ''
            for skin in data['champ_data']['skins']:
                if skin['num'] == data['cval']:
                    skin_name = skin['name'] if skin['name'] != 'default' else data['champ_data']['name']
                    break

            img_url = const.DDRAGON_SPL + '{}_{}.jpg'.format(data['champ'], data['cval'])
            img_url = await gen_uhtml_img(await self.check_for_jpg(session, img_url))
            await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_url),
                                      [lol_name(skin_name)]])
        elif data['qtype'] == 'spells':
            ability = {}
            if data['cval'] == 0:
                ability = data['champ_data']['passive']
                img_url = data['img'] + 'passive/{}'.format(ability['image']['full'])
                img_url = await gen_uhtml_img(await self.check_for_jpg(session, img_url))
                await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_url),
                                          [lol_name(ability['name'])]])
            else:
                ability = data['champ_data']['spells'][data['cval']-1]
                img_url = data['img'] + 'spell/{}'.format(ability['image']['full'])
                img_url = await gen_uhtml_img(await self.check_for_jpg(session, img_url))
                await self.questions.put(['/adduhtml {}, {}'.format(UHTML_NAME, img_url),
                                          [lol_name(ability['name'])]])

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

        # OpenTDB returns HTML-escaped text by default.
        for q in questions.get('results', []):
            formatted = f"""/announce {html.unescape(q['question'])}"""
            await self.questions.put([formatted, [html.unescape(q['correct_answer'])]])

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


def lol_name(name):
    '''
    Data Dragon names can carry markup, e.g. "<rarityLegendary>Fire at
    Will</rarityLegendary><br><subtitleLeft>...</subtitleLeft>". Keeps only
    the plain-text name before any line break.
    '''
    name = re.split(r'<br\s*/?>', name or '', maxsplit=1)[0]
    return strip_html(name)


def strip_html(text):
    ''' Turns AniList's HTML descriptions into plain text. '''
    text = re.sub(r'<br\s*/?>', ' ', text or '')
    text = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()


class DiscordTriviaGame(TriviaGame):
    '''
    Anime/manga trivia played in a Discord channel. Questions come from the
    same generators as the Showdown room; only the output differs. Scores
    are kept in their own all-time leaderboard.
    '''
    EMBED_COLOR = 0x2E51A2
    MAX_IMG_BYTES = 8 * 1024 * 1024
    QB_CHUNK_WORDS = 6
    QB_CHUNK_DELAY = 1.5    # Discord rate-limits message edits.

    def __init__(self, guild_id, bot):
        self.channel = None
        self.n = 0
        self.q_num = 0
        self.game_scores = {}
        self.anagrams = False
        self.quizbowl = False
        self.showing = False
        # Set by /trivia start before the game task runs, so two quick
        # starts can't both go ahead.
        self.starting = False
        super().__init__(f'{const.DISCORD_TRIVIA_PREFIX}{guild_id}', bot)

        # Scores are keyed by username, which never changes hands; this maps
        # them to the last display name seen, for when a lookup fails.
        self.names_file = f'trivia/{self.room}_names.json'
        try:
            with open(self.names_file) as f:
                self.names = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.names = {}

    def remember_name(self, member):
        if self.names.get(member.name) == member.display_name:
            return
        self.names[member.name] = member.display_name
        try:
            with open(self.names_file, 'w') as f:
                json.dump(self.names, f)
        except OSError as e:
            logger.warning(f'Could not save Discord trivia names: {e!r}')

    async def display_names(self, guild, users):
        '''
        Looks up the current display names of users (by username). Falls
        back to the last name seen, then the username.
        '''
        async def lookup(user):
            try:
                for member in await guild.query_members(query=user, limit=10):
                    if member.name == user:
                        self.remember_name(member)
                        return
            except Exception as e:
                logger.warning(f'Could not look up Discord member {user}: {e!r}')

        if guild is not None and users:
            try:
                await asyncio.wait_for(asyncio.gather(*(lookup(u) for u in users)), timeout=4)
            except asyncio.TimeoutError:
                pass
        return {u: self.names.get(u, u) for u in users}

    def reset_scoreboard(self, length=0):
        # The Discord leaderboard is all-time.
        pass

    async def run(self, n=10, **kwargs):
        self.starting = False
        if not self.active:
            self.n = n
            self.q_num = 0
            self.game_scores = {}
        await super().run(n=n, **kwargs)

    def update_scores(self, user):
        super().update_scores(user)
        self.game_scores[user] = self.game_scores.get(user, 0) + 1

    async def send(self, **kwargs):
        if self.channel is None:
            return None
        try:
            return await self.channel.send(allowed_mentions=discord.AllowedMentions.none(), **kwargs)
        except discord.HTTPException as e:
            logger.warning(f'Could not send trivia message to Discord: {e!r}')
            return None

    async def say(self, text):
        await self.send(content=text)

    async def fetch_image(self, url):
        '''
        Downloads a question image to attach to the message, so it shows
        even if the host blocks Discord's image proxy, and the URL isn't
        visible. Returns None if it can't be downloaded.
        '''
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as r:
                    if r.status != 200:
                        return None
                    expected = r.content_length
                    if expected and expected > self.MAX_IMG_BYTES:
                        return None
                    # read(n) only returns what has arrived so far, so keep
                    # going until the whole image is in.
                    data = bytearray()
                    async for chunk in r.content.iter_chunked(64 * 1024):
                        data.extend(chunk)
                        if len(data) > self.MAX_IMG_BYTES:
                            return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(f'Could not download trivia image {url}: {e!r}')
            return None

        if not data or (expected and len(data) != expected):
            logger.warning(f'Incomplete trivia image {url}: got {len(data)} of {expected} bytes')
            return None
        ext = url.rsplit('?', 1)[0].rsplit('.', 1)[-1].lower()
        if ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            ext = 'jpg'
        return discord.File(io.BytesIO(data), filename=f'question.{ext}')

    def question_embed(self, description=None):
        self.q_num += 1
        return discord.Embed(title=f'Question {self.q_num}/{self.n}',
                             description=description, color=self.EMBED_COLOR)

    async def show_question(self, question):
        # No guessing while the image downloads and nobody can see it yet.
        self.showing = True
        try:
            await self.post_question(question)
        finally:
            self.showing = False

    async def post_question(self, question):
        extra = question[2] if len(question) > 2 else {}

        if extra.get('image'):
            embed = self.question_embed('Name the series!')
            file = await self.fetch_image(extra['image'])
            if file:
                embed.set_image(url=f'attachment://{file.filename}')
                await self.send(embed=embed, file=file)
            else:
                embed.set_image(url=extra['image'])
                await self.send(embed=embed)
        else:
            text = extra.get('text') or strip_html(question[0])
            await self.send(embed=self.question_embed(text))

    async def quizbowl_question(self, question, skip_time, q_id):
        '''
        Reveals the description a few words at a time by editing one
        message, then starts the timer once it is fully shown.
        '''
        words = strip_html(question).split(' ')
        if len(' '.join(words)) > 3500:
            while len(' '.join(words)) > 3500:
                words.pop()
            words.append('...')

        embed = self.question_embed()
        shown = self.QB_CHUNK_WORDS
        embed.description = discord.utils.escape_markdown(' '.join(words[:shown]))
        msg = await self.send(embed=embed)

        while self.question_live(q_id):
            if shown >= len(words):
                if skip_time:
                    self.spawn(self.autoskip(skip_time, q_id))
                return
            await asyncio.sleep(self.QB_CHUNK_DELAY)
            shown += self.QB_CHUNK_WORDS
            embed.description = discord.utils.escape_markdown(' '.join(words[:shown]))
            if msg is not None:
                try:
                    await msg.edit(embed=embed)
                except discord.HTTPException as e:
                    logger.warning(f'Could not update quizbowl question: {e!r}')

        # Answered or skipped early: show the whole thing.
        if msg is not None and shown < len(words):
            embed.description = discord.utils.escape_markdown(' '.join(words))
            try:
                await msg.edit(embed=embed)
            except discord.HTTPException:
                pass

    def finish_question(self):
        self.correct.set()
        self.answers = []

    async def time_up(self, answer):
        if self.answers and self.answers[0] == answer:
            self.finish_question()
            await self.say(f"Time's up! The answer was **{discord.utils.escape_markdown(answer)}**.")

    async def skip_question(self):
        ''' Returns the skipped question's answer, or None if none was active. '''
        if not (self.active and self.answers):
            return None
        answer = self.answers[0]
        self.finish_question()
        return answer

    async def handle_guess(self, message):
        ''' Checks a chat message in the game's channel as a guess. '''
        if not (self.active and self.answers and not self.showing and self.channel is not None
                and message.channel.id == self.channel.id):
            return

        exact = 'anagrams' if self.anagrams else False
        answer = check_answer(message.content, self.answers, exact=exact)
        if not answer:
            return

        self.finish_question()
        self.update_scores(message.author.name)
        self.remember_name(message.author)
        await self.say(f'**{discord.utils.escape_markdown(message.author.display_name)}** wins. '
                       f'The answer was **{discord.utils.escape_markdown(answer)}**.')

    async def leaderboard_embed(self, title, rows, guild):
        names = await self.display_names(guild, [str(user) for user, _ in rows])
        lines = [f'**{i + 1}.** {discord.utils.escape_markdown(names[str(user)])} \u2014 {int(score)} pts'
                 for i, (user, score) in enumerate(rows)]
        return discord.Embed(title=title, description='\n'.join(lines) or 'No scores yet.',
                             color=self.EMBED_COLOR)

    async def show_results(self):
        rows = sorted(self.game_scores.items(), key=lambda x: x[1], reverse=True)[:10]
        title = 'Quizbowl Results' if self.quizbowl else 'Trivia Results'
        guild = getattr(self.channel, 'guild', None)
        embed = await self.leaderboard_embed(title, rows, guild)
        if not rows:
            embed.description = 'No one scored this game.'
        embed.set_footer(text='This trivia game has ended. Use /trivia leaderboard for all-time scores.')
        await self.send(embed=embed)
