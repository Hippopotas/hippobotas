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
VTUBE_ROOM = 'vtubers'
PEARY_ROOM = 'bikinibottom'
ARTS_ROOM = 'artsculture'
KPOP_ROOM = 'kpop'
SMASH_ROOM = 'smashbros'
WRESTLING_ROOM = 'prowrestling'

MAX_FRIENDS = 100

SIMPLE_COMMANDS = ['help', 'dab', 'owo', 'google', 'joogle', 'bing', 'jing', 'jibun',
                   'mal_add', 'mal_set', 'wpm_reset', 'wpm']
UHTML_COMMANDS = ['plebs', 'calendar', 'birthday', 'wpm_top',
                  'anime', 'manga', 'randanime', 'randmanga', 'mal']

TIMER_USER = 'T*'

JIKAN_API = 'https://api.jikan.moe/v4/'
MAL_API = 'https://api.myanimelist.net/v2/'
DEX_API = 'https://api.mangadex.org/'
ANILIST_API = 'https://graphql.anilist.co/'
DDRAGON_API = 'http://ddragon.leagueoflegends.com/cdn/11.14.1/data/en_US/'
DDRAGON_IMG = 'http://ddragon.leagueoflegends.com/cdn/11.14.1/img/'
DDRAGON_SPL = 'http://ddragon.leagueoflegends.com/cdn/img/champion/loading/'
STEAM_API = 'http://api.steampowered.com/'
IGDB_API = 'https://api.igdb.com/v4/'
PASTIE_API = 'https://pastie.io/documents'
OPENTDB_API = 'https://opentdb.com/api.php'

MTG_API = 'https://api.scryfall.com/cards/search?q='
PTCG_API = 'https://api.pokemontcg.io/v2/cards?q=name:'
YGO_API = 'https://db.ygoprodeck.com/api/v7/cardinfo.php?fname='

BANLISTFILE = os.path.join(BASE_DIR, 'data/banlist.json')
BIRTHDAYFILE = os.path.join(BASE_DIR, 'data/birthdays.json')
CALENDARFILE = os.path.join(BASE_DIR, 'data/calendar.json')
FRIENDFILE = os.path.join(BASE_DIR, 'data/friends.json')
SENTENCEFILE = os.path.join(BASE_DIR, 'data/sentences.txt')
SUCKFILE = os.path.join(BASE_DIR, 'data/suck.txt')
TOPICFILE = os.path.join(BASE_DIR, 'data/topics.json')
WPMFILE = os.path.join(BASE_DIR, 'data/wpm.txt')

ROOMDATA_DB = os.path.join(BASE_DIR, 'data/roomdata.db')

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

ANILIST_MEDIA = ['TV',
                 'TV_SHORT',
                 'MOVIE',
                 'SPECIAL',
                 'OVA',
                 'ONA',
                 'MANGA',
                 'NOVEL',
                 'ONE_SHOT']

ANILIST_GENRES = ["Action",
                  "Adventure",
                  "Comedy",
                  "Drama",
                  "Ecchi",
                  "Fantasy",
                  "Horror",
                  "Mahou Shoujo",
                  "Mecha",
                  "Music",
                  "Mystery",
                  "Psychological",
                  "Romance",
                  "Sci-Fi",
                  "Slice of Life",
                  "Sports",
                  "Supernatural",
                  "Thriller"]

