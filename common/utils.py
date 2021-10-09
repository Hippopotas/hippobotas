import datetime
import re
import urllib.request

from io import BytesIO
from PIL import Image

from common.constants import IMG_NOT_FOUND


def is_uhtml(text):
    """ Returns whether text is an html string. """
    return text.startswith('<')


def find_true_name(text):
    """ Return only non-uppercase alphanumeric characters. """
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()


def img_dims_from_uri(uri):
    """ Gets img dimensions from a URL.
        If it fails, returns (0, 0).
    """
    # Returns width, height
    dims = (0, 0)
    try:
        file = BytesIO(urllib.request.urlopen(uri).read())
        im = Image.open(file)
        dims = im.size
    except Exception as e:
        print(e)

    return dims


def gen_uhtml_img_code(url, height_resize=300, width_resize=None,
                       dims=None, center=True, **kwargs):
    """ Generates basic HTML code for an img tag from a URL. """
    w, h = (0, 0)
    if dims:
        w, h = dims
    else:
        w, h = img_dims_from_uri(url)
        if not w or not h:
            w, h = img_dims_from_uri(IMG_NOT_FOUND)
            url = IMG_NOT_FOUND

        if h > height_resize:
            w = w * height_resize // h
            h = height_resize
        
        if width_resize:
            if w > width_resize:
                h = h * width_resize // w
                w = width_resize

    kwarg_opts = ''
    for k in kwargs:
        kwarg_opts += f'{k}={kwargs[k]} '

    img_url = url if url.startswith('https') else url.replace('http', 'https', 1)

    uhtml = f'<img src="{img_url}" width={w} height={h} {kwarg_opts}>'
    if center:
        uhtml = f'<center>{uhtml}</center>'

    return uhtml


def trivia_leaderboard_msg(leaderboard, title, name='tleaderboard', metric='pts'):
    """ Generates basic HTML code for a leaderboard. """
    msg = (f'/adduhtml {name}, '
            '<center><table><tr><th colspan=\'3\' style=\'border-bottom:1px solid\'>'
            '{}</th></tr>'.format(title))

    for i, [user, score] in enumerate(leaderboard):
        msg += '<tr><td>{}</td><th>{}</th><td>{} {}</td></tr>'.format(i+1, user, int(score), metric)

    msg += '</table></center>'
    return msg


def monospace_table_row(text_list, delimiter='|'):
    """ Given list of (text, max_col_len pairs), returns string
        containing table-row-ified version of the text.
    """
    row_str = ''
    for text in text_list:
        col_str = f'{text[0]: <{text[1]}}'
        row_str += col_str
        row_str += f' {delimiter} '

    del_len = -1 * (len(delimiter) + 2)
    row_str = row_str[:del_len]

    return row_str


def curr_cal_date():
    """ Returns the current calendar date in a form e.g. Jan 1
    """
    curr_day = datetime.date.today()
    return curr_day.strftime('%B') + ' ' + str(curr_day.day)


def is_url(uri):
    """ Django's url validation code.
    """
    regex = re.compile(
            r'^(?:http|ftp)s?://' # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
            r'localhost|' #localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
            r'(?::\d+)?' # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    return (re.match(regex, uri) is not None)
