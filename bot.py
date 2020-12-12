import aiohttp
import argparse
import asyncio
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

from constants import ANIME_ROOM, LEAGUE_ROOM, VG_ROOM
from constants import JIKAN_API, DDRAGON_API, DDRAGON_IMG, DDRAGON_SPL
from constants import TIMER_USER
from user import User, set_mal_user, show_mal_user, mal_user_rand_series
from room import Room, trivia_leaderboard_msg

PS_SOCKET = 'ws://sim.smogon.com:8000/showdown/websocket'
USERNAME = ''
PASSWORD = ''
JOINLIST = [ANIME_ROOM, LEAGUE_ROOM, VG_ROOM]
SUCKLIST = {}
ROOMLIST = {}
WS = None

INCOMING = None
OUTGOING = None


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
    parser.add_argument('-d', '--diff', type=int, default=3)
    parser.add_argument('-p', '--points', type=int, default=1)
    parser.add_argument('-r', '--byrating', action='store_true')
    parser.add_argument('-s', '--autoskip', type=int, default=0)
    parser.add_argument('len', type=int)

    args = None
    try:
        args = parser.parse_args(shlex.split(s))

    # Incorrectly formatted input results in args = None
    except SystemExit:
        pass

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


async def listener(putter, uri):
    '''
    Puts messages from the websocket into the incoming queue.

    Args:
        putter (method): Queue.put for the relevant queue
        uri (str): websocket to connect to
    '''
    async with websockets.connect(uri) as ws:
        # The same websocket is used to send info back.
        global WS
        WS = ws
        async for msg in ws:
            await putter(msg)


async def interpreter(getter, putter, i_putter):
    '''
    Gets messages from the incoming queue and acts on them.

    Args:
        getter (method): Queue.get for the incoming queue
        putter (method): Queue.put for the outgoing queue,
                         to send any necessary responses
        i_putter (method): Queue.put for the incoming queue.
                           Useful for self-sending.
    '''
    while True:
        msg = await getter()
        
        print('Message: ')
        print(msg)

        await message_handler(msg, putter, i_putter)


async def message_handler(msg, putter, i_putter):
    '''
    Acts on websocket messages, depending on their contents.

    Args:
        msg (str): A message from the websocket
        putter (method): Queue.put for the outgoing queue to the websocket.
        i_putter (method): Queue.put for the incoming queue.
                           Useful for self-sending.
    '''
    global ROOMLIST

    curr_room = ''
    broken = msg.split('\n')
    if broken[0][0] == '>':
        curr_room = broken[0][1:]

    parts = msg.split('|')

    if len(parts) <= 1:
        print('!!! SEE THIS !!!')
        print(parts)
        return

    # Sanitation
    if parts[1] == 'c:' or parts[1] == 'pm':
        parts = parts[0:4] + ['|'.join(parts[4:])]

    # Login
    if parts[1] == 'challstr':
        print('Logging in...')
        await login(parts[2] + "|" + parts[3], putter)
    elif parts[1] == 'updateuser':
        await login_check(parts[2], parts[3], putter)

    # Function calls from chat
    elif (parts[1] == 'c:' or parts[1] == 'pm') and parts[4][0] == ']':
        is_pm = False
        caller = parts[3]
        if parts[1] == 'pm':
            is_pm = True
            caller = parts[2]
        await command_center(curr_room, caller, parts[4], putter, i_putter, pm=is_pm)

    # Trivia guesses
    elif parts[1] == 'c:':
        t_active = False
        try:
            t_active = ROOMLIST[curr_room].trivia.active
        except AttributeError:
            pass
        
        # ]tg is/was also a valid invocation for guessing. This is a neat shortcut.
        if t_active:
            await command_center(curr_room, parts[3], ']tg {}'.format(parts[4]), putter, i_putter)