ANILIST_TAGS = {'4-koma': 206,
                'Achromatic': 710,
                'Achronological Order': 156,
                'Acting': 548,
                'Adoption': 1052,
                'Advertisement': 505,
                'Afterlife': 147,
                'Age Gap': 138,
                'Age Regression': 488,
                'Agender': 334,
                'Agriculture': 909,
                'Airsoft': 167,
                'Aliens': 191,
                'Alternate Universe': 146,
                'American Football': 314,
                'Amnesia': 240,
                'Anachronism': 490,
                'Angels': 1068,
                'Animals': 433,
                'Anthology': 471,
                'Anti-Hero': 104,
                'Archery': 251,
                'Artificial Intelligence': 517,
                'Asexual': 622,
                'Assassins': 322,
                'Astronomy': 623,
                'Athletics': 264,
                'Augmented Reality': 364,
                'Autobiographical': 519,
                'Aviation': 355,
                'Badminton': 235,
                'Band': 110,
                'Bar': 161,
                'Baseball': 149,
                'Basketball': 192,
                'Battle Royale': 101,
                'Biographical': 239,
                'Bisexual': 294,
                'Body Swapping': 154,
                'Boxing': 169,
                "Boys' Love": 75,
                'Bullying': 171,
                'Butler': 812,
                'Calligraphy': 204,
                'Card Battle': 178,
                'Cars': 10,
                'Centaur': 632,
                'CGI': 90,
                'Cheerleading': 646,
                'Chibi': 324,
                'Chimera': 774,
                'Chuunibyou': 267,
                'Circus': 476,
                'Classic Literature': 227,
                'College': 404,
                'Coming of Age': 102,
                'Conspiracy': 456,
                'Cosmic Horror': 636,
                'Cosplay': 328,
                'Crime': 648,
                'Crossdressing': 186,
                'Crossover': 158,
                'Cult': 586,
                'Cultivation': 326,
                'Cute Boys Doing Cute Things': 1063,
                'Cute Girls Doing Cute Things': 92,
                'Cyberpunk': 108,
                'Cyborg': 801,
                'Cycling': 151,
                'Dancing': 209,
                'Death Game': 615,
                'Delinquents': 395,
                'Demons': 15,
                'Denpa': 654,
                'Detective': 694,
                'Dinosaurs': 704,
                'Dissociative Identities': 536,
                'Dragons': 224,
                'Drawing': 118,
                'Dullahan': 658,
                'Dungeon': 604,
                'Dystopian': 217,
                'E-Sports': 792,
                'Economics': 248,
                'Educational': 140,
                'Elf': 598,
                'Ensemble Cast': 105,
                'Environmental': 342,
                'Episodic': 193,
                'Espionage': 310,
                'Fairy Tale': 400,
                'Family Life': 87,
                'Fashion': 410,
                'Female Harem': 23,
                'Female Protagonist': 98,
                'Fencing': 1132,
                'Firefighters': 613,
                'Fishing': 212,
                'Fitness': 170,
                'Flash': 242,
                'Food': 142,
                'Football': 148,
                'Foreign': 198,
                'Fugitive': 226,
                'Full CGI': 89,
                'Full Color': 207,
                'Gambling': 91,
                'Gangs': 106,
                'Gender Bending': 77,
                'Ghost': 220,
                'Go': 443,
                'Goblin': 480,
                'Gods': 253,
                'Golf': 532,
                'Guns': 157,
                'Gyaru': 356,
                'Henshin': 99,
                'Heterosexual': 1045,
                'Hikikomori': 282,
                'Historical': 25,
                'Ice Skating': 228,
                'Idol': 115,
                'Isekai': 244,
                'Iyashikei': 81,
                'Josei': 27,
                'Judo': 1105,
                'Kaiju': 276,
                'Karuta': 182,
                'Kemonomimi': 254,
                'Kids': 28,
                'Kuudere': 779,
                'Lacrosse': 437,
                'Language Barrier': 516,
                'LGBTQ+ Themes': 483,
                'Lost Civilization': 466,
                'Love Triangle': 139,
                'Mafia': 107,
                'Magic': 29,
                'Mahjong': 117,
                'Maids': 249,
                'Make-up': 1140,
                'Male Harem': 123,
                'Male Protagonist': 82,
                'Martial Arts': 30,
                'Medicine': 659,
                'Memory Manipulation': 365,
                'Mermaid': 558,
                'Meta': 144,
                'Military': 34,
                'Monster Boy': 1090,
                'Monster Girl': 259,
                'Mopeds': 176,
                'Motorcycles': 173,
                'Musical': 265,
                'Mythology': 208,
                'Nekomimi': 113,
                'Ninja': 255,
                'No Dialogue': 341,
                'Noir': 327,
                'Nun': 614,
                'Office Lady': 653,
                'Ojou-sama': 780,
                'Otaku Culture': 97,
                'Outdoor': 262,
                'Pandemic': 874,
                'Parkour': 949,
                'Parody': 39,
                'Philosophy': 391,
                'Photography': 195,
                'Pirates': 201,
                'Poker': 183,
                'Police': 40,
                'Politics': 103,
                'Post-Apocalyptic': 93,
                'POV': 215,
                'Primarily Adult Cast': 109,
                'Primarily Child Cast': 446,
                'Primarily Female Cast': 86,
                'Primarily Male Cast': 88,
                'Puppetry': 325,
                'Rakugo': 481,
                'Real Robot': 160,
                'Rehabilitation': 311,
                'Reincarnation': 243,
                'Religion': 1091,
                'Revenge': 252,
                'Robots': 175,
                'Rotoscoping': 683,
                'Rugby': 221,
                'Rural': 250,
                'Samurai': 291,
                'Satire': 80,
                'School': 46,
                'School Club': 84,
                'Scuba Diving': 811,
                'Seinen': 50,
                'Shapeshifting': 772,
                'Ships': 305,
                'Shogi': 121,
                'Shoujo': 53,
                'Shounen': 56,
                'Shrine Maiden': 468,
                'Skateboarding': 809,
                'Skeleton': 499,
                'Slapstick': 83,
                'Slavery': 247,
                'Software Development': 386,
                'Space': 63,
                'Space Opera': 162,
                'Steampunk': 95,
                'Stop Motion': 323,
                'Succubus': 665,
                'Sumo': 1080,
                'Super Power': 66,
                'Super Robot': 159,
                'Superhero': 172,
                'Surfing': 678,
                'Surreal Comedy': 281,
                'Survival': 143,
                'Swimming': 150,
                'Swordplay': 43,
                'Table Tennis': 120,
                'Tanks': 174,
                'Tanned Skin': 335,
                'Teacher': 165,
                "Teens' Love": 649,
                'Tennis': 194,
                'Terrorism': 285,
                'Time Manipulation': 96,
                'Time Skip': 153,
                'Tokusatsu': 513,
                'Tomboy': 931,
                'Torture': 1121,
                'Tragedy': 85,
                'Trains': 122,
                'Triads': 214,
                'Tsundere': 164,
                'Twins': 494,
                'Urban': 595,
                'Urban Fantasy': 321,
                'Vampire': 74,
                'Video Games': 308,
                'Vikings': 618,
                'Villainess': 857,
                'Virtual World': 112,
                'Volleyball': 116,
                'VTuber': 1047,
                'War': 111,
                'Werewolf': 534,
                'Witch': 179,
                'Work': 145,
                'Wrestling': 231,
                'Writing': 394,
                'Wuxia': 303,
                'Yakuza': 199,
                'Yandere': 163,
                'Youkai': 233,
                'Yuri': 76,
                'Zombie': 152}
