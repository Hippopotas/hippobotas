import argparse
import shlex

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
