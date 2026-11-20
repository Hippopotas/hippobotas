import aiohttp
import argparse
import ast
import asyncio
import datetime
import discord
import dotenv
import html
import json
import logging
import logging.handlers
import os
import pandas as pd
import random
import re
import shlex
import sys
import time
import websockets

import common.constants as const

from battle import Battle
from gacha import GachaManager
from commands import *
from common.anilist import anilist_num_entries, anilist_post
from common.arg_parsers import trivia_arg_parser
from common.connections import ApiManager, DatabaseManager
from common.mal import MAL_DOWN_MSG, PROFILE_CACHE_TTL, MalManager, list_table
from common.steam import set_steam_user, show_steam_user, steam_user_rand_series
from common.tcg import display_mtg_card, display_ptcg_card, display_ygo_card
from common.utils import find_true_name, gen_uhtml_img, leaderboard_uhtml, birthday_text, is_url, \
                         monospace_table_row, pastie_upload
from room import Room
from trivia import check_answer, DiscordTriviaGame
from user import User

logger = logging.getLogger(__name__)

# Logs can never use more than (1 + LOG_BACKUPS) * LOG_MAX_BYTES of disk.
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUPS = 3
# Longest single log message; rooms can send very large blocks of HTML.
LOG_MAX_MESSAGE = 16 * 1024

PS_SOCKET = 'wss://sim3.psim.us/showdown/websocket'
PS_LOGIN = 'https://play.pokemonshowdown.com/api/login'
TWITCH_TOKEN_API = 'https://id.twitch.tv/oauth2/token'
RECONNECT_DELAY = 5
JOINLIST = [const.ANIME_ROOM,
            const.LEAGUE_ROOM,
            const.TCG_ROOM,
            const.VG_ROOM,
            const.PEARY_ROOM,
            const.VTUBE_ROOM,
            const.SPORTS_ROOM,
            const.ARTS_ROOM,
            const.KPOP_ROOM,
            const.SMASH_ROOM,
            const.WRESTLING_ROOM,
            const.HINDISUB_ROOM]
WS = None


class TruncateLongMessages(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        if len(message) > LOG_MAX_MESSAGE:
            record.msg = message[:LOG_MAX_MESSAGE] + '...[truncated]'
            record.args = ()
        return True


def setup_logging():
    '''
    Logs to a rotating set of files with a fixed maximum total size.
    '''
    os.makedirs(os.path.dirname(const.LOG_FILE), mode=0o700, exist_ok=True)

    handler = logging.handlers.RotatingFileHandler(const.LOG_FILE, maxBytes=LOG_MAX_BYTES,
                                                   backupCount=LOG_BACKUPS, encoding='utf-8')
    handler.addFilter(TruncateLongMessages())
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))

    logging.basicConfig(level=logging.INFO, handlers=[handler])
    logging.captureWarnings(True)


def incoming_for_log(msg):
    '''
    Returns a websocket message as one line, without login challenges
    or the contents of PMs that aren't bot commands.
    '''
    lines = msg.split('\n')
    for i, line in enumerate(lines):
        if line.startswith('|challstr|'):
            lines[i] = '|challstr|<redacted>'
        elif line.startswith('|pm|'):
            parts = line.split('|', 4)
            if len(parts) == 5 and not parts[4].startswith(']'):
                parts[4] = '<redacted>'
            # Anything after this line belongs to the same PM.
            lines = lines[:i] + ['|'.join(parts)]
            break

    return repr('\n'.join(lines))


def outgoing_for_log(msg):
    '''
    Returns a message being sent as one line, without login tokens
    or typing test answers forwarded for review.
    '''
    if msg.startswith('|/trn '):
        return '|/trn <redacted>'
    if ', They typed: ' in msg:
        msg = msg.split(', They typed: ')[0] + ', They typed: <redacted>'

    return repr(msg)


def is_int_str(s):
    '''
    Checks if a string can be converted to an int.

    Args:
        s (str): input string

    Returns:
        True if it can be converted, else False
    '''
    try:
        int(s)
        return True
    except ValueError:
        return False


