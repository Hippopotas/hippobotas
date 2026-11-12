# hippobotas
PokemonShowdown chat bot in Py3.


_lasciate ogne speranza, voi ch’intrate_


A constant WIP. Lots of things need hardening. Style is a mess. Many crucial files are missing here (mainly scripts and data).

Usage below. Unless noted otherwise, commands work in any room the bot is in. Many also work in PMs, where some take an
extra ROOM argument to say which room you mean.

## GENERAL

### ]help
Displays a link to this page. Alias: ]commands

### ]suck [top]
THIS ONLY WORKS IN PMs. Every time anyone gets a point from this command, a random cooldown between 5 and 30 minutes
is generated before it will award points again. Calling it before this cooldown ends results in your points getting reset to 0.

Also gets you banned from the room if @Beowulf is present.

top: If ]suck top is called in a chatroom, the 5 users with the most sucks are displayed.

### ]birthday [ROOM]
Displays the list of (anime) characters with birthdays today. Submit via https://forms.gle/qfKSeyNtpueTBACn7

ROOM (optional): Only used in PMs. Specifies the room to see the infobox in.

### ]birthday_add [ROOM] NAME LINK IMAGE DATE
ROOM STAFF ONLY! Adds a character to the room's birthdays.

NAME: The character's name. LINK: A page about the character. IMAGE: A picture URL. DATE: The birthday, with no spaces (e.g. March3).

### ]birthday_rm [ROOM] NAME
ROOM STAFF ONLY! Removes a character from the room's birthdays.

### ]calendar [ROOM]
Displays a random picture of the current date (Pacific time) from an anime/manga.

ROOM (optional): Only used in PMs. Specifies the room to see the infobox in.

### ]topic [TOPIC_TEXT]
Announces the room's current topic. Room staff can set a new topic by adding TOPIC_TEXT.

### ]bl_add CATEGORY ITEM
ROOM STAFF ONLY! animeandmanga only. Adds an item to the CATEGORY banlist. Currently supported categories: anime, manga, anotd.
Requires MAL ID number for anime and manga; requires MAL URL for anotd.

### ]bl_rm CATEGORY ITEM
ROOM STAFF ONLY! Removes an item from the CATEGORY banlist. See ]bl_add.

### ]bl_list CATEGORY
ROOM STAFF ONLY! PMs you the banlist for a category.

### ]emote_add EMOTE URL
ROOM OWNER ONLY! Sets a room's EMOTE to display the picture found at URL when called with :EMOTE: (case insensitive).
Note that discord URLs don't work very well, and I would suggest reuploading somewhere else. Alias: ]emote_set

### ]emote_rm EMOTE
ROOM OWNER ONLY! Removes a room's EMOTE (see ]emote_add).

### ]emote_list [ROOM]
Lists a room's emotes.

### ]emote_stats [ROOM]
Returns emote usage stats for a room.

### ]song_add [ROOM] TITLE URL
ROOM STAFF ONLY! Adds the URL to the room's pool of songs.

ROOM (optional): Only used in PMs. Specifies the room to add the song to.

TITLE: The name of the song.

URL: MUST BE A YOUTUBE LINK! The song link.

### ]song_rm [ROOM] TITLE
ROOM STAFF ONLY! Removes a song from a room's song pool.

ROOM (optional): Only used in PMs. Specifies the room to remove the song from.

TITLE: The name of the song to be removed (case insensitive).

### ]song_list [ROOM]
Returns a room's song pool in alphabetical order. Requires + and above in rooms.

ROOM (optional): Only used in PMs. Specifies the room whose songs to list.

### ]randsong [ROOM]
Returns a random song from a room's song pool. Requires + and above in rooms. Alias: ]rand_song

ROOM (optional): Only used in PMs. Specifies the room to pick a song from.

### ]typing_test
PMs you a paragraph for you to type as fast as you can. Checks punctuation and capitalization.

### ]wpm [USER]
Displays the highest typing speed achieved by someone.

USER (optional): If specified, this is the person's highest WPM you see. Defaults to yourself.

### ]wpm_top [-s SINGLE]
Displays the fastest typers, sorted by average speed over the past 5 runs. Users with less than 5 runs will not be shown.

-s SINGLE (optional): Sorts by fastest single run instead. Does not exclude users.

### ]wpm_reset
Resets your own typing test data.


## BATTLES

The bot will accept metronome battle challenges. Each user is limited to being in 1 battle vs the bot at a time.


## ANIME/MANGA

Note: Only usable in animeandmanga, by + and above. In PMs, the infobox is shown privately to you if you're in the room.
Series information comes from AniList.

### ]anime SERIES NAME
Displays an infobox about the anime called SERIES NAME.

