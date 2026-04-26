import requests
from datetime import datetime, timedelta, timezone
from odoo import models, fields


class GoogleAccount(models.Model):
    _name = 'google.account'
    _description = 'Google Account'

    name = fields.Char(required=True)

    client_id = fields.Char(required=True)
    client_secret = fields.Char(required=True)

    access_token = fields.Text()
    refresh_token = fields.Text()
    token_expiry = fields.Datetime()

    channel_ids = fields.One2many('youtube.channel', 'google_account_id')

    # ---------------- OAuth ----------------

    def _get_redirect_uri(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/youtube/callback"

    def get_auth_url(self):
        self.ensure_one()

        url = "https://accounts.google.com/o/oauth2/v2/auth"

        params = {
            'client_id': self.client_id,
            'redirect_uri': self._get_redirect_uri(),
            'response_type': 'code',
            'scope': ' '.join([
                'https://www.googleapis.com/auth/youtube.upload',
                'https://www.googleapis.com/auth/youtube',
                'https://www.googleapis.com/auth/youtube.force-ssl',
                'https://www.googleapis.com/auth/yt-analytics.readonly',
            ]),
            'include_granted_scopes': 'true',
            'access_type': 'offline',
            'prompt': 'consent',
            'state': self.id,
        }

        return f"{url}?{requests.compat.urlencode(params)}"

    def exchange_code(self, code):
        token_url = "https://oauth2.googleapis.com/token"

        data = {
            'code': code,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self._get_redirect_uri(),
            'grant_type': 'authorization_code',
        }

        res = requests.post(token_url, data=data).json()

        self.access_token = res.get('access_token')
        if res.get('refresh_token'):
            self.refresh_token = res.get('refresh_token')

        if res.get('expires_in'):
            self.token_expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=res['expires_in'])

    def _ensure_token(self):
        if self.token_expiry and datetime.now(timezone.utc).replace(tzinfo=None) >= self.token_expiry:
            self.refresh_token_func()

    def refresh_token_func(self):
        url = "https://oauth2.googleapis.com/token"

        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': self.refresh_token,
            'grant_type': 'refresh_token',
        }

        res = requests.post(url, data=data).json()
        self.access_token = res.get('access_token')

    # ---------------- UI ----------------

    def action_connect(self):
        return {
            'type': 'ir.actions.act_url',
            'url': self.get_auth_url(),
            'target': 'self',
        }

    # ---------------- SYNC ----------------

    def sync_channels(self):
        self.ensure_one()
        self._ensure_token()

        url = "https://www.googleapis.com/youtube/v3/channels"

        headers = {'Authorization': f'Bearer {self.access_token}'}
        params = {'part': 'snippet,statistics,status', 'mine': 'true'}

        res = requests.get(url, headers=headers, params=params).json()

        for item in res.get('items', []):
            self.env['youtube.channel'].create_or_update_from_api(self, item)

    def fetch_channel_analytics(self, start_date, end_date):
        self.ensure_one()
        self._ensure_token()

        import requests

        url = "https://youtubeanalytics.googleapis.com/v2/reports"

        headers = {
            'Authorization': f'Bearer {self.access_token}'
        }

        params = {
            'ids': 'channel==MINE',
            'startDate': start_date,
            'endDate': end_date,
            'metrics': 'views,estimatedMinutesWatched,subscribersGained,subscribersLost',
            'dimensions': 'day',
        }

        res = requests.get(url, headers=headers, params=params).json()

        if res.get('error'):
            raise Exception(res['error'])

        rows = res.get('rows', [])
        for row in rows:
            date, views, watch_time, gained, lost = row

            self.env['youtube.channel.stats'].create({
                'channel_id': self.channel_ids[:1].id,
                'date': date,
                'views': int(views),
                'watch_time': float(watch_time),
                'subscribers_gained': int(gained),
                'subscribers_lost': int(lost),
            })

    def fetch_video_analytics(self, video, start_date, end_date):
        self.ensure_one()
        self._ensure_token()

        import requests

        url = "https://youtubeanalytics.googleapis.com/v2/reports"

        headers = {
            'Authorization': f'Bearer {self.access_token}'
        }

        params = {
            'ids': 'channel==MINE',
            'startDate': start_date,
            'endDate': end_date,
            'metrics': 'views,likes,comments,estimatedMinutesWatched,averageViewDuration',
            'dimensions': 'day',
            'filters': f'video=={video.youtube_id}',
        }

        res = requests.get(url, headers=headers, params=params).json()

        if res.get('error'):
            raise Exception(res['error'])

        for row in res.get('rows', []):
            date, views, likes, comments, watch_time, avg = row

            self.env['youtube.video.stats'].create({
                'video_id': video.id,
                'date': date,
                'views': int(views),
                'likes': int(likes),
                'comments': int(comments),
                'watch_time': float(watch_time),
                'avg_view_duration': float(avg),
            })

    def cron_fetch_analytics(self):
        from datetime import date, timedelta

        end = date.today()
        start = end - timedelta(days=1)

        for acc in self.search([]):
            acc.fetch_channel_analytics(str(start), str(end))

            for video in self.env['youtube.video'].search([]):
                acc.fetch_video_analytics(video, str(start), str(end))

