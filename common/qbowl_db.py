from peewee import *
from playhouse.migrate import *


QB_DB = SqliteDatabase('data/quizbowl.db')

class QuestionTable(Model):
    qid = IntegerField(primary_key=True)
    question = CharField()
    question_type = CharField()
    answer = CharField()
    prev_b = IntegerField(null=True)
    next_b = IntegerField(null=True)

    class Meta:
        database = QB_DB
        table_name = 'questions'
