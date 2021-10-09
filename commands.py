import asyncio
import functools
import json
import random
import re
import requests
import sqlite3
import urllib

import common.constants as const

from common.anilist import anilist_search, anilist_rand_series
from common.arg_parsers import mal_arg_parser
from common.mal import set_mal_user, show_mal_user
from common.utils import find_true_name, gen_uhtml_img_code, curr_cal_date, \
                         monospace_table_row, is_url, is_uhtml
from user import User


class Command():
    def __init__(self, **kwargs):
#       bot, full_command, room, caller, is_pm, pm_only, room_only,
#       usage_msg, req_rank, allowed_rooms, min_args, max_args, req_rank
        for k, v in kwargs.items():
            setattr(self, k, v)

        self.find_rank()

        self.command = self.full_command[0]
        self.args = self.full_command[1:]

        if not self.room_only:
            self.allowed_rooms.append('')

        self.msg = ''

        if 'req_rank_pm' not in kwargs:
            self.req_rank_pm = self.req_rank


    @property
    def num_args(self):
        return len(self.args)


    def usage_with_error(self, error):
        return f'{error} Usage: {self.usage_msg}'


    def check_eligible(self):
        """ Returns 0 if is eligible.
        """
        if self.room not in self.allowed_rooms:
            self.msg = f'{self.room} is not a legal room for this command.'
            return 1

        if not User.compare_ranks(self.caller_rank, self.req_rank) and not \
                (self.is_pm and User.compare_ranks(self.caller_rank, self.req_rank_pm)):
            self.msg = ''
            return 2

        if self.is_pm and self.room_only:
            self.msg = f']{self.command} can only be used in rooms.'
            return 3
        elif not self.is_pm and self.pm_only:
            self.msg = f']{self.command} can only be used in PMs.'
            return 4

        if self.num_args > self.max_args:
            self.msg = self.usage_with_error('Too many arguments.')
            return 5
        elif self.num_args < self.min_args:
            self.msg = self.usage_with_error('Too few arguments.')
            return 6

        return 0


    def find_rank(self):
        self.caller_rank = self.caller_info['group']
        if self.room:
            for r in self.caller_info['rooms']:
                if r[1:] == self.room:
                    if User.compare_ranks(r[0], self.caller_rank):
                        self.caller_rank = r[0]
                    break


    async def pm_msg(self, message):
        if message:
            await self.bot.outgoing.put(f'|/w {self.true_caller}, {message}')


class SimpleCommand(Command):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if self.command == 'jibun':
            self.allowed_rooms = [const.ANIME_ROOM]
            self.room_only = True

        if self.command == 'mal_set':
            self.command = 'mal_add'


    async def evaluate(self):
        if self.check_eligible():
            await self.pm_msg(self.msg)
            return ''

        if self.command == 'help':
            self.msg = 'o3o [[README <https://github.com/Hippopotas/hippobotas/blob/master/README.md>]] o3o'
        elif self.command == 'dab':
            self.msg = '/me dabs'
        elif self.command == 'owo':
            self.msg = 'uwu'
        elif self.command == 'google':
            self.msg = 'Don\'t be mad someone is faster at googling than you :3c'
        elif self.command == 'joogle':
            self.msg = 'Don\'t be mad someone is faster at joogling than you :3c'
        elif self.command == 'bing':
            self.msg = 'Have you heard of google?'
        elif self.command == 'jing':
            self.msg = 'Have you heard of joogle?'
        elif self.command == 'jibun':
            self.msg = '/announce JIBUN WOOOOOOOOOO'

        elif self.command == 'mal_add':
            mal_user = ''.join(self.args)
            self.msg += await set_mal_user(self.true_caller, mal_user,
                                           self.bot.roomdata_man,
                                           self.bot.mal_man)

        return self.msg


