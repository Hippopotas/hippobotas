# hippobotas
PokemonShowdown chat bot in Py3.


_lasciate ogne speranza, voi ch’intrate_


A constant WIP. Lots of things need hardening. Style is a mess. Many crucial files are missing here (mainly scripts and data).

Usage below.

## GENERAL

### ]help
Displays a link to this page.

### ]suck [top]
THIS ONLY WORKS IN PMs. Every time anyone gets a point from this command, a random cooldown between 15 minutes and 90 minutes
is generated before it will award points again. Calling it before this cooldown ends results in your points getting reset to 0.

Also gets you banned from the room if @Beowulf is present.

top: If ]suck top is called in a chatroom, the 5 users with the most sucks are displayed.

### ]birthday [ROOM]
Displays the list of (anime) characters with birthdays today. Submit via https://forms.gle/qfKSeyNtpueTBACn7

ROOM (optional): Only used in PMs. Specifies the room to see the infobox in.

### ]calendar [ROOM]
Displays a random picture of the current date (Pacific time) from an anime/manga.

ROOM (optional): Only used in PMs. Specifies the room to see the infobox in.

### ]bl_add CATEGORY, ITEM
ROOM STAFF ONLY! Adds an item to the CATEGORY banlist. Currently supported categories: anime, manga. Requires MAL ID number.

### ]bl_remove CATEGORY, ITEM
ROOM STAFF ONLY! Removes an item from the CATEGORY banlist. See ]bl_add.

### ]bl_list CATEGORY
ROOM STAFF ONLY! PMs you the banlist for a category.

###]emote_add EMOTE URL
ROOM OWNER ONLY! Sets a room's EMOTE to display the picture found at URL when called with :EMOTE: (case insensitive).
Note that discord URLs don't work very well, and I would suggest reuploading somewhere else.

### ]emote_rm EMOTE
ROOM OWNER ONLY! Removes a room's EMOTE (see ]set_emote).

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

ROOM (optional): Only used in PMs. Specifies the room to add the song to.

TITLE: The name of the song to be removed (case insensitive).

### ]song_list [ROOM]
Returns a room's song pool in alphabetical order.

ROOM (optional): Only used in PMs. Specifies the room to add the song to.

### ]randsong [ROOM]
Returns a random song from a room's song pool.

ROOM (optional): Only used in PMs. Specifies the room to add the song to.

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

### ]anime ANIME
Displays an infographic about ANIME, as searched for on MAL.

### ]manga MANGA
See ]anime.


## MAL

Note: Only usable in animeandmanga right now.

### ]addmal USERNAME
Sets your MAL username to be USERNAME. This must be a valid MAL account.

### ]mal [USER] [-r]
Displays a summary of a MAL profile or rolls a random series from a MAL profile.

USER (optional): PS user you would like to see the MAL profile of, or roll a series from. If not set, defaults to yourself.

-r (optional): If this is set, this command returns a random series instead. You can specify which
               list(s) it chooses from. The valid categories are 'anime' and 'manga'. If no categories
               are specified, it chooses from both anime and manga lists.

               This only chooses from series with status 'Reading', 'Watching', or 'Completed'.

Example: ]mal ExampleUser
         will display a htmlbox with a summary of ExampleUser's MAL profile if it has been set with ]addmal.

Example: ]mal ExampleUser -r anime
         will choose a random anime from ExampleUser's MAL animelist.

### ]anime [ROOM] SERIES NAME
Displays a infobox about the anime called SERIES_NAME.

ROOM (optional): Only used in PMs. Specifies the room to see the infobox in.

### ]manga [ROOM] SERIES NAME
See ]anime.

### ]randanime [ROOM] [GENRES]
Displays an infobox about a random anime.

ROOM (optional): Only used in PMs. Specifies the room to see the infobox in.

GENRES (optional): The anime will be of at least one of the specified genres.

Example: ]randanime tv shounen police ova
         will return a (shounen or police) (tv or ova) series

