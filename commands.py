import asyncio
import json
import random
import requests

import common.constants as const

from common.mal import mal_search, mal_rand_series
from common.utils import find_true_name, gen_uhtml_img_code, curr_cal_date, monospace_table_row
from user import User


class Command():
    def __init__(self, **kwargs):
#       bot, full_command, room, caller, is_pm, pm_only, room_only,
#       usage_msg, req_rank, allowed_rooms, min_args, max_args, req_rank
        for k, v in kwargs.items():
            setattr(self, k, v)

        self.caller_rank = self.caller_info['group']
        if self.room:
            for r in self.caller_info['rooms']:
                if r[1:] == self.room:
                    if User.compare_ranks(r[0], self.caller_rank):
                        self.caller_rank = r[0]
                    break

        self.command = self.full_command[0]
        self.args = self.full_command[1:]

        if not self.room_only:
            self.allowed_rooms.append('')

        self.msg = ''


    @property
    def num_args(self):
        return len(self.args)


    def usage_with_error(self, error):
        return f'{error}. Usage: {self.usage_msg}'


    def is_eligible(self):
        if not User.compare_ranks(self.caller_rank, self.req_rank):
            self.msg = ''
            return False

        if self.room not in self.allowed_rooms:
            self.msg = f'{self.room} is not a legal room for this command.'
            return False

        if self.is_pm and self.room_only:
            self.msg = f']{self.command} can only be used in rooms.'
            return False
        elif not self.is_pm and self.pm_only:
            self.msg = f']{self.command} can only be used in PMs.'
            return False

        if self.num_args > self.max_args:
            self.msg = self.usage_with_error('Too many arguments')
            return False
        elif self.num_args < self.min_args:
            self.msg = self.usage_with_error('Too few arguments')
            return False

        return True


    async def pm_msg(self, message):
        if message:
            await self.bot.outgoing.put(f'|/w {self.true_caller}, {message}')


class SimpleCommand(Command):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if self.command == 'jibun':
            self.allowed_rooms = [const.ANIME_ROOM]
            self.room_only = True


    async def evaluate(self):
        if not self.is_eligible():
            await self.pm_msg(self.msg)
            return ''

        if self.command == 'help':
            self.msg = 'o3o https://pastebin.com/raw/LxnMv5hA o3o'
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

        return self.msg


class UhtmlCommand(Command):
    def __init__(self, **kwargs):
        if kwargs['is_pm'] and len(kwargs['full_command']) > 1:
            kwargs['room'] = kwargs['full_command'][1]

        super().__init__(**kwargs)

        if self.is_pm:
            self.min_args += 1
            self.usage_msg += '[ROOM]'


    async def evaluate(self):
        if not User.compare_ranks(self.caller_rank, self.req_rank):
            if self.is_pm:
                return
            else:
                await self.pm_msg(f'You can only use {self.command} in PMs...coming soon.')
                return
        elif not self.is_eligible():
            await self.pm_msg(self.msg)
            return ''

        if self.command == 'plebs':
            uhtml = gen_uhtml_img_code(const.PLEB_URL, height_resize=250)
            self.msg = f'/adduhtml hippo-pleb, {uhtml}'

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
            self.msg = f'/adduhtml hippo-calendar, {uhtml}'

        elif self.command == 'birthday':
            await self.bot.send_birthday_text(automatic=False)

        elif self.command == 'anime':
            query = ' '.join(self.args)
            self.msg = await mal_search('anime', query)

        elif self.command == 'manga':
            query = ' '.join(self.args)
            self.msg = await mal_search('manga', query)

        elif self.command == 'randanime':
            submediums = list(set(const.ANIME_TYPES) & set(self.args)) if self.args else ['']
            genres = list(set(const.ANIME_GENRES) & set(self.args)) if self.args else ['']

            submediums = [''] if not submediums else submediums
            genres = [''] if not genres else genres
            self.msg = await mal_rand_series('anime', submediums=submediums, genres=genres)

        elif self.command == 'randmanga':
            submediums = list(set(const.MANGA_TYPES) & set(self.args)) if self.args else ['']
            genres = list(set(const.MANGA_GENRES) & set(self.args)) if self.args else ['']

            submediums = [''] if not submediums else submediums
            genres = [''] if not genres else genres
            self.msg = await mal_rand_series('manga', submediums=submediums, genres=genres)

        return self.msg


