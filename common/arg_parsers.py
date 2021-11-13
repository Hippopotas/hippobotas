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
                         list(const.ANILIST_TAGS.keys()) + const.LEAGUE_CATS
        all_categories = list(map(find_true_name, all_categories))
        fixed_categories = []
        arg_categories = iter(args.categories)

        category = next(arg_categories, None)
        while category:
            category = find_true_name(category)

            if category in all_categories:
                fixed_categories.append(category)
                category = next(arg_categories, None)

            else:
                add_on = next(arg_categories, None)
                if add_on is None:
                    return

                category += add_on

        args.categories = fixed_categories
    # Incorrectly formatted input results in args = None
    except SystemExit:
        return
    except ValueError:
        return

    return args
