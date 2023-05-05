import dateutil
import functools
import json
import random
import requests
import urllib

import common.constants as const

from common.anilist import add_anotd_bl, anilist_search, anilist_rand_series, rm_anotd_bl
from common.arg_parsers import mal_arg_parser
from common.mal import mal_url_info
from common.utils import find_true_name, gen_uhtml_img_code, curr_cal_date, \
                         monospace_table_row, is_url, is_uhtml, birthday_text, leaderboard_uhtml
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
        if self.true_caller == 'hippopotas':
            self.caller_rank = '~'
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

        if self.command == 'mal_add':
            self.usage_msg += 'MAL_USERNAME'


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
            self.msg += await self.bot.mal_man.set_user(self.true_caller, mal_user, self.bot.jikan_man)

        elif self.command == 'wpm_reset':
            try:
                self.bot.wpms.loc[self.true_caller]
            except KeyError:
                pass
            else:
                self.bot.wpms.loc[self.true_caller, ['top_wpm', 'avg_wpm', 'recent_runs']] = 0, 0, []
                self.bot.wpms.to_csv(const.WPMFILE)
            self.msg = f'Reset {self.caller}\'s typing speed record to 0 WPM.'

        elif self.command == 'wpm':
            wpm_user = self.caller
            true_wpm_user = self.true_caller
            if self.args:
                wpm_user = ' '.join(self.args)
                true_wpm_user = find_true_name(wpm_user)

            try:
                wpminfo = self.bot.wpms.loc[true_wpm_user]
            except KeyError:
                self.msg = f'{wpm_user} has not taken a typing test.'
            else:
                top_wpm = wpminfo['top_wpm']
                avg_wpm = wpminfo['avg_wpm']
                run_count = len(wpminfo['recent_runs'])
                self.msg = f'{wpm_user} - Top speed: {top_wpm} WPM. Average of past {run_count} runs: {avg_wpm} WPM.'


        return self.msg


class UhtmlCommand(Command):
    def __init__(self, **kwargs):
        if kwargs['is_pm'] and len(kwargs['full_command']) > 1:
            kwargs['room'] = find_true_name(kwargs['full_command'][1])

        super().__init__(**kwargs)

        if self.is_pm:
            if self.command in ['mal', 'anime', 'manga']:
                self.room = const.ANIME_ROOM
            else:
                self.min_args += 1
                self.usage_msg += '[ROOM] '

        if self.command in ['anime', 'manga']:
            self.usage_msg += 'SERIES NAME'

        if self.command in ['randanime', 'randmanga']:
            self.usage_msg += '[GENRES]'

        if self.command == 'mal':
            self.req_rank_pm = ' '

            self.usage_msg += '[USERNAME] [-r CATEGORIES]'
            self.mal_args = mal_arg_parser(' '.join(self.args), self.true_caller)

            if self.mal_args.roll is not None:
                self.pm_response = self.is_pm


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
                json.dump(calendar, open(const.CALENDARFILE, 'w'), indent=4)
            if not calendar[self.room][curr_day_str]:
                return 'No images found for this date.'

            date_imgs = calendar[self.room][curr_day_str]
            uhtml = gen_uhtml_img_code(random.choice(date_imgs), height_resize=200)
            self.msg += f'hippo-calendar, {uhtml}'

        elif self.command == 'wpm_top':
            metric = 'avg_wpm'
            metric_title = '(Last 5 Runs Avg.)'
            if '-s' in self.args or '--single' in self.args:
                metric = 'top_wpm'
                metric_title = '(Single Run)'

            wpmboard = self.bot.wpms.sort_values(metric, ascending=False)
            if metric == 'avg_wpm':
                wpmboard = wpmboard[wpmboard['recent_runs'].map(len) >= 5]
            wpmboard = wpmboard.reset_index().head(n=5)[['user', metric]].values.tolist()

            self.msg += leaderboard_uhtml(wpmboard, f'Fastest WPM {metric_title}', name='wpmboard', metric='WPM')

        elif self.command == 'birthday':
            self.msg += await birthday_text(self.bot, automatic=False, room=self.room)

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
            true_mal_user = find_true_name(''.join(self.mal_args.username))

            if self.mal_args.roll is not None:
                media = ['anime', 'manga']
                if 'anime' not in self.mal_args.roll:
                    media.remove('anime')
                if 'manga' not in self.mal_args.roll:
                    media.remove('manga')

                return_msg = await self.bot.mal_man.user_rand_series(true_mal_user, media, anotd=self.is_anotd)

                if return_msg.startswith('rolled'):
                    self.msg = f'{self.caller} {return_msg}'
                else:
                    self.msg = return_msg

            else:
                return_msg = await self.bot.mal_man.show_user(true_mal_user, self.bot.jikan_man)

                if is_uhtml(return_msg):
                    self.msg += f'hippo-{true_mal_user}mal, {return_msg}'
                elif self.is_pm:
                    self.pm_response = self.is_pm
                    self.msg = return_msg
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