class UhtmlCommand(Command):
    def __init__(self, **kwargs):
        if kwargs['is_pm'] and len(kwargs['full_command']) > 1:
            kwargs['room'] = find_true_name(kwargs['full_command'][1])

        super().__init__(**kwargs)

        if self.is_pm:
            if self.command == 'mal':
                self.room = const.ANIME_ROOM
            else:
                self.min_args += 1
                self.usage_msg += '[ROOM] '

        if self.command in ['anime', 'manga']:
            self.usage_msg += 'SERIES NAME'

        if self.command in ['randanime', 'randmanga']:
            self.usage_msg += '[GENRES]'

        if self.command == 'mal':
            self.usage_msg += '[USERNAME] [-r CATEGORIES]'
            self.mal_args = mal_arg_parser(' '.join(self.args), self.true_caller)


    async def evaluate(self):
        self.msg = '/adduhtml '

        eligibility = self.check_eligible()

        if eligibility and eligibility != 2:
            await self.pm_msg(self.msg)
            return ''
        elif eligibility:
            if self.is_pm and not self.room:
                await self.pm_msg(self.usage_with_error(''))
                return ''
            elif self.is_pm and self.bot.roomlist[self.room].get_user(self.caller):
                self.msg = f'/sendprivateuhtml {self.true_caller}, '
            else:
                await self.pm_msg(f'You can only use {self.command} in PMs. '
                                   'Make sure you\'re in the specified room.')
                return ''
        elif self.is_pm:
            self.msg = f'/sendprivateuhtml {self.true_caller}, '

        if self.command == 'plebs':
            uhtml = gen_uhtml_img_code(const.PLEB_URL, height_resize=250)
            self.msg += f'hippo-pleb, {uhtml}'

        elif self.command == 'calendar':
            curr_day_str = curr_cal_date()
            calendar = json.load(open(const.CALENDARFILE))

            if self.room not in calendar:
                calendar[self.room] = {curr_day_str: []}
                json.dump(calendar, open(const.CALENDARFILE, 'w', indent=4))
            if not calendar[self.room][curr_day_str]:
                return 'No images found for this date.'

            date_imgs = calendar[self.room][curr_day_str]
            uhtml = gen_uhtml_img_code(random.choice(date_imgs), height_resize=200)
            self.msg += f'hippo-calendar, {uhtml}'

        elif self.command == 'birthday':
            await self.bot.send_birthday_text(automatic=False)

        elif self.command == 'anime':
            query = ' '.join(self.args)
            self.msg += await anilist_search('anime', query, self.bot.anilist_man)

        elif self.command == 'manga':
            query = ' '.join(self.args)
            self.msg += await anilist_search('manga', query, self.bot.anilist_man)

        elif self.command == 'randanime':
            genres = []
            tags = []

            true_args = list(map(find_true_name, self.args))

            for g in const.ANILIST_GENRES:
                if find_true_name(g) in true_args:
                    genres.append(g)
            for t in list(const.ANILIST_TAGS):
                if find_true_name(t) in true_args:
                    tags.append(t)

            self.msg += await anilist_rand_series('anime', self.bot.anilist_man, genres=genres, tags=tags)

        elif self.command == 'randmanga':            
            genres = []
            tags = []

            true_args = list(map(find_true_name, self.args))

            for g in const.ANILIST_GENRES:
                if find_true_name(g) in true_args:
                    genres.append(g)
            for t in list(const.ANILIST_TAGS):
                if find_true_name(t) in true_args:
                    tags.append(t)

            self.msg += await anilist_rand_series('manga', self.bot.anilist_man, genres=genres, tags=tags)

        elif self.command == 'mal':
            return_msg = await show_mal_user(self.mal_args.username[0],
                                             self.bot.roomdata_man,
                                             self.bot.mal_man)

            if is_uhtml(return_msg):
                self.msg += f'hippo-{self.mal_args.username[0]}mal, {return_msg}'
            elif self.is_pm:
                await self.pm_msg(return_msg)
                return
            else:
                self.msg = return_msg

        return self.msg


class ModifiableCommand(Command):
    def __init__(self, **kwargs):
        if kwargs['is_pm'] and len(kwargs['full_command']) > 1:
            kwargs['room'] = kwargs['full_command'][1]

        super().__init__(**kwargs)

        if self.is_pm:
            self.min_args += 1


    @functools.cached_property
    def json_info(self):
        return json.load(open(self.file, encoding='utf-8'))


