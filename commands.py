import json
import random

import common.constants as const

from common.utils import find_true_name, gen_uhtml_img_code, curr_cal_date
from user import User


class Command():
    def __init__(self, **kwargs):
#       bot, full_command, room, caller, is_pm, pm_only, room_only,
#       usage_msg, req_rank, allowed_rooms, min_args, max_args, req_rank
        for k, v in kwargs.items():
            setattr(self, k, v)

        self.caller_rank = self.caller_info['group']

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
        super().__init__(**kwargs)


    async def evaluate(self):
        if not self.is_eligible():
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


        return self.msg


class ModifiableCommand(Command):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if self.is_pm:
            self.min_args += 1
            
            if self.args:
                self.room = self.args[0]

                for r in self.caller_info['rooms']:
                    if r[1:] == self.room:
                        if User.compare_ranks(r[0], self.caller_rank):
                            self.caller_rank = r[0]
                        break


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
