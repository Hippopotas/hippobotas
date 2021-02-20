import json
import os
import requests
import time

from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv()
    payload = {'client_id': os.getenv('TWITCH_ID'),
               'client_secret': os.getenv('TWITCH_SECRET'),
               'grant_type': 'client_credentials'}
    r = requests.post('https://id.twitch.tv/oauth2/token', data=payload)
    
    access_token = json.loads(r.text)['access_token']

    big_data = []
    for i in range(10):
        offset = i * 500
        headers = {'Client-ID': os.getenv('TWITCH_ID'),
                   'Authorization': f'Bearer {access_token}'}
        data = ('fields name, summary, slug, screenshots.url; '
                'sort follows desc; '
                'where follows != null & screenshots != null & themes != (42); '
                f'offset {offset}; limit 500;')
        r = requests.post('https://api.igdb.com/v4/games', headers=headers, data=data)

        if r.status_code == 200:
            big_data += json.loads(r.text)
        else:
            print(f'{i}/n{r.text}')

        time.sleep(0.5)

    with open('data/vg_trivia.json', 'w', encoding='utf-8') as f:
        json.dump(big_data, f)