import os

# Base directory of the bot.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

ANIME_ROOM = 'animeandmanga'
GACHA_ROOM = 'gacha'
LEAGUE_ROOM = 'leagueoflegends'
SCHOL_ROOM = 'scholastic'
SPORTS_ROOM = 'sports'
TCG_ROOM = 'tcgtabletop'
VG_ROOM = 'videogames'
PEARY_ROOM = 'bikinibottom'

MAX_FRIENDS = 100

SIMPLE_COMMANDS = ['help', 'dab', 'owo', 'google', 'joogle', 'bing', 'jing', 'jibun']
UHTML_COMMANDS = ['plebs', 'calendar', 'birthday']

TIMER_USER = 'T*'

JIKAN_API = 'https://api.jikan.moe/v3/'
JIKAN_SEARCH_API = 'https://api.jikan.moe/v3/search/'
DEX_API = 'https://api.mangadex.org/'
DDRAGON_API = 'http://ddragon.leagueoflegends.com/cdn/11.14.1/data/en_US/'
DDRAGON_IMG = 'http://ddragon.leagueoflegends.com/cdn/11.14.1/img/'
DDRAGON_SPL = 'http://ddragon.leagueoflegends.com/cdn/img/champion/loading/'
STEAM_API = 'http://api.steampowered.com/'
IGDB_API = 'https://api.igdb.com/v4/'
PASTIE_API = 'https://pastie.io/documents'

MTG_API = 'https://api.scryfall.com/cards/search?q='
PTCG_API = 'https://api.pokemontcg.io/v2/cards?q=name:'
YGO_API = 'https://db.ygoprodeck.com/api/v7/cardinfo.php?fname='

BANLISTFILE = os.path.join(BASE_DIR, 'data/banlist.json')
BIRTHDAYFILE = os.path.join(BASE_DIR, 'data/birthdays.json')
CALENDARFILE = os.path.join(BASE_DIR, 'data/calendar.json')
EMOTEFILE = os.path.join(BASE_DIR, 'data/emotes.json')
FRIENDFILE = os.path.join(BASE_DIR, 'data/friends.json')
SENTENCEFILE = os.path.join(BASE_DIR, 'data/sentences.txt')
SUCKFILE = os.path.join(BASE_DIR, 'data/suck.txt')
TOPICFILE = os.path.join(BASE_DIR, 'data/topics.json')
WPMFILE = os.path.join(BASE_DIR, 'data/wpm.txt')

MALFILE = os.path.join(BASE_DIR, 'data/mal.txt')
STEAMFILE = os.path.join(BASE_DIR, 'data/steam.txt')

GACHAINFOFILE = os.path.join(BASE_DIR, 'data/gacha/gacha.json')
GACHADBFILE = os.path.join(BASE_DIR, 'data/gacha/gachas.db')

MAL_URL = 'https://myanimelist.net/'
MAL_IMG_URL = 'https://cdn.myanimelist.net/images/'

IMG_NOT_FOUND = 'https://i.imgur.com/Mlw966x.png'
BLANK_IMG = 'https://i.imgur.com/skY68qe.png'
PLEB_URL = 'https://i.imgur.com/c9nyFqJ.png'

METRONOME_BATTLE = 'gen8metronomebattle'

OWNER = 'hippopotas'

GACHAS = ['fgo']

LEAGUE_CATS = ['skins', 'spells', 'items']

MAL_GENRES = {'action': 1,
              'adventure': 2,
              'cars': 3,
              'comedy': 4,
              'dementia': 5,
              'demons': 6,
              'mystery': 7,
              'drama': 8,
              'ecchi': 9,
              'fantasy': 10,
              'game': 11,
              'historical': 13,
              'horror': 14,
              'kids': 15,
              'magic': 16,
              'martialarts': 17,
              'mecha': 18,
              'music': 19,
              'parody': 20,
              'samurai': 21,
              'romance': 22,
              'school': 23,
              'scifi': 24,
              'shoujo': 25,
              'shoujoai': 26,
              'shounen': 27,
              'shounenai': 28,
              'space': 29,
              'sports': 30,
              'superpower': 31,
              'vampire': 32,
              'yaoi': 33,
              'yuri': 34,
              'harem': 35,
              'sliceoflife': 36,
              'supernatural': 37,
              'military': 38,
              'police': 39,
              'psychological':40}