def steam_arg_parser(s, caller):
    '''
    Parses a steam invocation as if it were CLI input.

    Args:
        s (str): input str
        caller (str): username of the person who invoked the command

    Returns:
        args (Namespace): contains the arguments as methods
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument('-r', '--roll', action='store_true')
    parser.add_argument('username', type=str, nargs='*', default=[caller])

    args = None
    try:
        args = parser.parse_args(shlex.split(s))

    # Incorrectly formatted input results in args = None
    except SystemExit:
        pass
    except ValueError:
        return

    return args


class Bot:
    def __init__(self):
        self.username = os.getenv('PS_USERNAME')
        self.password = os.getenv('PS_PASSWORD')
        self.sucklist = self.load_sucklist()
        with open(const.FRIENDFILE) as f:
            self.friendslist = json.load(f)
        self.logged_in = False

        self.incoming = asyncio.Queue()
        self.outgoing = asyncio.Queue()

        self.roomlist = {}
        self.users = {}

        self.battles = {}
        self.allow_laddering = False

        self.typers = {}
        self.wpms = pd.read_csv(const.WPMFILE, converters={'recent_runs': ast.literal_eval}).set_index('user')
        with open(const.SENTENCEFILE) as f:
            self.num_typing_sentences = sum(1 for _ in f)


        self.roomdata_man = DatabaseManager(const.ROOMDATA_DB)
        self.gachaman = GachaManager()

        self.anilist_man = ApiManager(0.7)
        self.mal_man = MalManager(self.roomdata_man)

        self.mal_rooms = [const.ANIME_ROOM, const.PEARY_ROOM]
        self.steam_rooms = [const.VG_ROOM, const.PEARY_ROOM]

        # Fetched on first use of ]vg.
        self.igdb_token = None
        self.igdb_token_expire = 0


    @staticmethod
    def load_sucklist():
        '''
        Loads the suck leaderboard, starting a fresh one if the file
        is missing or unreadable.
        '''
        try:
            sucklist = pd.read_csv(const.SUCKFILE)
            if {'user', 'count'} <= set(sucklist.columns):
                return sucklist
            logger.warning(f'{const.SUCKFILE} is missing columns; starting a new suck list.')
        except (FileNotFoundError, pd.errors.EmptyDataError) as e:
            logger.warning(f'Could not read {const.SUCKFILE} ({e}); starting a new suck list.')

        return pd.DataFrame([[const.TIMER_USER, 0.0]], columns=['user', 'count'])


    async def refresh_igdb_token(self):
        '''
        Gets IGDB access token.

        Args:
        '''
        payload = {'client_id': os.getenv('TWITCH_ID'),
                   'client_secret': os.getenv('TWITCH_SECRET'),
                   'grant_type': 'client_credentials'}

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(TWITCH_TOKEN_API, data=payload) as r:
                    igdb_info = await r.json(content_type=None)
            self.igdb_token = igdb_info['access_token']
            self.igdb_token_expire = time.time() + int(igdb_info['expires_in'])
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError, TypeError) as e:
            logger.warning(f'Could not get an IGDB token: {e!r}')


    async def check_igdb_token(self):
        '''
        Checks if IGDB access token has expired, and
        generates a new one if it has.

        Args:
        '''
        if time.time() > self.igdb_token_expire:
            await self.refresh_igdb_token()


    async def start_repeats(self):
        '''
        Start the bot's repeating processes.

        Args:
        '''
        asyncio.create_task(self.ping_connect(), name='ping-connect')
        asyncio.create_task(self.user_repeater(), name='user-repeat')
        asyncio.create_task(self.prune_anotd(), name='anotd_repeat')
        asyncio.create_task(self.mal_man.refresh_repeater(), name='mal-refresh')

        birthday_rooms = await self.roomdata_man.execute("SELECT DISTINCT room FROM birthdays")
        for room in birthday_rooms:
            asyncio.create_task(self.birthday_repeater(room[0]), name=f'{room[0]}-birthdays')


    async def ping_connect(self):
        '''
        Pings Showdown to check that messages are still flowing.

        Args:
        '''
        await asyncio.sleep(30)
        await self.outgoing.put(f'|/w {self.username}, ping')


    async def birthday_repeater(self, ctx):
        '''
        Repeating process for birthday display.

        Args:
        '''
        next_time = await self.roomdata_man.execute(f"SELECT day FROM birthdays WHERE name='next_time' AND room='{ctx}'")
        try:
            next_time = next_time[0][0]
        except:
            next_time = 0

        while True:
            sleep_len = next_time - time.time()
            if sleep_len < 0:
                sleep_len = 60 * 60 * 6

                new_time = time.time() + sleep_len
                await self.roomdata_man.execute(f"UPDATE birthdays SET day={new_time} WHERE name='next_time' AND room='{ctx}'")

            await asyncio.sleep(sleep_len)
            text = await birthday_text(self, automatic=True, room=ctx)
            if text:
                await self.outgoing.put(f'{ctx}|/adduhtml {text}')

            new_time = time.time() + 60 * 60 * 6
            await self.roomdata_man.execute(f"UPDATE birthdays SET day={new_time} WHERE name='next_time' AND room='{ctx}'")


    async def gacha_repeater(self):
        '''
        Repeating process for adding gacha currency.
        Triggers at the top of every hour.

        Args:
        '''
        while True:
            now = datetime.datetime.now()
            next_hour = (now + datetime.timedelta(hours=1)).replace(second=0, minute=1)
            sleep_len = (next_hour - now).seconds

            await asyncio.sleep(sleep_len)
            # Potential race condition vs bot startup should
            # be fine given the above sleep delay.
            self.gachaman.add_rolls()


    async def get_userinfo(self, true_user):
        '''
        Gets userinfo from cached dict or queries PS
        for it if it does not exist.

        Args:
            true_user (str): user to get rooms and ranks for
        '''

        if true_user not in self.users:
            self.users[true_user] = {'group': None,
                                     'rooms': None,
                                     'event': asyncio.Event()}

        if not self.users[true_user]['group']:
            await self.outgoing.put(f'|/cmd userdetails {true_user}')

            try:
                await asyncio.wait_for(self.users[true_user]['event'].wait(), timeout=10)
            except asyncio.TimeoutError:
                logger.warning(f'No userdetails response for {true_user}.')
            self.users[true_user]['event'].clear()

        return self.users[true_user]


    async def user_repeater(self):
        '''
        Repeating process for updating user list.

        Args:
        '''
        while True:
            now = datetime.datetime.now()
            next_hour = (now + datetime.timedelta(hours=3)).replace(second=0, minute=1)
            sleep_len = (next_hour - now).seconds

            await asyncio.sleep(sleep_len)
            # Potential race condition vs bot startup should
            # be fine given the above sleep delay.
            # Copy, since commands can add users while this awaits.
            for u in list(self.users):
                self.users[u]['group'] = None
                await self.get_userinfo(u)


    async def prune_anotd(self):
        '''
        Prunes the anotd banlist once a day.

        Args:
        '''
        query = "SELECT medium, mal_id FROM anotd_banlist WHERE expiration < date('now')"
        while True:
            to_delete = await self.roomdata_man.execute(query)
            for medium, mal_id in to_delete:
                await self.roomdata_man.execute("DELETE FROM anotd_banlist WHERE medium=? AND mal_id=?",
                                                (medium, mal_id))

            await asyncio.sleep(24 * 60 * 60)


    async def wpm(self, true_user):
        '''
        Starts a typing test for a user. Takes from typeracer database.

        Args:
            true_user (str): user to run the typing test for
        '''
        if true_user in self.typers:
            return

        await self.outgoing.put(f'|/w {true_user}, Typing test starting soon...')

        idx = random.randrange(self.num_typing_sentences)
        sentence = ''
        with open(const.SENTENCEFILE) as f:
            for i, l in enumerate(f):
                if i == idx:
                    sentence = l.rstrip('\n')
                    break

        words = sentence.split(' ')

        test_str = ''
        for i, w in enumerate(words):
            if i % 2 == 0:
                test_str += u'\u2060\u2800'
            else:
                test_str += u' \u2060'
            test_str += w

        await asyncio.sleep(5)

        self.typers[true_user] = (time.time(), words)
        await self.outgoing.put(f'|/w {true_user}, {test_str}')


    async def listener(self, uri):
        '''
        Puts messages from the websocket into the incoming queue.

        Args:
            uri (str): websocket to connect to
        '''
        global WS
        while True:
            try:
                async with websockets.connect(uri, max_size=None) as ws:
                    # The same websocket is used to send info back.
                    WS = ws
                    self.logged_in = False
                    async for msg in ws:
                        await self.incoming.put(msg)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f'Showdown connection error: {e!r}')
            finally:
                WS = None

            logger.warning(f'Disconnected from Showdown. Reconnecting in {RECONNECT_DELAY}s.')
            await asyncio.sleep(RECONNECT_DELAY)


    async def interpreter(self):
        '''
        Gets messages from the incoming queue and acts on them.

        Args:
        '''
        while True:
            msg = await self.incoming.get()

            logger.info('< %s', incoming_for_log(msg))

            # One bad message must not stop the bot from handling the rest.
            try:
                await self.message_handler(msg)
            except Exception:
                logger.exception('Error handling message')


    async def message_handler(self, msg):
        '''
        Acts on websocket messages, depending on their contents.

        Args:
            msg (str): A message from the websocket
        '''

        curr_room = ''
        broken = msg.split('\n')
        if broken[0].startswith('>'):
            curr_room = broken[0][1:]

        parts = msg.split('|')

        if len(parts) <= 1:
            return

        # Query Responses
        if parts[1] == 'queryresponse':
            if parts[2] == 'userdetails':
                userinfo = json.loads(parts[3])
                true_name = userinfo['id'] if userinfo else ''
                if true_name in self.users:
                    if userinfo.get('group'):
                        self.users[true_name]['group'] = userinfo['group']
                    # Showdown often answers "rooms": false (e.g. for idle users), which
                    # doesn't mean they've lost their room ranks, so keep what we knew.
                    if userinfo.get('rooms'):
                        self.users[true_name]['rooms'] = userinfo['rooms']
                    elif self.users[true_name]['rooms'] is None:
                        self.users[true_name]['rooms'] = {}
                    self.users[true_name]['event'].set()

        # Managing room userlists
        room_obj = self.roomlist.get(curr_room)
        if parts[1] == 'init' and 'chat' in parts[2] and room_obj:
            room_obj.users = []
            for line in broken:
                if line.startswith('|users|'):
                    for user in line[len('|users|'):].split(',')[1:]:
                        rank = user[0]
                        username = user[1:].split('@')[0]
                        room_obj.add_user(username, rank)

        if parts[1] in ('J', 'j', 'join') and room_obj:
            user = parts[2].rstrip('\n')
            rank = user[0]
            username = user[1:].split('@')[0]
            room_obj.add_user(username, rank)

        elif parts[1] in ('L', 'l', 'leave') and room_obj:
            user = parts[2].rstrip('\n')
            username = user[1:].split('@')[0]
            room_obj.remove_user(username)

        elif parts[1] in ('N', 'n', 'name') and room_obj:
            new_user = parts[2].rstrip('\n')
            rank = new_user[0]
            username = new_user[1:].split('@')[0]
            old_user = parts[3].strip()
            room_obj.remove_user(old_user)
            room_obj.add_user(username, rank)

        # Battles
        if parts[1] == 'updatesearch':
            await self.update_battles(json.loads(parts[2]))
        
        if parts[1] == 'updatechallenges':
            challenges = json.loads(parts[2])['challengesFrom']
            for challenge in challenges:
                await self.respond_challenge(challenge, challenges[challenge])

        if curr_room.startswith('battle-'):
            await self.battle_handler(msg, curr_room, parts)

        # Sanitation
        if parts[1] == 'c:' or parts[1] == 'pm':
            chat_msg = '|'.join(parts[4:])
            if chat_msg.startswith('.motd') and find_true_name(parts[3]) == 'koakuma':
                chat_msg = chat_msg.replace('.motd', ']topic', 1)
            parts = parts[0:4] + [chat_msg]

        # Emote calls from chat
        if parts[1] == 'c:' and parts[4].count(':') >= 2:
            caller = parts[3]
            asyncio.create_task(self.emote_center(curr_room, caller, parts[4]))

        # Friend requests
        if parts[1] == 'pm' and parts[4].startswith('/raw'):
            m = re.match(r'/raw <span class="username">(?P<friend>.*)</span> sent you a friend request!', parts[4])
            if m:
                await self.friend_center(m.group('friend'))
                return

        # Login
        if parts[1] == 'challstr':
            logger.info('Logging in...')
            await self.login(parts[2] + "|" + parts[3])
        elif parts[1] == 'updateuser':
            await self.login_check(parts[2], parts[3])

        # Typing test responses
        elif parts[1] == 'pm' and find_true_name(parts[2]) in self.typers:
            true_caller = find_true_name(parts[2])
            sec_elapsed = time.time() - self.typers[true_caller][0]
            answer_key = self.typers[true_caller][1]
            typing_wc = len(answer_key)
            del self.typers[true_caller]

            words = parts[4].split(' ')
            if len(words) < (0.85*typing_wc):
                await self.outgoing.put(f'|/w {true_caller}, Too inaccurate for a reasonable measurement.')
                return

            correct_words = []
            for w in words:
                try:
                    idx = answer_key.index(w)
                except ValueError:
                    continue
                correct_words.append(answer_key.pop(idx))

            if len(correct_words) < (0.85*typing_wc):
                await self.outgoing.put(f'|/w {true_caller}, Too inaccurate for a reasonable measurement.')
                return

            speed = round(len(correct_words) / (sec_elapsed / 60), 1)
            acc = len(correct_words) / typing_wc * 100
            msg = f'You typed at {speed} WPM with {acc:0.1f}% accuracy. '

            if speed >= 160:
                msg += 'Sending results for manual review.'
                await self.outgoing.put(f'|/w {true_caller}, {msg}')
                await self.outgoing.put(f'|/w {const.OWNER}, {true_caller} had {speed} WPM with {acc:0.1f}% accuracy.')
                await self.outgoing.put(f'|/w {const.OWNER}, They typed: {parts[4]}')

                return

            try:
                wpminfo = self.wpms.loc[true_caller]
            except KeyError:
                wpminfo = pd.DataFrame([[true_caller, speed, speed, [speed]]],
                                       columns=['user', 'top_wpm', 'avg_wpm', 'recent_runs'])
                wpminfo = wpminfo.set_index('user')
                self.wpms = pd.concat([self.wpms, wpminfo])
                msg += 'Set a new record!'
            else:
                current_best = wpminfo['top_wpm']
                if speed > current_best:
                    self.wpms.at[true_caller, 'top_wpm'] = speed
                    msg += 'Set a new record! '
                else:
                    msg += f'Current best: {current_best} WPM. '

                old_runs = wpminfo['recent_runs']
                new_runs = old_runs + [speed]
                if len(new_runs) > 5:
                    new_runs = new_runs[1:]
                new_avg = round(sum(new_runs) / len(new_runs), 1)
                msg += f'Average of past {len(new_runs)} runs: {new_avg} WPM.'

                self.wpms.at[true_caller, 'avg_wpm'] = new_avg
                self.wpms.at[true_caller, 'recent_runs'] = new_runs

            self.wpms.to_csv(const.WPMFILE)
            await self.outgoing.put(f'|/w {true_caller}, {msg}')

        # Function calls from chat
        elif (parts[1] == 'c:' or parts[1] == 'pm') and parts[4].startswith(']'):
            is_pm = False
            caller = parts[3]
            if parts[1] == 'pm':
                is_pm = True
                caller = parts[2]
            asyncio.create_task(self.command_center(curr_room, caller, parts[4], pm=is_pm))

        # Trivia guesses
        elif parts[1] == 'c:':
            t_active = room_obj is not None and room_obj.trivia.active

            if t_active:
                msg = ''
                answer_check = ''
                trivia_game = self.roomlist[curr_room].trivia
                # Anime/manga/video game titles have a lot of different colloquial names.
                # Those rooms are more flexible in accepting answers.
                lenient_rooms = [const.ANIME_ROOM, const.HINDISUB_ROOM, const.VG_ROOM, const.SCHOL_ROOM]
                is_exact = False if curr_room in lenient_rooms else "league"
                is_exact = "anagrams" if self.roomlist[curr_room].trivia.anagrams else is_exact
                answer_check = check_answer(parts[4], trivia_game.answers, exact=is_exact)

                if answer_check:
                    msg = f'{parts[3]} wins.'
                    if find_true_name(parts[3]) == self.username:
                        if '/uhtml' in ''.join(parts[4]):
                            return
                        msg = 'Question skipped.'
                    else:
                        trivia_game.update_scores(find_true_name(parts[3]))

                    msg += f' The answer was {answer_check}.'

                    trivia_game.correct.set()
                    trivia_game.answers = []

                if msg:
                    await self.outgoing.put(f'{curr_room}|{msg}')


    async def battle_handler(self, msg, curr_room, parts):
        '''
        Handler for battle-specific messages.

        Args:
            msg (str): The raw message in its entirety
            curr_room (str): Room (well, battle) name
            parts (str): msg split on |
        '''
        if curr_room in self.battles:
            # Action required
            if parts[1] == 'request':
                await self.act_in_battle(curr_room)

            elif parts[1] == 'error':
                if 'more choices than unfainted' in parts[2]:
                    await self.act_in_battle(curr_room, one_poke=True)
                else:
                    await self.outgoing.put(f'{curr_room}|/choose default, default')
            else:
                # Otherwise is just battle information
                battle_info = msg.split('\n')[1:]
                for line in battle_info:
                    self.battles[curr_room].update_info(line)

        # Somehow a battle has slipped through the cracks?
        elif parts[1] == 'inactive' and parts[2].startswith(self.username):
            # Refreshes updatesearch
            await self.outgoing.put('|/cancelsearch')
            await self.act_in_battle(curr_room)


    async def respond_challenge(self, challenger, battle_format):
        '''
        Accepts challenges in supported formats. Does not accept
        challenges from people it is already battling.

        Args:
            challenger (str): The user requesting a battle
            battle_format (str): The format of the requested battle
        '''
        true_challenger = find_true_name(challenger)

        for battle in self.battles:
            if true_challenger in self.battles[battle].players:
                return

        if battle_format == const.METRONOME_BATTLE:
            team = Battle.make_team(battle_format)
            await self.outgoing.put(f'|/utm {team}\n/accept {challenger}')


    async def update_battles(self, updatesearch):
        '''
        Updates list of current battles self is in.

        Args:
            updatesearch (dict): Queues being currently searched and current battles;
                                 contains 'searching' and 'games' fields
        '''
        games = updatesearch['games']
        # Is None in case of no currently active games
        if not games:
            games = {}

            # Play on ladder if idle
            if not updatesearch['searching'] and self.allow_laddering:
                team = Battle.make_team(const.METRONOME_BATTLE)
                await self.outgoing.put(f'|/utm {team}\n/search {const.METRONOME_BATTLE}')

        for battle in games:
            if battle not in self.battles:
                self.battles[battle] = Battle(games[battle])

                await self.outgoing.put(f'|/join {battle}')
                await self.outgoing.put(f'{battle}|glhf!')
                await self.outgoing.put(f'{battle}|/timer on')
                await self.act_in_battle(battle)

        temp_battles = {}
        for battle in self.battles:
            if battle not in games:
                await self.outgoing.put(f'{battle}|gg!')
                await self.outgoing.put(f'|/leave {battle}')
            else:
                temp_battles[battle] = self.battles[battle]

        self.battles = temp_battles


    async def act_in_battle(self, battle_id, one_poke=False):
        '''
        Figures out what to do in a given battle.

        Args:
            battle_id (str): The battle's room name
        '''
        battle_format = battle_id.split('-')[1]
        action = Battle.act(battle_format, one_poke=one_poke)

        await self.outgoing.put(f'{battle_id}|{action}')


    async def emote_center(self, room, caller, line):
        '''
        Sends an emote if applicable.

        Args:
            room (str): Context in which the emote was invoked
            caller (str): User who invoked the emote
            line (str): The emote being invoked
        '''
        if not User.compare_ranks(caller[0], '+'):
            return

        emote_list = await self.roomdata_man.execute("SELECT name, url, times_used FROM emotes "
                                                     "WHERE room=?", (room,))

        if not emote_list:
            return

        emote_dict = {}
        for name, url, times_used in emote_list:
            emote_dict[name] = {'url': url, 'times_used': times_used}

        # Find emote
        possible_emotes = line.split(':')
        for pe in possible_emotes[1:-1]:
            emote = pe.lower()
            if emote in emote_dict:
                await self.roomdata_man.execute("UPDATE emotes SET times_used=times_used+1 "
                                                "WHERE room=? AND name=?", (room, emote))

                uhtml = await gen_uhtml_img(emote_dict[emote]['url'], height_resize=50, alt=emote)
                await self.outgoing.put(f'{room}|/adduhtml hippo-{emote}, {uhtml}')


    async def login(self, keyword):
        '''
        Performs the login dance with Showdown.

        Args:
            keyword (str): The challstr presented by showdown via websocket
        '''
        details = {'name': self.username,
                   'pass': self.password,
                   'challstr': keyword}

        async with aiohttp.ClientSession() as session:
            async with session.post(PS_LOGIN, data=details) as r:
                resp = await r.text()

        # Response is prefixed with ']' to prevent JSON hijacking.
        try:
            login_info = json.loads(resp[1:])
        except ValueError:
            logger.warning(f'Unexpected login response: {resp[:200]}')
            return

        assertion = login_info.get('assertion', '')
        if not assertion or assertion.startswith(';;'):
            logger.warning(f"Login failed: {login_info.get('actionerror') or assertion}")
            return

        await self.outgoing.put('|/trn ' + self.username + ',0,'  + str(assertion))
        logger.info('Sending assertion')


    async def login_check(self, name, logged_in):
        '''
        Sets up if login was successful, otherwise stops the bot.

        Args:
            name (str): Showdown username
            logged_in (bool): Whether or not login was successful
        '''
        logger.info('Logged in as: %s', name)

        # Showdown sends '0' as a guest before the login goes through, and
        # resends updateuser on other changes (e.g. avatar), so only act once.
        if logged_in.strip() != '1' or self.logged_in:
            return

        if find_true_name(name.split('@')[0]) == find_true_name(self.username):
            self.logged_in = True
            await self.outgoing.put('|/avatar 97')

            for room in JOINLIST:
                if room not in self.roomlist:
                    self.roomlist[room] = Room(room, self)
                await self.outgoing.put('|/join ' + room)


    async def friend_center(self, new_friend):
        new_friend = find_true_name(new_friend)

        if new_friend in self.friendslist:
            return

        if len(self.friendslist) >= const.MAX_FRIENDS:
            await self.outgoing.put(f'|/unfriend {self.friendslist[0]}')
            del self.friendslist[0]

        self.friendslist.append(new_friend)
        with open(const.FRIENDFILE, 'w') as ff:
            json.dump(self.friendslist, ff, indent=4)

        await self.outgoing.put(f'|/friend accept {new_friend}')


    async def birthday_chars_to_uhtml(self, characters):
        '''
        Generates table-rows-html, given a list of characters and their info.

        Args:
            characters (list): list of character infos.
        '''
        num_chars = len(characters)
        display_len = 4
        if num_chars % 3 == 0 and (num_chars / 3) < 4:
            display_len = 3

        # Measure all the images at once rather than one after another.
        img_uhtmls = await asyncio.gather(*[gen_uhtml_img(char[1] or const.IMG_NOT_FOUND,
                                                          height_resize=64, width_resize=64)
                                            for char in characters])

        char_uhtml = '<tr>'
        for i, (char, img_uhtml) in enumerate(zip(characters, img_uhtmls)):

            char_url = ''
            if len(char) == 3:
                char_url = char[2]

            char_uhtml += (f'<td style=\'padding:5px\'>{img_uhtml}</td>'
                            '<td style=\'padding-right:5px; width:80px\'>'
                           f'<a href=\'{char_url}\' style=\'color:inherit\'>'
                           f'{char[0]}</a></td>')

            # Maximum of 3 characters per line
            if i % display_len == (display_len - 1):
                char_uhtml += '</tr><tr>'

        char_uhtml += '</tr>'

        return char_uhtml


    async def gen_game_uhtml(self, game_info, headers, true_caller, ctx):
        '''
        Generates the uhtml to display for a given game's info.

        Args:
            game_info (dict): IGDB returned json of game information.
            headers (dict): header info for IGDB session.
            true_caller (str): user who invoked the command.
            ctx (str): context to send the message to.

        Returns:
        '''
        cover = game_info.get('cover')
        name = game_info['name']
        summary = game_info.get('summary', '')
        url = game_info['url']

        if ctx == 'pm':
            await self.outgoing.put(f'|/w {true_caller},{url}')
            return

        if len(summary) > 400:
            split_summary = summary.split()
            summary = ''
            for word in split_summary:
                summary += ' ' + word
                if len(summary) >= 400:
                    break
            summary += '...'

        platform_rds = {}
        for rd in game_info.get('release_dates', []):
            platform = ''
            for p in game_info.get('platforms', []):
                if p['id'] == rd['platform']:
                    try:
                        platform = p['abbreviation']
                    except KeyError:
                        platform = p['name']
                    break

            platform_rds[platform] = 'TBD'
            if 'date' in rd:
                unix_ts = rd['date']
                year = datetime.datetime.fromtimestamp(unix_ts, datetime.timezone.utc).strftime('%Y')

                platform_rds[platform] = year

        rd_str = ''
        for p in platform_rds:
            rd = platform_rds[p]
            rd_str += f'{p} ({rd}); '

        cover = 'https:' + cover['url'] if cover else const.IMG_NOT_FOUND

        if rd_str:
            rd_str = rd_str[:-2]

        uhtml = (f'/adduhtml {name}-gameinfo, <table style=\'border:3px solid #858585; '
                 'border-spacing:0px; border-radius:10px; background-image:'
                 'url(\'https://i.imgur.com/c68ilQW.png\'); background-size:cover\'><thead><tr>'
                 '<th width=96 style=\'font-size:14px; padding:5px\'>'
                f'<a href=\'{url}\' style=\'color:#FFF\'>{name}</a></th>'
                 '<th align=left style=\'font-weight:normal; color:#858585; padding-top:5px\'>'
                f'{rd_str}</th></tr></thead><tbody><tr><td style=\'padding:5px\'>'
                f'<center><img src=\'{cover}\' width=80 height=80></center>'
                 '</td><td style=\'vertical-align:top; width:400px\'>'
                f'{summary}</td></tr></tbody></table>')

        await self.outgoing.put(f'{ctx}|{uhtml}')


    async def command_center(self, room, caller, command, pm=False):
        '''
        Handles command messages targeted at the bot.

        Args:
            room (str): The room the command was posted in
            caller (str): The user who invoked the command
            command (str): The entire message sent by the user
            pm (bool): Whether or not the command came via PM
        '''

        msg = ''
        true_caller = find_true_name(caller)

        if not command:
            return
        if command[0] != ']' or command == ']':
            return

        command = command[1:].split()
        if not command:
            return

        # Aliases
        if command[0] == 'rand_song':
            command[0] = 'randsong'
        if command[0] == 'commands':
            command[0] = 'help'

        is_anotd = False
        if command[0] == 'anotd':
            is_anotd = True
            command[0] = 'mal'
            command.append('-r')

        userinfo = await self.get_userinfo(true_caller)

        cmd_kwargs = {'bot': self,
                      'full_command': command,
                      'room': room,
                      'caller': caller,
                      'true_caller': true_caller,
                      'caller_info': userinfo,
                      'is_pm': pm,
                      'pm_only': False,
                      'room_only': False,
                      'pm_response': pm,
                      'min_args': 0,
                      'max_args': 9999,
                      'usage_msg': f']{command[0]} ',
                      'req_rank': ' ',
                      'allowed_rooms': list(self.roomlist)}

        cmd_obj = None  # Remove when all commands are refactored

        if command[0] in const.SIMPLE_COMMANDS:
            if command[0] in ['mal_add', 'mal_set']:
                cmd_kwargs['allowed_rooms'] = [const.ANIME_ROOM]
                cmd_kwargs['min_args'] = 1

            cmd_obj = SimpleCommand(**cmd_kwargs)

        elif command[0] in const.UHTML_COMMANDS:
            cmd_kwargs['req_rank'] = '+'
            cmd_kwargs['pm_response'] = False

            if command[0] in ['anime', 'manga', 'randanime', 'randmanga']:
                cmd_kwargs['allowed_rooms'] = [const.ANIME_ROOM]

            if command[0] in ['mal']:
                cmd_kwargs['allowed_rooms'] = [const.ANIME_ROOM, const.PEARY_ROOM]
                cmd_kwargs['is_anotd'] = is_anotd

            if command[0] in ['anime', 'manga']:
                cmd_kwargs['min_args'] = 1

            cmd_obj = UhtmlCommand(**cmd_kwargs)

        elif command[0] in ['topic', 'topic_list', 'topic_rm']:
            cmd_kwargs['file'] = const.TOPICFILE
            cmd_obj = TopicCommand(**cmd_kwargs)

        elif command[0] in ['bl_add', 'bl_list', 'bl_rm']:
            cmd_kwargs['req_rank'] = '%'
            cmd_kwargs['allowed_rooms'] = [const.ANIME_ROOM]
            cmd_obj = BanlistCommand(**cmd_kwargs)

        elif command[0] in ['emote_add', 'emote_set', 'emote_list', 'emote_rm', 'emote_stats']:
            if command[0] == 'emote_set':
                cmd_kwargs['full_command'][0] = 'emote_add'

            cmd_kwargs['usage_msg'] += '[ROOM] '
            cmd_obj = EmoteCommand(**cmd_kwargs)

        elif command[0] in ['song_add', 'song_rm', 'song_list', 'randsong']:
            cmd_kwargs['req_rank'] = '%'

            if command[0] in ['randsong', 'song_list']:
                cmd_kwargs['req_rank'] = '+'
                cmd_kwargs['req_rank_pm'] = ' '

            cmd_obj = SongCommand(**cmd_kwargs)

        elif command[0] in ['birthday_add', 'birthday_rm']:
            cmd_kwargs['req_rank'] = '%'

            cmd_obj = BirthdayCommand(**cmd_kwargs)


        if cmd_obj: # Remove when all commands are refactored
            msg = await cmd_obj.evaluate()
            if not msg:
                return

            if cmd_obj.pm_response:
                msg = '|/w {}, '.format(true_caller) + msg
            else:
                msg = f'{cmd_obj.room}|{msg}'

            await self.outgoing.put(msg)
            return

        # Typing test
        if command[0] == 'typing_test':
            asyncio.create_task(self.wpm(true_caller), name='wpm-{}'.format(true_caller))
            return

        # tcg commands
        elif command[0] == 'mtg' and room == const.TCG_ROOM and User.compare_ranks(caller[0], '+'):
            query = ' '.join(command[1:])
            asyncio.create_task(display_mtg_card(self.outgoing.put, query))

        elif command[0] == 'ptcg' and room == const.TCG_ROOM and User.compare_ranks(caller[0], '+'):
            query = ' '.join(command[1:])
            asyncio.create_task(display_ptcg_card(self.outgoing.put, query))

        elif command[0] == 'ygo' and room == const.TCG_ROOM and User.compare_ranks(caller[0], '+'):
            query = ' '.join(command[1:])
            asyncio.create_task(display_ygo_card(self.outgoing.put, query))

        # Steam
        elif command[0] == 'addsteam' and (room in self.steam_rooms or pm):
            if len(command) > 1:
                ctx = room
                if pm:
                    ctx = 'pm'
                asyncio.create_task(set_steam_user(self.outgoing.put, true_caller, command[1], ctx),
                                    name='setsteam-{}'.format(true_caller))
            else:
                msg = 'Please enter a Steam ID (from the URL).'

        elif command[0] == 'steam' and (room in self.steam_rooms or pm):
            args = None

            to_parse = ''
            if len(command) > 1:
                to_parse = ' '.join(command[1:])
            args = steam_arg_parser(to_parse, true_caller)

            if args:
                args.username = find_true_name(' '.join(args.username))
            else:
                msg = 'Incorrect formatting.'
                if pm:
                    msg = f'/w {true_caller}, {msg}'
                await self.outgoing.put(f'{room}|{msg}')
                return

            steam_list = pd.read_csv(const.STEAMFILE)
            existing_user = steam_list[steam_list['user'] == args.username]
            if existing_user.empty:
                msg = 'This user does not have a Steam set. Please use ]addsteam to set a valid account. Make sure to use the URL ID and not the Steam username.'
            else:
                # Unvoiced users get the response in PMs.
                ctx = room
                if pm or not User.compare_ranks(caller[0], '+'):
                    ctx = 'pm'
                steam_user = existing_user.iloc[0]['steam']

                if args.roll:
                    asyncio.create_task(steam_user_rand_series(self.outgoing.put, steam_user,
                                                               args.username, caller, ctx),
                                        name='randsteam-{}'.format(args.username))
                else:
                    asyncio.create_task(show_steam_user(self.outgoing.put, steam_user, true_caller, ctx),
                                        name='showsteam-{}'.format(args.username))

        # Game search
        elif (command[0] == 'vg' and ((room in self.steam_rooms and User.compare_ranks(caller[0], '+'))
                                                                or pm)):
            ctx = 'pm' if pm else room
            if len(command) < 2:
                msg = 'Please specify a game to search for.'
            else:
                search = ' '.join(command[1:]).replace('"', '')
                await self.check_igdb_token()
                if not self.igdb_token:
                    msg = 'Game search is unavailable right now.'
                    if pm:
                        msg = f'/w {true_caller}, {msg}'
                    await self.outgoing.put(f'{room}|{msg}')
                    return

                headers = {'Client-ID': os.getenv('TWITCH_ID'),
                        'Authorization': f'Bearer {self.igdb_token}'}
                data = (f'search "{search}"; fields cover.url, name, '
                         'release_dates.*, platforms.*, summary, url; '
                         'where themes != (42);')

                async with aiohttp.ClientSession(headers=headers) as session:
                    r = await session.post(const.IGDB_API + 'games', data=data)

                    resp = await r.text()
                    if r.status != 200:
                        logger.warning(f'IGDB query failed on {data}: code {r.status}')
                        msg = 'Game not found.'
                    else:
                        game_list = json.loads(resp)
                        if not game_list:
                            msg = 'Game not found.'
                        else:
                            game_info = game_list[0]
                            asyncio.create_task(self.gen_game_uhtml(game_info, headers, true_caller, ctx))

        # Suck
        elif command[0] == 'suck':
            scount = 0
            suckinfo = self.sucklist[self.sucklist['user'] == true_caller]
            if len(command) > 1:
                if command[1] == 'top' and not pm:
                    suckboard = self.sucklist.sort_values('count', ascending=False)
                    suckboard = suckboard[suckboard['user'] != const.TIMER_USER].head(n=5).values.tolist()
                    msg = f"/adduhtml {leaderboard_uhtml(suckboard, 'Suckiest', name='suckboard')}"

                    await self.outgoing.put(room + '|' + msg)
                    return
            elif true_caller == 'hippopotas':
                scount = 69420
                msg = '{} has sucked {} times'.format(caller, str(scount))
            elif true_caller == 'hipposfavorite':
                scount = -1
                msg = '{} has sucked {} times. You are the best. Congrats!'.format(caller, str(scount))
            elif pm:
                if suckinfo.empty:
                    suckinfo = pd.DataFrame([[true_caller, 0]],
                                            columns=['user', 'count'])
                    self.sucklist = pd.concat([self.sucklist, suckinfo], ignore_index=True)

                # There's a global cooldown of a random number between
                # 5 and 30 minutes.
                end_time = self.sucklist.loc[self.sucklist['user'] == const.TIMER_USER, 'count'].iloc[0]
                if time.time() > end_time:
                    self.sucklist.loc[self.sucklist['user'] == true_caller, 'count'] += 1
                    scount = int(suckinfo['count'].iat[0] + 1)
                    self.sucklist.loc[self.sucklist['user'] == const.TIMER_USER, 'count'] = time.time() + random.randint(60*5, 60*30)
                else:
                    self.sucklist.loc[self.sucklist['user'] == true_caller, 'count'] = 0
                    scount = 0

                msg = '{} has sucked {} times.'.format(caller, str(scount))

            self.sucklist.to_csv(const.SUCKFILE, index=False)


        # Trivia

        elif (command[0] == 'trivia' or command[0] == 'anagrams') and not pm:
            if len(command) < 2:
                return

            trivia_game = self.roomlist[room].trivia
            trivia_status = trivia_game.active

            if (command[1] == 'start' and not trivia_status and
                    (User.compare_ranks(caller[0], '*') or true_caller == const.OWNER)):

                args = trivia_arg_parser(' '.join(command[2:])) if len(command) > 2 else None
                if not args:
                    msg = 'Invalid parameters. Trivia not started.'

                else:
                    if args.quizbowl and room == const.LEAGUE_ROOM:
                        args.quizbowl = None
                    if not args.quizbowl and room == const.SCHOL_ROOM:
                        args.quizbowl = True
                    anagrams = False
                    if command[0] == 'anagrams':
                        if args.quizbowl:
                            args.quizbowl = None
                        if args.autoskip == 15:
                            args.autoskip = 45
                        anagrams = True
                    is_dex = True if 'mangadex' in args.categories else False

                    timer_msg = f', with a {args.autoskip} second timer' if args.autoskip else ''
                    msg = (f'Starting a trivia with {args.len} questions{timer_msg}. '
                            'Type your answers to guess!')

                    asyncio.create_task(self.roomlist[room].trivia.run(
                        n=args.len, diff=args.diff, categories=args.categories,
                        excludecats=args.excludecats, by_rating=args.byrating,
                        autoskip=args.autoskip, quizbowl=args.quizbowl,
                        is_dex=is_dex, anagrams=anagrams), name=f'trivia-{room}')

            elif (command[1] == 'stop' or command[1] =='end') and User.compare_ranks(caller[0], '+'):
                if trivia_status:
                    await self.roomlist[room].trivia.stop()
                    return
                else:
                    msg = 'No trivia game in progress.'
            elif command[1] == 'score':
                user = ''
                score = 0

                if len(command) > 2:
                    user, score = trivia_game.userscore(find_true_name(''.join(command[2:])))
                else:
                    user, score = trivia_game.userscore(find_true_name(caller))

                if user is None:
                    msg = 'User not found.'
                else:
                    msg = '{} has earned {} points in trivia.'.format(user, score)
            elif command[1] == 'leaderboard':
                to_show = 5
                if len(command) > 2:
                    if is_int_str(command[2]):
                        to_show = int(command[2])

                title = 'Trivia Leaderboard'
                msg = f'/adduhtml {leaderboard_uhtml(trivia_game.leaderboard(n=to_show), title)}'
            elif command[1] == 'skip' and User.compare_ranks(caller[0], '+'):
                if trivia_game.active and trivia_game.answers:
                    answer = trivia_game.answers[-1]

                    trivia_game.correct.set()
                    trivia_game.answers = []
                    await trivia_game.skip(self.outgoing.put)

                    msg = 'Skipping question. A correct answer would have been {}.'.format(answer)

        elif command[0] == 'skip' and not pm:      # Trivia skip alias
            new_command = ']trivia ' + ' '.join(command)
            await self.command_center(room, caller, new_command)
            return

        # Gachas
        elif command[0] == 'gacha_join' and (pm or room == const.GACHA_ROOM):
            if self.gachaman.player_check(true_caller):
                msg = f'{caller} is already playing!'
            else:
                self.gachaman.player_add(true_caller)
                msg = f'{caller} can now use gacha commands.'

        elif ((command[0] == 'gacha_box' or command[0] == 'box')
                and (room == const.GACHA_ROOM or pm)):
            if not self.gachaman.player_check(true_caller):
                msg = 'You don\'t have an account! Use ]gacha_join first'
            else:
                msg = await self.gachaman.player_box(true_caller)

        elif command[0] == 'gprofile' and room == const.GACHA_ROOM:
            if not self.gachaman.player_check(true_caller):
                msg = 'You don\'t have an account! Use ]gacha_join first'
            else:
                pass
                msg = self.gachaman.profile(true_caller)

        elif ((command[0] == 'gacha_roll' or command[0] == 'roll')
                and room == const.GACHA_ROOM):
            gachas_str = '; '.join(const.GACHAS)

            if len(command) < 2 or len(command) > 3:
                msg = ('Please roll using ]gacha_roll GACHA [num_rolls]. '
                      f'The current list of GACHAs is: {gachas_str}')
            elif command[1] not in const.GACHAS:
                msg = f'Invalid gacha. The current list of gachas is: {gachas_str}'
            elif len(command) == 3 and not command[2].isnumeric():
                msg = f'Please enter a valid number (integer from 1-10).'
            elif len(command) == 3 and (int(command[2]) < 1 or int(command[2]) > 10):
                msg = f'Please enter a valid number (integer from 1-10).'
            elif not self.gachaman.player_check(true_caller):
                msg = 'You don\'t have an account! Use ]gacha_join first.'  

            else:
                num_rolls = 1
                if len(command) == 3:
                    num_rolls = int(command[2])

                pulls = self.gachaman.roll(true_caller, command[1], num_rolls=num_rolls)
                if not pulls:
                    user_rolls = self.gachaman.player_info(true_caller).roll_currency
                    msg = f'Not enough rolls in your account: {caller} has {user_rolls} rolls.'
                else:
                    msg = f'/adduhtml {true_caller}-rolls, {pulls}'

        elif command[0] == 'fav' and pm:
            if len(command) < 2:
                return
            if not self.gachaman.player_check(true_caller):
                msg = 'You don\'t have an account! Use ]gacha_join first.'
            cmd_args = ''.join(command[1:])
            try:
                unit_ids = [int(x) for x in cmd_args.split(',')]
            except ValueError:
                msg = 'All IDs must be whole numbers.'
            else:
                num_updates = self.gachaman.favorite(true_caller, unit_ids)
                msg = f'Favorited {num_updates} units.'

        elif command[0] == 'unfav' and pm:
            if len(command) < 2:
                return
            if not self.gachaman.player_check(true_caller):
                msg = 'You don\'t have an account! Use ]gacha_join first.'
            cmd_args = ''.join(command[1:])
            try:
                unit_ids = [int(x) for x in cmd_args.split(',')]
            except ValueError:
                msg = 'All IDs must be whole numbers.'
            else:
                num_updates = self.gachaman.unfavorite(true_caller, unit_ids)
                msg = f'Unfavorited {num_updates} units.'

        elif command[0] == 'showcase' and pm:
            if len(command) < 3:
                return
            if not self.gachaman.player_check(true_caller):
                msg = 'You don\'t have an account! Use ]gacha_join first.'

            try:
                uid = int(re.sub('[^0-9]', '', command[1]))
                place = int(re.sub('[^0-9]', '', command[2]))
                if 0 > place or place > 5:
                    raise Exception
            except ValueError:
                msg = 'Please enter whole number values as arguments.'
            except Exception:
                msg = 'Showcase slot must be somewhere from 1-5.'
            else:
                updated = self.gachaman.showcase(true_caller, uid, place)
                msg = f'Set unit {uid} to slot {place}.' if updated else 'Nothing happened.'

        elif command[0] == 'unshowcase' and pm:
            if len(command) < 2:
                return
            if not self.gachaman.player_check(true_caller):
                msg = 'You don\'t have an account! Use ]gacha_join first.'

            try:
                uid = int(re.sub('[^0-9]', '', command[1]))
            except ValueError:
                msg = 'Please enter whole number values as arguments.'
            else:
                updated = self.gachaman.unshowcase(true_caller, uid)
                msg = f'Removed {uid} from showcase.' if updated else 'Nothing happened.'

        elif command[0] == 'merge' and pm:
            if not self.gachaman.player_check(true_caller):
                msg = 'You don\'t have an account! Use ]gacha_join first.'

            try:
                ids = None
                if len(command) > 1:
                    cmd_args = ''.join(command[1:])
                    ids = [int(x) for x in cmd_args.split(',')]
            except ValueError:
                msg = 'Please enter whole number values as arguments.'
            else:
                num_merged = self.gachaman.merge(true_caller, ids)
                msg = f'{num_merged} units merged.'

        elif command[0] == 'unit' and not pm:
            if len(command) < 3:
                return

            msg = self.gachaman.show_unit_info(command[1], ' '.join(command[2:]))

            if not msg:
                msg = 'Usage: ]unit GACHA UNIT_NAME'
            else:
                msg = f'/adduhtml hippo-{command[2]}, {msg}'

        # Self maintenance
        elif command[0] == 'ladder_toggle' and true_caller == const.OWNER:
            self.allow_laddering = not self.allow_laddering
            # Refreshes updatesearch as well.
            await self.outgoing.put('|/cancelsearch')

            msg = f'Laddering is now {self.allow_laddering}.'

        elif command[0] == 'exec' and true_caller == const.OWNER:
            to_exec = ' '.join(command[1:])
            await self.outgoing.put(f'|{to_exec}')
            return

        elif command[0] == 'roomexec' and true_caller == const.OWNER:
            to_exec = ' '.join(command[2:])
            await self.outgoing.put(f'{command[1]}|{to_exec}')
            return

        elif command[0] == 'test' and true_caller == const.OWNER:
            await self.outgoing.put('|/friend')
            return

        if not msg:
            return

        if pm:
            msg = '/w {}, '.format(true_caller) + msg

        await self.outgoing.put(room + '|' + msg)


    async def sender(self):
        '''
        Sends messages destined for Showdown.

        Args:
        '''
        while True:
            msg = await self.outgoing.get()

            # AFD
            if not msg.startswith('|') and random.random() < 0.0001:
                room = msg.split('|')[0]
                url = 'https://i.imgur.com/z4nlXPW.png'
                uhtml = await gen_uhtml_img(url, height_resize=50, alt='worryclown')
                msg = f'{room}|/adduhtml hippo-worryclown, {uhtml}'

            logger.info('> %s', outgoing_for_log(msg))
            if WS is None:
                logger.warning('Not connected; dropping message.')
                continue
            try:
                await WS.send(msg)
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f'Could not send, connection closed: {e!r}')
            await asyncio.sleep(0.1)


# Discord embed colors.
ANILIST_COLOR = 0x02A9FF
MAL_COLOR = 0x2E51A2
# Discord allows more, but long synopses swamp the embed.
SYNOPSIS_MAX = 1000
# Autocomplete choices can be at most 100 characters, and at most 25 are shown.
CHOICE_MAX = 100
CHOICES_SHOWN = 25
# Discord users' MAL links share the table with Showdown names, which
# can't contain a colon.
MAL_KEY_PREFIX = 'discord:'

NO_PINGS = discord.AllowedMentions.none()

def series_fields(fallback_title):
    '''
    The fields asked for each series. Like on Showdown, ]anime and ]manga
    fall back to the romaji title, and ]randanime/]randmanga to AniList's
    preferred title, when there's no English one.
    '''
    return f'''
                id
                idMal
                title {{
                    english
                    {fallback_title}
                }}
                coverImage {{
                    extraLarge
                }}
                status
                episodes
                chapters
                description
                averageScore
