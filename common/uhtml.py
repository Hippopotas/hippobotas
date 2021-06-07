from airium import Airium


class Uhtml():
    def __init__(self):
        self.html = Airium()

    def uglify(self):
        stripped = ''
        for l in str(self.html).split('\n'):
            stripped += l.strip()
        
        return stripped


class InfoBox(Uhtml):
    def __init__(self, bg_img, border_color):
        self.bg_img = bg_img
        self.border_color = border_color
        super(InfoBox, self).__init__()


class UserInfo(InfoBox):
    def __init__(self, username, userlink, palette):
        self.username = username
        self.userlink = userlink

        if palette == 'mal':
            super(UserInfo, self).__init__('https://i.imgur.com/l8iJKoX.png', '#0088cc')
        elif palette == 'steam':
            super(UserInfo, self).__init__('https://i.imgur.com/c68ilQW.png', '#858585')

        self.table_style = (f'border:3px solid {self.border_color};'
                             'border-spacing:0px;'
                             'border-radius:10px;'
                            f'background-image:url({self.bg_img});'
                             'background-size:cover')


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

        with self.html.table(style=self.table_style):
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
