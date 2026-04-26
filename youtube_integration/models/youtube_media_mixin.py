"""Abstract mixin shared by ``youtube.video`` and ``youtube.short``.

Both models map to YouTube videos at the API level (Shorts are just videos
under 60 seconds), so they share almost the entire field set and most of the
fetch/upload behaviour. The mixin captures all of that, while the concrete
models add their own structural fields:

- ``youtube.video`` (Episode): ``playlist_id``, ``short_ids``, analytics, etc.
- ``youtube.short``  (Reel):    ``video_id`` (parent episode), ``reel_number``.
"""
import base64
import os

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

from . import _helpers


PRIVACY_STATUS_SELECTION = [
    ('public', 'Public'),
    ('unlisted', 'Unlisted'),
    ('private', 'Private'),
]

UPLOAD_STATUS_SELECTION = [
    ('uploaded', 'Uploaded'),
    ('processed', 'Processed'),
    ('failed', 'Failed'),
    ('rejected', 'Rejected'),
    ('deleted', 'Deleted'),
]

LICENSE_SELECTION = [
    ('youtube', 'Standard YouTube License'),
    ('creativeCommon', 'Creative Commons'),
]

DEFINITION_SELECTION = [
    ('hd', 'HD'),
    ('sd', 'SD'),
]

DIMENSION_SELECTION = [
    ('2d', '2D'),
    ('3d', '3D'),
]

PROJECTION_SELECTION = [
    ('rectangular', 'Rectangular'),
    ('360', '360'),
]

CAPTION_SELECTION = [
    ('true', 'Yes'),
    ('false', 'No'),
]

LIVE_BROADCAST_SELECTION = [
    ('none', 'None'),
    ('upcoming', 'Upcoming'),
    ('live', 'Live'),
    ('completed', 'Completed'),
]

CONTENT_TYPE_SELECTION = [
    ('episode', 'Episode'),
    ('short', 'Short'),
]

PLATFORM_SELECTION = [
    ('youtube', 'YouTube'),
    ('facebook', 'Facebook'),
    ('instagram', 'Instagram'),
]

PLATFORM_FORMAT_SELECTION = [
    ('long_video', 'Long Video'),
    ('short', 'Shorts'),
    ('video', 'Video'),
    ('reel', 'Reel'),
]