'''


def anilist_error(resp):
    return (resp or {}).get('errors', [{}])[0].get('message', 'unknown error')


def series_title(series):
    ''' The English title, or whichever fallback title the query asked for. '''
    title = series['title']
    return title['english'] or title.get('romaji') or title.get('userPreferred')


async def anilist_search_data(medium, search, anilist_man):
    '''
    AniList's best match for search, fetched the same way as ]anime and
    ]manga (which return Showdown HTML, so Discord can't use them).

    Returns:
        (series, error): the series' AniList data, or None and why not.
    '''
    query = '''
    query ($search: String) {
        Page (page: 1, perPage: 1) {
            media (type: TYPE_PLACEHOLDER, search: $search, isAdult: false) {
                FIELDS_PLACEHOLDER
            }
        }
    }
    '''.replace('TYPE_PLACEHOLDER', medium.upper()).replace('FIELDS_PLACEHOLDER', series_fields('romaji'))

    async with anilist_man.lock():
        async with aiohttp.ClientSession() as session:
            async with session.post(const.ANILIST_API, json={'query': query, 'variables': {'search': search}}) as r:
                resp = await r.json(content_type=None)

                if r.status != 200:
                    return None, f'Status code {r.status} when fetching {search}: {anilist_error(resp)}'

                series_list = resp['data']['Page']['media']
                if not series_list:
                    return None, f'No {medium} found for {search}.'
                return series_list[0], None


async def anilist_rand_data(medium, anilist_man, genres=(), tags=()):
    '''
    A random series with at least one of the genres or tags (any series
    if neither is given), like ]randanime and ]randmanga.

    Returns:
        (series, error): the series' AniList data, or None and why not.
    '''
    category_params = []
    if genres:
        category_params.append(f'genre_in: {json.dumps(list(genres))}')
    if tags:
        category_params.append(f'tag_in: {json.dumps(list(tags))}')
    categories = ''.join(f'{p},' for p in category_params)

    query = '''
    query ($page: Int) {
        Page (page: $page, perPage: 1) {
            pageInfo {
                total
            }
            media (CATEGORIES_PLACEHOLDER minimumTagRank: 50, type: TYPE_PLACEHOLDER, isAdult: false) {
                FIELDS_PLACEHOLDER
            }
        }
    }
    '''.replace('CATEGORIES_PLACEHOLDER', categories).replace('TYPE_PLACEHOLDER', medium.upper()) \
       .replace('FIELDS_PLACEHOLDER', series_fields('userPreferred'))
    query_vars = {'page': 1}

    async with aiohttp.ClientSession() as session:
        num_entries = await anilist_num_entries(query, query_vars, session, anilist_man)
        if not num_entries:
            return None, 'No series found with the given specifications.'

        query_vars['page'] = random.randint(1, num_entries)
        while True:
            status, resp = await anilist_post(session, query, query_vars, anilist_man)
            if status != 200 or not resp:
                return None, f'Status code {status} when fetching a random {medium}: {anilist_error(resp)}'

            media = resp['data']['Page']['media']
            if media:
                return media[0], None
            if query_vars['page'] <= 1:
                return None, 'No series found with the given specifications.'
            # The total can shrink between requests; look earlier.
            query_vars['page'] //= 2


def is_discord_trivia_staff(member):
    ''' Driver and above (or the server owner) in the Discord trivia server. '''
    guild = getattr(member, 'guild', None)
    if guild is not None and guild.owner_id == member.id:
        return True
    return any(role.name in const.DISCORD_TRIVIA_ROLES for role in getattr(member, 'roles', []))


def in_command_category(channel):
    ''' Whether a channel (or the channel a thread is in) is under an allowed category. '''
    channel = getattr(channel, 'parent', None) or channel
    category = getattr(channel, 'category', None)
    return category is not None and find_true_name(category.name) in const.DISCORD_COMMAND_CATEGORIES


async def require_command_channel(ctx, staff=False):
    '''
    In the trivia server, commands only work under the command categories,
    and staff commands only for Drivers and above. Tells the caller (only
    them) if they can't use the command here.
    '''
    if ctx.guild_id != const.DISCORD_TRIVIA_GUILD:
        return True
    if not in_command_category(ctx.channel):
        where = ' or '.join(sorted(const.DISCORD_COMMAND_CATEGORIES))
        await ctx.respond(f'This command only works in the {where} channels.', ephemeral=True)
        return False
    if staff and not is_discord_trivia_staff(ctx.author):
        await ctx.respond('Only Drivers and above can do that.', ephemeral=True)
        return False
    return True


async def require_discord_staff(ctx):
    '''
    In the trivia server, only Drivers and above, in any channel. Tells the
    caller (only them) if they can't use the command.
    '''
    if ctx.guild_id != const.DISCORD_TRIVIA_GUILD or is_discord_trivia_staff(ctx.author):
        return True
    await ctx.respond('Only Drivers and above can do that.', ephemeral=True)
    return False


def escape_link_text(text):
    ''' Escapes text to go inside [text](url). '''
    return discord.utils.escape_markdown(text).replace('[', '\\[').replace(']', '\\]')


def md_link(text, url):
    ''' A Discord markdown link. '''
    return f'[{escape_link_text(text)}]({url})'


def plain_text(description, limit):
    ''' AniList's HTML descriptions, as escaped Discord text of at most limit characters. '''
    if not description:
        return 'No synopsis available.'
    text = re.sub(r'<br\s*/?>', '\n', description, flags=re.IGNORECASE)
    text = html.unescape(re.sub(r'<[^>]+>', '', text))
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(' ', 1)[0].rstrip() + '…'
    return discord.utils.escape_markdown(text)