class TopicCommand(ModifiableCommand):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if 'list' in self.command:
            self.req_rank = '+'
            self.usage_msg += '[ROOM]'
        elif 'rm' in self.command:
            self.req_rank = '%'
            self.min_args += 1
            self.usage_msg += '[ROOM] TOPIC_ID'
        elif self.command == 'topic':
            if self.num_args:
                self.req_rank = '%'
                self.min_args += 1
                self.usage_msg += '[ROOM] TOPIC_TEXT'
            else:
                self.usage_msg += '(use in a room)'


    async def evaluate(self):
        if self.check_eligible():
            await self.pm_msg(self.msg)
            return ''

        if self.room not in self.json_info:
            self.json_info[self.room] = {'current': '', 'random': []}
        room_topics = self.json_info[self.room]

        if self.command == 'topic':
            if self.num_args:
                new_topic = ' '.join(self.args)
                if self.is_pm:
                    new_topic = ' '.join(self.args[1:])
                room_topics['current'] = new_topic

            curr_topic = room_topics['current']
            if not curr_topic:
                self.msg = '/announce No topic right now!'
            else:
                self.msg = f'/announce {curr_topic}'

        elif self.command == 'topic_list':
            pass

        json.dump(self.json_info, open(self.file, 'w'), indent=4)

        return self.msg


class BanlistCommand(ModifiableCommand):
    def __init__(self, **kwargs):
        full_cmd = kwargs['full_command']
        if len(full_cmd) > 1:
            self.banlist = full_cmd[1]
            if full_cmd[1] == 'anime' or full_cmd[1] == 'manga':
                full_cmd[1] = 'animeandmanga'

        super().__init__(**kwargs)

        if self.command == 'bl_add':
            self.min_args = 2
            self.usage_msg += 'LIST_TO_MODIFY THING_TO_BAN'
            self.pm_only = True
        elif self.command == 'bl_rm':
            self.min_args = 2
            self.usage_msg += 'LIST_TO_MODIFY THING_TO_UNBAN'
            self.pm_only = True
        elif self.command == 'bl_list':
            self.min_args = 1
            self.usage_msg += 'LIST_TO_SEE'


    async def evaluate(self):
        if self.check_eligible():
            await self.pm_msg(self.msg)
            return ''

        if self.banlist not in self.json_info:
            await self.pm_msg(f'{self.banlist} is not a recognized banlist.')
            return ''

        if self.command == 'bl_add':
            if self.args[1] in self.json_info[self.banlist]:
                await self.pm_msg(f'{self.args[1]} already in {self.banlist} banlist.')
                return ''
            self.json_info[self.banlist].append(self.args[1])
            self.msg = f'{self.args[1]} added to {self.banlist} banlist.'

        elif self.command == 'bl_rm':
            if self.args[1] not in self.json_info[self.banlist]:
                await self.pm_msg(f'{self.args[1]} not in {self.banlist} banlist.')
                return ''
            self.json_info[self.banlist].remove(self.args[1])
            self.msg = f'{self.args[1]} removed from {self.banlist} banlist.'

        elif self.command == 'bl_list':
            if self.is_pm:
                self.msg = f'!code {self.banlist} banlist\n'
            else:
                self.msg = (f'/addrankuhtml %, hippo-{self.banlist}bl, '
                            f'<center>{self.banlist} banlist</center><br>')

            self.msg += ', '.join(self.json_info[self.banlist])

        json.dump(self.json_info, open(self.file, 'w'), indent=4)
        return self.msg


