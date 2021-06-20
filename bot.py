import aiohttp
import argparse
import asyncio
import datetime
import discord
import json
import logging
import numpy as np
import os
import pandas as pd
import random
import re
import requests
import shlex
import time
import websockets

from discord.ext import commands
from dotenv import load_dotenv

import common.constants as const

from battle import Battle
from gacha import GachaManager
from commands import *
from common.mal import set_mal_user, show_mal_user, mal_user_rand_series, mal_search
from common.steam import set_steam_user, show_steam_user, steam_user_rand_series
from common.tcg import display_mtg_card, display_ptcg_card, display_ygo_card
from common.utils import find_true_name, gen_uhtml_img_code, trivia_leaderboard_msg
from room import Room
from trivia import check_answer
from user import User

PS_SOCKET = 'ws://sim.smogon.com:8000/showdown/websocket'
JOINLIST = [const.ANIME_ROOM,
            const.LEAGUE_ROOM,
            const.TCG_ROOM,
            const.VG_ROOM,
            const.PEARY_ROOM,
            const.GACHA_ROOM,
            const.SCHOL_ROOM,
            const.SPORTS_ROOM]
WS = None


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


def mal_arg_parser(s, caller):
    '''
    Parses a mal invocation as if it were CLI input.

    Args:
        s (str): input str
        caller (str): username of the person who invoked the command
    
    Returns:
        args (Namespace): contains the arguments as methods
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument('-r', '--roll', type=str, nargs='*')
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

def trivia_arg_parser(s):
    '''
    Parses a trivia start invocation as if it were CLI input.

    Args:
        s (str): input string

    Returns:
        args (Namespace): contains the arguments as methods.
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--categories', nargs='*', default=['all'])
    parser.add_argument('-cx', '--excludecats', action='store_true')
    parser.add_argument('-d', '--diff', type=int, default=3)
    parser.add_argument('-q', '--quizbowl', action='store_true')
    parser.add_argument('-r', '--byrating', action='store_true')
    parser.add_argument('-s', '--autoskip', type=int, default=15)
    parser.add_argument('len', type=int)

    args = None
    try:
        args = parser.parse_args(shlex.split(s))

        all_categories = ['all', 'mangadex'] + const.ANIME_TYPES + const.MANGA_TYPES + \
                         list(const.ANIME_GENRES.keys()) + list(const.MANGA_GENRES.keys()) + \
                         const.LEAGUE_CATS
        fixed_categories = []
        arg_categories = iter(args.categories)

        category = next(arg_categories, None)
        while category:
            category = find_true_name(category)

            if category in all_categories:
                fixed_categories.append(category)
                category = next(arg_categories, None)

            else:
                add_on = next(arg_categories, None)
                if add_on is None:
                    return

                category += add_on

        args.categories = fixed_categories
    # Incorrectly formatted input results in args = None
    except SystemExit:
        return
    except ValueError:
        return

    if args.excludecats and args.categories == ['all']:
        return

    return args


