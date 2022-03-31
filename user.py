import aiohttp
import asyncio
import json
import os
import pandas as pd
import random
import re

from common.utils import find_true_name


class User:
    Groups = {'‽': -1, '!': -1, ' ': 0, '^': 1.1, '+': 1, '*': 1.5, '★': 2, '%': 2, '@': 3, '&': 4, '#': 5, '＋': 6, '~': 6}

    @staticmethod
    def compare_ranks(rank1, rank2):
        try:
            return User.Groups[rank1] >= User.Groups[rank2]
        except KeyError:
            if rank1 not in User.Groups:
                print('{rank} is not a supported usergroup'.format(rank = rank1))
            if rank2 not in User.Groups:
                print('{rank} is not a supported usergroup'.format(rank = rank2))
            return False

    def __init__(self, username, rank=' '):
        self.name = username
        self.true_name = find_true_name(self.name)
        self.rank = rank
