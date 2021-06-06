import json
import peewee
import random
import requests

from datetime import datetime
from peewee import EnclosedNodeList, Tuple, ValuesList

import common.constants as const

from common.gacha_db import PlayerAccInfoTable, PlayerBoxTable
from common.gacha_db import AllGachasTable, PadTable, FgoTable
from common.utils import gen_uhtml_img_code, monospace_table_row

HOURLY_ROLLS = 2


def unit_uhtml(unit, pm=False):
    """ Generates the uhtml for a unit. """
    img_url = json.loads(unit.img_url_pv)[-1]
    img_uhtml = gen_uhtml_img_code(img_url, height_resize=40, center=False,
                                   alt=f'\'{unit.name}\'')

    all_uhtml = ('<span style=\'padding: 1px\'>'
                f'<a href=\'{unit.unit_url}\'>'
                f'{img_uhtml}</a></span>')

    return all_uhtml


def roll_uhtml(user, gacha, pulls, pm=False):
    """ Generates the uhtml for a set of rolls. """
    images_uhtml = ''
    for i, u in enumerate(pulls):
        images_uhtml += unit_uhtml(u)

        if i > 0 and i % 5 == 4:
            images_uhtml += '<br>'

    uhtml = (f'<center><b>{user}\'s {gacha.upper()} {len(pulls)} Roll Result</b><br>'
             f'{images_uhtml}</center>')

    return uhtml


def box_output(box):
    """ Formats a query from PlayerBoxTable that
        represents a user's owned units.
    """
    box_text = ''
    header_text = monospace_table_row([('ID', 5),
                                       ('Name', 40),
                                       ('Gacha', 5),
                                       ('Level', 7),
                                       ('Fav.', 4),
                                       ('Showcase', 8)])
    header_text += '\n' + '-'*85
    for u in box:
        fav = 'Yes' if u.favorited else 'No'
        showcase = u.showcase if u.showcase else 'No'

        box_text += monospace_table_row([(u.id, 5),
                                         (u.name, 40),
                                         (u.gacha.upper(), 5),
                                         (f'Lvl {u.unit_level}', 7),
                                         (fav, 4),
                                         (showcase, 8)])
        box_text += '\n'

    if not box_text:
        box_text = 'Currently empty...'

    all_text = f'{header_text}\n{box_text}'

    r = requests.post(const.PASTIE_API, data=all_text)

    msg = 'Could not generate box. Please try again later.'
    if r.status_code == 200:
        url = json.loads(r.text)['key']
        msg = f'https://pastie.io/raw/{url}'

    return msg


