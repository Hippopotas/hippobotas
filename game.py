from user import User

STATUS_SIGNUP = 1
STATUS_FULL = 2
STATUS_PROGRESS = 3
STATUS_DONE = 4

HOLDEM = 'holdem'

class Game:
    def __init__(self, putter, room, game):
        self.players = []
        self.active_player = None

        self.putter = putter
        self.room = room

        self.min_players = 1
        self.max_players = 8
        if game == HOLDEM:
            self.min_players = 2

        self.curr_round = 0
        self.total_rounds = 0

        self.board = None
        self.discard = None

        self.help = ''

        self.status = STATUS_SIGNUP

    @classmethod
    async def create_game(cls, putter, room, game):
        new_game = cls(putter, room, game)

    async def game_msg(self, msg):
        await self.putter(f'{self.room}|{msg}')
    
    def register(self, player):
        if self.status != STATUS_SIGNUP:
            

class Player(User):
    def __init__(self):
        self.hand = None