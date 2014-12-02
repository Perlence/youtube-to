from __future__ import absolute_import

from gevent import monkey
monkey.patch_all(thread=False, select=False)

import json

import arrow
from apiclient.discovery import build
from gevent.pool import Pool
from httplib2 import Http
from logbook import Logger
from oauth2client import client

from . import config

logger = Logger('youtubeto.raindrop')


class Raindrop(object):
    path = 'https://raindrop.io/api/'

    def __init__(self, session_id=None):
        self.session_id = session_id

    def _request(self, uri, method='GET', body=None, headers=None, **kwargs):
        uri = self.path + uri
        if headers is None:
            headers = {}
        if body is not None:
            body = json.dumps(body)
            headers['Content-Type'] = 'application/json; charset=UTF-8'
        if self.session_id is not None:
            headers['Cookie'] = 'connect.sid=' + self.session_id
        _, content = Http().request(uri, method, body, headers, **kwargs)
        return json.loads(content)

    def get(self, uri):
        return self._request(uri, 'GET')

    def create(self, uri, **params):
        return self._request(uri, 'POST', params)

    def delete(self, uri):
        return self._request(uri, 'DELETE')

    def update(self, uri, **params):
        return self._request(uri, 'PUT', params)


def main():
    if config.YOUTUBE_TOKEN_EXPIRY:
        youtube_token_expiry = arrow.get(config.YOUTUBE_TOKEN_EXPIRY)
    else:
        youtube_token_expiry = None
    if config.YOUTUBE_REFRESH_TOKEN:
        creds = client.OAuth2Credentials(
            config.YOUTUBE_ACCESS_TOKEN, config.YOUTUBE_CLIENT_ID,
            config.YOUTUBE_CLIENT_SECRET, config.YOUTUBE_REFRESH_TOKEN,
            youtube_token_expiry, config.YOUTUBE_TOKEN_URI,
            config.YOUTUBE_USER_AGENT)
        if youtube_token_expiry <= arrow.get():
            creds.refresh(Http())
            config.YOUTUBE_ACCESS_TOKEN = creds.access_token
            config.YOUTUBE_TOKEN_EXPIRY = creds.token_expiry.isoformat()
            config.save()
    else:
        import webbrowser
        flow = client.OAuth2WebServerFlow(
            config.YOUTUBE_CLIENT_ID,
            config.YOUTUBE_CLIENT_SECRET,
            config.YOUTUBE_SCOPE,
            config.YOUTUBE_REDIRECT_URI)
        webbrowser.open(flow.step1_get_authorize_url())
        code = raw_input('Input code: ')
        creds = flow.step2_exchange(code)
        config.YOUTUBE_ACCESS_TOKEN = creds.access_token
        config.YOUTUBE_CLIENT_ID = creds.client_id
        config.YOUTUBE_CLIENT_SECRET = creds.client_secret
        config.YOUTUBE_REFRESH_TOKEN = creds.refresh_token
        config.YOUTUBE_TOKEN_EXPIRY = creds.token_expiry.isoformat()
        config.YOUTUBE_TOKEN_URI = creds.token_uri
        config.YOUTUBE_USER_AGENT = creds.user_agent
        config.save()

    http = authorized_http(creds)
    youtube = build('youtube', 'v3', http=http())

    if not config.RAINDROP_SESSION_ID:
        import webbrowser
        webbrowser.open('https://raindrop.io/account/signin')
        config.RAINDROP_SESSION_ID = raw_input('Input session id: ')
        config.save()
    raindrop = Raindrop(config.RAINDROP_SESSION_ID)

    playlists = youtube.playlists().list(part='snippet', mine=True).execute()
    favorites = next((item for item in playlists['items']
                      if item['snippet']['title'] == 'Favorites'), None)
    req = youtube.playlistItems().list(part='snippet',
                                       playlistId=favorites['id'])
    pool = Pool()
    while req:
        res = req.execute()
        for item in res['items']:
            pool.spawn(put_in_raindrop, youtube, http, raindrop, item)
        pool.join()
        req = youtube.playlistItems().list_next(req, res)


def authorized_http(creds):
    return lambda: creds.authorize(Http())


def put_in_raindrop(youtube, http, raindrop, item):
    logger.info('Adding bookmark for {snippet[title]}', **item)
    collection_id = config.RAINDROP_COLLECTION_ID
    req = youtube.videos().list(part='snippet',
                                id=item['snippet']['resourceId']['videoId'])
    video = req.execute(http())['items'][0]
    url = ('http://www.youtube.com/watch'
           '?v={resourceId[videoId]}'
           '&list={playlistId}'
           .format(**item['snippet']))
    title = u'{title} by {channelTitle}'.format(**video['snippet'])
    result = raindrop.create(
        'raindrop',
        collectionId=collection_id,
        cover=0,
        coverEnabled=True,
        drop=False,
        excerpt=video['snippet']['description'],
        haveScreenshot=False,
        media=[{
            'link': get_biggest_thumbnail(item),
            'type': 'image'
        }],
        tags=[],
        title=title,
        url=url)
    logger.info('Added bookmark for {snippet[title]}', **item)


def get_biggest_thumbnail(item):
    for thumbnail in ('maxres', 'standard', 'high', 'medium', 'default'):
        result = item['snippet']['thumbnails'].get(thumbnail)
        if result is not None:
            return result['url']


if __name__ == '__main__':
    main()