def series_embed(medium, series):
    ''' A Discord infobox for an AniList anime or manga. '''
    al_url = f'https://anilist.co/{medium}/{series["id"]}'
    embed = discord.Embed(title=series_title(series)[:256], url=al_url,
                          description=plain_text(series['description'], SYNOPSIS_MAX),
                          color=ANILIST_COLOR)
    cover = (series.get('coverImage') or {}).get('extraLarge')
    if cover:
        embed.set_thumbnail(url=cover)

    parts = 'Episodes' if medium == 'anime' else 'Chapters'
    score = f'{series["averageScore"]}%' if series['averageScore'] else 'N/A'
    # Shown as AniList gives them, like on Showdown (e.g. FINISHED, None).
    embed.add_field(name='Status', value=str(series['status']))
    embed.add_field(name=parts, value=str(series[parts.lower()]))
    embed.add_field(name='Score', value=score)

    # Like on Showdown, the MAL link is always shown, even for series
    # AniList has no MAL ID for.
    mal_url = f'https://myanimelist.net/{medium}/{series["idMal"]}'
    embed.add_field(name='Links', value=f'[AniList]({al_url}) · [MAL]({mal_url})', inline=False)
    return embed


def parse_categories(text):
    '''
    Picks AniList genres and tags out of text the same way as ]randanime:
    each word is compared using find_true_name, so multi-word ones are
    typed without spaces (sliceoflife), and other words are ignored.

    Returns:
        (genres, tags)
    '''
    true_args = list(map(find_true_name, text.split()))
    genres = [g for g in const.ANILIST_GENRES if find_true_name(g) in true_args]
    tags = [t for t in list(const.ANILIST_TAGS) if find_true_name(t) in true_args]
    return genres, tags