async def login(keyword, putter):
    '''
    Performs the login dance with Showdown.

    Args:
        keyword (str): The challstr presented by showdown via websocket
        putter (method): Queue.put for the outgoing queue, to send verification
                         via websocket to finish login
    '''
    details = { 'act': 'login',
                'name': USERNAME,
                'pass': PASSWORD,
                'challstr': keyword
                }

    async with aiohttp.ClientSession() as session:
        async with session.post('http://play.pokemonshowdown.com/action.php', json=details) as r:
            resp = await r.text()
            assertion = json.loads(resp[1:])['assertion']
            await putter('|/trn ' + USERNAME + ',0,'  + str(assertion))
            print('Sending assertion')


async def login_check(name, logged_in, putter):
    '''
    Sets up if login was successful, otherwise stops the bot.

    Args:
        name (str): Showdown username
        logged_in (bool): Whether or not login was successful
        putter (method): Queue.put method for the outgoing queue; used to
                         complete setting up on Showdown
    '''
    print("Logged in as: " + name)

    if not logged_in:
        raise Exception("Not logged in.")
        asyncio.get_running_loop.close()

    if re.sub(r'\W+', '', name) == re.sub(r'\W+', '', USERNAME):
        await putter('|/avatar 97')

        for room in JOINLIST:
            ROOMLIST[room] = Room(room)
            await putter('|/join ' + room)