ANIME_GENRES = {**MAL_GENRES, 'thriller': 41, 'seinen': 42, 'josei': 43}
MANGA_GENRES = {**MAL_GENRES, 'seinen': 41, 'josei': 42, 'genderbender': 44, 'thriller': 45}

ANIME_TYPES = ['anime', 'tv', 'ova', 'movie', 'special', 'ona', 'music']
MANGA_TYPES = ['manga', 'novel', 'oneshot', 'manhwa', 'manhua']

VG_GENRES = ['fighting',
             'shooter',
             'music',
             'platform',
             'puzzle',
             'racing',
             'real-time-strategy-rts',
             'role-playing-rpg',
             'simulator',
             'sport',
             'strategy',
             'turn-based-strategy-tbs',
             'tactical',
             'quiz-trivia',
             'hack-and-slash-beat-em-up',
             'pinball',
             'adventure',
             'arcade',
             'visual-novel',
             'indie',
             'card-and-board-game',
             'moba',
             'point-and-click']

VG_THEMES = ['thriller',
             'science-fiction',
             'action',
             'horror',
             'survival',
             'fantasy',
             'historical',
             'stealth',
             'comedy',
             'business',
             'drama',
             'non-fiction',
             'kids',
             'sandbox',
             'open-world',
             'warfare',
             '4x-explore-expand-exploit-and-exterminate',
             'educational',
             'mystery',
             'party',
             'romance']

