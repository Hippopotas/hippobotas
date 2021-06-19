import common.constants as const

from common.utils import find_true_name
from user import User


class Command():
    def __init__(self, **kwargs):
#       full_command, room, caller, is_pm, pm_only, room_only,
#       usage_msg, req_rank, allowed_rooms, min_args, max_args, req_rank
        for k, v in kwargs.items():
            setattr(self, k, v)

        self.caller_rank = self.caller[0]
        self.true_caller = find_true_name(self.caller)
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
            self.msg = ''
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


class SimpleCommand(Command):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if self.command == 'jibun':
            self.allowed_rooms = [const.ANIME_ROOM]
            self.room_only = True


    def evaluate(self):
        if not self.is_eligible():
            return self.msg

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