### ]randmanga [ROOM] [GENRES]
See ]randanime.


## STEAM

Note: Only usable in videogames right now.

### ]addsteam STEAM_ID
Sets your Steam account to be STEAM_ID. This must be a valid Steam account. This must be the ID in the URL of your profile.

### ]steam [USER] [-r]
Displays a summary of a Steam profile or rolls a random series from a Steam profile.

USER (optional): PS user you would like to see the Steam profile of, or roll a series from. If not set, defaults to yourself.

-r (optional): rolls a random game instead of displaying the profile.

Example: ]steam ExampleUser
         will display a htmlbox with a summary of ExampleUser's Steam profile if it has been set with ]addsteam.

Example: ]steam ExampleUser -r
         will choose a random game from ExampleUser's Steam profile.


## TRIVIA

### ]trivia start LENGTH [-c CATEGORIES] [-cx] [-d DIFF] [-r] [-q] [-s AUTOSKIP]
Starts a trivia session. Requires + and above.

LENGTH (required): number of questions in the round.

-c CATEGORIES (optional): categories of questions that are allowed. Defaults to all categories if not set. See the "Categories"
                          section for a list of valid categories per room.

-cx EXCLUDECATS (optional): if set, will exclude CATEGORIES instead from room defaults. Will fail if no categories are specified.
                            Only works for animeandmanga.

-d DIFF (optional): difficulty of questions in the round, set as an integer from 1 (easy) to 10 (hard). Defaults to 3 if not set.

-r (optional): for animeandmanga room use. Set this to have the difficulty be based on rating of shows.
               Defaults to sort by popularity if not set.

-q (optional): uses quizbowl-style questions instead, with automatic text reveal.

-s AUTOSKIP (optional): number of seconds to wait before automatically skipping each question. Defaults to being 15.

Example: ]trivia start 5 -c anime manga -d 9
         will start a round of trivia with 5 questions, choosing from the categories of anime and manga, with difficulty 9.

Example: ]trivia start 10 -r -s 20
         will start a round of trivia with 10 questions, choosing from all room categories, with difficulty 3. Each question
         will be skipped after 20 seconds if not answered correctly.
         If in the animeandmanga room, the difficulty will be based on the rating of the shows.

### ]trivia stop
Ends the current trivia session. Requires + and above.

### ]trivia end
See ]trivia stop.

### ]trivia skip
Skips the current trivia question. Requires + and above.

### ]trivia leaderboard [NUM]
Displays the room leaderboard for trivia if the room has one.

NUM (optional): Shows the top NUM players. Defaults to 5 if not set.

### ]trivia score [USERNAME]
Outputs the trivia score of [USERNAME] if the room has a leaderboard.

USERNAME (optional): Defaults to the caller's username if not set.

### Categories:

leagueoflegends - items, skins, spells

videogames - Coming Soon TM

