import asyncio
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
        file = BytesIO(urllib.request.urlopen(uri, timeout=10).read())
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


def leaderboard_uhtml(leaderboard, title, name='tleaderboard', metric='pts'):
    """ Generates basic HTML code for a leaderboard. """
    msg = (f'{name}, '
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


def sanitize_html(text):
    """ Escape annoying characters from text that goes in uhtml.
    """
    return text.replace('<', '&lt;').replace('>', '&gt;')


async def birthday_text(bot, automatic, room):
    '''
    Sends a uhtml-formatted table of the current date's birthdays.

    Args:
        automatic (bool): Whether or not this was automatically scheduled.
        room (str): The room to get birthdays of.
    '''
    today = datetime.datetime.today().strftime('%B %d').replace(' 0', ' ')
    short_today = datetime.datetime.today().strftime('%b %d').replace(' 0', ' ')
    birthday_chars = await bot.roomdata_man.execute("SELECT name, image, link FROM birthdays "
                                                    f"WHERE day='{today}' AND room='{room}'")

    if not birthday_chars:
        if not automatic:
            return 'No known birthdays today! Get a staff to add some with ]birthday_add!'
        return

    char_uhtml = bot.birthday_chars_to_uhtml(birthday_chars)

    tomorrow_uhtml = ''
    curr_year = datetime.datetime.today().year

    max_scroll = ''
    if len(birthday_chars) > 15:
        max_scroll = 'overflow-y: scroll; max-height: 250px'

    if today == 'February 28' and (curr_year % 4 != 0 or curr_year % 100 == 0):
        tomorrow_uhtml = '<tr><td colspan=10><b><center>(Feb 29)</center></b></td></tr>'
        tomorrow_chars = await bot.roomdata_man.execute("SELECT name, image, link FROM birthdays "
                                                       f"WHERE day='February 29' AND room='{room}'")
        tomorrow_uhtml += bot.birthday_chars_to_uhtml(tomorrow_chars)

    uhtml = (f'<div style=\'{max_scroll}\'>'
                '<center><table style=\'border:3px solid #0088cc; border-spacing:0px; '
                'border-radius:10px; background-image:url(https://i.imgur.com/l8iJKoX.png); '
                'background-size:cover\'>'
                '<thead><tr><th colspan=10 style=\'padding:5px 5px 10px 5px\'>'
                f'Today\'s Birthdays ({short_today})</th></tr></thead><tbody>'
                f'{char_uhtml}'
                f'{tomorrow_uhtml}'
                '</tbody></table></center></div>')

    return f'hippo-birthdays, {uhtml}'
