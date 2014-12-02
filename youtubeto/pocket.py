from __future__ import absolute_import

from gevent import monkey
monkey.patch_all(thread=False, select=False)

import arrow
from httplib2 import Http
from pocket import Pocket
from apiclient.discovery import build
from oauth2client import client
from gevent.pool import Pool

from . import config


def main():
    creds = client.OAuth2Credentials(
        config.YOUTUBE_ACCESS_TOKEN, config.YOUTUBE_CLIENT_ID,
        config.YOUTUBE_CLIENT_SECRET, config.YOUTUBE_REFRESH_TOKEN,
        arrow.get(config.YOUTUBE_TOKEN_EXPIRY),
        config.YOUTUBE_TOKEN_URI, config.YOUTUBE_USER_AGENT)
    if creds.token_expiry <= arrow.get():
        creds.refresh(Http())
        config.YOUTUBE_ACCESS_TOKEN = creds.access_token
        config.YOUTUBE_TOKEN_EXPIRY = creds.token_expiry.isoformat()
        config.save()
    http = authorized_http(creds)
    youtube = build('youtube', 'v3', http=http())

    if not config.POCKET_ACCESS_TOKEN:
        import webbrowser
        request_token = Pocket.get_request_token(config.POCKET_CONSUMER_KEY)
        auth_url = Pocket.get_auth_url(request_token)
        webbrowser.open(auth_url)
        raw_input('Press ENTER when done ')
        access_token = Pocket.get_access_token(config.POCKET_CONSUMER_KEY,
                                               request_token)
        config.POCKET_ACCESS_TOKEN = access_token
        config.save()
    pocket = Pocket(config.POCKET_CONSUMER_KEY, config.POCKET_ACCESS_TOKEN)

    playlists = youtube.playlists().list(part='snippet', mine=True).execute()
    favorites = next((item for item in playlists['items']
                      if item['snippet']['title'] == 'Favorites'), None)
    req = youtube.playlistItems().list(part='snippet',
                                       playlistId=favorites['id'])
    pool = Pool()
    while req:
        res = req.execute()
        for item in res['items']:
            pool.spawn(put_in_pocket, youtube, http, pocket, item)
        req = youtube.playlistItems().list_next(req, res)
    pool.join()


def authorized_http(creds):
    return lambda: creds.authorize(Http())


def put_in_pocket(youtube, http, pocket, item):
    req = youtube.videos().list(part='snippet',
                                id=item['snippet']['resourceId']['videoId'])
    video = req.execute(http())['items'][0]
    url = ('http://www.youtube.com/watch'
           '?v={resourceId[videoId]}'
           '&list={playlistId}'
           .format(**item['snippet']))
    title = u'{title} by {channelTitle}'.format(**video['snippet'])
    tags = 'youtube'
    pocket.add(url, title, tags)


if __name__ == '__main__':
    main()
