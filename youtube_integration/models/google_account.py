import requests
from datetime import datetime, timedelta
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
            'scope': 'https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube',
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
            self.token_expiry = datetime.utcnow() + timedelta(seconds=res['expires_in'])

    def _ensure_token(self):
        if self.token_expiry and datetime.utcnow() >= self.token_expiry:
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
