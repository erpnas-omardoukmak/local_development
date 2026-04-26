"""``youtube.playlist`` represents a **Program** in the Damma Dashboard
hierarchy: channel → playlist (program) → video (episode) → shorts (reels).
"""
import requests

from odoo import fields, models


class YouTubePlaylist(models.Model):
    _name = 'youtube.playlist'
    _description = 'YouTube Playlist (Program)'
    _order = 'program_code, name'

    name = fields.Char()
    youtube_id = fields.Char()

    channel_id = fields.Many2one('youtube.channel')
    video_ids = fields.One2many('youtube.video', 'playlist_id')
    description = fields.Text()
    status = fields.Char()

    # Damma Dashboard program fields
    program_code = fields.Char(
        help="Short program code, e.g. HAW, MTH, SHB, BDB, HJR, FRM",
    )
    program_name = fields.Char(
        help="Human-readable program name, e.g. Haweyah",
    )

    video_count = fields.Integer(compute='_compute_counts')
    short_count = fields.Integer(compute='_compute_counts')

    def _compute_counts(self):
        Short = self.env['youtube.short']
        for rec in self:
            rec.video_count = len(rec.video_ids)
            rec.short_count = Short.search_count([('playlist_id', '=', rec.id)])

    def create_or_update_from_api(self, channel, data):
        existing = self.search([('youtube_id', '=', data['id'])], limit=1)
        vals = {
            'name': data['snippet']['title'],
            'youtube_id': data['id'],
            'channel_id': channel.id,
            'status': data.get('status', {}).get('privacyStatus'),
            'description': data['snippet'].get('description'),
        }
        # Don't clobber a user-set program_name if it already exists.
        if existing:
            existing.write(vals)
        else:
            vals.setdefault('program_name', data['snippet'].get('title'))
            self.create(vals)

    def action_sync_videos(self):
        account = self.channel_id.google_account_id
        account._ensure_token()
        url = "https://www.googleapis.com/youtube/v3/playlistItems"
        headers = {'Authorization': f'Bearer {account.access_token}'}
        params = {'part': 'snippet', 'playlistId': self.youtube_id}
        res = requests.get(url, headers=headers, params=params, timeout=60).json()
        for item in res.get('items', []):
            self.env['youtube.video'].create_or_update_from_api(self, item)

    def action_fetch_playlist_by_id(self):
        self.ensure_one()
        account = self.channel_id.google_account_id
        account._ensure_token()
        url = "https://www.googleapis.com/youtube/v3/playlists"
        headers = {'Authorization': f'Bearer {account.access_token}'}
        params = {'part': 'snippet,status,contentDetails', 'id': self.youtube_id}
        res = requests.get(url, headers=headers, params=params, timeout=30).json()
        if res.get('items'):
            self.create_or_update_from_api(self.channel_id, res['items'][0])

    def action_create_playlist(self):
        self.ensure_one()
        account = self.channel_id.google_account_id
        account._ensure_token()
        url = "https://www.googleapis.com/youtube/v3/playlists?part=snippet,status"
        headers = {
            'Authorization': f'Bearer {account.access_token}',
            'Content-Type': 'application/json',
        }
        data = {
            "snippet": {
                "title": self.name,
                "description": self.description or "",
            },
            "status": {
                "privacyStatus": self.status,
            },
        }
        res = requests.post(url, headers=headers, json=data, timeout=30).json()
        self.youtube_id = res.get('id')
