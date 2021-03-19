import re

from PIL import ImageFile
from urllib import request as ulreq
from urllib.error import HTTPError

from common.constants import IMG_NOT_FOUND


def find_true_name(text):
    """ Return only non-uppercase alphanumeric characters. """
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()


def img_dims_from_uri(uri):
    """ Gets img dimensions from a URL.
        If it fails, returns (0, 0).
    """
    # Returns width, height
    dims = (0, 0)
    data = None
    retry = 0
    try:
        with ulreq.urlopen(uri) as f:
            while retry < 1000:
                p = ImageFile.Parser()

                if not data:
                    data = f.read(1024)
                else:
                    data += f.read(1024)

                p.feed(data)

                try:
                    dims = p.image.size
                except AttributeError:
                    retry += 1
                    continue
                else:
                    break
    except HTTPError as e:
        print(e)

    return dims


def gen_uhtml_img_code(url, height_resize=300, width_resize=None):
    """ Generates basic HTML code for an img tag from a URL. """
    w, h = img_dims_from_uri(url)
    if not w or not h:
        w, h = img_dims_from_uri(IMG_NOT_FOUND)

    if h > height_resize:
        w = w * height_resize // h
        h = height_resize
    
    if width_resize:
        if w > width_resize:
            h = h * width_resize // w
            w = width_resize

    return '<center><img src=\'{}\' width={} height={}></center>'.format(url, w, h)


def trivia_leaderboard_msg(leaderboard, title, name='tleaderboard', metric='pts'):
    """ Generates basic HTML code for a leaderboard. """
    msg = (f'/adduhtml {name}, '
            '<center><table><tr><th colspan=\'3\' style=\'border-bottom:1px solid\'>'
            '{}</th></tr>'.format(title))

    for i, [user, score] in enumerate(leaderboard):
        msg += '<tr><td>{}</td><th>{}</th><td>{} {}</td></tr>'.format(i+1, user, int(score), metric)

    msg += '</table></center>'
    return msg