class EmoteCommand(ModifiableCommand):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if self.command == 'emote_list':
            self.req_rank = ' '
            self.usage_msg += '[ROOM]'
        elif self.command == 'emote_stats':
            self.req_rank = ' '
            self.usage_msg += '[ROOM]'
        elif self.command == 'emote_add':
            self.min_args += 2
            self.usage_msg += '[ROOM] EMOTE URL'
        elif self.command == 'emote_rm':
            self.min_args += 1
            self.usage_msg += '[ROOM] EMOTE'

    async def evaluate(self):
        if self.check_eligible():
            await self.pm_msg(self.msg)
            return ''

        arg_offset = 1 if self.is_pm else 0

        if self.command == 'emote_add':
            emote = self.args[arg_offset].lower()
            if emote.endswith(','):
                emote = emote[:-1]

            if find_true_name(emote) != emote:
                await self.pm_msg('Emotes must be only letters and/or numbers.')

            emote_url = self.args[1 + arg_offset]
            if 'discordapp' in emote_url:
                await self.pm_msg('Discord URLs do not work as emotes.')

            self.json_info[self.room][emote] = {'times_used': 0, 'url': emote_url}
            json.dump(self.json_info, open(self.file, 'w'), indent=4)

            self.msg = f'Set :{emote}: to show {emote_url}.'
        
        elif self.command == 'emote_rm':
            emote = find_true_name(self.args[arg_offset])
            self.msg = f'{self.room} does not have emote {emote}.'

            try:
                del self.json_info[self.room][emote]
                json.dump(self.json_info, open(self.file, 'w'), indent=4)

                self.msg = f'Removed {emote} from {self.room} emotes.'
            except KeyError:
                pass

        elif self.command == 'emote_list':
            self.msg = 'No emotes found.'

            if self.room in self.json_info:
                if len(self.json_info[self.room]) >= 1:
                    self.msg = f'!code {self.room} emotes: ' + ', '.join(self.json_info[self.room])

        elif self.command == 'emote_stats':
            self.msg = f'No emotes found for {self.room}.'

            if self.room in self.json_info:
                room_emotes = self.json_info[self.room]
                if len(room_emotes) >= 1:
                    header_text = monospace_table_row([('Emote', 30),
                                                       ('Times Used', 12)])
                    header_text += '\n' + '-'*44
                    box_text = ''
                    for e in sorted(room_emotes,
                                    key=lambda x: room_emotes[x]['times_used'],
                                    reverse=True):
                        box_text += monospace_table_row([(e, 30),
                                                         (room_emotes[e]['times_used'], 12)])
                        box_text += '\n'

                    r = requests.post(const.PASTIE_API, data=f'{header_text}\n{box_text}')

                    if r.status_code == 200:
                        self.msg = f"""https://pastie.io/raw/{r.json()['key']}"""

        return self.msg


class SongCommand(ModifiableCommand):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.usage_msg += '[ROOM] '

        if self.command == 'song_add':
            self.min_args += 2
            self.usage_msg += 'TITLE URL'
        elif self.command == 'song_rm':
            self.min_args += 1
            self.usage_msg += 'TITLE'

    def check_eligible(self):
        eligibility = super().check_eligible()

        if not eligibility and self.command == 'song_add':
            if not is_url(self.args[-1]):
                eligibility = 101
                self.msg = self.usage_with_error('Please provide a valid URL.')

        return eligibility

    async def evaluate(self):
        if self.check_eligible():
            await self.pm_msg(self.msg)
            return ''

        arg_offset = 1 if self.is_pm else 0

        if self.command == 'song_add':
            title = ' '.join(self.args[arg_offset:-1])

            if self.room not in self.json_info:
                self.json_info[self.room] = {}
            self.json_info[self.room][title] = self.args[-1]
            self.msg = f'Added {title} to song pool.'

        elif self.command == 'song_rm':
            title = ' '.join(self.args[arg_offset:])
            self.msg = f'{title} not found in song pool.'

            if self.room in self.json_info:
                for s in self.json_info[self.room]:
                    if find_true_name(s) == find_true_name(title):
                        del self.json_info[self.room][s]
                        self.msg = f'Deleted {title} from song pool.'
                        break

        elif self.command == 'song_list':
            self.msg = f'No songs found for {self.room}.'

            if self.room in self.json_info:
                room_songs = self.json_info[self.room]
                if len(room_songs) >= 1:
                    header_text = monospace_table_row([('Song Title', 100),
                                                       ('Link', 25)])
                    header_text += '\n' + '-'*146
                    box_text = ''
                    for s in sorted(room_songs.keys()):
                        box_text += monospace_table_row([(s, 100),
                                                         (room_songs[s], 25)])
                        box_text += '\n'

                    r = requests.post(const.PASTIE_API, data=f'{header_text}\n{box_text}'.encode('utf-8'))

                    if r.status_code == 200:
                        self.msg = f"""https://pastie.io/raw/{r.json()['key']}"""

        elif self.command == 'randsong':
            if self.room not in self.json_info or not self.json_info[self.room]:
                self.msg = f'There are no songs for {self.room}!'
            else:
                title = random.choice(list(self.json_info[self.room].keys()))
                # Decode the URL because PS re-encodes it
                song_url = self.json_info[self.room][title]
                self.msg = f'[[{title}<{urllib.parse.unquote(song_url)}>]]'

        json.dump(self.json_info, open(self.file, 'w'), indent=4)
        print(self.msg is None)
        return self.msg
