import json

from airium import Airium

from common.utils import img_dims_from_uri, sanitize_html

SHOWCASE_BORDER_1 = 'https://i.imgur.com/auG4Q2a.png'

class Uhtml():
    def __init__(self):
        self.html = Airium()

    def uglify(self, html=None):
        stripped = ''
        to_uglify = html if html else self.html
        for l in str(to_uglify).split('\n'):
            stripped += l.strip()
        
        return stripped


class InfoBox(Uhtml):
    def __init__(self, palette):
        if palette == 'mal':
            self.bg_img = 'https://i.imgur.com/l8iJKoX.png'
            self.border_color = '#0088cc'
        elif palette == 'steam':
            self.bg_img = 'https://i.imgur.com/c68ilQW.png'
            self.border_color = '#858585'

        super(InfoBox, self).__init__()


    def table_style(self):
        return (f'border:3px solid {self.border_color};'
                 'border-spacing:0px;'
                 'border-radius:10px;'
                f'background-image:url({self.bg_img});'
                 'background-size:cover')


class UserInfo(InfoBox):
    def __init__(self, username, userlink, palette):
        self.username = username
        self.userlink = userlink

        super(UserInfo, self).__init__(palette)


    def mal_user(self, **kwargs):
        username_style = ('font-size:14px;'
                          'padding:5px;'
                         f'border-right:3px solid {self.border_color}')

        userpic_style = (f'border-right:3px solid {self.border_color}')

        title_style = ('font-size:10px;'
                       'font-style:italic;'
                       'text-align:center;'
                       'vertical-align:top;'
                       'padding-bottom:5px')

        with self.html.table(style=self.table_style()):
            with self.html.thead():
                with self.html.tr():
                    with self.html.th(width=96, style=username_style):
                        self.html.a(href=self.userlink,
                                    style='color:#8311a6',
                                    _t=f'{self.username}')

                    self.html.th(colspan=2, _t='Anime')
                    self.html.th(colspan=2, _t='Manga')

            with self.html.tbody():
                with self.html.tr():
                    self.html.td(rowspan=3,
                                 style=userpic_style,
                                 _t=kwargs['profile_pic'])
                    self.html.td(style='text-align:center', _t='Rand Fav')

                    with self.html.td(rowspan=3, style='font-size:10px; vertical-align:middle'):
                        self.html(f"""Completed: {kwargs['anime_completed']}""")
                        self.html.br()
                        self.html.br()
                        self.html(f"""Watching: {kwargs['anime_watching']}""")
                        self.html.br()
                        self.html.br()
                        self.html(f"""Episodes Watched: {kwargs['ep_watched']}""")
                        self.html.br()
                        self.html.br()
                        self.html(f"""Mean Score: {kwargs['anime_score']}""")

                    self.html.td(style='text-align:center', _t='Rand Fav')
                    with self.html.td(rowspan=3, style='font-size:10px; vertical-align:middle; padding-right:5px'):
                        self.html(f"""Completed: {kwargs['manga_completed']}""")
                        self.html.br()
                        self.html.br()
                        self.html(f"""Reading: {kwargs['manga_reading']}""")
                        self.html.br()
                        self.html.br()
                        self.html(f"""Chapters Read: {kwargs['chp_read']}""")
                        self.html.br()
                        self.html.br()
                        self.html(f"""Mean Score: {kwargs['manga_score']}""")

                with self.html.tr():
                    self.html.td(_t=kwargs['anime_img'])
                    self.html.td(_t=kwargs['manga_img'])
                
                with self.html.tr():
                    with self.html.td(width=80, style=title_style):
                        self.html.a(href=kwargs['anime_link'],
                                    style='text-decoration:none; color: #8311a6',
                                    _t=kwargs['anime_title'])

                    with self.html.td(width=80, style=title_style):
                        self.html.a(href=kwargs['manga_link'],
                                    style='text-decoration:none; color: #8311a6',
                                    _t=kwargs['manga_title'])

        return self.uglify()


    @staticmethod
    def steam_game_uhtml(**kwargs):
        html = Airium()

        game_stat_style = ('vertical-align:bottom;'
                           'font-size:10px;'
                           'color:#FFF;'
                           'padding: 0px 5px 5px 0px')

        with html.tr():
            html.td(style='padding: 0px 5px 5px 5px',
                    _t=kwargs['img_uhtml'])

            with html.td(align='left', style='vertical-align:top; font-size:10px'):
                html.a(href=kwargs['url'], style='color:#FFF', _t=kwargs['name'])

            with html.td(align='right', style=game_stat_style):
                html(f"""{kwargs['recent_hours']} hrs last 2 weeks""")
                html.br()
                html(f"""{kwargs['total_hours']} hrs total playtime""")

        return html


    def steam_user(self, **kwargs):
        username_style = ('font-size;14px;'
                          'padding:5px;'
                         f'border-right:3px solid {self.border_color}')

        userpic_style = ('padding:5px;'
                        f'border-right:3px solid {self.border_color}')

        with self.html.table(style=self.table_style()):
            with self.html.thead():
                with self.html.tr():
                    with self.html.th(width=96, style=username_style):
                        self.html.a(href=self.userlink,
                                    style='color:#FFF',
                                    _t=self.username)

                    self.html.th(align='left', colspan=2,
                                 style=('font-weight:normal;'
                                       f'color:{self.border_color};'
                                        'padding-left:5px'),
                                 _t='Recent Activity')

                    self.html.th(align='right', style=('font-weight:normal;'
                                                      f'color:{self.border_color};'
                                                       'padding-left:30px;'
                                                       'padding-right:5px'),
                                 _t=f"""{kwargs['hours']} hours past 2 weeks""")

            with self.html.tbody():
                self.html.td(rowspan=6, style=userpic_style, _t=kwargs['img_uhtml'])
            
                for game in kwargs['game_uhtmls']:
                    self.html(self.uglify(game))
    
        return self.uglify()


    @staticmethod
    def showcase_uhtml(**kwargs):
        html = Airium()

        div_style = 'padding-top:9px'
        if kwargs['is_first']:
            div_style = ('padding-left:6px;'
                         'padding-top:18px;'
                         'min-width:80px;'
                        f'background-image: url(\'{SHOWCASE_BORDER_1}\');'
                         'background-repeat: no-repeat')

        with html.td(style='padding:5px'):
            with html.div(style=div_style):
                html.a(href=kwargs['unit_url'], _t=kwargs['img_uhtml'])
        
        return html


    def gacha_user(self, **kwargs):
        username_style = ('font-size:14px;'
                          'color:#FFF;'
                          'padding:5px;'
                         f'border-bottom:3px solid {self.border_color}')

        stats_style = ('font-weight:normal;'
                       'color:#858585;'
                       'padding-left:5px;'
                      f'border-bottom:3px solid {self.border_color}')

        with self.html.table(style=self.table_style()):
            with self.html.thead():
                with self.html.tr():
                    self.html.th(style=username_style, _t=self.username)

                    with self.html.th(colspan=4, align='left', style=stats_style):
                        self.html(f"""Rolls: {kwargs['roll_currency']} | """
                                  f"""Rerolls: {kwargs['reroll_currency']}""")

            with self.html.tbody():
                with self.html.tr():
                    for sc_html in kwargs['showcases']:
                        self.html(self.uglify(sc_html))

        return self.uglify()


