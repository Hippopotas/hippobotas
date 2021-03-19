import random

from common.constants import METRONOME_BATTLE
from common.utils import find_true_name


class Battle:
    def __init__(self, battle_format):
        self.format = battle_format
        self.info = None
        self.players = []
        self.team = []


    def update_info(self, info_line):
        parts = info_line.split('|')

        if len(parts) <= 2:
            return

        if parts[1] == 'player':
            self.players.append(find_true_name(parts[3]))


    @staticmethod
    def make_team(battle_format):
        team = 'null'
        with open(f'teams/{battle_format}.txt') as f:
            pokes = f.readlines()

            if battle_format == METRONOME_BATTLE:
                team = ']'.join(random.sample(pokes, 2))

        team = team.replace('\n', '')
        return team


    @staticmethod
    def act(battle_format, one_poke=False):
        action = 'default'
        if battle_format == METRONOME_BATTLE:
            action = 'move 1, move 1'
            if one_poke:
                action = 'move 1'
        
        return f'/choose {action}'


    @staticmethod
    def find_true_name(battle):
        battle_parts = battle.split('-')
        if len(battle_parts) > 3:
            battle_parts = battle_parts[:3]
        
        return '-'.join(battle_parts)