def mal_link(medium, node):
    ''' A link to a MAL list entry's series page. '''
    return md_link(node['title'], f'https://myanimelist.net/{medium}/{node["id"]}')


def mal_key(member):
    ''' The mal_users key for a Discord user. '''
    return f'{MAL_KEY_PREFIX}{member.id}'


class DiscordBot:
    def __init__(self, ps_bot=None):
        # Trivia and the song/anime/MAL commands use the Showdown bot's
        # database and AniList/MAL managers.
        self.ps_bot = ps_bot
        self.trivia = DiscordTriviaGame(const.DISCORD_TRIVIA_GUILD, ps_bot) if ps_bot else None
        self.message_content = True
        self.bot = self.build_bot()

    def build_bot(self):
        intents = discord.Intents.default()
        # Needed to read trivia guesses typed in chat. It's a privileged
        # intent, so it must also be switched on in the Developer Portal.
        intents.message_content = self.message_content
        bot = discord.Bot(intents=intents)

        @bot.command(description="Restarts the bot, reloading its code.", guild_ids=[218560071540408320, 1567948160020643870])
        async def restart_ps(ctx):
            if not await require_command_channel(ctx, staff=True):
                return
            await ctx.send_response("Restarting bot.", ephemeral=True)
            try:
                await restart_process()
            except OSError as e:
                logger.exception('Restart failed')
                await ctx.followup.send(f'Restart failed: {e}', ephemeral=True)

        @bot.event
        async def on_ready():
            logger.info('Logged into discord.')
            await bot.sync_commands()

        if self.trivia is not None:
            self.add_trivia_commands(bot)
        if self.ps_bot is not None:
            self.add_song_commands(bot)
            self.add_animanga_commands(bot)
            self.add_mal_commands(bot)

        return bot

    def add_trivia_commands(self, bot):
        game = self.trivia
        trivia = bot.create_group('trivia', 'Anime and manga trivia',
                                  guild_ids=[const.DISCORD_TRIVIA_GUILD])

        async def require_channel(ctx):
            channel = ctx.channel
            # Threads count as part of the channel they're in.
            parent = getattr(channel, 'parent', None)
            names = {getattr(channel, 'name', None), getattr(parent, 'name', None)}
            if const.DISCORD_TRIVIA_CHANNEL in names:
                return True
            target = None
            if ctx.guild is not None:
                target = discord.utils.get(ctx.guild.text_channels, name=const.DISCORD_TRIVIA_CHANNEL)
            where = target.mention if target else f'#{const.DISCORD_TRIVIA_CHANNEL}'
            await ctx.respond(f'Trivia commands only work in {where}.', ephemeral=True)
            return False

        async def require_staff(ctx):
            if not await require_channel(ctx):
                return False
            if is_discord_trivia_staff(ctx.author):
                return True
            await ctx.respond('Only Drivers and above can do that.', ephemeral=True)
            return False

        @trivia.command(name='start', description=f'Start an anime/manga trivia game in #{const.DISCORD_TRIVIA_CHANNEL}.')
        async def trivia_start(
                ctx,
                questions: discord.Option(int, 'Number of questions', min_value=1, max_value=50, default=10),
                mode: discord.Option(str, 'Kind of questions', default='standard',
                                     choices=['standard', 'anagrams', 'quizbowl', 'mangadex']),
                difficulty: discord.Option(int, '1 (popular series) to 10 (obscure)',
                                           min_value=1, max_value=10, default=3),
                timer: discord.Option(int, 'Seconds before a question is skipped, 0 for no timer '
                                           '(default 15, or 45 for anagrams)',
                                      min_value=0, max_value=300, required=False, default=None),
                categories: discord.Option(str, 'Genres, tags or formats to include, e.g. "romance slice of life"',
                                           required=False, default=''),
                exclude: discord.Option(str, 'Genres, tags or formats to leave out',
                                        required=False, default=''),
                by_rating: discord.Option(bool, 'Pick series by score instead of popularity', default=False)):
            if not await require_staff(ctx):
                return
            if not self.message_content:
                await ctx.respond("I can't read chat messages, so nobody could answer. Turn on the "
                                  "Message Content Intent for this bot in the Discord Developer "
                                  "Portal, then restart me.", ephemeral=True)
                return
            if game.active or game.starting:
                where = game.channel.mention if game.channel is not None else 'another channel'
                await ctx.respond(f'There is already a trivia game running in {where}.', ephemeral=True)
                return

            if timer is None:
                timer = 45 if mode == 'anagrams' else 15

            arg_str = f'{questions} -d {difficulty} -s {timer}'
            if categories.strip():
                arg_str += ' -c ' + ' '.join(shlex.quote(c) for c in categories.split())
            if exclude.strip():
                arg_str += ' -cx ' + ' '.join(shlex.quote(c) for c in exclude.split())
            if by_rating:
                arg_str += ' -r'
            args = trivia_arg_parser(arg_str)
            if args is None:
                await ctx.respond("I didn't recognize some of those categories. They should be "
                                  "AniList genres, tags or formats.", ephemeral=True)
                return

            is_dex = mode == 'mangadex' or 'mangadex' in args.categories
            anagrams = mode == 'anagrams' and not is_dex
            quizbowl = mode == 'quizbowl' and not is_dex

            # Claim the game before anything that waits, so a second start
            # arriving meanwhile is turned away.
            game.starting = True
            game.channel = ctx.channel
            # The question generator cancels this task by name if it fails.
            asyncio.create_task(game.run(
                n=questions, diff=difficulty, categories=args.categories,
                excludecats=args.excludecats, by_rating=by_rating, autoskip=timer,
                quizbowl=quizbowl, is_dex=is_dex, anagrams=anagrams), name=f'trivia-{game.room}')

            timer_msg = f', with a {timer} second timer' if timer else ''
            kind = 'MangaDex' if is_dex else mode
            await ctx.respond(f'Starting a {kind} trivia with {questions} questions{timer_msg}. '
                              'Type your answers in this channel to guess!')

        @trivia.command(name='stop', description='End the current trivia game.')
        async def trivia_stop(ctx):
            if not await require_staff(ctx):
                return
            if not game.active:
                await ctx.respond('No trivia game in progress.', ephemeral=True)
                return
            await ctx.respond('Stopping the trivia game.')
            await game.stop()

        @trivia.command(name='skip', description='Skip the current question.')
        async def trivia_skip(ctx):
            if not await require_staff(ctx):
                return
            answer = await game.skip_question()
            if answer is None:
                await ctx.respond('There is no question to skip.', ephemeral=True)
                return
            await ctx.respond(f'Question skipped. The answer was **{discord.utils.escape_markdown(answer)}**.')

        @trivia.command(name='score', description="Show someone's all-time trivia score.")
        async def trivia_score(ctx, user: discord.Option(discord.Member, 'Whose score (default: yours)',
                                                         required=False, default=None)):
            if not await require_channel(ctx):
                return
            member = user or ctx.author
            game.remember_name(member)
            _, score = game.userscore(member.name)
            name = discord.utils.escape_markdown(member.display_name)
            if score is None:
                await ctx.respond(f"{name} hasn't scored in trivia yet.", ephemeral=True)
            else:
                await ctx.respond(f'{name} has earned {int(score)} points in trivia.', ephemeral=True)

        @trivia.command(name='leaderboard', description='Show the all-time trivia leaderboard.')
        async def trivia_leaderboard(ctx, count: discord.Option(int, 'How many places to show',
                                                                min_value=1, max_value=10, default=5)):
            if not await require_channel(ctx):
                return
            # Looking up display names can take a moment.
            await ctx.defer(ephemeral=True)
            embed = await game.leaderboard_embed('Trivia Leaderboard', game.leaderboard(n=count), ctx.guild)
            await ctx.respond(embed=embed, ephemeral=True)

        @bot.event
        async def on_message(message):
            if (message.author.bot or message.guild is None
                    or message.guild.id != const.DISCORD_TRIVIA_GUILD):
                return
            await game.handle_guess(message)

    def add_song_commands(self, bot):
        ''' Song commands, sharing the animeandmanga room's song pool. '''
        guild_ids = [const.DISCORD_TRIVIA_GUILD]
        db = self.ps_bot.roomdata_man
        room = const.ANIME_ROOM

        async def song_titles(actx: discord.AutocompleteContext):
            rows = await db.execute("SELECT title FROM songs WHERE room=?", (room,))
            typed = (actx.value or '').lower()
            titles = sorted({r[0] for r in rows if typed in r[0].lower() and len(r[0]) <= CHOICE_MAX},
                            key=str.lower)
            return titles[:CHOICES_SHOWN]

        @bot.slash_command(name='song_add', description=f'Add a song to the {room} song pool.', guild_ids=guild_ids)
        async def song_add(ctx,
                           title: discord.Option(str, 'The name of the song'),
                           url: discord.Option(str, 'A YouTube link to the song')):
            if not await require_discord_staff(ctx):
                return
            url = url.strip()
            if not is_url(url):
                await ctx.respond('Please give a valid URL.', ephemeral=True)
                return
            if await db.execute("SELECT 1 FROM songs WHERE room=? AND url=?", (room, url)):
                await ctx.respond(f'That URL is already in the {room} song pool.', ephemeral=True)
                return
            await db.execute("INSERT INTO songs (room, title, url) VALUES (?, ?, ?)", (room, title, url))
            await ctx.respond(f'Added **{discord.utils.escape_markdown(title)}** to the {room} song pool.',
                              allowed_mentions=NO_PINGS)

        @bot.slash_command(name='song_rm', description=f'Remove a song from the {room} song pool.',
                           guild_ids=guild_ids)
        async def song_rm(ctx, title: discord.Option(str, 'The name of the song (not case sensitive)',
                                                     autocomplete=song_titles)):
            if not await require_discord_staff(ctx):
                return
            rows = await db.execute("SELECT DISTINCT title FROM songs WHERE room=?", (room,))
            matches = [r[0] for r in rows if find_true_name(r[0]) == find_true_name(title)]
            if not matches:
                await ctx.respond(f'**{discord.utils.escape_markdown(title)}** is not in the song pool.',
                                  ephemeral=True, allowed_mentions=NO_PINGS)
                return
            for match in matches:
                await db.execute("DELETE FROM songs WHERE room=? AND title=?", (room, match))
            await ctx.respond(f'Deleted all songs called **{discord.utils.escape_markdown(title)}** '
                              f'from the {room} song pool.', allowed_mentions=NO_PINGS)

        @bot.slash_command(name='song_list', description=f'List the {room} song pool.', guild_ids=guild_ids)
        async def song_list(ctx):
            ''' Uploads the song pool to pastie.io, like ]song_list. '''
            # The upload can take longer than Discord waits for a reply.
            await ctx.defer()
            msg = f'No songs found for {room}.'

            song_exists = await db.execute("SELECT title, url FROM songs WHERE room=?", (room,))

            if song_exists:
                room_songs = {}
                for song in song_exists:
                    room_songs[song[0]] = song[1]

                header_text = monospace_table_row([('Song Title', 100),
                                                   ('Link', 25)])
                header_text += '\n' + '-'*146
                box_text = ''
                for s in sorted(room_songs.keys()):
                    box_text += monospace_table_row([(s, 100),
                                                     (room_songs[s], 25)])
                    box_text += '\n'

                paste_url = await pastie_upload(f'{header_text}\n{box_text}')
                msg = paste_url or 'Unable to generate song list at this time.'

            await ctx.respond(msg)

        @bot.slash_command(name='randsong', description=f'Play a random song from the {room} song pool.',
                           guild_ids=guild_ids)
        async def randsong(ctx):
            rows = await db.execute("SELECT title, url FROM songs WHERE room=?", (room,))
            if not rows:
                await ctx.respond(f'There are no songs in the {room} song pool!', ephemeral=True)
                return
            title, url = random.choice(rows)
            # The bare URL on its own line lets Discord show the video player.
            await ctx.respond(f'\U0001F3B5 **{discord.utils.escape_markdown(title)}**\n{url}',
                              allowed_mentions=NO_PINGS)

    def add_animanga_commands(self, bot):
        ''' AniList lookups, like ]anime, ]manga, ]randanime and ]randmanga. '''
        guild_ids = [const.DISCORD_TRIVIA_GUILD]
        anilist_man = self.ps_bot.anilist_man

        async def search(ctx, medium, title):
            await ctx.defer()
            series, error = await anilist_search_data(medium, title, anilist_man)
            if error:
                await ctx.respond(discord.utils.escape_markdown(error), allowed_mentions=NO_PINGS)
                return
            await ctx.respond(embed=series_embed(medium, series))

        async def random_series(ctx, medium, genres):
            genre_list, tag_list = parse_categories(genres)
            await ctx.defer()
            series, error = await anilist_rand_data(medium, anilist_man, genres=genre_list, tags=tag_list)
            if error:
                await ctx.respond(discord.utils.escape_markdown(error))
                return
            await ctx.respond(embed=series_embed(medium, series))

        @bot.slash_command(name='anime', description='Look up an anime on AniList.', guild_ids=guild_ids)
        async def anime(ctx, title: discord.Option(str, 'The anime to look up')):
            await search(ctx, 'anime', title)

        @bot.slash_command(name='manga', description='Look up a manga on AniList.', guild_ids=guild_ids)
        async def manga(ctx, title: discord.Option(str, 'The manga to look up')):
            await search(ctx, 'manga', title)

        # Discord allows at most 100 characters here.
        genre_help = 'AniList genres or tags to pick from; type them without spaces, e.g. "romance sliceoflife"'

        @bot.slash_command(name='randanime', description='Show a random anime.', guild_ids=guild_ids)
        async def randanime(ctx, genres: discord.Option(str, genre_help, required=False, default='')):
            await random_series(ctx, 'anime', genres)

        @bot.slash_command(name='randmanga', description='Show a random manga.', guild_ids=guild_ids)
        async def randmanga(ctx, genres: discord.Option(str, genre_help, required=False, default='')):
            await random_series(ctx, 'manga', genres)

    def add_mal_commands(self, bot):
        ''' MAL commands, like ]mal_add, ]mal and ]anotd, with links kept per Discord account. '''
        guild_ids = [const.DISCORD_TRIVIA_GUILD]
        mal_man = self.ps_bot.mal_man
        # Recently fetched lists: lowercase MAL name -> (time, lists).
        list_cache = {}

        def for_discord(msg, member):
            '''
            The MAL manager's messages name users by their mal_users key and
            mention ]commands; show the display name and /commands instead.
            '''
            return msg.replace(mal_key(member), member.display_name).replace(']mal', '/mal')

        async def profile_lists(member):
            '''
            Someone's whole anime and manga lists, as ]mal reads them.

            Returns:
                (mal_user, lists, error): lists maps 'anime' and 'manga' to their
                entries (None if that list is private). On failure, error says why.
            '''
            mal_user = await mal_man.mal_of_ps(mal_key(member))
            if not mal_user:
                return None, None, (f'{member.display_name} does not have a linked MAL account. '
                                    'They can link one with /mal_add.')

            cached = list_cache.get(mal_user.lower())
            if cached and time.time() - cached[0] < PROFILE_CACHE_TTL:
                return mal_user, cached[1], None

            lists = {}
            for medium in ('anime', 'manga'):
                code, entries = await mal_man.fetch_full_list(mal_user, medium)
                if code == 404:
                    mal_man.missing_accounts.add(list_table(mal_user))
                    return mal_user, None, (f"{mal_user} wasn't found on MAL. "
                                            "They may need to update their account with /mal_add.")
                if code == 403:
                    lists[medium] = None    # This list is private.
                elif entries is None:
                    return mal_user, None, MAL_DOWN_MSG
                else:
                    lists[medium] = entries

            if lists['anime'] is None and lists['manga'] is None:
                return mal_user, None, f"{mal_user}'s MAL lists are private, so their profile can't be shown."

            # Remember the NSFW ratings seen, which rolls and trivia also use.
            seen = [(medium, e['node']['id'], e['node']['title'], e['node'].get('nsfw', 'gray'))
                    for medium, entries in lists.items() if entries for e in entries]
            if seen:
                await mal_man.store_series(seen)

            list_cache[mal_user.lower()] = (time.time(), lists)
            return mal_user, lists, None

        def latest_update(lists):
            ''' (medium, entry) of the SFW series most recently updated, or None. '''
            recent = [(e.get('list_status', {}).get('updated_at', ''), medium, e)
                      for medium, entries in lists.items() if entries for e in entries
                      if e['node'].get('nsfw') == 'white']
            if not recent:
                return None
            _, medium, entry = max(recent, key=lambda r: r[0])
            return medium, entry

        async def profile_embed(member):
            ''' (embed, None) summarizing someone's MAL, or (None, why not). '''
            mal_user, lists, error = await profile_lists(member)
            if error:
                return None, error

            embed = discord.Embed(title=f"{mal_user}'s MAL", url=f'https://myanimelist.net/profile/{mal_user}',
                                  color=MAL_COLOR)
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)

            for medium, current, progress in (('anime', 'Watching', 'Episodes'),
                                              ('manga', 'Reading', 'Chapters')):
                entries = lists[medium]
                if entries is None:
                    value = 'Private'
                else:
                    stats = mal_man.list_stats(entries, medium)
                    value = (f'Completed: {stats["completed"]}\n{current}: {stats["current"]}\n'
                             f'{progress}: {stats["progress"]}\nMean score: {stats["mean"]}')
                    top = mal_man.top_rated(entries)
                    if top:
                        value += f'\nTop rated: {mal_link(medium, top["node"])}'
                embed.add_field(name=medium.title(), value=value[:1024])

            latest = latest_update(lists)
            if latest:
                medium, entry = latest
                node = entry['node']
                embed.description = f'Latest update: {mal_link(medium, node)}'
                pictures = node.get('main_picture') or {}
                picture = pictures.get('large') or pictures.get('medium')
                if picture:
                    embed.set_thumbnail(url=picture)
            return embed, None

        async def roll(ctx, member, media, anotd):
            msg = for_discord(await mal_man.user_rand_series(mal_key(member), media, anotd=anotd), member)
            if msg.startswith('rolled '):
                msg = f'{ctx.author.display_name} {msg}'
            await ctx.respond(discord.utils.escape_markdown(msg), allowed_mentions=NO_PINGS)

        @bot.slash_command(name='mal_add', description='Link your MyAnimeList account.', guild_ids=guild_ids)
        async def mal_add(ctx, username: discord.Option(str, 'Your MAL username')):
            await ctx.defer(ephemeral=True)
            msg = for_discord(await mal_man.set_user(mal_key(ctx.author), username.strip()), ctx.author)
            await ctx.respond(discord.utils.escape_markdown(msg), ephemeral=True, allowed_mentions=NO_PINGS)

        @bot.slash_command(name='mal', description="Show someone's MAL profile, or roll a series from their lists.",
                           guild_ids=guild_ids)
        async def mal(ctx,
                      user: discord.Option(discord.Member, 'Whose MAL (default: yours)',
                                           required=False, default=None),
                      roll_from: discord.Option(str, 'Roll a random series from these lists instead',
                                                name='roll', choices=['anime', 'manga', 'both'],
                                                required=False, default=None)):
            member = user or ctx.author
            await ctx.defer()
            if roll_from:
                media = ['anime', 'manga'] if roll_from == 'both' else [roll_from]
                await roll(ctx, member, media, anotd=False)
                return
            embed, error = await profile_embed(member)
            if error:
                await ctx.respond(discord.utils.escape_markdown(error), allowed_mentions=NO_PINGS)
                return
            await ctx.respond(embed=embed)

        @bot.slash_command(name='anotd', description="Roll anime of the day from someone's MAL, skipping banned series.",
                           guild_ids=guild_ids)
        async def anotd(ctx, user: discord.Option(discord.Member, 'Whose MAL (default: yours)',
                                                  required=False, default=None)):
            await ctx.defer()
            await roll(ctx, user or ctx.author, ['anime', 'manga'], anotd=True)

    async def start(self):
        # Discord being unavailable shouldn't take the Showdown bot down with it.
        token = os.getenv('DISCORD_TOKEN')
        try:
            try:
                await self.bot.start(token)
            except discord.errors.PrivilegedIntentsRequired:
                logger.warning('The Message Content Intent is not enabled for this bot in the '
                               'Discord Developer Portal; starting without it, so Discord trivia '
                               'answers cannot be read.')
                self.message_content = False
                self.bot = self.build_bot()
                await self.bot.start(token)
        except Exception:
            logger.exception('Discord bot stopped')


