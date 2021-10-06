import asyncio

from common.constants import ANIME_ROOM, LEAGUE_ROOM, VG_ROOM
from common.utils import find_true_name, trivia_leaderboard_msg
from trivia import TriviaGame
from user import User


class Room:
    def __init__(self, room):
        self.roomname = room
        self.users = []
        self.trivia = TriviaGame(self.roomname)
    
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

    async def trivia_game(self, putter, i_putter, n=10, diff=3,
                          categories=['all'], excludecats=None, by_rating=False, autoskip=20):
        if self.trivia.active:
            await putter(self.roomname + '|There is already a running trivia!')
            return

        is_dex = True if 'mangadex' in categories else False
        anagrams = True if 'anagrams' in categories else False

        try:
            await self.trivia.start(n, diff, categories, excludecats, by_rating, is_dex=is_dex, anagrams=anagrams)

            for _ in range(n):
                await asyncio.sleep(5)

                curr_question = await self.trivia.questions.questions.get()
                self.trivia.answers = curr_question[1]

                # Autoskip handling
                if autoskip:
                    asyncio.create_task(self.trivia.autoskip(autoskip, i_putter))

                await putter(self.roomname + '|' + curr_question[0])
                self.trivia.q_active.set()

                await self.trivia.correct.wait()
                self.trivia.correct.clear()

        except asyncio.CancelledError:
            if not self.trivia.questions.series_exist:
                await putter(self.roomname + '|There are not enough series for this combination of categories.')
            for task in asyncio.all_tasks():
                if task.get_name() == 'tquestions-{}'.format(self.roomname):
                    task.cancel()
                    break

            print('Trivia stopped early.')
        finally:
            leaderboard = self.trivia.leaderboard()
            
            await self.trivia.end(putter)
            await asyncio.sleep(1)

            msg = trivia_leaderboard_msg(leaderboard, 'Trivia Leaderboard')

            await putter(self.roomname + '|' + msg)

    async def quizbowl_game(self, putter, i_putter, n=10, diff=3,
                            categories=['all'], excludecats=None, by_rating=False, autoskip=20):
        if self.trivia.active:
            await putter(self.roomname + '|There is already a running trivia!')
            return

        try:
            await self.trivia.start(n, diff, categories, excludecats, by_rating, quizbowl=True)

            for _ in range(n):
                curr_question = await self.trivia.questions.questions.get()
                self.trivia.answers = curr_question[1]

                await asyncio.sleep(5)

                asyncio.create_task(self.trivia.quizbowl_question(curr_question[0], autoskip, putter, i_putter))
                self.trivia.q_active.set()

                await self.trivia.correct.wait()
                self.trivia.correct.clear()

        except asyncio.CancelledError:
            if not self.trivia.questions.series_exist:
                await putter(self.roomname + '|There are not enough series for this combination of these categories.')
            else:
                await putter(self.roomname + '|Something broke. Ending trivia.')

            for task in asyncio.all_tasks():
                if task.get_name() == 'tquestions-{}'.format(self.roomname):
                    task.cancel()
                    break

        finally:
            leaderboard = self.trivia.leaderboard()
            
            await self.trivia.end(putter)
            await asyncio.sleep(1)

            msg = trivia_leaderboard_msg(leaderboard, 'Quizbowl Leaderboard')

            await putter(self.roomname + '|' + msg)