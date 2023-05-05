import asyncio

from common.constants import ANIME_ROOM, LEAGUE_ROOM, VG_ROOM
from common.utils import find_true_name
from trivia import TriviaGame
from user import User


class Room:
    def __init__(self, room, bot):
        self.bot = bot
        self.roomname = room
        self.users = []

        self.trivia = TriviaGame(self.roomname, self.bot)
    
    def add_user(self, username, rank):
        self.users.append(User(username, rank))
    
    def remove_user(self, username):
        for u in self.users:
            if u.true_name == find_true_name(username):
                self.users.remove(u)

    def get_user(self, username):
        for u in self.users:
            if u.true_name == find_true_name(username):
                return u

        return None
