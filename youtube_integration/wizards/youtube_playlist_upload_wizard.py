from odoo import api, fields, models
from odoo.exceptions import UserError
import requests


class YouTubePlaylistUploadWizard(models.TransientModel):
    _name = 'youtube.playlist.upload.wizard'
    _description = 'YouTube Playlist Upload Wizard'

    google_account_id = fields.Many2one('google.account', required=True)
    channel_id = fields.Many2one(
        'youtube.channel',
        domain="[('google_account_id', '=', google_account_id)]",
        required=True,
    )

    name = fields.Char(required=True)
    description = fields.Text()

    privacy_status = fields.Selection(
        [
            ('public', 'Public'),
            ('unlisted', 'Unlisted'),
            ('private', 'Private'),
        ],
        default='private',
        required=True,
    )

    @api.onchange('google_account_id')
    def _onchange_google_account_id(self):
        self.channel_id = False

    def action_upload_playlist(self):
        self.ensure_one()

        account = self.google_account_id
        account._ensure_token()

        url = "https://www.googleapis.com/youtube/v3/playlists?part=snippet,status"

        headers = {
            'Authorization': f'Bearer {account.access_token}',
            'Content-Type': 'application/json'
        }

        body = {
            "snippet": {
                "title": self.name,
                "description": self.description or ""
            },
            "status": {
                "privacyStatus": self.privacy_status
            }
        }

        res = requests.post(url, headers=headers, json=body, timeout=30)

        if res.status_code not in (200, 201):
            error = res.json().get('error', {}).get('message', res.text)
            raise UserError(f"Playlist creation failed:\n{error}")

        data = res.json()

        playlist = self.env['youtube.playlist'].create({
            'name': self.name,
            'youtube_id': data.get('id'),
            'channel_id': self.channel_id.id,
            'status': self.privacy_status,
            'description': self.description,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'youtube.playlist',
            'res_id': playlist.id,
            'view_mode': 'form',
            'target': 'current',
        }