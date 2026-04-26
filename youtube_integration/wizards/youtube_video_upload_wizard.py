import os

from odoo import api, fields, models
from odoo.exceptions import UserError


class YouTubeVideoUploadWizard(models.TransientModel):
    _name = 'youtube.video.upload.wizard'
    _description = 'YouTube Video Upload Wizard'

    # Account / target
    google_account_id = fields.Many2one('google.account', required=True)
    channel_id = fields.Many2one(
        'youtube.channel',
        domain="[('google_account_id', '=', google_account_id)]",
    )
    playlist_id = fields.Many2one(
        'youtube.playlist',
        domain="[('channel_id', '=', channel_id)]",
        help="Optional: add the new video to this playlist after upload",
    )

    # Video file
    video_file_path = fields.Char(
        string='Video File Path',
        required=True,
        help="Absolute path on the Odoo server to the video file to upload",
    )

    # Snippet
    title = fields.Char(required=True)
    description = fields.Text()
    tags = fields.Char(help="Comma separated tags")
    category_id = fields.Char(
        string='Category ID',
        default='22',
        help="YouTube category ID. Defaults to 22 (People & Blogs).",
    )
    default_language = fields.Char()
    default_audio_language = fields.Char()

    # Status
    privacy_status = fields.Selection(
        [
            ('public', 'Public'),
            ('unlisted', 'Unlisted'),
            ('private', 'Private'),
        ],
        default='private',
        required=True,
    )
    license = fields.Selection(
        [
            ('youtube', 'Standard YouTube License'),
            ('creativeCommon', 'Creative Commons'),
        ],
        default='youtube',
    )
    embeddable = fields.Boolean(default=True)
    public_stats_viewable = fields.Boolean(default=True)
    self_declared_made_for_kids = fields.Boolean()

    # Schedule
    publish_at = fields.Datetime(
        string='Scheduled Publish At',
        help="If set, the video will stay private until this UTC time.",
    )

    # Recording
    recording_date = fields.Datetime()

    # Thumbnail
    custom_thumbnail = fields.Binary(string='Custom Thumbnail')
    custom_thumbnail_filename = fields.Char()

    # ---------------- Onchange ----------------
    @api.onchange('google_account_id')
    def _onchange_google_account_id(self):
        self.channel_id = False
        self.playlist_id = False

    @api.onchange('channel_id')
    def _onchange_channel_id(self):
        self.playlist_id = False

    # ---------------- Action ----------------
    def action_upload(self):
        self.ensure_one()

        if not self.video_file_path or not os.path.exists(self.video_file_path):
            raise UserError("Video file not found at the given path")

        if self.publish_at and self.privacy_status != 'private':
            raise UserError("Scheduled publish requires Privacy Status = Private")

        vals = {
            'name': self.title,
            'description': self.description,
            'tags': self.tags,
            'category_id': self.category_id,
            'default_language': self.default_language,
            'default_audio_language': self.default_audio_language,
            'privacy_status': self.privacy_status,
            'license': self.license,
            'embeddable': self.embeddable,
            'public_stats_viewable': self.public_stats_viewable,
            'self_declared_made_for_kids': self.self_declared_made_for_kids,
            'publish_at': self.publish_at,
            'recording_date': self.recording_date,
            'video_file_path': self.video_file_path,
            'custom_thumbnail': self.custom_thumbnail,
            'custom_thumbnail_filename': self.custom_thumbnail_filename,
            'playlist_id': self.playlist_id.id if self.playlist_id else False,
        }

        video = self.env['youtube.video'].create(vals)

        # If no playlist link was provided, we still need an account for upload.
        # The video model resolves the account via playlist -> channel -> account,
        # so if no playlist is set we temporarily attach it to the channel's
        # "uploads" context by using the selected account directly.
        if not video.playlist_id:
            # Create a synthetic context by using the selected account via a
            # monkeypatched helper: we pass the account into a dedicated upload path.
            self._upload_without_playlist(video)
        else:
            video.action_upload_video_resumable()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'youtube.video',
            'res_id': video.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _upload_without_playlist(self, video):
        """Run the resumable upload using the wizard's account directly."""
        account = self.google_account_id
        account._ensure_token()

        video.file_size = os.path.getsize(video.video_file_path)
        if not video.upload_url:
            video.upload_url = video._initiate_upload(account)

        video._resume_upload()

        if video.youtube_id:
            if video.custom_thumbnail:
                try:
                    video._upload_thumbnail(account)
                except Exception:
                    pass

            try:
                # Fetch fresh metadata using this account (no playlist linkage yet)
                self._fetch_video_with_account(video, account)
            except Exception:
                pass

    def _fetch_video_with_account(self, video, account):
        import requests

        from ..models import _helpers

        url = "https://www.googleapis.com/youtube/v3/videos"
        headers = {'Authorization': f'Bearer {account.access_token}'}
        params = {
            'part': 'snippet,statistics,status,contentDetails,topicDetails,recordingDetails,liveStreamingDetails',
            'id': video.youtube_id,
        }
        res = requests.get(url, headers=headers, params=params, timeout=30).json()
        if res.get('items'):
            vals = _helpers.parse_video_payload(res['items'][0])
            if not vals.get('thumbnail'):
                vals.pop('thumbnail', None)
            video.write(vals)
