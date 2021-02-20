import asyncio

from constants import ANIME_ROOM, LEAGUE_ROOM, VG_ROOM
from user import User
from trivia import TriviaGame


def trivia_leaderboard_msg(leaderboard, title, name='tleaderboard', metric='pts'):
    msg = (f'/adduhtml {name}, '
            '<center><table><tr><th colspan=\'3\' style=\'border-bottom:1px solid\'>'
            '{}</th></tr>'.format(title))

    for i, [user, score] in enumerate(leaderboard):
        msg += '<tr><td>{}</td><th>{}</th><td>{} {}</td></tr>'.format(i+1, user, int(score), metric)

    msg += '</table></center>'
    return msg


class Room:
    def __init__(self, room):
        self.roomname = room
        self.trivia = TriviaGame(self.roomname)

    async def trivia_game(self, putter, i_putter, n=10, diff=3,
                          categories=['all'], excludecats=False, by_rating=False, autoskip=20):
        if self.trivia.active:
            await putter(self.roomname + '|There is already a running trivia!')
            return

        try:
            await self.trivia.start(n, diff, categories, excludecats, by_rating)

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
                await putter(self.roomname + '|There are no series for some combination(s) of these categories.')
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
                            categories=['all'], excludecats=False, by_rating=False, autoskip=20):
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
                await putter(self.roomname + '|There are no series for some combination(s) of these categories.')
            for task in asyncio.all_tasks():
                if task.get_name() == 'tquestions-{}'.format(self.roomname):
                    task.cancel()
                    break

            print('Quizbowl stopped early.')
        finally:
            leaderboard = self.trivia.leaderboard()
            
            await self.trivia.end(putter)
            await asyncio.sleep(1)

            msg = trivia_leaderboard_msg(leaderboard, 'Quizbowl Leaderboard')

            await putter(self.roomname + '|' + msg)