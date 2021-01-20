import aiohttp
import argparse
import asyncio
import datetime
import json
import numpy as np
import os
import pandas as pd
import random
import re
import shlex
import time
import websockets

from dotenv import load_dotenv

from battle import Battle
from constants import ANIME_ROOM, LEAGUE_ROOM, VG_ROOM, PEARY_ROOM
from constants import ANIME_GENRES, MANGA_GENRES, ANIME_TYPES, MANGA_TYPES, LEAGUE_CATS
from constants import JIKAN_API, DDRAGON_API, DDRAGON_IMG, DDRAGON_SPL
from constants import TIMER_USER, OWNER
from constants import METRONOME_BATTLE
from constants import PLEB_URL
from user import User, set_mal_user, show_mal_user, mal_user_rand_series, set_steam_user, show_steam_user
from room import Room, trivia_leaderboard_msg
from trivia import gen_uhtml_img_code

PS_SOCKET = 'ws://sim.smogon.com:8000/showdown/websocket'
JOINLIST = [ANIME_ROOM, LEAGUE_ROOM, VG_ROOM, PEARY_ROOM]
WS = None
SUCKFILE = 'suck.txt'
CALENDARFILE = 'calendar.txt'

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
    parser.add_argument('-r', '--roll', type=bool, default=False)
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
    parser.add_argument('-r', '--byrating', action='store_true')
    parser.add_argument('-s', '--autoskip', type=int, default=20)
    parser.add_argument('len', type=int)

    args = None
    try:
        args = parser.parse_args(shlex.split(s))

        all_categories = ['all'] + ANIME_TYPES + MANGA_TYPES + \
                         list(ANIME_GENRES.keys()) + list(MANGA_GENRES.keys()) + \
                         LEAGUE_CATS
        fixed_categories = []
        arg_categories = iter(args.categories)

        category = next(arg_categories, None)
        while category:
            category = User.find_true_name(category)

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


def check_answer(guess, answers):
    '''
    Checks if a guess is correct for a trivia question.

    Args:
        guess (str): The raw guess
        answers (str list): Base list of acceptable answers 
    
    Returns:
        An empty string if the guess is incorrect, else the matching answer
        from answers.
    '''
    t_guess = User.find_true_name(guess)

    for answer in answers:
        t_answer = User.find_true_name(answer)
        if t_guess == t_answer:
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
            acceptable.append(User.find_true_name(prefix))

        if t_guess in acceptable:
            return answer

    return ''


