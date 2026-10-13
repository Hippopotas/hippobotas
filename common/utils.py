import aiohttp
import asyncio
import calendar
import datetime
import re
import sqlite3
import time
import urllib.request

from io import BytesIO
from PIL import Image, ImageFile

from common.constants import IMG_DIMS_DB, IMG_NOT_FOUND

# Give up on finding an image's header after this many bytes.
IMG_READ_LIMIT = 4 * 1024 * 1024
IMG_TIMEOUT = 10
# Don't retry a URL that failed to load for this many seconds.
IMG_RETRY_DELAY = 10 * 60
IMG_HEADERS = {'User-Agent': 'hippobotas (Pokemon Showdown chat bot)'}


def is_uhtml(text):
    """ Returns whether text is an html string. """
    return text.startswith('<')


def find_true_name(text):
    """ Return only non-uppercase alphanumeric characters. """
    return re.sub(r'[^a-zA-Z0-9]', '', text).lower()


class ImageDimCache:
    """ Remembers the (width, height) of image URLs, in memory and in
        sqlite, so each image only has to be measured once.
    """
    def __init__(self, db_file):
        self.db_file = db_file
        self.dims = {}
        self.failed = {}
        self.pending = {}
        self.session = None
        self.loaded = False


    def _connect(self):
        conn = sqlite3.connect(self.db_file)
        conn.execute('CREATE TABLE IF NOT EXISTS img_dims (url VARCHAR PRIMARY KEY, '
                     'width INTEGER NOT NULL, height INTEGER NOT NULL, '
                     'fetched DATETIME DEFAULT CURRENT_TIMESTAMP)')
        return conn


    def _load(self):
        if self.loaded:
            return
        self.loaded = True

        try:
            conn = self._connect()
            try:
                for url, w, h in conn.execute('SELECT url, width, height FROM img_dims'):
                    self.dims[url] = (w, h)
            finally:
                conn.close()
        except sqlite3.Error as e:
            print(f'Could not load image size cache: {e}')


    def lookup(self, url):
        """ Returns cached dimensions, or None if the URL hasn't been measured. """
        self._load()
        return self.dims.get(url)


    def store(self, url, dims):
        if not all(dims):
            self.failed[url] = time.time()
            return

        self.dims[url] = dims
        self.failed.pop(url, None)
        try:
            conn = self._connect()
            try:
                with conn:
                    conn.execute('INSERT OR REPLACE INTO img_dims (url, width, height) '
                                 'VALUES (?, ?, ?)', (url, dims[0], dims[1]))
            finally:
                conn.close()
        except sqlite3.Error as e:
            print(f'Could not save image size for {url}: {e}')


    def recently_failed(self, url):
        return time.time() - self.failed.get(url, 0) < IMG_RETRY_DELAY


    async def get(self, url):
        """ Returns (width, height) of the image at url, or (0, 0) if it
            can't be loaded. Concurrent requests for one URL share a fetch.
        """
        cached = self.lookup(url)
        if cached:
            return cached
        if self.recently_failed(url):
            return (0, 0)

        if url not in self.pending:
            self.pending[url] = asyncio.ensure_future(self._measure(url))
        return await asyncio.shield(self.pending[url])


    async def _measure(self, url):
        try:
            dims = await self._fetch_header_dims(url)
            self.store(url, dims)
            return dims
        finally:
            self.pending.pop(url, None)


    async def _fetch_header_dims(self, url):
        """ Streams the image only until Pillow can read its header. """
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=IMG_HEADERS,
                                                 timeout=aiohttp.ClientTimeout(total=IMG_TIMEOUT))

        parser = ImageFile.Parser()
        head = b''
        read = 0
        try:
            async with self.session.get(url) as r:
                if r.status != 200:
                    print(f'Image request for {url} returned {r.status}.')
                    return (0, 0)

                async for chunk in r.content.iter_chunked(16 * 1024):
                    if len(head) < 30:
                        head += chunk[:30]
                        webp_dims = webp_header_dims(head)
                        if webp_dims:
                            return webp_dims

                    parser.feed(chunk)
                    read += len(chunk)
                    if parser.image or read >= IMG_READ_LIMIT:
                        break
        except Exception as e:
            print(f'Could not measure image {url}: {e!r}')
            return (0, 0)

        if not parser.image:
            print(f'Could not read an image header from {url}.')
            return (0, 0)

        return parser.image.size