class YouTubeMediaMixin(models.AbstractModel):
    _name = 'youtube.media.mixin'
    _description = 'YouTube Media Mixin'

    # =========================================================
    # Basic Info (snippet)
    # =========================================================
    name = fields.Char()
    youtube_id = fields.Char(index=True)
    youtube_url = fields.Char(compute='_compute_youtube_url')

    description = fields.Text()
    tags = fields.Char(help="Comma separated tags")
    category_id = fields.Char(string='Category ID')
    default_language = fields.Char()
    default_audio_language = fields.Char()
    published_at = fields.Datetime()
    channel_youtube_id = fields.Char(string='Channel YouTube ID')
    channel_title = fields.Char()
    live_broadcast_content = fields.Selection(LIVE_BROADCAST_SELECTION)

    # =========================================================
    # Media
    # =========================================================
    video_file_path = fields.Char()

    thumbnail = fields.Binary()
    thumbnail_url = fields.Char()
    custom_thumbnail = fields.Binary(help="Optional custom thumbnail to set on YouTube after upload")
    custom_thumbnail_filename = fields.Char()

    # =========================================================
    # YouTube Statistics
    # =========================================================
    view_count = fields.Integer()
    like_count = fields.Integer()
    dislike_count = fields.Integer()
    comment_count = fields.Integer()
    favorite_count = fields.Integer()

    # =========================================================
    # Content Details
    # =========================================================
    duration = fields.Char(help="ISO 8601 duration (e.g. PT1H2M10S)")
    duration_seconds = fields.Integer()
    definition = fields.Selection(DEFINITION_SELECTION)
    dimension = fields.Selection(DIMENSION_SELECTION)
    caption = fields.Selection(CAPTION_SELECTION)
    licensed_content = fields.Boolean()
    projection = fields.Selection(PROJECTION_SELECTION)

    # =========================================================
    # Status / Meta
    # =========================================================
    status = fields.Char(help="Legacy privacy status field")
    privacy_status = fields.Selection(PRIVACY_STATUS_SELECTION, default='private')
    upload_status = fields.Selection(UPLOAD_STATUS_SELECTION)
    license = fields.Selection(LICENSE_SELECTION, default='youtube')
    embeddable = fields.Boolean(default=True)
    public_stats_viewable = fields.Boolean(default=True)
    made_for_kids = fields.Boolean()
    self_declared_made_for_kids = fields.Boolean()
    publish_at = fields.Datetime(help="Scheduled publish time (privacy must be private)")
    is_short = fields.Boolean()

    # =========================================================
    # Topic / Recording / Live
    # =========================================================
    topic_categories = fields.Text()
    recording_date = fields.Datetime()
    actual_start_time = fields.Datetime()
    actual_end_time = fields.Datetime()
    scheduled_start_time = fields.Datetime()
    scheduled_end_time = fields.Datetime()
    concurrent_viewers = fields.Integer()

    # =========================================================
    # Damma Dashboard fields
    # =========================================================
    program_code = fields.Char()
    program_name = fields.Char()
    asset_code = fields.Char(help="Unique asset code, e.g. HAW-2026-W15-YTEP")
    base_episode_code = fields.Char(help="e.g. HAW | 2026 | WK15")
    display_name = fields.Char()
    week_label = fields.Char(help="e.g. WK15")
    week_number = fields.Integer()
    year = fields.Integer()
    publish_day = fields.Char(help="Monday..Sunday")
    content_type = fields.Selection(CONTENT_TYPE_SELECTION)
    platform = fields.Selection(PLATFORM_SELECTION, default='youtube')
    platform_format = fields.Selection(PLATFORM_FORMAT_SELECTION)

    topic = fields.Char()
    guest = fields.Char()
    hook = fields.Char()

    # Dashboard analytics aggregates
    reach = fields.Integer()
    shares = fields.Integer()
    saves = fields.Integer()
    watch_time_min = fields.Float(string='Watch Time (min)')
    avg_view_duration_sec = fields.Float(string='Avg View Duration (sec)')
    avg_pct_viewed = fields.Float(string='Avg % Viewed')
    retention_30s_pct = fields.Float(string='Retention 30s %')
    followers_gained = fields.Integer()
    engagement_rate = fields.Float(compute='_compute_engagement_rate', store=True)

    # =========================================================
    # Upload tracking
    # =========================================================
    upload_url = fields.Text()
    upload_progress = fields.Integer(default=0)
    file_size = fields.Integer()

    # =========================================================
    # COMPUTED
    # =========================================================
    @api.depends('youtube_id')
    def _compute_youtube_url(self):
        for rec in self:
            rec.youtube_url = (
                f"https://www.youtube.com/watch?v={rec.youtube_id}"
                if rec.youtube_id else False
            )

    @api.depends('view_count', 'like_count', 'comment_count', 'shares', 'saves',
                 'reach', 'followers_gained')
    def _compute_engagement_rate(self):
        for rec in self:
            views = rec.view_count or rec.reach or 0
            if not views:
                rec.engagement_rate = 0.0
                continue
            interactions = (
                (rec.like_count or 0)
                + (rec.comment_count or 0)
                + (rec.shares or 0)
                + (rec.saves or 0)
            )
            rec.engagement_rate = interactions / views

    # =========================================================
    # ABSTRACT: subclasses must resolve their google.account
    # =========================================================
    def _get_account(self):
        raise NotImplementedError("Subclasses must implement _get_account")

    # =========================================================
    # FETCH FROM YOUTUBE
    # =========================================================
    def action_fetch_video_by_id(self):
        for rec in self:
            rec._fetch_one()
        return True

    def _fetch_one(self):
        self.ensure_one()

        if not self.youtube_id:
            raise UserError("No YouTube ID provided")

        account = self._get_account()
        if not account:
            raise UserError("No Google account linked")
        account._ensure_token()

        url = "https://www.googleapis.com/youtube/v3/videos"
        headers = {'Authorization': f'Bearer {account.access_token}'}
        params = {
            'part': 'snippet,statistics,status,contentDetails,topicDetails,'
                    'recordingDetails,liveStreamingDetails,localizations',
            'id': self.youtube_id,
        }
        res = requests.get(url, headers=headers, params=params, timeout=30).json()

        if res.get('error'):
            raise UserError(res['error'].get('message', 'YouTube API error'))
        if not res.get('items'):
            raise UserError("Video not found")

        vals = _helpers.parse_video_payload(res['items'][0])
        # Drop falsy thumbnail entries to avoid wiping existing thumbnails
        if not vals.get('thumbnail'):
            vals.pop('thumbnail', None)
        self.write(vals)

    # =========================================================
    # RESUMABLE UPLOAD
    # =========================================================
    def action_upload_video_resumable(self):
        self.ensure_one()

        if not self.video_file_path:
            raise UserError("No file path provided")
        if not os.path.exists(self.video_file_path):
            raise UserError("File does not exist")

        self.file_size = os.path.getsize(self.video_file_path)

        account = self._get_account()
        if not account:
            raise UserError("No Google account linked")
        account._ensure_token()

        if not self.upload_url:
            self.upload_url = self._initiate_upload(account)

        self._resume_upload()

        if self.youtube_id:
            self._update_recording_details(account)
            if self.custom_thumbnail:
                try:
                    self._upload_thumbnail(account)
                except Exception:
                    pass
            self._post_upload_hook(account)
            try:
                self._fetch_one()
            except Exception:
                pass

    def _post_upload_hook(self, account):
        """Override in subclasses to do model-specific post-upload work
        (e.g. add to playlist for ``youtube.video``)."""
        return

    def _initiate_upload(self, account):
        url = (
            "https://www.googleapis.com/upload/youtube/v3/videos"
            "?uploadType=resumable&part=snippet,status"
        )
        headers = {
            'Authorization': f'Bearer {account.access_token}',
            'Content-Type': 'application/json',
            'X-Upload-Content-Length': str(self.file_size),
            'X-Upload-Content-Type': 'video/*',
        }
        body = self._build_upload_body()
        res = requests.post(url, headers=headers, json=body, timeout=60)
        if res.status_code not in (200, 201):
            raise UserError(res.text)
        return res.headers.get('Location')

    def _build_upload_body(self):
        tags = [t.strip() for t in (self.tags or '').split(',') if t.strip()]
        snippet = {
            'title': self.name or 'Untitled',
            'description': self.description or '',
        }
        if tags:
            snippet['tags'] = tags
        if self.category_id:
            snippet['categoryId'] = self.category_id
        if self.default_language:
            snippet['defaultLanguage'] = self.default_language
        if self.default_audio_language:
            snippet['defaultAudioLanguage'] = self.default_audio_language

        status = {
            'privacyStatus': self.privacy_status or 'private',
            'embeddable': bool(self.embeddable),
            'publicStatsViewable': bool(self.public_stats_viewable),
            'selfDeclaredMadeForKids': bool(self.self_declared_made_for_kids),
        }
        if self.license:
            status['license'] = self.license
        if self.publish_at:
            status['privacyStatus'] = 'private'
            status['publishAt'] = _helpers.format_datetime_rfc3339(self.publish_at)

        return {'snippet': snippet, 'status': status}

    def _update_recording_details(self, account):
        if not self.youtube_id or not self.recording_date:
            return
        url = "https://www.googleapis.com/youtube/v3/videos?part=recordingDetails"
        headers = {
            'Authorization': f'Bearer {account.access_token}',
            'Content-Type': 'application/json',
        }
        body = {
            'id': self.youtube_id,
            'recordingDetails': {
                'recordingDate': _helpers.format_datetime_rfc3339(self.recording_date),
            },
        }
        res = requests.put(url, headers=headers, json=body, timeout=30)
        if res.status_code not in (200, 201):
            raise UserError(res.text)

    def _resume_upload(self):
        chunk_size = 1024 * 1024 * 10  # 10 MB
        uploaded = self._get_uploaded_bytes()

        with open(self.video_file_path, 'rb') as f:
            f.seek(uploaded)
            while uploaded < self.file_size:
                end = min(uploaded + chunk_size - 1, self.file_size - 1)
                chunk = f.read(end - uploaded + 1)
                headers = {
                    'Content-Length': str(len(chunk)),
                    'Content-Range': f'bytes {uploaded}-{end}/{self.file_size}',
                }
                res = requests.put(self.upload_url, headers=headers, data=chunk, timeout=600)

                if res.status_code in (200, 201):
                    try:
                        data = res.json()
                        self.youtube_id = data.get('id')
                    except Exception:
                        pass
                    self.upload_progress = self.file_size
                    return
                elif res.status_code == 308:
                    uploaded = self._parse_range(res)
                    self.upload_progress = uploaded
                else:
                    raise UserError(f"Upload failed: {res.text}")

    def _get_uploaded_bytes(self):
        headers = {'Content-Range': f'bytes */{self.file_size}'}
        res = requests.put(self.upload_url, headers=headers, timeout=60)
        if res.status_code == 308:
            return self._parse_range(res)
        return 0

    def _parse_range(self, res):
        range_header = res.headers.get('Range')
        if not range_header:
            return 0
        return int(range_header.split('-')[1]) + 1

    # =========================================================
    # THUMBNAIL UPLOAD
    # =========================================================
    def _upload_thumbnail(self, account):
        self.ensure_one()
        if not self.youtube_id or not self.custom_thumbnail:
            return
        account._ensure_token()
        url = (
            "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
            f"?videoId={self.youtube_id}&uploadType=media"
        )
        content_type = 'image/jpeg'
        name = (self.custom_thumbnail_filename or '').lower()
        if name.endswith('.png'):
            content_type = 'image/png'
        headers = {
            'Authorization': f'Bearer {account.access_token}',
            'Content-Type': content_type,
        }
        data = base64.b64decode(self.custom_thumbnail)
        res = requests.post(url, headers=headers, data=data, timeout=60)
        if res.status_code not in (200, 201):
            raise UserError(f"Thumbnail upload failed: {res.text}")

    def action_upload_thumbnail(self):
        self.ensure_one()
        account = self._get_account()
        if not account:
            raise UserError("No Google account linked")
        self._upload_thumbnail(account)