class DatabaseCommand(Command):
    def __init__(self, **kwargs):
        if kwargs['is_pm'] and len(kwargs['full_command']) > 1:
            kwargs['room'] = kwargs['full_command'][1]

        super().__init__(**kwargs)

        if self.is_pm:
            self.min_args += 1

    @property
    def db_man(self):
        return self.bot.roomdata_man


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


class BanlistCommand(DatabaseCommand):
    VALID_BANLISTS = {'anime': 'mal_id',
                      'manga': 'mal_id',
                      'anotd': 'mal_id'}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if self.args:
            self.banlist = self.args[0]
            if self.banlist in ['anime', 'manga', 'anotd']:
                self.room = 'animeandmanga'
            self.find_rank()

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
            self.usage_msg += 'LIST_TO_VIEW'


    async def evaluate(self):
        if self.check_eligible():
            await self.pm_msg(self.msg)
            return ''

        if self.banlist not in self.VALID_BANLISTS:
            await self.pm_msg(f'{self.banlist} is not a valid banlist.')
            return ''
        else:
            self.bl_key = self.VALID_BANLISTS[self.banlist]

        if len(self.args) > 1:
            if self.banlist in ['anime', 'manga']:
                self.bl_value = self.args[1]
            elif self.banlist == 'anotd':
                try:
                    self.bl_value2, self.bl_value = mal_url_info(self.args[1])
                except TypeError:
                    await self.pm_msg(f'{self.args[1]} is not a valid MAL url.')
                    return ''

            self.where_clause = f"WHERE {self.bl_key}={self.bl_value}"
            if self.banlist in ['anime', 'manga']:
                self.where_clause += f" AND medium='{self.banlist}'"
                self.check_query = (f"SELECT * FROM mal_banlist {self.where_clause}")
            elif self.banlist == 'anotd':
                self.where_clause += f" AND medium='{self.bl_value2}'"
                self.check_query = (f"SELECT * FROM {self.banlist}_banlist {self.where_clause}")

        if self.command == 'bl_add':
            entry_exists = await self.db_man.execute(self.check_query)
            if entry_exists:
                await self.pm_msg(f'{self.bl_value} already in {self.banlist} banlist.')
                return ''

            if self.banlist in ['anime', 'manga']:
                await self.db_man.execute(f"INSERT INTO mal_banlist (medium, mal_id, manual) "
                                                f"VALUES ('{self.banlist}', {self.bl_value}, 1)")
            elif self.banlist == 'anotd':
                await add_anotd_bl(self.bl_value2, self.bl_value, self.bot.anilist_man, self.db_man)

            self.msg = f'{self.args[1]} added to {self.banlist} banlist.'

        elif self.command == 'bl_rm':
            entry_exists = await self.db_man.execute(self.check_query)
            if not entry_exists:
                await self.pm_msg(f'{self.bl_value} not in {self.banlist} banlist.')
                return ''

            if self.banlist in ['anime', 'manga']:
                await self.db_man.execute(f"DELETE FROM mal_banlist WHERE medium='{self.banlist}' AND mal_id={self.bl_value} AND manual=1")
            elif self.banlist == 'anotd':
                await rm_anotd_bl(self.bl_value2, self.bl_value, self.bot.anilist_man, self.db_man)

            self.msg = f'{self.args[1]} removed from {self.banlist} banlist.'

        elif self.command == 'bl_list':
            header_text = monospace_table_row([(self.banlist, 20)])
            if self.banlist == 'anotd':
                header_text = monospace_table_row([('Franchise/Title', 30)])            
            header_text += '\n' + '-'*30

            box_text = ''
            if self.banlist in ['anime', 'manga']:
                mal_ids = await self.db_man.execute("SELECT mal_id FROM mal_banlist "
                                                        f"WHERE medium='{self.banlist}' AND manual=1")
                for mid in list(sum(mal_ids, ())):
                    box_text += monospace_table_row([(mid, 20)])
                    box_text += '\n'
            
            elif self.banlist == 'anotd':
                names = await self.db_man.execute("SELECT name FROM anotd_banlist")
                for name in list(sum(names, ())):
                    fixed_name = name.encode('ascii', 'ignore').decode()
                    box_text += monospace_table_row([(fixed_name, 30)])
                    box_text += '\n'

            r = requests.post(const.PASTIE_API, data=f'{header_text}\n{box_text}')
            if r.status_code == 200:
                self.msg = f"""https://pastie.io/raw/{r.json()['key']}"""
            else:
                self.msg = 'Cannot generate banlist info at this time.'

            if not self.is_pm:
                self.msg = (f'/addrankuhtml %, hippo-{self.banlist}bl, '
                            f'<center>{self.banlist} banlist: {self.msg}</center><br>')

        return self.msg


