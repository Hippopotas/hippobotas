import argparse
import shlex

import common.constants as const

from common.utils import find_true_name

def mal_arg_parser(s, caller):
    '''
    Parses a mal invocation as if it were CLI input.

    Args:
        s (str): input str
        caller (str): username of the person who invoked the command
    
    Returns:
        args (Namespace): contains the arguments as methods
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument('-r', '--roll', type=str, nargs='*')
    parser.add_argument('username', type=str, nargs='*', default=[caller])

    args = None
    try:
        args = parser.parse_args(shlex.split(s))

    # Incorrectly formatted input results in args = None
    except SystemExit:
        pass
    except ValueError:
        return

    return args


def match_categories(words, all_categories):
    '''
    Joins words into known categories, so multi-word ones like
    "slice of life" or "tv short" work, preferring the longest match
    ("tv short" is TV_SHORT, not TV and "short").

    Returns None if some words don't form a known category.
    '''
    words = [find_true_name(w) for w in words]
    matched = []
    i = 0
    while i < len(words):
        for j in range(len(words), i, -1):
            joined = ''.join(words[i:j])
            if joined in all_categories:
                matched.append(joined)
                i = j
                break
        else:
            return None
    return matched


def trivia_arg_parser(s):
    '''
    Parses a trivia start invocation as if it were CLI input.

    Args:
        s (str): input string

    Returns:
        args (Namespace): contains the arguments as methods.
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--categories', nargs='*', default=['all'])
    parser.add_argument('-cx', '--excludecats', nargs='*', default=None)
    parser.add_argument('-d', '--diff', type=int, default=3)
    parser.add_argument('-q', '--quizbowl', action='store_true')
    parser.add_argument('-r', '--byrating', action='store_true')
    parser.add_argument('-s', '--autoskip', type=int, default=15)
    parser.add_argument('len', type=int)

    args = None
    try:
        args = parser.parse_args(shlex.split(s))

        all_categories = ['all', 'mangadex'] + const.ANILIST_GENRES + const.ANILIST_MEDIA + \
                         list(const.ANILIST_TAGS.keys()) + const.LEAGUE_CATS + \
                         const.LEAGUE_EXTRA_CATS
        all_categories = set(map(find_true_name, all_categories))

        args.categories = match_categories(args.categories, all_categories)
        if args.categories is None:
            return
        if not args.categories:
            args.categories = ['all']

        if args.excludecats:
            args.excludecats = match_categories(args.excludecats, all_categories)
            if args.excludecats is None:
                return
    # Incorrectly formatted input results in args = None
    except SystemExit:
        return
    except ValueError:
        return

    return args
