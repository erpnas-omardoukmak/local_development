from odoo import models, fields


class YouTubePlaylist(models.Model):
    _name = 'youtube.playlist'

    name = fields.Char()
    youtube_id = fields.Char()

    channel_id = fields.Many2one('youtube.channel')
    video_ids = fields.One2many('youtube.video', 'playlist_id')
    description = fields.Text()
    status = fields.Char()

    def create_or_update_from_api(self, channel, data):
        existing = self.search([('youtube_id', '=', data['id'])], limit=1)
        vals = {
            'name': data['snippet']['title'],
            'youtube_id': data['id'],
            'channel_id': channel.id,
            'status': data.get('status', {}).get('privacyStatus'),
            'description': data['snippet']['description']
        }

        if existing:
            existing.write(vals)
        else:
            self.create(vals)

    def action_sync_videos(self):
        import requests

        account = self.channel_id.google_account_id
        account._ensure_token()

        url = "https://www.googleapis.com/youtube/v3/playlistItems"

        headers = {'Authorization': f'Bearer {account.access_token}'}
        params = {'part': 'snippet', 'playlistId': self.youtube_id}

        res = requests.get(url, headers=headers, params=params).json()

        for item in res.get('items', []):
            self.env['youtube.video'].create_or_update_from_api(self, item)

    def action_fetch_playlist_by_id(self):
        self.ensure_one()

        account = self.channel_id.google_account_id
        account._ensure_token()

        import requests

        url = "https://www.googleapis.com/youtube/v3/playlists"

        headers = {'Authorization': f'Bearer {account.access_token}'}
        params = {
            'part': 'snippet,status,contentDetails',
            'id': self.youtube_id
        }

        res = requests.get(url, headers=headers, params=params).json()
        if res.get('items'):
            self.create_or_update_from_api(self.channel_id, res['items'][0])

    def action_create_playlist(self):
        self.ensure_one()

        account = self.channel_id.google_account_id
        account._ensure_token()

        import requests

        url = "https://www.googleapis.com/youtube/v3/playlists?part=snippet,status"

        headers = {
            'Authorization': f'Bearer {account.access_token}',
            'Content-Type': 'application/json'
        }

        data = {
            "snippet": {
                "title": self.name,
                "description": self.description or ""
            },
            "status": {
                "privacyStatus": self.status
            }
        }

        res = requests.post(url, headers=headers, json=data).json()

        self.youtube_id = res.get('id')
