from bot import mal_arg_parser

print(mal_arg_parser('aa bb -r', 'test2').username)
print(mal_arg_parser('aaaaa -r', 'test2').username)
print(mal_arg_parser('aaaaa -r anime', 'test2').roll)
print(mal_arg_parser('', 'test2').roll == None)