async def command_center(room, caller, command, putter, i_putter, pm=False):
    '''
    Handles command messages targeted at the bot.

    Args:
        room (str): The room the command was posted in
        caller (str): The user who invoked the command
        command (str): The entire message sent by the user
        putter (method): Queue.put method for the outgoing queue, in case
                         a message response is necessary
        i_putter (method): Queue.put method for the incoming queue.
                           Useful for self-sending.
        pm (bool): Whether or not the command came via PM
    '''
    global ROOMLIST
    global SUCKLIST
    global USERNAME
    
    msg = ''
    true_caller = User.find_true_name(caller)

    if command[0] != ']' or command == ']':
        return

    command = command[1:].split()

    if not command:
        return

    # All-room commands
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

    # animeandmanga
    elif command[0] == 'jibun' and room == ANIME_ROOM:
        msg = '/announce JIBUN WOOOOOOOOOO'

    # MAL
    elif command[0] == 'addmal' and room == ANIME_ROOM:
        if len(command) > 1:
            asyncio.create_task(set_mal_user(putter, true_caller, command[1]),
                                name='setmal-{}'.format(true_caller))
        else:
            msg = 'Please enter an MAL username.'
    
    elif command[0] == 'mal' and room == ANIME_ROOM:
        args = None

        to_parse = ''
        if len(command) > 1:
            to_parse = ' '.join(command[1:])
        args = mal_arg_parser(to_parse, true_caller)
        
        if args:
            args.username = User.find_true_name(' '.join(args.username))
        else:
            await putter(room + '| Incorrect formatting.')
            return

        mal_list = pd.read_csv('mal.txt')
        existing_user = mal_list[mal_list['user'] == args.username]
        if existing_user.empty:
            msg = 'This user does not have a MAL set.'
        else:
            mal_user = existing_user.iloc[0]['mal']
            if args.roll is not None:
                if args.roll == []:
                    args.roll = ['anime', 'manga']

                asyncio.create_task(mal_user_rand_series(putter, mal_user,
                                                         caller, args.roll),
                                    name='randmal-{}'.format(args.username))
            else:
                asyncio.create_task(show_mal_user(putter, mal_user),
                                    name='showmal-{}'.format(args.username))

    # Suck
    elif command[0] == 'suck':
        scount = 0
        suckinfo = SUCKLIST[SUCKLIST['user'] == true_caller]
        if len(command) > 1:
            if command[1] == 'top' and not pm:
                suckboard = SUCKLIST.sort_values('count', ascending=False)
                suckboard = suckboard[suckboard['user'] != TIMER_USER].head(n=5).values.tolist()
                msg = trivia_leaderboard_msg(suckboard, 'Suckiest', name='suckboard')

                await putter(room + '|' + msg)
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
                SUCKLIST = SUCKLIST.append(suckinfo)
            
            # There's a global cooldown of a random number between
            # 15 and 90 minutes.
            end_time = SUCKLIST.loc[SUCKLIST['user'] == TIMER_USER, 'count'][0]
            if time.time() > end_time:
                SUCKLIST.loc[SUCKLIST['user'] == true_caller, 'count'] += 1
                scount = int(suckinfo['count'].iat[0] + 1)
                SUCKLIST.loc[SUCKLIST['user'] == TIMER_USER, 'count'] = time.time() + random.randint(60*5, 60*30)
            else:
                SUCKLIST.loc[SUCKLIST['user'] == true_caller, 'count'] = 0
                scount = 0

            msg = '{} has sucked {} times.'.format(caller, str(scount))

        SUCKLIST.to_csv('suck.txt', index=False)
    
    # Trivia
    elif command[0] == 'trivia' and not pm:
        if len(command) < 2:
            return

        trivia_game = ROOMLIST[room].trivia
        trivia_status = trivia_game.active

        if (command[1] == 'start' and not trivia_status and
                User.compare_ranks(caller[0], '%')):

            args = None
            if len(command) > 2:
                args = trivia_arg_parser(' '.join(command[2:]))
            
            if not args:
                msg = 'Invalid parameters. Trivia not started.'
            else:
                msg = 'Starting a round of trivia with {} questions, each ' \
                      'worth {} points. Type your answers to guess!'.format(args.len, args.points)
                asyncio.create_task(ROOMLIST[room].trivia_game(putter,
                                                               i_putter,
                                                               args.len,
                                                               args.points,
                                                               args.diff,
                                                               args.categories,
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
            if room == ANIME_ROOM:
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
            if room == ANIME_ROOM:
                title = 'No leaderboard for this room.'
            msg = trivia_leaderboard_msg(trivia_game.leaderboard(n=to_show), title)
        elif command[1] == 'skip' and User.compare_ranks(caller[0], '%'):
            if trivia_game.active and trivia_game.answers:
                answer = trivia_game.answers[-1]

                trivia_game.correct.set()
                trivia_game.answers = []
                await trivia_game.skip(putter)

                msg = 'Skipping question. A correct answer would have been {}.'.format(answer)

    elif command[0] == 'tg' and not pm:
        trivia_game = ROOMLIST[room].trivia
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
                if true_caller == USERNAME:
                    msg = 'Question skipped.'
                else:
                    trivia_game.update_scores(true_caller)

                msg += f' The answer was {answer_check}.'

                trivia_game.correct.set()
                trivia_game.answers = []

    elif command[0] == 'skip' and not pm:      # Trivia skip alias
        new_command = ']trivia ' + ' '.join(command)
        await command_center(room, caller, new_command, putter, i_putter)
        return

    if msg == '':
        return

    if pm:
        msg = '/w {}, '.format(true_caller) + msg
    await putter(room + '|' + msg)


async def sender(getter):
    '''
    Sends messages destined for Showdown.

    Args:
        getter (method): Queue.get for the outgoing queue, where the messages
                         are taken from
    '''
    while True:
        msg = await getter()

        print('Sending: ')
        print(msg)
        await WS.send(msg)


if __name__ == "__main__":
    load_dotenv()
    USERNAME = os.getenv('PS_USERNAME')
    PASSWORD = os.getenv('PS_PASSWORD')
    SUCKLIST = pd.read_csv('suck.txt')

    loop = asyncio.get_event_loop()
    loop.set_debug(True)

    INCOMING = asyncio.Queue()
    OUTGOING = asyncio.Queue()

    try:
        loop.run_until_complete(asyncio.wait((listener(INCOMING.put, PS_SOCKET),
                                            interpreter(INCOMING.get, OUTGOING.put, INCOMING.put),
                                            sender(OUTGOING.get))))
    except:
        # Useful for debugging, since I can't figure out how else
        # to make async stuff return the actual error.
        import traceback
        traceback.print_exc()
    finally:
        loop.close()