class EmoteCommand(DatabaseCommand):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if self.command == 'emote_add':
            self.min_args += 2
            self.req_rank = '#'
            self.usage_msg += 'EMOTE URL'
        elif self.command == 'emote_rm':
            self.min_args += 1
            self.req_rank = '#'
            self.usage_msg += 'EMOTE'


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
                return

            emote_url = self.args[arg_offset+1]
            if 'discordapp' in emote_url:
                await self.pm_msg('Discord URLs do not work as emotes.')
                return

            emote_exists = await self.db_man.execute("SELECT * FROM emotes WHERE "
                                                        f"room='{self.room} AND name={emote}'")
            if emote_exists:
                await self.db_man.execute(f"UPDATE emotes SET url='{emote_url}' "
                                            f"WHERE room='{self.room}' AND name='{emote}'")
            else:
                await self.db_man.execute("INSERT INTO emotes (room, name, url) "
                                            f"VALUES ('{self.room}', '{emote}', '{emote_url}')")

            self.msg = f'Set :{emote}: to show {emote_url}.'
        
        elif self.command == 'emote_rm':
            emote = find_true_name(self.args[arg_offset])

            emote_exists = await self.db_man.execute("SELECT * FROM emotes WHERE "
                                                        f"room='{self.room}' AND name='{emote}'")

            if not emote_exists:
                await self.pm_msg(f'{self.room} does not have emote {emote}.')
                return

            await self.db_man.execute("DELETE FROM emotes WHERE "
                                        f"room='{self.room}' AND name='{emote}'")
            self.msg = f'Removed {emote} from {self.room}.'

        elif self.command == 'emote_list':
            self.msg = 'No emotes found.'

            emote_list = await self.db_man.execute("SELECT name FROM emotes "
                                                        f"WHERE room='{self.room}'")

            if emote_list:
                # Flatten
                emote_list = list(sum(emote_list, ()))
                self.msg = f'!code {self.room} emotes: ' + ', '.join(emote_list)

        elif self.command == 'emote_stats':
            self.msg = f'No emotes found for {self.room}.'

            emote_list = await self.db_man.execute("SELECT name, times_used FROM emotes "
                                                    f"WHERE room='{self.room}'")

            if emote_list:
                header_text = monospace_table_row([('Emote', 30), ('Times Used', 12)])
                header_text += '\n' + '-'*44
                box_text = ''
                for e in sorted(emote_list, key=lambda x: x[1], reverse=True):
                    box_text += monospace_table_row([(e[0], 30), (e[1], 12)])
                    box_text += '\n'

                r = requests.post(const.PASTIE_API, data=f'{header_text}\n{box_text}')

                if r.status_code == 200:
                    self.msg = f"""https://pastie.io/raw/{r.json()['key']}"""
                else:
                    self.msg = 'Unable to generate emote stats at this time.'

        return self.msg