class GachaManager:
    def __init__(self, gachas=const.GACHAS):

        self.gacha_db = peewee.SqliteDatabase(const.GACHADBFILE)
        try:
            self.gacha_db.connect()
        except peewee.OperationalError as e:
            print(e)
            pass

        self.player_db = peewee.SqliteDatabase(const.GPLAYERDBFILE)
        try:
            self.player_db.connect()
        except peewee.OperationalError as e:
            print(e)
            pass

        self.gachas = {}
        for g in gachas:
            self.gachas[g] = Gacha(g)

        self.current_banners = []


    def player_add(self, username):
        PlayerAccInfoTable.create(username=username)

        player_box = type(username, (PlayerBoxTable,), {})
        player_box.create_table()


    def player_check(self, username):
        q = PlayerAccInfoTable.select().where(PlayerAccInfoTable.username == username)
        if q.exists():
            return True

        return False


    def player_info(self, username):
        """ Returns player info. Assumes player exists. """
        q = PlayerAccInfoTable.select().where(PlayerAccInfoTable.username == username)
        return q[0]


    def profile(self, username):
        player = self.player_info(username)
        box = type(username, (PlayerBoxTable,), {})

        showcases = box.select().where(box.showcase).order_by(box.showcase)
        sc_infos = [(const.BLANK_IMG, '', '', 1)] * 5
        for i, sc in enumerate(range(min(5, len(showcases)))):
            sc_infos[i] = (sc.full_img, sc.name, sc.unit_url, sc.unit_level)

        showcase_uhtml = ''
        for i, info in enumerate(sc_infos):
            img_height = 100 if i == 0 else 70
            showcase_uhtml += ('<td style=\'padding:5px; border-right:3px '
                              f'solid #858585\'><a href=\'{sc_infos[0][2]}\'>'
                              f'{gen_uhtml_img_code(sc_infos[0][0], height_resize=img_height, alt=sc_infos[0][1])}'
                               '</a></td>')

        uhtml = ('<table style=\'border:3px solid #858585; border-spacing:0px;'
                 'border-radius:10px; background-image:url(https://i.imgur.com/c68ilQW.png);'
                 'background-size:cover\'><thead><tr>'
                 '<th style=\'font-size:14px; padding:5px; border-right:3px '
                f'solid #858585\'>{username}</th>'
                 '<th colspan=2 align=left style=\'font-weight:normal; color:#858585; padding-left: 5px\'>'
                f'Rolls: {player.roll_currency} | Rerolls: {player.reroll_currency}</th></tr>'
                f'<tr>{showcase_uhtml}</tr></table>')


    def player_box(self, username):
        pb = type(username, (PlayerBoxTable,), {})
        box = pb.select().order_by(pb.favorited.desc(), pb.unit_id.asc())
        return box_output(box)


    def add_rolls(self):
        q = (PlayerAccInfoTable
                .update({PlayerAccInfoTable.roll_currency:
                            PlayerAccInfoTable.roll_currency + HOURLY_ROLLS}))
        q.execute()


    def roll(self, username, gacha, num_rolls=1):
        pulls = self.gachas[gacha].roll(username, num_rolls=num_rolls)
        if pulls:
            return roll_uhtml(username, gacha, pulls)
        else:
            return


    def favorite(self, username, ids):
        pb = type(username, (PlayerBoxTable,), {})
        return (pb.update(favorited=True)
                  .where((pb.id << ids) & ~pb.favorited)
                  .execute())


    def unfavorite(self, username, ids):
        pb = type(username, (PlayerBoxTable,), {})
        return (pb.update(favorited=False)
                  .where((pb.id << ids) & pb.favorited)
                  .execute())


    def showcase(self, username, uid, place):
        pb = type(username, (PlayerBoxTable,), {})
        exists = (pb.select()
                    .where(pb.showcase == place))
        if exists:
            if exists[0].id != uid:
                self.unshowcase(username, exists[0].id)

        return (pb.update(favorited=True, showcase=place)
                  .where(pb.id == uid)
                  .execute())


    def unshowcase(self, username, uid):
        pb = type(username, (PlayerBoxTable,), {})
        return (pb.update(showcase=0)
                  .where((pb.id == uid) & pb.showcase)
                  .execute())


    def can_merge(self, username, ids=None):
        pb = type(username, (PlayerBoxTable,), {})

        unit_id_rows = None
        if ids:
            unit_id_rows = (pb.select(pb.gacha, pb.unit_id)
                            .where(~pb.favorited & (pb.id << ids))
                            .group_by(pb.gacha, pb.unit_id)
                            .having(peewee.fn.COUNT(pb.unit_id) >= 3))
        else:
            unit_id_rows = (pb.select(pb.gacha, pb.unit_id)
                            .where(~pb.favorited)
                            .group_by(pb.gacha, pb.unit_id)
                            .having(peewee.fn.COUNT(pb.unit_id) >= 3))

        valid_units = []
        for uir in unit_id_rows:
            if not str(uir.unit_id).endswith('5'):
                valid_units.append((uir.gacha, uir.unit_id))

        vl = ValuesList(valid_units)
        return EnclosedNodeList([vl])


    def merge(self, username, ids=None):
        pb = type(username, (PlayerBoxTable,), {})

        valid_units = self.can_merge(username, ids)

        if ids:
            to_merge = (pb.select()
                          .where((Tuple(pb.gacha, pb.unit_id).in_(valid_units)) &
                                 (pb.id << ids))
                          .order_by(pb.unit_id))
        else:
            to_merge = (pb.select()
                          .where(Tuple(pb.gacha, pb.unit_id).in_(valid_units))
                          .order_by(pb.unit_id))

        grouped_units = {}
        curr_unit = []
        curr_id = None
        for row in to_merge:
            if row.gacha not in grouped_units:
                grouped_units[row.gacha] = {}

            if curr_id != (row.gacha, row.unit_id):
                if curr_unit:
                    grouped_units[curr_id[0]][curr_id[1]] = curr_unit
                curr_unit = []
                curr_id = (row.gacha, row.unit_id)

            curr_unit.append(row)

        if curr_unit:
            grouped_units[curr_id[0]][curr_id[1]] = curr_unit

        to_add = {}
        to_delete = []
        for gacha in grouped_units:
            to_add[gacha] = []

            for uid in grouped_units[gacha]:
                num_merged = len(grouped_units[gacha][uid]) // 3
                to_add[gacha] += [round(uid + 0.1, 1)] * num_merged
                for u in grouped_units[gacha][uid][:(num_merged * 3)]:
                    to_delete.append((gacha, u.id))
        
        add_query = []
        for gacha in to_add:
            add_query += self.gachas[gacha].gen_unit_infos(to_add[gacha])

        delete_query = EnclosedNodeList([ValuesList(to_delete)])

        pb.insert_many(add_query).execute()
        return pb.delete().where(Tuple(pb.gacha, pb.id).in_(delete_query)).execute()


class Gacha:
    def __init__(self, franchise):
        self.franchise = franchise

        self.table = None
        if franchise == 'fgo':
            self.table = FgoTable
        elif franchise == 'pad':
            self.table = PadTable


    def unit_dict(self, unit_info):
        img_url_pvs = json.loads(unit_info.img_url_pv)
        img_url_fulls = json.loads(unit_info.img_url_full)
        asc = int(10 * round(unit_info.unit_id % 1, 1)) + 1
        return {'gacha': self.franchise,
                'unit_id': unit_info.unit_id,
                'name': unit_info.name,
                'unit_url': unit_info.unit_url,
                'pv_img': img_url_pvs[-1],
                'full_img': img_url_fulls[-1],
                'unit_level': asc}


    def gen_unit_infos(self, unit_ids):
        to_box = []
        unit_infos = self.table.select().where(self.table.unit_id << unit_ids)
        for uid in unit_ids:
            unit = None
            for info in unit_infos:
                if info.unit_id == uid:
                    unit = info
                    break

            to_box.append(self.unit_dict(unit))
        
        return to_box


    def roll(self, username, num_rolls=1):
        user_info = PlayerAccInfoTable.select().where(PlayerAccInfoTable.username == username)[0]
        user_rolls = user_info.roll_currency

        if user_rolls < num_rolls:
            return

        pool = self.table.select()

        weights = []
        for u in pool:
            weights.append(u.base_pull_rate)

        pulls = random.choices(pool, weights=weights, k=num_rolls)

        to_box = []
        for p in pulls:
            img_url_pvs = json.loads(p.img_url_pv)
            img_url_fulls = json.loads(p.img_url_full)
            to_box.append(self.unit_dict(p))

        player_box = type(username, (PlayerBoxTable,), {})
        player_box.insert_many(to_box).execute()

        new_rolls = user_rolls - num_rolls
        (PlayerAccInfoTable
            .update({PlayerAccInfoTable.roll_currency: new_rolls})
            .where(PlayerAccInfoTable.username == username)
            .execute())

        return pulls