animeandmanga - tv, tvshort, movie, special, ova, ona, manga, novel, oneshot, \
               action, adventure, comedy, drama, ecchi, fantasy, horror, mahoushoujo, mecha, music, mystery, psychological, romance, scifi, sliceoflife, sports, supernatural, thriller, \
               4koma, achromatic, achronologicalorder, acting, adoption, advertisement, afterlife, agegap, ageregression, agender, agriculture, airsoft, aliens, alternateuniverse, americanfootball, amnesia, anachronism, angels, animals, anthology, antihero, archery, artificialintelligence, asexual, assassins, astronomy, athletics, augmentedreality, autobiographical, aviation, badminton, band, bar, baseball, basketball, battleroyale, biographical, bisexual, bodyswapping, boxing, boyslove, bullying, butler, calligraphy, cardbattle, cars, centaur, cgi, cheerleading, chibi, chimera, chuunibyou, circus, classicliterature, college, comingofage, conspiracy, cosmichorror, cosplay, crime, crossdressing, crossover, cult, cultivation, cuteboysdoingcutethings, cutegirlsdoingcutethings, cyberpunk, cyborg, cycling, dancing, deathgame, delinquents, demons, denpa, detective, dinosaurs, dissociativeidentities, dragons, drawing, dullahan, dungeon, dystopian, esports, economics, educational, elf, ensemblecast, environmental, episodic, espionage, fairytale, familylife, fashion, femaleharem, femaleprotagonist, fencing, firefighters, fishing, fitness, flash, food, football, foreign, fugitive, fullcgi, fullcolor, gambling, gangs, genderbending, ghost, go, goblin, gods, golf, guns, gyaru, henshin, heterosexual, hikikomori, historical, iceskating, idol, isekai, iyashikei, josei, judo, kaiju, karuta, kemonomimi, kids, kuudere, lacrosse, languagebarrier, lgbtqthemes, lostcivilization, lovetriangle, mafia, magic, mahjong, maids, makeup, maleharem, maleprotagonist, martialarts, medicine, memorymanipulation, mermaid, meta, military, monsterboy, monstergirl, mopeds, motorcycles, musical, mythology, nekomimi, ninja, nodialogue, noir, nun, officelady, ojousama, otakuculture, outdoor, pandemic, parkour, parody, philosophy, photography, pirates, poker, police, politics, postapocalyptic, pov, primarilyadultcast, primarilychildcast, primarilyfemalecast, primarilymalecast, puppetry, rakugo, realrobot, rehabilitation, reincarnation, religion, revenge, robots, rotoscoping, rugby, rural, samurai, satire, school, schoolclub, scubadiving, seinen, shapeshifting, ships, shogi, shoujo, shounen, shrinemaiden, skateboarding, skeleton, slapstick, slavery, softwaredevelopment, space, spaceopera, steampunk, stopmotion, succubus, sumo, superpower, superrobot, superhero, surfing, surrealcomedy, survival, swimming, swordplay, tabletennis, tanks, tannedskin, teacher, teenslove, tennis, terrorism, timemanipulation, timeskip, tokusatsu, tomboy, torture, tragedy, trains, triads, tsundere, twins, urban, urbanfantasy, vampire, videogames, vikings, villainess, virtualworld, volleyball, vtuber, war, werewolf, witch, work, wrestling, writing, wuxia, yakuza, yandere, youkai, yuri, zombie


## GACHA

### ]gacha_join
Use this to start playing.

### ]box
Displays your own box of units.

### ]gprofile
WIP

### ]roll GACHA_NAME NUM_ROLLS
Rolls NUM_ROLLS times in GACHA_NAME and adds the units to your box.

GACHA_NAME: The code for the gacha you want to roll. See the gacha roomintro for a list of available banners.

NUM_ROLLS: The number of times to roll. Must be an integer from 1-10, and cannot be more than
           the number of rolls you currently have.

### ]fav ID_LIST
PM ONLY. Sets the units corresponding to ID_LIST to be favorited.

ID_LIST: A comma separated list of IDs, as reported by ]box. Ex: 4, 93, 20, 1

### ]unfav ID_LIST
PM ONLY. Sets the units corresponding to ID_LIST to be unfavorited.

ID_LIST: A comma separated list of IDs, as reported by ]box. Ex: 4, 93, 20, 1

### ]showcase ID, PLACE
WIP
PM ONLY. Sets the unit with id ID to be in the PLACE slot of your showcase. Also favorites the unit if it isn't already.

ID: An ID of a unit in your box.

PLACE: An integer from 1-5.

### ]unshowcase ID
PM ONLY. Removes the unit with id ID from the showcase. Does not change the position of any of the other showcase units.

ID: An ID of a unit in your box.

### ]merge [ID_LIST]
PM ONLY. Merges any merge-able units in your box. 3 of the same unit (at the same level) will fuse into 1 unit of the next level.
Favorited units can and will not be merged. If ID_LIST is not specified, automatically merges all merge-able units.

ID_LIST (optional): A comma separated list of IDs, as reported by ]box. Ex: 4, 93, 20, 1
