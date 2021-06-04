import argparse
import sys

from peewee import *
from playhouse.migrate import *
from playhouse.sqliteq import SqliteQueueDatabase

import common.constants as const

# Table management

def add_column(db, table, col_name, col_type):
    migrator = SqliteMigrator(db)
    migrate(migrator.add_column(table, col_name, col_type))


def drop_column(db, table, col_name):
    migrator = SqliteMigrator(db)
    migrate(migrator.drop_column(table, col_name))


def add_to_db(db, table, **kwargs):
    try:
        db.connect()
    except OperationalError as e:
        print(e)
        pass
    new_row = table(**kwargs)
    print(kwargs)
    print(new_row.save(force_insert=True))


# User DBs
PLAYER_DB = SqliteQueueDatabase(const.GPLAYERDBFILE, pragmas={'journal_mode': 'wal'})

class PlayerAccInfoTable(Model):
    username = CharField(primary_key=True)
    roll_currency = IntegerField(default=100)
    level_currency = IntegerField(default=10000)
    reroll_currency = IntegerField(default=0)

    class Meta:
        database = PLAYER_DB
        table_name = 'metadata'


class PlayerBoxTable(Model):
    gacha = CharField()
    unit_id = FloatField()
    name = CharField()
    unit_url = CharField()
    pv_img = CharField()
    full_img = CharField()
    unit_level = IntegerField(default=1)
    favorited = BooleanField(default=False)
    showcase = IntegerField(default=0)

    class Meta:
        database = PLAYER_DB


# Gacha DBs
GACHA_DB = SqliteDatabase(const.GACHADBFILE)

class AllGachasTable(Model):
    slug = CharField()
    full_name = CharField()

    class Meta:
        database = GACHA_DB
        table_name = 'gachas'


class GachaTable(Model):
    unit_id = FloatField(primary_key=True)
    name = CharField()
    unit_url = CharField()
    img_url_pv = CharField()
    img_url_full = CharField()
    unit_type = CharField()
    base_pull_rate = FloatField()
    base_feed_amount = IntegerField()
    exp_curve = IntegerField()
    
    class Meta:
        database = GACHA_DB


class PadTable(GachaTable):
    evo_from = CharField(null=True)
    evo_to = CharField(null=True)

    class Meta:
        table_name = 'pad'


class FgoTable(GachaTable):
    evo_from = IntegerField(null=True)
    evo_to = IntegerField(null=True)

    class Meta:
        table_name = 'fgo'