class SongCommand(DatabaseCommand):
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
            url = self.args[-1]

            song_exists = await self.db_man.execute("SELECT * FROM songs WHERE "
                                                        f"room='{self.room}' AND url='{url}'")

            if song_exists:
                self.msg = f'This url already exists in the song pool for {self.room}.'
            else:
                # Sqlite escape
                title = title.replace("'", "''")
                await self.db_man.execute("INSERT INTO songs (room, title, url) "
                                            f"VALUES ('{self.room}', '{title}', '{url}')")
                self.msg = f'Added {title} to {self.room} song pool.'

        elif self.command == 'song_rm':
            title = ' '.join(self.args[arg_offset:])
            self.msg = f'{title} not found in song pool.'

            room_songs = await self.db_man.execute("SELECT title FROM songs "
                                                    f"WHERE room='{self.room}'")

            for s in list(sum(room_songs, ())):
                if find_true_name(s) == find_true_name(title):
                    escaped_s = s.replace("'", "''")
                    await self.db_man.execute("DELETE FROM songs WHERE "
                                                f"room='{self.room}' AND title='{escaped_s}'")

            self.msg = f'Deleted all songs called {title} from song pool.'

        elif self.command == 'song_list':
            self.msg = f'No songs found for {self.room}.'

            song_exists = await self.db_man.execute("SELECT title, url FROM songs "
                                                    f"WHERE room='{self.room}'")

            if song_exists:
                room_songs = {}
                for song in song_exists:
                    room_songs[song[0]] = song[1]

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
                else:
                    self.msg = 'Unable to generate song list at this time.'

        elif self.command == 'randsong':
            song_exists = await self.db_man.execute("SELECT title, url FROM songs "
                                                    f"WHERE room='{self.room}'")

            if not song_exists:
                self.msg = f'There are no songs for {self.room}!'
            else:
                rand_song = random.choice(song_exists)
                # Decode the URL because PS re-encodes it
                self.msg = f'[[{rand_song[0]}<{urllib.parse.unquote(rand_song[1])}>]]'

        return self.msg


class BirthdayCommand(DatabaseCommand):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.usage_msg += '[ROOM] '

        if self.command == 'birthday_add':
            self.min_args += 2
            self.usage_msg += 'NAME LINK IMAGE DATE'
        elif self.command == 'birthday_rm':
            self.min_args += 1
            self.usage_msg += 'NAME'


    def check_eligible(self):
        eligibility = super().check_eligible()

        if not eligibility and self.command == 'birthday_add':
            if not is_url(self.args[-2]) or not is_url(self.args[-3]):
                eligibility = 101
                self.msg = self.usage_with_error('Please provide a valid URL.')

            if not dateutil.parser.parse(self.args[-1]):
                eligibility = 101
                self.msg = self.usage_with_error('Please provide a recognizable day (with no space).')

        return eligibility


    async def evaluate(self):
        if self.check_eligible():
            await self.pm_msg(self.msg)
            return ''

        arg_offset = 1 if self.is_pm else 0

        if self.command == 'birthday_add':
            name = ' '.join(self.args[arg_offset:-3])
            link = self.args[-3]
            image = self.args[-2]
            day = dateutil.parser.parse(self.args[-1]).strftime('%B %#d')

            char_exists = await self.db_man.execute("SELECT * FROM birthdays WHERE "
                                                        f"room='{self.room}' AND name='{name}' AND day='{day}'")

            if char_exists:
                self.msg = f'This character is already in the birthdays for {self.room}.'
            else:
                # Sqlite escape
                name = name.replace("'", "''")
                await self.db_man.execute("INSERT INTO birthdays (name, room, day, image, link) "
                                            f"VALUES ('{name}', '{self.room}', '{day}', '{image}', '{link}')")
                self.msg = f'Added {name} to {self.room} birthdays.'

        elif self.command == 'birthday_rm':
            name = ' '.join(self.args[arg_offset:])
            self.msg = f'{name} not found in birthdays.'

            room_bdays = await self.db_man.execute("SELECT name FROM birthdays "
                                                    f"WHERE room='{self.room}'")

            for n in list(sum(room_bdays, ())):
                if find_true_name(n) == find_true_name(name):
                    escaped_n = n.replace("'", "''")
                    await self.db_man.execute("DELETE FROM birthdays WHERE "
                                                f"room='{self.room}' AND name='{escaped_n}'")

            self.msg = f'Deleted all birthdays of {name} in {self.room}.'

        return self.msg
