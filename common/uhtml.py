from airium import Airium


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


class ItemInfo(InfoBox):
    def __init__(self, item_name, item_link, palette):
        self.item_name = item_name
        self.item_link = item_link

        super(ItemInfo, self).__init__(palette)


    def animanga(self, **kwargs):
        title_style = ('font-size:14px;'
                       'padding:5px;'
                      f'border-bottom: 3px solid {self.border_color}')

        ongoing_color = '#E0DD24' if kwargs['ongoing'] == 'Ongoing' else '#00FF00'

        status_style = ('color:#555;'
                        'font-size:10px;'
                        'padding-top:5px')

        with self.html.table(style=self.table_style()):
            with self.html.thead():
                with self.html.tr():
                    with self.html.th(colspan=4, width=96, style=title_style):
                        self.html.a(href=self.item_link,
                                    style='color:#8311a6',
                                    _t=self.item_name)

                with self.html.tr(style='text-align:center'):
                    self.html.td(rowspan=2, style='padding:5px',
                                 _t=kwargs['img_uhtml'])

                    self.html.td(style=(f'color:{ongoing_color};'
                                         'font-size:10px;'
                                         'padding-top:5px'),
                                 _t=kwargs['ongoing'])

                    self.html.td(style=status_style, _t=kwargs['parts'])
                    self.html.td(style=status_style, _t=kwargs['score'])

                with self.html.tr():
                    self.html.td(colspan=3, style='width:300px; padding:5px',
                                 _t=kwargs['synopsis'])

        return self.uglify()