class ModifiableCommand(Command):
    def __init__(self, **kwargs):
        if kwargs['is_pm'] and len(kwargs['full_command']) > 1:
            kwargs['room'] = kwargs['full_command'][1]

        super().__init__(**kwargs)

        if self.is_pm:
            self.min_args += 1


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
        if not self.is_eligible():
            await self.pm_msg(self.msg)
            return

        json_info = json.load(open(self.file))
        if self.room not in json_info:
            json_info[self.room] = {'current': '', 'random': []}
        room_topics = json_info[self.room]

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

        json.dump(json_info, open(self.file, 'w'), indent=4)

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
        if not self.is_eligible():
            await self.pm_msg(self.msg)
            return

        json_info = json.load(open(self.file))
        if self.banlist not in json_info:
            await self.pm_msg(f'{self.banlist} is not a recognized banlist.')
            return

        if self.command == 'bl_add':
            if self.args[1] in json_info[self.banlist]:
                await self.pm_msg(f'{self.args[1]} already in {self.banlist} banlist.')
                return
            json_info[self.banlist].append(self.args[1])
            self.msg = f'{self.args[1]} added to {self.banlist} banlist.'

        elif self.command == 'bl_rm':
            if self.args[1] not in json_info[self.banlist]:
                await self.pm_msg(f'{self.args[1]} not in {self.banlist} banlist.')
                return
            json_info[self.banlist].remove(self.args[1])
            self.msg = f'{self.args[1]} removed from {self.banlist} banlist.'

        elif self.command == 'bl_list':
            if self.is_pm:
                self.msg = f'!code {self.banlist} banlist\n'
            else:
                self.msg = (f'/addrankuhtml %, hippo-{self.banlist}bl, '
                            f'<center>{self.banlist} banlist</center><br>')

            self.msg += ', '.join(json_info[self.banlist])

        json.dump(json_info, open(self.file, 'w'), indent=4)
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
        if not self.is_eligible():
            await self.pm_msg(self.msg)
            return

        arg_offset = 1 if self.is_pm else 0

        json_info = json.load(open(self.file))
        if self.command == 'emote_add':
            emote = self.args[1 + arg_offset].lower()
            if emote.endswith(','):
                emote = emote[:-1]

            if find_true_name(emote) != emote:
                await self.pm_msg('Emotes must be only letters and/or numbers.')

            emote_url = self.args[2 + arg_offset]
            if 'discordapp' in emote_url:
                await self.pm_msg('Discord URLs do not work as emotes.')

            json_info[self.room][emote] = {'times_used': 0, 'url': emote_url}
            json.dump(json_info, open(self.file, 'w'), indent=4)

            self.msg = f'Set :{emote}: to show {emote_url}.'
        
        elif self.command == 'emote_rm':
            emote = find_true_name(self.args[1 + arg_offset])
            self.msg = f'{self.room} does not have emote {emote}.'

            try:
                del json_info[self.room][emote]
                json.dump(json_info, open(self.file, 'w'), indent=4)

                self.msg = f'Removed {emote} from {self.room} emotes.'
            except KeyError:
                pass

        elif self.command == 'emote_list':
            self.msg = 'No emotes found.'

            if self.room in json_info:
                if len(json_info[self.room]) >= 1:
                    self.msg = f'!code {self.room} emotes: ' + ', '.join(json_info[self.room])

        elif self.command == 'emote_stats':
            self.msg = 'No emotes found.'

            if self.room in json_info:
                room_emotes = json_info[self.room]
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