class Bot:
    def __init__(self):
        load_dotenv()
        self.username = os.getenv('PS_USERNAME')
        self.password = os.getenv('PS_PASSWORD')
        self.calendar = json.load(open(CALENDARFILE))
        self.sucklist = pd.read_csv(SUCKFILE)

        self.incoming = asyncio.Queue()
        self.outgoing = asyncio.Queue()

        self.roomlist = {}
        self.battles = {}

        self.allow_laddering = True

        self.mal_rooms = [ANIME_ROOM, PEARY_ROOM]
        self.steam_rooms = [VG_ROOM, PEARY_ROOM]


    async def listener(self, uri):
        '''
        Puts messages from the websocket into the incoming queue.

        Args:
            uri (str): websocket to connect to
        '''
        async with websockets.connect(uri) as ws:
            # The same websocket is used to send info back.
            global WS
            WS = ws
            async for msg in ws:
                await self.incoming.put(msg)


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
            parts = parts[0:4] + ['|'.join(parts[4:])]

        # Login
        if parts[1] == 'challstr':
            print('Logging in...')
            await self.login(parts[2] + "|" + parts[3])
        elif parts[1] == 'updateuser':
            await self.login_check(parts[2], parts[3])

        # Function calls from chat
        elif (parts[1] == 'c:' or parts[1] == 'pm') and parts[4][0] == ']':
            is_pm = False
            caller = parts[3]
            if parts[1] == 'pm':
                is_pm = True
                caller = parts[2]
            await self.command_center(curr_room, caller, parts[4], pm=is_pm)

        # Trivia guesses
        elif parts[1] == 'c:':
            t_active = False
            try:
                t_active = self.roomlist[curr_room].trivia.active
            except AttributeError:
                pass
            
            # ]tg is/was also a valid invocation for guessing. This is a neat shortcut.
            if t_active:
                await self.command_center(curr_room, parts[3], ']tg {}'.format(parts[4]))


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
        true_challenger = User.find_true_name(challenger)

        for battle in self.battles:
            if true_challenger in self.battles[battle].players:
                return
        
        if battle_format == METRONOME_BATTLE:
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
                team = Battle.make_team(METRONOME_BATTLE)
                await self.outgoing.put(f'|/utm {team}\n/search {METRONOME_BATTLE}')

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
            raise Exception("Not logged in.")
            asyncio.get_running_loop.close()

        if re.sub(r'\W+', '', name) == re.sub(r'\W+', '', self.username):
            await self.outgoing.put('|/avatar 97')

            for room in JOINLIST:
                self.roomlist[room] = Room(room)
                await self.outgoing.put('|/join ' + room)


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
        true_caller = User.find_true_name(caller)

        if command[0] != ']' or command == ']':
            return

        command = command[1:].split()

        if not command:
            return

        # General commands
        if command[0] == 'help':
            msg = 'o3o https://pastebin.com/raw/LxnMv5hA o3o'
        elif command[0] == 'dab':
            msg = '/me dabs'
        elif command[0] == 'owo':
            msg = 'uwu'
        elif command[0] == 'google':
            msg = 'Don\'t be mad someone is faster at googling than you :3c'
        elif command[0] == 'joogle':
            msg = 'Don\'t be mad someone is faster at joogling than you :3c'
        elif command[0] == 'bing':
            msg = 'Have you heard of google?'
        elif command[0] == 'jing':
            msg = 'Have you heard of joogle?'
        
        elif command[0] == 'plebs' and User.compare_ranks(caller[0], '+'):
            uhtml = gen_uhtml_img_code(PLEB_URL, height_resize=250)
            msg = f'/adduhtml hippo-pleb, {uhtml}'

        elif command[0] == 'calendar':
            curr_day = datetime.date.today()
            curr_day_str = curr_day.strftime('%B') + ' ' + str(curr_day.day)
            date_imgs = self.calendar[curr_day_str]

            uhtml = gen_uhtml_img_code(random.choice(date_imgs), height_resize=200)
            msg = f'/adduhtml hippo-calendar, {uhtml}'

        # animeandmanga
        elif command[0] == 'jibun' and room == ANIME_ROOM:
            msg = '/announce JIBUN WOOOOOOOOOO'

        # MAL
        elif command[0] == 'addmal' and (room in self.mal_rooms or pm):
            if len(command) > 1:
                ctx = room
                if pm:
                    ctx = 'pm'
                asyncio.create_task(set_mal_user(self.outgoing.put, true_caller, command[1], ctx),
                                    name='setmal-{}'.format(true_caller))
            else:
                msg = 'Please enter an MAL username.'
        
        elif command[0] == 'mal' and (room in self.mal_rooms or pm):
            args = None

            to_parse = ''
            if len(command) > 1:
                to_parse = ' '.join(command[1:])
            args = mal_arg_parser(to_parse, true_caller)
            
            if args:
                args.username = User.find_true_name(' '.join(args.username))
            else:
                await self.outgoing.put(room + '| Incorrect formatting.')
                return

            mal_list = pd.read_csv('mal.txt')
            existing_user = mal_list[mal_list['user'] == args.username]
            if existing_user.empty:
                msg = 'This user does not have a MAL set. Please set a valid account using ]addmal'
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
                args.username = User.find_true_name(' '.join(args.username))
            else:
                await self.outgoing.put(room + '| Incorrect formatting.')
                return

            steam_list = pd.read_csv('steam.txt')
            existing_user = steam_list[steam_list['user'] == args.username]
            if existing_user.empty:
                msg = 'This user does not have a Steam set. Please set a valid account using ]addsteam'
            else:
                ctx = room
                if pm:
                    ctx = 'pm'
                steam_user = existing_user.iloc[0]['steam']

                if args.roll:
                    msg = 'Coming soon TM'
                else:
                    asyncio.create_task(show_steam_user(self.outgoing.put, steam_user, true_caller, ctx),
                                        name='showsteam-{}'.format(args.username))

        # Suck
        elif command[0] == 'suck':
            scount = 0
            suckinfo = self.sucklist[self.sucklist['user'] == true_caller]
            if len(command) > 1:
                if command[1] == 'top' and not pm:
                    suckboard = self.sucklist.sort_values('count', ascending=False)
                    suckboard = suckboard[suckboard['user'] != TIMER_USER].head(n=5).values.tolist()
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
                end_time = self.sucklist.loc[self.sucklist['user'] == TIMER_USER, 'count'][0]
                if time.time() > end_time:
                    self.sucklist.loc[self.sucklist['user'] == true_caller, 'count'] += 1
                    scount = int(suckinfo['count'].iat[0] + 1)
                    self.sucklist.loc[self.sucklist['user'] == TIMER_USER, 'count'] = time.time() + random.randint(60*5, 60*30)
                else:
                    self.sucklist.loc[self.sucklist['user'] == true_caller, 'count'] = 0
                    scount = 0

                msg = '{} has sucked {} times.'.format(caller, str(scount))

            self.sucklist.to_csv(SUCKFILE, index=False)

        
        # Trivia
        elif command[0] == 'trivia' and not pm:
            if len(command) < 2:
                return

            trivia_game = self.roomlist[room].trivia
            trivia_status = trivia_game.active

            if (command[1] == 'start' and not trivia_status and
                    User.compare_ranks(caller[0], '%')):

                args = None
                if len(command) > 2:
                    args = trivia_arg_parser(' '.join(command[2:]))
                
                if not args:
                    msg = 'Invalid parameters. Trivia not started.'
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
            elif (command[1] == 'stop' or command[1] =='end') and User.compare_ranks(caller[0], '%'):
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

                # Persistent trivia scores are disabled in animeandmanga.
                if room == ANIME_ROOM or room == VG_ROOM:
                    return

                if len(command) > 2:
                    user, score = trivia_game.userscore(User.find_true_name(''.join(command[2:])))
                else:
                    user, score = trivia_game.userscore(User.find_true_name(caller))

                if user is None:
                    msg = 'User not found.'
                else:
                    msg = '{} has {} points in trivia games here.'.format(user, score)
            elif command[1] == 'leaderboard':
                to_show = 5
                if len(command) > 2:
                    if is_int_str(command[2]):
                        to_show = int(command[2])

                title = 'Semi-weekly Trivia Leaderboard'
                if room == ANIME_ROOM or room == VG_ROOM:
                    title = 'No leaderboard for this room.'
                msg = trivia_leaderboard_msg(trivia_game.leaderboard(n=to_show), title)
            elif command[1] == 'skip' and User.compare_ranks(caller[0], '%'):
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
                if room == ANIME_ROOM or room == VG_ROOM:
                    answer_check = check_answer(''.join(command[1:]), trivia_game.answers)
                else:
                    for answer in trivia_game.answers:
                        if User.find_true_name(answer) == User.find_true_name(''.join(command[1:])):
                            answer_check = answer
                            break
                if answer_check:
                    msg = f'{caller} wins.'
                    if true_caller == self.username:
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
        
        elif command[0] == 'ladder_toggle' and true_caller == OWNER:
            self.allow_laddering = not self.allow_laddering
            # Refreshes updatesearch as well.
            await self.outgoing.put('|/cancelsearch')

            msg = f'Laddering is now {self.allow_laddering}.'


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
        while True:
            msg = await self.outgoing.get()

            print('Sending: ')
            print(msg)
            await WS.send(msg)
            await asyncio.sleep(0.1)

    
if __name__ == "__main__":

    loop = asyncio.get_event_loop()
    loop.set_debug(True)

    while True:
        bot = Bot()

        try:
            loop.run_until_complete(asyncio.wait((bot.listener(PS_SOCKET), bot.interpreter(), bot.sender())))
        except:
            # Useful for debugging, since I can't figure out how else
            # to make async stuff return the actual error.
            import traceback
            traceback.print_exc()
        finally:
            loop.close()

        time.sleep(30)