def webp_header_dims(data):
    """ Reads width/height from the first 30 bytes of a WebP file.
        Pillow needs the whole file to open WebP, so this avoids that.
    """
    if len(data) < 30 or data[:4] != b'RIFF' or data[8:12] != b'WEBP':
        return None

    chunk = data[12:16]
    if chunk == b'VP8X':
        return (1 + int.from_bytes(data[24:27], 'little'),
                1 + int.from_bytes(data[27:30], 'little'))
    if chunk == b'VP8 ':
        return (int.from_bytes(data[26:28], 'little') & 0x3FFF,
                int.from_bytes(data[28:30], 'little') & 0x3FFF)
    if chunk == b'VP8L':
        bits = int.from_bytes(data[21:25], 'little')
        return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)

    return None


IMG_DIMS = ImageDimCache(IMG_DIMS_DB)


async def image_dims(url):
    """ Gets img dimensions from a URL without blocking.
        If it fails, returns (0, 0).
    """
    return await IMG_DIMS.get(url)


def img_dims_from_uri(uri):
    """ Gets img dimensions from a URL.
        If it fails, returns (0, 0).

        Blocks while downloading; async code should use image_dims.
    """
    cached = IMG_DIMS.lookup(uri)
    if cached:
        return cached

    # Returns width, height
    dims = (0, 0)
    try:
        req = urllib.request.Request(uri, headers=IMG_HEADERS)
        file = BytesIO(urllib.request.urlopen(req, timeout=IMG_TIMEOUT).read())
        im = Image.open(file)
        dims = im.size
    except Exception as e:
        print(e)

    IMG_DIMS.store(uri, dims)
    return dims


def scale_dims(dims, height_resize=300, width_resize=None):
    """ Shrinks dims to fit within height_resize (and width_resize). """
    w, h = dims
    if h > height_resize:
        w = w * height_resize // h
        h = height_resize

    if width_resize:
        if w > width_resize:
            h = h * width_resize // w
            w = width_resize

    return (w, h)


def gen_uhtml_img_code(url, height_resize=300, width_resize=None,
                       dims=None, center=True, **kwargs):
    """ Generates basic HTML code for an img tag from a URL.

        Blocks while measuring the image; async code should use gen_uhtml_img.
    """
    if not dims:
        dims = img_dims_from_uri(url)
        if not all(dims):
            dims = img_dims_from_uri(IMG_NOT_FOUND)
            url = IMG_NOT_FOUND
        dims = scale_dims(dims, height_resize, width_resize)

    return img_tag(url, dims, center=center, **kwargs)


async def gen_uhtml_img(url, height_resize=300, width_resize=None,
                        dims=None, center=True, **kwargs):
    """ Generates basic HTML code for an img tag from a URL.
        Image sizes are cached, and only the start of each file is downloaded.
    """
    if not dims:
        dims = await image_dims(url)
        if not all(dims):
            dims = await image_dims(IMG_NOT_FOUND)
            url = IMG_NOT_FOUND
        dims = scale_dims(dims, height_resize, width_resize)

    return img_tag(url, dims, center=center, **kwargs)


def img_tag(url, dims, center=True, **kwargs):
    """ Formats an img tag of the given size. """
    w, h = dims
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
    if not text:
        return ''
    return text.replace('<br>', '').replace('<', '&lt;').replace('>', '&gt;')


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
                                                    "WHERE day=? AND room=?", (today, room))

    if not birthday_chars:
        if not automatic:
            return 'No known birthdays today! Get a staff to add some with ]birthday_add!'
        return

    char_uhtml = await bot.birthday_chars_to_uhtml(birthday_chars)

    tomorrow_uhtml = ''
    curr_year = datetime.datetime.today().year

    max_scroll = ''
    if len(birthday_chars) > 15:
        max_scroll = 'overflow-y: scroll; max-height: 250px'

    if today == 'February 28' and not calendar.isleap(curr_year):
        tomorrow_uhtml = '<tr><td colspan=10><b><center>(Feb 29)</center></b></td></tr>'
        tomorrow_chars = await bot.roomdata_man.execute("SELECT name, image, link FROM birthdays "
                                                       "WHERE day='February 29' AND room=?", (room,))
        tomorrow_uhtml += await bot.birthday_chars_to_uhtml(tomorrow_chars)

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