class Bot:
    def __init__(self):
        load_dotenv()
        self.username = os.getenv('PS_USERNAME')
        self.password = os.getenv('PS_PASSWORD')
        self.discord_token = os.getenv('DISCORD_TOKEN')
        self.birthdays = json.load(open(const.BIRTHDAYFILE))
        self.calendar = json.load(open(const.CALENDARFILE))
        self.sucklist = pd.read_csv(const.SUCKFILE)

        self.incoming = asyncio.Queue()
        self.outgoing = asyncio.Queue()

        self.roomlist = {}
        self.users = {}

        self.topics = json.load(open(const.TOPICFILE))
        self.banlists = json.load(open(const.BANLISTFILE))
        self.room_emotes = json.load(open(const.EMOTEFILE))

        self.battles = {}
        self.allow_laddering = False

        self.typers = {}
        self.wpms = pd.read_csv(const.WPMFILE, converters={'recent_runs': eval}).set_index('user')
        with open(const.SENTENCEFILE) as f:
            for i, _ in enumerate(f):
                pass
            self.num_typing_sentences = i+1

        self.gachaman = GachaManager()

        self.mal_rooms = [const.ANIME_ROOM, const.PEARY_ROOM]
        self.steam_rooms = [const.VG_ROOM, const.PEARY_ROOM]

        self.get_igdb_token()


    def reconnect(self, restart=True):
        '''
        Wrapper for reconnect calls from within the bot.
        '''
        start_bot(restart=restart, timer=10)


    async def monitor_discord(self):
        '''
        Spin up the discord connection to listen to manual restarts.
        '''
        discord_bot = DiscordBot()
        discord_bot.add_cog(DiscordReconnecter(discord_bot))
        await discord_bot.start(self.discord_token)


    def get_igdb_token(self):
        '''
        Gets IGDB access token.

        Args:
        '''
        payload = {'client_id': os.getenv('TWITCH_ID'),
                   'client_secret': os.getenv('TWITCH_SECRET'),
                   'grant_type': 'client_credentials'}

        r = requests.post('https://id.twitch.tv/oauth2/token', data=payload)

        igdb_info = json.loads(r.text)
        self.igdb_token = igdb_info['access_token']
        self.igdb_token_expire = time.time() + int(igdb_info['expires_in'])


    def check_igdb_token(self):
        '''
        Checks if IGDB access token has expired, and
        generates a new one if it has.

        Args:
        '''
        if time.time() > self.igdb_token_expire:
            self.get_igdb_token()


    async def start_repeats(self):
        '''
        Start the bot's repeating processes.

        Args:
        '''
        asyncio.create_task(self.ping_connect(), name='ping-connect')
        asyncio.create_task(self.birthday_repeater(), name='birthdays')
        asyncio.create_task(self.gacha_repeater(), name='gacha-repeat')
        asyncio.create_task(self.user_repeater(), name='user-repeat')


    async def ping_connect(self):
        '''
        Pings Showdown to check that messages are still flowing.

        Args:
        '''
        await asyncio.sleep(30)
        await self.outgoing.put(f'|/w {self.username}, ping')


    async def birthday_repeater(self):
        '''
        Repeating process for birthday display.
        
        Args:
        '''
        self.birthdays = json.load(open(const.BIRTHDAYFILE))
        while True:
            sleep_len = self.birthdays['next_time'] - time.time()

            if sleep_len < 0:
                sleep_len = 60 * 60 * 6

                self.birthdays['next_time'] = time.time() + sleep_len
                with open(const.BIRTHDAYFILE, 'w') as f:
                    json.dump(self.birthdays, f, indent=4)
  
            await asyncio.sleep(sleep_len)
            await self.send_birthday_text(automatic=True)

            self.birthdays = json.load(open(const.BIRTHDAYFILE))
            self.birthdays['next_time'] = time.time() + 60 * 60 * 6
            with open(const.BIRTHDAYFILE, 'w') as f:
                json.dump(self.birthdays, f, indent=4)


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

            await self.users[true_user]['event'].wait()
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
            for u in self.users:
                self.users[u]['group'] = None
                await self.get_userinfo(u)


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
                    sentence = l[:-1]
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
        try:
            async with websockets.connect(uri) as ws:
                # The same websocket is used to send info back.
                global WS
                WS = ws
                async for msg in ws:
                    await self.incoming.put(msg)
        except:
            self.reconnect()


    async def interpreter(self):
        '''
        Gets messages from the incoming queue and acts on them.

        Args:
        '''
        while True:
            msg = await self.incoming.get()

            print('Message: ')
            print(msg.encode('utf-8'))

            await self.message_handler(msg)


    async def message_handler(self, msg):
        '''
        Acts on websocket messages, depending on their contents.

        Args:
            msg (str): A message from the websocket
        '''

        curr_room = ''
        broken = msg.split('\n')
        if broken[0][0] == '>':
            curr_room = broken[0][1:]

        parts = msg.split('|')

        if len(parts) <= 1:
            print('!!! SEE THIS !!!')
            print(parts)
            return

        # Query Responses
        if parts[1] == 'queryresponse':
            print(parts)
            if parts[2] == 'userdetails':
                userinfo = json.loads(parts[3])
                true_name = userinfo['userid']
                self.users[true_name]['group'] = userinfo['group']
                self.users[true_name]['rooms'] = userinfo['rooms']
                self.users[true_name]['event'].set()

        # Managing room userlists
        if parts[1] == 'init' and 'chat' in parts[2]:
            userlist = parts[6].split(',')[1:]
            for user in userlist:
                rank = user[0]
                username = user[1:].split('@')[0]
                self.roomlist[curr_room].add_user(username, rank)
        
        if parts[1] == 'J':
            user = parts[2]
            rank = user[0]
            username = user[1:].split('@')[0]
            self.roomlist[curr_room].add_user(username, rank)

        elif parts[1] == 'L':
            user = parts[2]
            rank = user[0]
            username = user[1:].split('@')[0]
            self.roomlist[curr_room].remove_user(username)

        elif parts[1] == 'N':
            new_user = parts[2]
            rank = new_user[0]
            username = new_user[1:].split('@')[0]
            old_user = parts[3]
            self.roomlist[curr_room].remove_user(old_user)
            self.roomlist[curr_room].add_user(username, rank)

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

        # Login
        if parts[1] == 'challstr':
            print('Logging in...')
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
                self.wpms = self.wpms.append(wpminfo)
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
        elif (parts[1] == 'c:' or parts[1] == 'pm') and parts[4][0] == ']':
            is_pm = False
            caller = parts[3]
            if parts[1] == 'pm':
                is_pm = True
                caller = parts[2]
            asyncio.create_task(self.command_center(curr_room, caller, parts[4], pm=is_pm))

        # Trivia guesses
        elif parts[1] == 'c:':
            t_active = False
            try:
                t_active = self.roomlist[curr_room].trivia.active
            except AttributeError:
                pass
            
            # ]tg is/was also a valid invocation for guessing. This is a neat shortcut.
            if t_active:
                asyncio.create_task(self.command_center(curr_room, parts[3], ']tg {}'.format(parts[4])))


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

            elif parts[1] == 'error' and 'more choices than unfainted' in parts[2]:
                await self.act_in_battle(curr_room, one_poke=True)
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
            emote (str): The emote being invoked
        '''
        if room not in self.room_emotes or not User.compare_ranks(caller[0], '+'):
            return

        # Find emote
        possible_emotes = line.split(':')
        for pe in possible_emotes:
            emote = pe.lower()
            if emote in self.room_emotes[room]:
                self.room_emotes[room][emote]['times_used'] += 1
                json.dump(self.room_emotes, open(const.EMOTEFILE, 'w'), indent=4)

                uhtml = gen_uhtml_img_code(self.room_emotes[room][emote]['url'], height_resize=50, alt=emote)
                await self.outgoing.put(f'{room}|/adduhtml hippo-{emote}, {uhtml}')


    async def login(self, keyword):
        '''
        Performs the login dance with Showdown.

        Args:
            keyword (str): The challstr presented by showdown via websocket
        '''
        details = { 'act': 'login',
                    'name': self.username,
                    'pass': self.password,
                    'challstr': keyword
                    }

        async with aiohttp.ClientSession() as session:
            async with session.post('http://play.pokemonshowdown.com/action.php', json=details) as r:
                resp = await r.text()
                assertion = json.loads(resp[1:])['assertion']
                await self.outgoing.put('|/trn ' + self.username + ',0,'  + str(assertion))
                print('Sending assertion')


    async def login_check(self, name, logged_in):
        '''
        Sets up if login was successful, otherwise stops the bot.

        Args:
            name (str): Showdown username
            logged_in (bool): Whether or not login was successful
        '''
        print("Logged in as: " + name)

        if not logged_in:
            print("Not logged in.")
            self.reconnect()

        if re.sub(r'\W+', '', name) == re.sub(r'\W+', '', self.username):
            await self.outgoing.put('|/avatar 97')

            for room in JOINLIST:
                self.roomlist[room] = Room(room)
                await self.outgoing.put('|/join ' + room)


    def birthday_chars_to_uhtml(self, characters):
        '''
        Generates table-rows-html, given a list of characters and their info.

        Args:
            characters (list): list of character infos.
        '''
        num_chars = len(characters)
        display_len = 5
        if num_chars % 3 == 0 and (num_chars / 3) < 4:
            display_len = 3
        elif num_chars % 4 == 0 and (num_chars / 4) < 5:
            display_len = 4
        elif num_chars % 5 == 0 and (num_chars / 5) < 5:
            display_len = 5
        elif num_chars % 5 > 2:
            display_len = 5
        elif num_chars % 4 > 1:
            display_len = 4

        char_uhtml = '<tr>'
        for i, char in enumerate(characters):
            img_uhtml = ''
            char_url = ''
            if len(char) == 4:
                # MAL char formatting is [name, img suffix, MAL page suffix]
                img_uhtml = gen_uhtml_img_code(const.IMG_NOT_FOUND, height_resize=64, width_resize=64)
                if char[1]:
                    img_uhtml = gen_uhtml_img_code(f'{const.MAL_IMG_URL}{char[1]}', height_resize=64, width_resize=64)

                char_url = f'{const.MAL_URL}{char[3]}/{char[2]}'

            elif len(char) == 2:
                # A/M staff formatting is [name, img link]
                img_uhtml = f'<center><img src=\'{char[1]}\' width=64 height=64></center>'

            char_uhtml += (f'<td style=\'padding:5px\'>{img_uhtml}</td>'
                            '<td style=\'padding-right:5px; width:80px\'>'
                           f'<a href=\'{char_url}\' style=\'color:inherit\'>'
                           f'{char[0]}</a></td>')

            # Maximum of 3 characters per line
            if i % display_len == (display_len - 1):
                char_uhtml += '</tr><tr>'

        char_uhtml += '</tr>'

        return char_uhtml


    async def send_birthday_text(self, automatic, ctx=const.ANIME_ROOM):
        '''
        Sends a uhtml-formatted table of the current date's birthdays.

        Args:
            automatic (bool): Whether or not this was automatically scheduled.
            ctx (str): the context to send to.
        '''
        self.birthdays = json.load(open(const.BIRTHDAYFILE))
        today = datetime.datetime.today().strftime('%B %d').replace(' 0', ' ')
        short_today = datetime.datetime.today().strftime('%b %d').replace(' 0', ' ')
        birthday_chars = self.birthdays[today]

        if not birthday_chars:
            if not automatic:
                await self.outgoing.put(f'{ctx}|No known birthdays today! Submit birthdays here: https://forms.gle/qfKSeyNtpueTBACn7')
            return

        char_uhtml = self.birthday_chars_to_uhtml(birthday_chars)

        tomorrow_uhtml = ''
        curr_year = datetime.datetime.today().year

        max_scroll = ''
        if len(birthday_chars) > 15:
            max_scroll = 'overflow-y: scroll; max-height: 250px'

        if today == 'February 28' and (curr_year % 4 != 0 or curr_year % 100 == 0):
            tomorrow_uhtml = '<tr><td colspan=10><b><center>(Feb 29)</center></b></td></tr>'
            tomorrow_uhtml += self.birthday_chars_to_uhtml(self.birthdays['February 29'])

        uhtml = (f'<div style=\'{max_scroll}\'>'
                  '<center><table style=\'border:3px solid #0088cc; border-spacing:0px; '
                  'border-radius:10px; background-image:url(https://i.imgur.com/l8iJKoX.png); '
                  'background-size:cover\'>'
                  '<thead><tr><th colspan=10 style=\'padding:5px 5px 10px 5px\'>'
                 f'Today\'s Birthdays ({short_today})</th></tr></thead><tbody>'
                 f'{char_uhtml}'
                 f'{tomorrow_uhtml}'
                  '<tr><td colspan=10 style=\'text-align:right; font-size:8px; '
                  'padding: 0px 5px 5px 0px\'><a href=\'https://forms.gle/qfKSeyNtpueTBACn7\' '
                  'style=\'color:inherit\'>Submit characters here</a></td></tr>'
                  '</tbody></table></center></div>')

        await self.outgoing.put(f'{ctx}|/adduhtml hippo-birthdays, {uhtml}')


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
        cover = game_info['cover']
        name = game_info['name']
        summary = game_info['summary']
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
        for rd in game_info['release_dates']:
            platform = ''
            for p in game_info['platforms']:
                if p['id'] == rd['platform']:
                    try:
                        platform = p['abbreviation']
                    except KeyError:
                        platform = p['name']
                    break

            unix_ts = rd['date']
            year = datetime.datetime.utcfromtimestamp(unix_ts).strftime('%Y')

            platform_rds[platform] = year

        rd_str = ''
        for p in platform_rds:
            rd = platform_rds[p]
            rd_str += f'{p} ({rd}); '

        cover = 'https:' + cover['url']

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

        if command[0] != ']' or command == ']':
            return

        command = command[1:].split()

        if not command:
            return

        userinfo = await self.get_userinfo(true_caller)
        userrank = userinfo['group']
        if not pm:
            for r in userinfo['rooms']:
                if r[1:] == room:
                    if User.compare_ranks(room[0], userrank):
                        userrank = room[0]
                    break


        cmd_kwargs = {'full_command': command,
                      'room': room,
                      'caller': caller,
                      'true_caller': true_caller,
                      'caller_rank': userrank,
                      'is_pm': pm,
                      'pm_only': False,
                      'room_only': False,
                      'min_args': -1,
                      'max_args': 9999,
                      'usage_msg': '',
                      'req_rank': ' ',
                      'allowed_rooms': list(self.roomlist)}

        # General commands
        if command[0] in const.SIMPLE_COMMANDS:
            cmd_obj = SimpleCommand(**cmd_kwargs)
            msg = cmd_obj.evaluate()

        elif command[0] == 'plebs' and User.compare_ranks(caller[0], '+'):
            uhtml = gen_uhtml_img_code(const.PLEB_URL, height_resize=250)
            msg = f'/adduhtml hippo-pleb, {uhtml}'

        elif command[0] == 'calendar' and User.compare_ranks(caller[0], '+'):
            curr_day = datetime.date.today()
            curr_day_str = curr_day.strftime('%B') + ' ' + str(curr_day.day)
            date_imgs = self.calendar[curr_day_str]

            uhtml = gen_uhtml_img_code(random.choice(date_imgs), height_resize=200)
            msg = f'/adduhtml hippo-calendar, {uhtml}'
        
        elif command[0] == 'birthday' and not pm and User.compare_ranks(caller[0], '+'):
            await self.send_birthday_text(automatic=False, ctx=room)

        elif command[0] == 'topic' and not pm:
            if room not in self.topics:
                self.topics[room] = {}
            
            if 'current' not in self.topics[room]:
                self.topics[room]['current'] = ''

            if len(command) > 1 and User.compare_ranks(caller[0], '%'):
                self.topics[room]['current'] = ' '.join(command[1:])

            curr_topic = self.topics[room]['current']
            if not curr_topic:
                msg = '/announce No topic right now! Feel free to set one.'
            else:
                msg = f'/announce {curr_topic}'

            json.dump(self.topics, open(const.TOPICFILE, 'w'), indent=4)

        # Banlists
        elif command[0] == 'bl_add':
            if len(command) != 3:
                await self.outgoing.put(f'{room}|Invalid syntax. Use ]bl_add category, item_to_ban')
                return

            has_perms = False
            list_name = find_true_name(command[1])
            if pm:
                if list_name == 'anime' or list_name == 'manga':
                    user_info = self.roomlist[const.ANIME_ROOM].get_user(caller)
                    room_rank = ' '
                    if user_info:
                        room_rank = user_info.rank

                    if User.compare_ranks(room_rank, '%') or User.compare_ranks(caller[0], '%'):
                        has_perms = True
            else:
                if list_name == 'anime' or list_name == 'manga' and room in self.mal_rooms:
                    if User.compare_ranks(caller[0], '%'):
                        has_perms = True

            if has_perms:
                try:
                    to_bl = int(command[2])
                except ValueError:
                    await self.outgoing.put(f'{room}|Please use the MAL id number of the series to banlist.')
                    return

                if to_bl in self.banlists[list_name]:
                    await self.outgoing.put(f'{room}|Series already on banlist.')
                    return

                async with aiohttp.ClientSession() as session:
                    async with session.get(f'{const.JIKAN_API}{list_name}/{to_bl}') as r:
                        resp = await r.text()

                        if r.status != 200:
                            await self.outgoing.put(f'{room}|Invalid MAL series.')
                            return
                        
                        self.banlists[list_name].append(to_bl)
                        with open(const.BANLISTFILE, 'w') as f:
                            json.dump(self.banlists, f, indent=4)
                        
                msg = f'Added {to_bl} to {list_name} banlist.'

        elif command[0] == 'bl_remove':
            if len(command) != 3:
                await self.outgoing.put(f'{room}|Invalid syntax. Use ]bl_remove category, item_to_unbl')
                return

            has_perms = False
            list_name = find_true_name(command[1])
            if pm:
                if list_name == 'anime' or list_name == 'manga':
                    user_info = self.roomlist[const.ANIME_ROOM].get_user(caller)
                    room_rank = ' '
                    if user_info:
                        room_rank = user_info.rank

                    if User.compare_ranks(room_rank, '%') or User.compare_ranks(caller[0], '%'):
                        has_perms = True
            else:
                if list_name == 'anime' or list_name == 'manga' and room in self.mal_rooms:
                    if User.compare_ranks(caller[0], '%'):
                        has_perms = True

            if has_perms:
                try:
                    to_bl = int(command[2])
                except ValueError:
                    await self.outgoing.put(f'{room}|Please enter the MAL id number of the series to un-banlist.')
                    return

                if to_bl in self.banlists[list_name]:
                    self.banlists[list_name].remove(to_bl)
                    with open(const.BANLISTFILE, 'w') as f:
                        json.dump(self.banlists, f, indent=4)
                    msg = 'Removed series from banlist.'
                else:
                    msg = 'Series not on banlist.'

        elif command[0] == 'bl_list':
            if len(command) != 2:
                await self.outgoing.put(f'{room}|Invalid syntax. Use ]bl_list category')
                return

            has_perms = False
            list_name = find_true_name(command[1])
            if pm:
                if list_name == 'anime' or list_name == 'manga':
                    user_info = self.roomlist[const.ANIME_ROOM].get_user(caller)
                    room_rank = ' '
                    if user_info:
                        room_rank = user_info.rank

                    if User.compare_ranks(room_rank, '%') or User.compare_ranks(caller[0], '%'):
                        has_perms = True
            else:
                if list_name == 'anime' or list_name == 'manga' and room in self.mal_rooms:
                    if User.compare_ranks(caller[0], '%'):
                        has_perms = True

            if not pm:
                pm = True
                room = ''

            msg = 'Category not found.'
            if list_name in self.banlists and has_perms:
                msg = f'{list_name} banlist: {json.dumps(self.banlists[list_name])}'

        # Emotes
        elif (command[0] == 'emote_set' or command[0] == 'emote_add') and User.compare_ranks(caller[0], '#'):
            # Args: set_emote emote, url
            if len(command) != 3:
                await self.outgoing.put(f'{room}|Invalid syntax. Use ]emote_set emote, url')
                return
            emote = command[1].lower()
            if emote.endswith(','):
                emote = emote[:-1]
            if find_true_name(emote) != emote:
                await self.outgoing.put(f'{room}|Invalid syntax. Use ]emote_set emote, url')
                return

            if room not in self.room_emotes:
                self.room_emotes[room] = {}

            emote_url = command[2]
            if 'discordapp' in emote_url:
                await self.outgoing.put(f'{room}|Please no discord URLs.')
                return

            self.room_emotes[room][emote] = {'times_used': 0, 'url': emote_url}

            with open(const.EMOTEFILE, 'w') as f:
                json.dump(self.room_emotes, f, indent=4)

            msg = f'Set :{emote}: to show {emote_url}.'

        elif command[0] == 'emote_del' and User.compare_ranks(caller[0], '#'):
            # Args: del_emote emote
            if len(command) != 2:
                await self.outgoing.put(f'{room}|Invalid syntax. Use ]emote_del emote')
                return

            emote = command[1].lower()

            msg = f'Did not find {emote} emote.'
            if room in self.room_emotes:
                if emote in self.room_emotes[room]:
                    del self.room_emotes[room][emote]

                    with open(const.EMOTEFILE, 'w') as f:
                        json.dump(self.room_emotes, f, indent=4)

                    msg = f'Removed {emote} from room emotes.'

        elif command[0] == 'emote_list':
            msg = 'No emotes found.'
            if len(command) > 1:
                room = ''.join(command[1:])
            if room in self.room_emotes:
                if len(self.room_emotes[room]) >= 1:
                    msg = f'!code {room} emotes: ' + ', '.join(self.room_emotes[room])

        # Typing test
        elif command[0] == 'typing_test':
            asyncio.create_task(self.wpm(true_caller), name='wpm-{}'.format(true_caller))
            return

        elif command[0] == 'wpm_top':
            metric = 'avg_wpm'
            metric_title = '(Last 5 Runs Avg.)'
            if len(command) > 1:
                if command[1] == '-s' or command[1] == '--single':
                    metric = 'top_wpm'
                    metric_title = '(Single Run)'

            wpmboard = self.wpms.sort_values(metric, ascending=False)
            if metric == 'avg_wpm':
                wpmboard = wpmboard[wpmboard['recent_runs'].map(len) >= 5]
            wpmboard = wpmboard.reset_index().head(n=5)[['user', metric]].values.tolist()

            msg = trivia_leaderboard_msg(wpmboard, f'Fastest WPM {metric_title}', name='wpmboard', metric='WPM')
            if pm:
                msg = "This command is not supported in PMs."

        elif command[0] == 'wpm_reset':
            try:
                wpminfo = self.wpms.loc[true_caller]
            except KeyError:
                pass
            else:
                self.wpms.loc[true_caller, ['top_wpm', 'avg_wpm', 'recent_runs']] = 0, 0, []
                self.wpms.to_csv(const.WPMFILE)
            msg = f'Reset {caller}\'s typing speed record to 0 WPM.'

        elif command[0] == 'wpm':
            wpm_user = caller
            true_wpm_user = true_caller
            if len(command) > 1:
                wpm_user = ' '.join(command[1:])
                true_wpm_user = find_true_name(wpm_user)
            
            try:
                wpminfo = self.wpms.loc[true_wpm_user]
            except KeyError:
                msg = f'{wpm_user} has not taken a typing test.'
            else:
                top_wpm = wpminfo['top_wpm']
                avg_wpm = wpminfo['avg_wpm']
                run_count = len(wpminfo['recent_runs'])
                msg = f'{wpm_user} - Top speed: {top_wpm} WPM. Average of past {run_count} runs: {avg_wpm} WPM.'

        # animeandmanga
        elif command[0] == 'anime' and room == const.ANIME_ROOM and User.compare_ranks(caller[0], '+'):
            if len(command) > 1:
                query = ' '.join(command[1:])
                asyncio.create_task(mal_search(self.outgoing.put, const.ANIME_ROOM, 'anime', query))

        elif command[0] == 'manga' and room == const.ANIME_ROOM and User.compare_ranks(caller[0], '+'):
            if len(command) > 1:
                query = ' '.join(command[1:])
                asyncio.create_task(mal_search(self.outgoing.put, const.ANIME_ROOM, 'manga', query))

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

        # MAL
        elif command[0] == 'addmal' and (room in self.mal_rooms or pm):
            if len(command) > 1:
                ctx = room
                if pm:
                    ctx = 'pm'
                asyncio.create_task(set_mal_user(self.outgoing.put, true_caller, command[1], ctx),
                                    name='setmal-{}'.format(true_caller))
            else:
                msg = 'Usage: ]addmal [MYANIMELIST USERNAME]'
        
        elif command[0] == 'mal' and (room in self.mal_rooms or pm):
            args = None

            to_parse = ''
            if len(command) > 1:
                to_parse = ' '.join(command[1:])
            args = mal_arg_parser(to_parse, true_caller)
            
            if args:
                args.username = find_true_name(' '.join(args.username))
            else:
                await self.outgoing.put(room + '| Incorrect formatting.')
                return

            mal_list = pd.read_csv(const.MALFILE)
            existing_user = mal_list[mal_list['user'] == args.username]
            if existing_user.empty:
                msg = 'This user does not have a MAL set. Please use ]addmal to set a valid account.'
            else:
                ctx = room
                if pm:
                    ctx = 'pm'
                mal_user = existing_user.iloc[0]['mal']

                if args.roll is not None:
                    if args.roll == []:
                        args.roll = ['anime', 'manga']

                    asyncio.create_task(mal_user_rand_series(self.outgoing.put, mal_user,
                                                             caller, args.roll, ctx),
                                        name='randmal-{}'.format(args.username))
                else:
                    if not (User.compare_ranks(caller[0], '+')):
                        ctx = 'pm'
                    asyncio.create_task(show_mal_user(self.outgoing.put, mal_user, true_caller, ctx),
                                        name='showmal-{}'.format(args.username))

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
                await self.outgoing.put(room + '| Incorrect formatting.')
                return

            steam_list = pd.read_csv(const.STEAMFILE)
            existing_user = steam_list[steam_list['user'] == args.username]
            if existing_user.empty:
                msg = 'This user does not have a Steam set. Please use ]addsteam to set a valid account. Make sure to use the URL ID and not the Steam username.'
            else:
                ctx = room
                if pm:
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
                search = ' '.join(command[1:])
                self.check_igdb_token()

                headers = {'Client-ID': os.getenv('TWITCH_ID'),
                        'Authorization': f'Bearer {self.igdb_token}'}
                data = (f'search "{search}"; fields cover.url, name, '
                         'release_dates.*, platforms.*, summary, url; '
                         'where themes != (42);')

                async with aiohttp.ClientSession(headers=headers) as session:
                    r = await session.post(const.IGDB_API + 'games', data=data)

                    resp = await r.text()
                    if r.status != 200:
                        print(f'IGDB query failed on {data}: code {r.status}')
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
                    msg = trivia_leaderboard_msg(suckboard, 'Suckiest', name='suckboard')

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
                    self.sucklist = self.sucklist.append(suckinfo)
                
                # There's a global cooldown of a random number between
                # 15 and 90 minutes.
                end_time = self.sucklist.loc[self.sucklist['user'] == const.TIMER_USER, 'count'][0]
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
                    (User.compare_ranks(caller[0], '+') or true_caller == const.OWNER)):

                args = None
                if len(command) > 2:
                    args = trivia_arg_parser(' '.join(command[2:]))

                if args:
                    if args.quizbowl and room == const.LEAGUE_ROOM:
                        args.quizbowl = None
                    if not args.quizbowl and room == const.SCHOL_ROOM:
                        args.quizbowl = True
                    if command[0] == 'anagrams':
                        if args.quizbowl:
                            args.quizbowl = None
                        args.categories.append('anagrams')
                        if args.autoskip == 15:
                            args.autoskip = 45
                if not args:
                    msg = 'Invalid parameters. Trivia not started.'
                elif args.quizbowl:
                    msg = 'Starting a round of quizbowl with {} questions. ' \
                          'Type your answers to guess!'.format(args.len)
                    asyncio.create_task(self.roomlist[room].quizbowl_game(self.outgoing.put,
                                                                          self.incoming.put,
                                                                          args.len,
                                                                          args.diff,
                                                                          args.categories,
                                                                          args.excludecats,
                                                                          args.byrating,
                                                                          args.autoskip),
                                        name='trivia-{}'.format(room))
                else:
                    msg = 'Starting a round of trivia with {} questions, with a ' \
                          '{} second timer. Type your answers to guess!'.format(args.len, args.autoskip)
                    asyncio.create_task(self.roomlist[room].trivia_game(self.outgoing.put,
                                                                        self.incoming.put,
                                                                        args.len,
                                                                        args.diff,
                                                                        args.categories,
                                                                        args.excludecats,
                                                                        args.byrating,
                                                                        args.autoskip),
                                        name='trivia-{}'.format(room))
            elif (command[1] == 'stop' or command[1] =='end') and User.compare_ranks(caller[0], '+'):
                if trivia_status:
                    for task in asyncio.all_tasks():
                        if task.get_name() == 'trivia-{}'.format(room):
                            task.cancel()
                            break
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
                msg = trivia_leaderboard_msg(trivia_game.leaderboard(n=to_show), title)
            elif command[1] == 'skip' and User.compare_ranks(caller[0], '+'):
                if trivia_game.active and trivia_game.answers:
                    answer = trivia_game.answers[-1]

                    trivia_game.correct.set()
                    trivia_game.answers = []
                    await trivia_game.skip(self.outgoing.put)

                    msg = 'Skipping question. A correct answer would have been {}.'.format(answer)

        elif command[0] == 'tg' and not pm:
            trivia_game = self.roomlist[room].trivia
            if trivia_game.active:
                answer_check = ''
                # Anime/manga/video game titles have a lot of different colloquial names.
                # Those rooms are more flexible in accepting answers.
                is_exact = False if room in [const.ANIME_ROOM, const.VG_ROOM, const.SCHOL_ROOM] else True
                is_exact = True if self.roomlist[room].trivia.anagrams else is_exact
                answer_check = check_answer(''.join(command[1:]), trivia_game.answers, exact=is_exact)

                if answer_check:
                    msg = f'{caller} wins.'
                    if true_caller == self.username:
                        if '/uhtml' in ''.join(command):
                            return
                        msg = 'Question skipped.'
                    else:
                        trivia_game.update_scores(true_caller)

                    msg += f' The answer was {answer_check}.'

                    trivia_game.correct.set()
                    trivia_game.answers = []

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
                msg = self.gachaman.player_box(true_caller)

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

        elif command[0] == 'test' and true_caller == const.OWNER:
            await self.outgoing.put('|/cmd userdetails hippopotas')
            return

        if msg == '':
            return

        if pm:
            msg = '/w {}, '.format(true_caller) + msg
        await self.outgoing.put(room + '|' + msg)


    async def sender(self):
        '''
        Sends messages destined for Showdown.

        Args:
        '''
        try:
            while True:
                msg = await self.outgoing.get()

                print('Sending: ')
                print(msg)
                await WS.send(msg)
                await asyncio.sleep(0.1)
        except:
            self.reconnect()


class DiscordBot(discord.ext.commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.reactions = True
        intents.messages = True

        super().__init__(command_prefix=']', intents=intents)
        self.logger = logging.getLogger('discord')

    async def on_ready(self):
        self.logger.info(f'Client logged in as {self.user}.')

    def reconnect(self):
        start_bot()


class DiscordReconnecter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(brief='Forces the PS bot to reconnect.')
    @commands.has_any_role('Moderator', 'Owner', 'Driver')
    @commands.guild_only()
    async def restart_ps(self, ctx):
        await ctx.message.add_reaction('👀')
        self.bot.reconnect()


def start_bot(restart=True, timer=0):
    loop = asyncio.get_event_loop()

    if restart:
        for task in asyncio.all_tasks():
            task.cancel()

    print(f'Restarting. Waiting {timer} seconds...')
    time.sleep(timer)

    loop.set_debug(True)
    bot = Bot()

    asyncio.set_event_loop(loop)
    loop.create_task(bot.listener(PS_SOCKET))
    loop.create_task(bot.interpreter())
    loop.create_task(bot.sender())
    loop.create_task(bot.start_repeats())
    loop.create_task(bot.monitor_discord())
    loop.run_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    start_bot(restart=False)