### ]manga SERIES NAME
See ]anime.

### ]randanime [ROOM] [GENRES]
Displays an infobox about a random anime.

GENRES (optional): The anime will be of at least one of the specified genres, tags or formats (see the animeandmanga
                   trivia categories below).

Example: ]randanime tv shounen police ova
         will return a (shounen or police) (tv or ova) series

### ]randmanga [ROOM] [GENRES]
See ]randanime.


## MAL

Note: Only usable in animeandmanga (and PMs). Uses MAL's official API.

### ]mal_add USERNAME
Sets your MAL username to be USERNAME. This must be a valid MAL account. If your lists are private, the account is
still linked, but the bot can't show or roll from them until you make them public. Alias: ]mal_set

### ]mal [USER] [-r [anime] [manga]]
Displays a summary of a MAL profile or rolls a random series from a MAL profile.

USER (optional): PS user you would like to see the MAL profile of, or roll a series from. If not set, defaults to yourself.

-r (optional): If this is set, this command returns a random series instead. You can specify which
               list(s) it chooses from. The valid categories are 'anime' and 'manga'. If no categories
               are specified, it chooses from both anime and manga lists.

               This only chooses from series with status 'Reading', 'Watching', or 'Completed'.

The profile summary shows completed, current and mean score stats for each list, a top-rated series from each list,
and the cover of the most recently updated series. MAL's API doesn't share avatars or favorites.

Example: ]mal ExampleUser
         will display a htmlbox with a summary of ExampleUser's MAL profile if it has been set with ]mal_add.

Example: ]mal ExampleUser -r anime
         will choose a random anime from ExampleUser's MAL animelist.

### ]anotd [USER]
Rolls a random series for anime of the day. Like ]mal USER -r, but skips series on the anotd banlist.


## STEAM

Note: Only usable in videogames (and PMs). Users below + get the response in PMs.

### ]addsteam STEAM_ID
Sets your Steam account. STEAM_ID is the part after /profiles/ or /id/ in your profile's URL: either the long number
(e.g. 76561197960287930) or your custom URL name. Your Steam display name won't work.

### ]steam [USER] [-r]
Displays a summary of a Steam profile or rolls a random game from a Steam profile. In PMs, it sends the profile link instead.

USER (optional): PS user you would like to see the Steam profile of, or roll a game from. If not set, defaults to yourself.

-r (optional): rolls a random game instead of displaying the profile.

Example: ]steam ExampleUser
         will display a htmlbox with a summary of ExampleUser's Steam profile if it has been set with ]addsteam.

Example: ]steam ExampleUser -r
         will choose a random game from ExampleUser's Steam profile.

### ]vg GAME
Searches IGDB for GAME and displays an infobox about it. Requires + and above in rooms; also works in PMs.


## TCG

Note: Only usable in tcgtabletop, by + and above.

### ]mtg CARD
Displays a Magic: The Gathering card.

### ]ptcg CARD
Displays a Pokemon TCG card.

### ]ygo CARD
Displays a Yu-Gi-Oh! card.


## TRIVIA

Trivia runs in animeandmanga, leagueoflegends, videogames and sports.

### ]trivia start LENGTH [-c CATEGORIES] [-cx EXCLUDECATS] [-d DIFF] [-r] [-q] [-s AUTOSKIP]
Starts a trivia session. Requires % and above.

LENGTH (required): number of questions in the round.

-c CATEGORIES (optional): categories of questions that are allowed. Defaults to all categories if not set. See the "Categories"
                          section for a list of valid categories per room. Multi-word categories can be typed with spaces
                          (e.g. slice of life).

-cx EXCLUDECATS (optional): categories to leave out. Can be combined with -c.

-d DIFF (optional): difficulty of questions in the round, set as an integer from 1 (easy) to 10 (hard). Defaults to 3 if not set.

-r (optional): for animeandmanga room use. Set this to have the difficulty be based on rating of shows.
               Defaults to sort by popularity if not set.

-q (optional): uses quizbowl-style questions instead, with automatic text reveal. Not available in leagueoflegends.

-s AUTOSKIP (optional): number of seconds to wait before automatically skipping each question. Defaults to being 15.
                        0 turns the timer off. Quizbowl timers start once the whole question is shown.

If AniList is rate limiting the bot, new questions wait until it's ready again instead of failing.

Example: ]trivia start 5 -c anime manga -d 9
         will start a round of trivia with 5 questions, choosing from the categories of anime and manga, with difficulty 9.

Example: ]trivia start 10 -r -s 20
         will start a round of trivia with 10 questions, choosing from all room categories, with difficulty 3. Each question
         will be skipped after 20 seconds if not answered correctly.
         If in the animeandmanga room, the difficulty will be based on the rating of the shows.