class ItemInfo(InfoBox):
    def __init__(self, item_name, item_link, palette):
        self.item_name = item_name
        self.item_link = item_link

        super(ItemInfo, self).__init__(palette)


    def animanga(self, **kwargs):
        title_style = ('font-size:14px;'
                       'padding:5px;'
                      f'border-bottom: 3px solid {self.border_color}')

        ongoing_color = '#00FF00' if kwargs['ongoing'] == 'FINISHED' else '#E0DD24'

        status_style = ('color:#555;'
                        'font-size:10px;'
                        'padding-top:5px;'
                        'width:120px')

        with self.html.table(style=self.table_style()):
            with self.html.thead():
                with self.html.tr():
                    with self.html.th(colspan=4, width=96, style=title_style):
                        self.html.span(_t=self.item_name+' ')
                        self.html.a(href=kwargs['al_link'],
                                    style='color:#8311a6; font-size:11px',
                                    _t='(AL)')
                        self.html.span(_t=' ')
                        self.html.a(href=self.item_link,
                                    style='color:#8311a6; font-size:11px',
                                    _t='(MAL)')

            with self.html.tbody():
                with self.html.tr(style='text-align:center'):
                    self.html.td(rowspan=2, style='padding:5px',
                                 _t=kwargs['img_uhtml'])

                    self.html.td(style=(f'color:{ongoing_color};'
                                         'font-size:10px;'
                                         'padding-top:5px;'
                                         'width:120px'),
                                 _t=kwargs['ongoing'])

                    self.html.td(style=status_style, _t=kwargs['parts'])
                    self.html.td(style=status_style, _t=kwargs['score'])

                with self.html.tr():
                    with self.html.td(colspan=3, style='width:360px; padding:5px'):
                        self.html.div(style='overflow-y: scroll; max-height: 100px',
                                      _t=sanitize_html(kwargs['synopsis']))

        return self.uglify()


    def gacha_unit(self, **kwargs):
        unit = kwargs['unit']
        gacha = kwargs['gacha']

        img_url_pvs = json.loads(unit.img_url_pv)
        img_url_fulls = json.loads(unit.img_url_full)

        name_style = ('font-size:14px;'
                      'padding:5px;'
                     f'border-bottom: 3px solid {self.border_color}')

        font_style = ('text-align:center;'
                      'font-size:12px;'
                      'font-weight:bold;'
                      'color:#FFD700;'
                      'text-shadow: -1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000, 1px 1px 0 #000')

        base_div_style = ('border-radius:5px;'
                          'border: 1px solid #FFD700')

        with self.html.table(style=self.table_style()):
            with self.html.thead():
                with self.html.tr():
                    with self.html.th(colspan=10, style=name_style):
                        self.html.a(href=self.item_link, style='color:#FFF',
                                    _t=f'{self.item_name} [{gacha.upper()}]')

            with self.html.tbody():
                with self.html.tr(style=font_style):
                    for i, img in enumerate(img_url_fulls):
                        img_height = 100
                        img_width = 100

                        if gacha == 'fgo':
                            img_width = (img_height * 512 // 724)
                        else:
                            base_img_dims = img_dims_from_uri(img)
                            img_width = img_height * base_img_dims[0] // base_img_dims[1]

                        with self.html.td(style='padding:5px'):
                            div_style = (f'min-height:{img_height}px;'
                                         f'width:{img_width}px;'
                                         f'background-image: url(\'{img}\');'
                                          'background-position: center;'
                                          'background-repeat: no-repeat;'
                                          'background-size: contain;'
                                         f'{base_div_style}')
                            self.html.div(style=div_style, _t=i+1)

        return self.uglify()