MAL_LAST_PAGES = {
    "anime": {
        "anime": {
            "action": 81,
            "adventure": 62,
            "cars": 3,
            "comedy": 125,
            "dementia": 11,
            "demons": 11,
            "mystery": 15,
            "drama": 54,
            "ecchi": 16,
            "fantasy": 69,
            "game": 9,
            "historical": 24,
            "horror": 10,
            "kids": 61,
            "magic": 23,
            "martialarts": 10,
            "mecha": 23,
            "music": 48,
            "parody": 14,
            "samurai": 5,
            "romance": 39,
            "school": 34,
            "scifi": 54,
            "shoujo": 14,
            "shoujoai": 2,
            "shounen": 40,
            "shounenai": 3,
            "space": 11,
            "sports": 15,
            "superpower": 13,
            "vampire": 3,
            "yaoi": 1,
            "yuri": 1,
            "harem": 9,
            "sliceoflife": 40,
            "supernatural": 31,
            "military": 12,
            "police": 6,
            "psychological": 8,
            "thriller": 3,
            "seinen": 17,
            "josei": 2,
            "": 367
        },
        "tv": {
            "action": 30,
            "adventure": 25,
            "cars": 2,
            "comedy": 50,
            "dementia": 1,
            "demons": 4,
            "mystery": 7,
            "drama": 19,
            "ecchi": 7,
            "fantasy": 23,
            "game": 4,
            "historical": 8,
            "horror": 3,
            "kids": 21,
            "magic": 10,
            "martialarts": 3,
            "mecha": 9,
            "music": 5,
            "parody": 4,
            "samurai": 2,
            "romance": 17,
            "school": 16,
            "scifi": 20,
            "shoujo": 7,
            "shoujoai": 1,
            "shounen": 18,
            "shounenai": 1,
            "space": 4,
            "sports": 7,
            "superpower": 5,
            "vampire": 2,
            "yaoi": -1,
            "yuri": -1,
            "harem": 5,
            "sliceoflife": 18,
            "supernatural": 12,
            "military": 4,
            "police": 2,
            "psychological": 3,
            "thriller": 2,
            "seinen": 8,
            "josei": 2,
            "": 107
        },
        "ova": {
            "action": 15,
            "adventure": 9,
            "cars": 1,
            "comedy": 19,
            "dementia": 1,
            "demons": 4,
            "mystery": 3,
            "drama": 13,
            "ecchi": 5,
            "fantasy": 13,
            "game": 1,
            "historical": 4,
            "horror": 3,
            "kids": 12,
            "magic": 5,
            "martialarts": 2,
            "mecha": 6,
            "music": 2,
            "parody": 3,
            "samurai": 1,
            "romance": 10,
            "school": 7,
            "scifi": 12,
            "shoujo": 3,
            "shoujoai": 1,
            "shounen": 8,
            "shounenai": 1,
            "space": 3,
            "sports": 3,
            "superpower": 3,
            "vampire": 1,
            "yaoi": 1,
            "yuri": 1,
            "harem": 3,
            "sliceoflife": 4,
            "supernatural": 7,
            "military": 3,
            "police": 2,
            "psychological": 2,
            "thriller": 1,
            "seinen": 4,
            "josei": 1,
            "": 79
        },
        "movie": {
            "action": 16,
            "adventure": 16,
            "cars": 1,
            "comedy": 18,
            "dementia": 7,
            "demons": 2,
            "mystery": 3,
            "drama": 14,
            "ecchi": 1,
            "fantasy": 16,
            "game": 1,
            "historical": 6,
            "horror": 2,
            "kids": 12,
            "magic": 4,
            "martialarts": 2,
            "mecha": 5,
            "music": 4,
            "parody": 2,
            "samurai": 1,
            "romance": 5,
            "school": 3,
            "scifi": 11,
            "shoujo": 3,
            "shoujoai": 1,
            "shounen": 8,
            "shounenai": 1,
            "space": 3,
            "sports": 3,
            "superpower": 3,
            "vampire": 1,
            "yaoi": 1,
            "yuri": -1,
            "harem": 1,
            "sliceoflife": 5,
            "supernatural": 5,
            "military": 4,
            "police": 2,
            "psychological": 2,
            "thriller": 1,
            "seinen": 3,
            "josei": 1,
            "": 64
        },
        "special": {
            "action": 10,
            "adventure": 8,
            "cars": 1,
            "comedy": 23,
            "dementia": 1,
            "demons": 2,
            "mystery": 3,
            "drama": 6,
            "ecchi": 4,
            "fantasy": 8,
            "game": 2,
            "historical": 3,
            "horror": 1,
            "kids": 4,
            "magic": 3,
            "martialarts": 1,
            "mecha": 3,
            "music": 3,
            "parody": 4,
            "samurai": 1,
            "romance": 5,
            "school": 6,
            "scifi": 7,
            "shoujo": 2,
            "shoujoai": 1,
            "shounen": 6,
            "shounenai": 1,
            "space": 2,
            "sports": 3,
            "superpower": 2,
            "vampire": 1,
            "yaoi": 1,
            "yuri": -1,
            "harem": 1,
            "sliceoflife": 7,
            "supernatural": 4,
            "military": 2,
            "police": 1,
            "psychological": 1,
            "thriller": 1,
            "seinen": 3,
            "josei": 1,
            "": 46
        },
        "ona": {
            "action": 10,
            "adventure": 5,
            "cars": 1,
            "comedy": 16,
            "dementia": 2,
            "demons": 2,
            "mystery": 2,
            "drama": 4,
            "ecchi": 1,
            "fantasy": 10,
            "game": 2,
            "historical": 4,
            "horror": 2,
            "kids": 4,
            "magic": 2,
            "martialarts": 3,
            "mecha": 2,
            "music": 4,
            "parody": 4,
            "samurai": 1,
            "romance": 4,
            "school": 3,
            "scifi": 5,
            "shoujo": 1,
            "shoujoai": 1,
            "shounen": 2,
            "shounenai": 1,
            "space": 1,
            "sports": 1,
            "superpower": 1,
            "vampire": 1,
            "yaoi": 1,
            "yuri": -1,
            "harem": 1,
            "sliceoflife": 7,
            "supernatural": 4,
            "military": 1,
            "police": 1,
            "psychological": 1,
            "thriller": 1,
            "seinen": 1,
            "josei": 1,
            "": 42
        },
        "music": {
            "action": 1,
            "adventure": 1,
            "cars": 1,
            "comedy": 1,
            "dementia": 2,
            "demons": 1,
            "mystery": 1,
            "drama": 2,
            "ecchi": 1,
            "fantasy": 2,
            "game": 1,
            "historical": 1,
            "horror": 1,
            "kids": 10,
            "magic": 1,
            "martialarts": -1,
            "mecha": 1,
            "music": 31,
            "parody": 1,
            "samurai": 1,
            "romance": 1,
            "school": 1,
            "scifi": 1,
            "shoujo": 1,
            "shoujoai": -1,
            "shounen": -1,
            "shounenai": -1,
            "space": 1,
            "sports": 1,
            "superpower": 1,
            "vampire": 1,
            "yaoi": -1,
            "yuri": -1,
            "harem": 1,
            "sliceoflife": 1,
            "supernatural": 1,
            "military": 1,
            "police": 1,
            "psychological": 1,
            "thriller": -1,
            "seinen": 1,
            "josei": -1,
            "": 31
        },
        "": {
            "action": 81,
            "adventure": 62,
            "cars": 3,
            "comedy": 125,
            "dementia": 11,
            "demons": 11,
            "mystery": 15,
            "drama": 54,
            "ecchi": 16,
            "fantasy": 69,
            "game": 9,
            "historical": 24,
            "horror": 10,
            "kids": 61,
            "magic": 23,
            "martialarts": 10,
            "mecha": 23,
            "music": 48,
            "parody": 14,
            "samurai": 5,
            "romance": 39,
            "school": 34,
            "scifi": 54,
            "shoujo": 14,
            "shoujoai": 2,
            "shounen": 40,
            "shounenai": 3,
            "space": 11,
            "sports": 15,
            "superpower": 13,
            "vampire": 3,
            "yaoi": 1,
            "yuri": 1,
            "harem": 9,
            "sliceoflife": 40,
            "supernatural": 31,
            "military": 12,
            "police": 6,
            "psychological": 8,
            "thriller": 3,
            "seinen": 17,
            "josei": 2,
            "": 367
        }
    },
    "manga": {
        "manga": {
            "action": 102,
            "adventure": 48,
            "cars": 2,
            "comedy": 196,
            "dementia": 2,
            "demons": 10,
            "mystery": 34,
            "drama": 132,
            "ecchi": 54,
            "fantasy": 98,
            "game": 6,
            "historical": 36,
            "horror": 26,
            "kids": 5,
            "magic": 16,
            "martialarts": 10,
            "mecha": 11,
            "music": 7,
            "parody": 6,
            "samurai": 4,
            "romance": 203,
            "school": 133,
            "scifi": 44,
            "shoujo": 128,
            "shoujoai": 13,
            "shounen": 93,
            "shounenai": 23,
            "space": 4,
            "sports": 20,
            "superpower": 8,
            "vampire": 6,
            "yaoi": 114,
            "yuri": 8,
            "harem": 18,
            "sliceoflife": 85,
            "supernatural": 86,
            "military": 10,
            "police": 6,
            "psychological": 21,
            "seinen": 127,
            "josei": 42,
            "genderbender": 17,
            "thriller": 5,
            "": 771
        },
        "novel": {
            "action": 37,
            "adventure": 15,
            "cars": -1,
            "comedy": 35,
            "dementia": 1,
            "demons": 2,
            "mystery": 7,
            "drama": 16,
            "ecchi": 15,
            "fantasy": 61,
            "game": 2,
            "historical": 2,
            "horror": 3,
            "kids": -1,
            "magic": 7,
            "martialarts": 1,
            "mecha": 3,
            "music": 1,
            "parody": 1,
            "samurai": 1,
            "romance": 67,
            "school": 38,
            "scifi": 12,
            "shoujo": 5,
            "shoujoai": 1,
            "shounen": 3,
            "shounenai": 1,
            "space": 1,
            "sports": 1,
            "superpower": 3,
            "vampire": 2,
            "yaoi": 4,
            "yuri": 1,
            "harem": 26,
            "sliceoflife": 5,
            "supernatural": 31,
            "military": 3,
            "police": 1,
            "psychological": 3,
            "seinen": 1,
            "josei": 27,
            "genderbender": 3,
            "thriller": 1,
            "": 197
        },
        "oneshot": {
            "action": 7,
            "adventure": 2,
            "cars": 1,
            "comedy": 15,
            "dementia": 1,
            "demons": 1,
            "mystery": 2,
            "drama": 9,
            "ecchi": 4,
            "fantasy": 6,
            "game": 1,
            "historical": 2,
            "horror": 3,
            "kids": 1,
            "magic": 1,
            "martialarts": 1,
            "mecha": 1,
            "music": 1,
            "parody": 1,
            "samurai": 1,
            "romance": 18,
            "school": 13,
            "scifi": 3,
            "shoujo": 15,
            "shoujoai": 3,
            "shounen": 13,
            "shounenai": 3,
            "space": 1,
            "sports": 2,
            "superpower": 1,
            "vampire": 1,
            "yaoi": 6,
            "yuri": 2,
            "harem": 1,
            "sliceoflife": 5,
            "supernatural": 10,
            "military": 1,
            "police": 1,
            "psychological": 2,
            "seinen": 8,
            "josei": 2,
            "genderbender": 3,
            "thriller": 1,
            "": 93
        },
        "manhwa": {
            "action": 5,
            "adventure": 3,
            "cars": -1,
            "comedy": 8,
            "dementia": 1,
            "demons": 1,
            "mystery": 2,
            "drama": 8,
            "ecchi": 1,
            "fantasy": 6,
            "game": 1,
            "historical": 2,
            "horror": 1,
            "kids": 1,
            "magic": 1,
            "martialarts": 2,
            "mecha": 1,
            "music": 1,
            "parody": 1,
            "samurai": -1,
            "romance": 11,
            "school": 4,
            "scifi": 2,
            "shoujo": 8,
            "shoujoai": 1,
            "shounen": 2,
            "shounenai": 1,
            "space": 1,
            "sports": 1,
            "superpower": 1,
            "vampire": 1,
            "yaoi": 1,
            "yuri": 1,
            "harem": 1,
            "sliceoflife": 3,
            "supernatural": 3,
            "military": 1,
            "police": 1,
            "psychological": 2,
            "seinen": 1,
            "josei": 1,
            "genderbender": 1,
            "thriller": 1,
            "": 21
        },
        "manhua": {
            "action": 2,
            "adventure": 2,
            "cars": 1,
            "comedy": 2,
            "dementia": -1,
            "demons": 1,
            "mystery": 1,
            "drama": 2,
            "ecchi": 1,
            "fantasy": 3,
            "game": 1,
            "historical": 2,
            "horror": 1,
            "kids": 1,
            "magic": 1,
            "martialarts": 1,
            "mecha": 1,
            "music": 1,
            "parody": -1,
            "samurai": -1,
            "romance": 3,
            "school": 1,
            "scifi": 1,
            "shoujo": 2,
            "shoujoai": 1,
            "shounen": 1,
            "shounenai": 1,
            "space": -1,
            "sports": 1,
            "superpower": 1,
            "vampire": 1,
            "yaoi": 1,
            "yuri": -1,
            "harem": 1,
            "sliceoflife": 1,
            "supernatural": 1,
            "military": 1,
            "police": 1,
            "psychological": 1,
            "seinen": 1,
            "josei": 1,
            "genderbender": 1,
            "thriller": -1,
            "": 6
        },
        "": {
            "action": 153,
            "adventure": 68,
            "cars": 2,
            "comedy": 257,
            "dementia": 3,
            "demons": 14,
            "mystery": 44,
            "drama": 167,
            "ecchi": 73,
            "fantasy": 174,
            "game": 9,
            "historical": 43,
            "horror": 32,
            "kids": 5,
            "magic": 23,
            "martialarts": 13,
            "mecha": 14,
            "music": 9,
            "parody": 6,
            "samurai": 5,
            "romance": 302,
            "school": 191,
            "scifi": 60,
            "shoujo": 156,
            "shoujoai": 18,
            "shounen": 110,
            "shounenai": 28,
            "space": 5,
            "sports": 23,
            "superpower": 12,
            "vampire": 9,
            "yaoi": 133,
            "yuri": 12,
            "harem": 44,
            "sliceoflife": 98,
            "supernatural": 132,
            "military": 13,
            "police": 7,
            "psychological": 26,
            "seinen": 137,
            "josei": 71,
            "genderbender": 27,
            "thriller": 6,
            "": 1118
        }
    }