Example: ]trivia start 10 -c arena_augments items
         in leagueoflegends, mixes Arena augment descriptions with item pictures.

### ]anagrams start LENGTH [OPTIONS]
Like ]trivia start, but each question is a scrambled title to unscramble. The timer defaults to 45 seconds.
Works in animeandmanga and videogames.

### ]trivia stop
Ends the current trivia session. Requires + and above.

### ]trivia end
See ]trivia stop.

### ]trivia skip
Skips the current trivia question. Requires + and above. Alias: ]skip

### ]trivia leaderboard [NUM]
Displays the room leaderboard for trivia if the room has one.

NUM (optional): Shows the top NUM players. Defaults to 5 if not set.

### ]trivia score [USERNAME]
Outputs the trivia score of [USERNAME] if the room has a leaderboard.

USERNAME (optional): Defaults to the caller's username if not set.

### Categories:

leagueoflegends - items, skins, spells, tft_augments, arena_augments \
                  (augment categories are only played when chosen with -c) \
                  tft_augments shows an augment's icon; arena_augments shows its description a few words at a time.

videogames, sports - no categories

animeandmanga - mangadex (MangaDex cover questions), \
               tv, tvshort, movie, special, ova, ona, manga, novel, oneshot, \
               action, adventure, comedy, drama, ecchi, fantasy, horror, mahoushoujo, mecha, music, mystery, psychological, romance, scifi, sliceoflife, sports, supernatural, thriller, \
               4koma, achromatic, achronologicalorder, acting, adoption, advertisement, afterlife, agegap, ageregression, agender, agriculture, airsoft, aliens, alternateuniverse, americanfootball, amnesia, anachronism, angels, animals, anthology, antihero, archery, artificialintelligence, asexual, assassins, astronomy, athletics, augmentedreality, autobiographical, aviation, badminton, band, bar, baseball, basketball, battleroyale, biographical, bisexual, bodyswapping, boxing, boyslove, bullying, butler, calligraphy, cardbattle, cars, centaur, cgi, cheerleading, chibi, chimera, chuunibyou, circus, classicliterature, college, comingofage, conspiracy, cosmichorror, cosplay, crime, crossdressing, crossover, cult, cultivation, cuteboysdoingcutethings, cutegirlsdoingcutethings, cyberpunk, cyborg, cycling, dancing, deathgame, delinquents, demons, denpa, detective, dinosaurs, dissociativeidentities, dragons, drawing, dullahan, dungeon, dystopian, esports, economics, educational, elf, ensemblecast, environmental, episodic, espionage, fairytale, familylife, fashion, femaleharem, femaleprotagonist, fencing, firefighters, fishing, fitness, flash, food, football, foreign, fugitive, fullcgi, fullcolor, gambling, gangs, genderbending, ghost, go, goblin, gods, golf, guns, gyaru, henshin, heterosexual, hikikomori, historical, iceskating, idol, isekai, iyashikei, josei, judo, kaiju, karuta, kemonomimi, kids, kuudere, lacrosse, languagebarrier, lgbtqthemes, lostcivilization, lovetriangle, mafia, magic, mahjong, maids, makeup, maleharem, maleprotagonist, martialarts, medicine, memorymanipulation, mermaid, meta, military, monsterboy, monstergirl, mopeds, motorcycles, musical, mythology, nekomimi, ninja, nodialogue, noir, nun, officelady, ojousama, otakuculture, outdoor, pandemic, parkour, parody, philosophy, photography, pirates, poker, police, politics, postapocalyptic, pov, primarilyadultcast, primarilychildcast, primarilyfemalecast, primarilymalecast, puppetry, rakugo, realrobot, rehabilitation, reincarnation, religion, revenge, robots, rotoscoping, rugby, rural, samurai, satire, school, schoolclub, scubadiving, seinen, shapeshifting, ships, shogi, shoujo, shounen, shrinemaiden, skateboarding, skeleton, slapstick, slavery, softwaredevelopment, space, spaceopera, steampunk, stopmotion, succubus, sumo, superpower, superrobot, superhero, surfing, surrealcomedy, survival, swimming, swordplay, tabletennis, tanks, tannedskin, teacher, teenslove, tennis, terrorism, timemanipulation, timeskip, tokusatsu, tomboy, torture, tragedy, trains, triads, tsundere, twins, urban, urbanfantasy, vampire, videogames, vikings, villainess, virtualworld, volleyball, vtuber, war, werewolf, witch, work, wrestling, writing, wuxia, yakuza, yandere, youkai, yuri, zombie