async def restart_process():
    '''
    Replaces the running bot with a fresh copy of itself (same PID, working
    directory, environment, and log), so code and package updates on disk
    take effect. Only returns if the relaunch fails.
    '''
    logger.info('Restarting the bot process.')

    # Trivia scores are otherwise only saved when a game ends.
    if BOT is not None:
        for room in BOT.roomlist.values():
            if room.trivia.active:
                try:
                    room.trivia.save_scores()
                except Exception:
                    logger.exception('Could not save trivia scores')
    if DISCORD_BOT is not None and DISCORD_BOT.trivia is not None and DISCORD_BOT.trivia.active:
        try:
            DISCORD_BOT.trivia.save_scores()
        except Exception:
            logger.exception('Could not save Discord trivia scores')

    # Log out of Showdown cleanly rather than just dropping the socket.
    if WS is not None:
        try:
            await asyncio.wait_for(WS.close(), timeout=5)
        except Exception:
            pass

    logging.shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(sys.executable, [sys.executable] + sys.argv)


BOT = None
DISCORD_BOT = None
async def start_bot():
    global BOT
    global DISCORD_BOT

    BOT = Bot()

    tasks = [asyncio.create_task(BOT.listener(PS_SOCKET), name='listener'),
             asyncio.create_task(BOT.interpreter(), name='interpreter'),
             asyncio.create_task(BOT.sender(), name='sender'),
             asyncio.create_task(BOT.start_repeats(), name='start-repeats')]

    if os.getenv('DISCORD_TOKEN'):
        DISCORD_BOT = DiscordBot(BOT)
        tasks.append(asyncio.create_task(DISCORD_BOT.start(), name='discord'))
    else:
        logger.info('DISCORD_TOKEN not set; skipping the Discord bot.')

    # Runs until the process is stopped.
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    setup_logging()
    dotenv.load_dotenv()

    asyncio.run(start_bot())