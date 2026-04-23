from odoo import models, fields


class YouTubeChannel(models.Model):
    _name = 'youtube.channel'

    name = fields.Char()
    youtube_id = fields.Char()

    google_account_id = fields.Many2one('google.account')

    playlist_ids = fields.One2many('youtube.playlist', 'channel_id')

    subscriber_count = fields.Integer()
    view_count = fields.Integer()

    status = fields.Char()

    def create_or_update_from_api(self, account, data):
        existing = self.search([('youtube_id', '=', data['id'])], limit=1)

        vals = {
            'name': data['snippet']['title'],
            'youtube_id': data['id'],
            'google_account_id': account.id,
            'subscriber_count': int(data['statistics'].get('subscriberCount', 0)),
            'view_count': int(data['statistics'].get('viewCount', 0)),
            'status': data.get('status', {}).get('privacyStatus'),
        }

        if existing:
            existing.write(vals)
        else:
            self.create(vals)

    def action_sync_playlists(self):
        self.ensure_one()
        account = self.google_account_id
        account._ensure_token()

        import requests

        url = "https://www.googleapis.com/youtube/v3/playlists"

        headers = {'Authorization': f'Bearer {account.access_token}'}
        params = {'part': 'snippet,status', 'channelId': self.youtube_id}

        res = requests.get(url, headers=headers, params=params).json()

        for item in res.get('items', []):
            self.env['youtube.playlist'].create_or_update_from_api(self, item)

    def action_fetch_channel_by_id(self):
        self.ensure_one()

        account = self.google_account_id
        account._ensure_token()

        import requests

        url = "https://www.googleapis.com/youtube/v3/channels"

        headers = {'Authorization': f'Bearer {account.access_token}'}
        params = {
            'part': 'snippet,statistics,status,brandingSettings',
            'id': self.youtube_id
        }

        res = requests.get(url, headers=headers, params=params).json()

        if res.get('items'):
            self.create_or_update_from_api(account, res['items'][0])