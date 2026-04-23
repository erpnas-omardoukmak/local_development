import base64
import os
import re

import requests

from odoo import fields, models
from odoo.exceptions import UserError


ISO8601_DURATION_RE = re.compile(
    r'PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?'
)

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


class YouTubeVideo(models.Model):
    _name = 'youtube.video'
    _description = 'YouTube Video'
    _order = 'published_at desc, id desc'

    # -------------------------------
    # Basic Info (snippet)
    # -------------------------------
    name = fields.Char()
    youtube_id = fields.Char(index=True)
    youtube_url = fields.Char(compute='_compute_youtube_url')

    playlist_id = fields.Many2one('youtube.playlist', ondelete='set null')

    description = fields.Text()
    tags = fields.Char(help="Comma separated tags")
    category_id = fields.Char(string='Category ID')
    default_language = fields.Char()
    default_audio_language = fields.Char()
    published_at = fields.Datetime()
    channel_youtube_id = fields.Char(string='Channel YouTube ID')
    channel_title = fields.Char()
    live_broadcast_content = fields.Selection(LIVE_BROADCAST_SELECTION)

    # -------------------------------
    # Media
    # -------------------------------
    video_file_path = fields.Char()

    thumbnail = fields.Binary()
    thumbnail_url = fields.Char()
    custom_thumbnail = fields.Binary(help="Optional custom thumbnail to set on YouTube after upload")
    custom_thumbnail_filename = fields.Char()

    # -------------------------------
    # Statistics
    # -------------------------------
    view_count = fields.Integer()
    like_count = fields.Integer()
    dislike_count = fields.Integer()
    comment_count = fields.Integer()
    favorite_count = fields.Integer()

    # -------------------------------
    # Content Details
    # -------------------------------
    duration = fields.Char(help="ISO 8601 duration (e.g. PT1H2M10S)")
    duration_seconds = fields.Integer()
    definition = fields.Selection(DEFINITION_SELECTION)
    dimension = fields.Selection(DIMENSION_SELECTION)
    caption = fields.Selection(CAPTION_SELECTION)
    licensed_content = fields.Boolean()
    projection = fields.Selection(PROJECTION_SELECTION)

    # -------------------------------
    # Status / Meta
    # -------------------------------
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

    # -------------------------------
    # Topic / Recording / Live
    # -------------------------------
    topic_categories = fields.Text()
    recording_date = fields.Datetime()
    actual_start_time = fields.Datetime()
    actual_end_time = fields.Datetime()
    scheduled_start_time = fields.Datetime()
    scheduled_end_time = fields.Datetime()
    concurrent_viewers = fields.Integer()

    # -------------------------------
    # Upload tracking
    # -------------------------------
    upload_url = fields.Text()
    upload_progress = fields.Integer(default=0)
    file_size = fields.Integer()

    # =========================================================
    # COMPUTED
    # =========================================================
    def _compute_youtube_url(self):
        for rec in self:
            rec.youtube_url = f"https://www.youtube.com/watch?v={rec.youtube_id}" if rec.youtube_id else False

    # =========================================================
    # FETCH VIDEO BY ID
    # =========================================================
    def action_fetch_video_by_id(self):
        self.ensure_one()

        if not self.youtube_id:
            raise UserError("No YouTube ID provided")

        account = self._get_account()
        if not account:
            raise UserError("No Google account linked to this video")
        account._ensure_token()

        url = "https://www.googleapis.com/youtube/v3/videos"

        headers = {
            'Authorization': f'Bearer {account.access_token}'
        }

        params = {
            'part': 'snippet,statistics,status,contentDetails,topicDetails,recordingDetails,liveStreamingDetails,localizations',
            'id': self.youtube_id,
        }

        res = requests.get(url, headers=headers, params=params, timeout=30).json()

        if res.get('error'):
            raise UserError(res['error'].get('message', 'YouTube API error'))

        if not res.get('items'):
            raise UserError("Video not found")

        vals = self._parse_video_payload(res['items'][0])
        self.write(vals)

    # =========================================================
    # PARSE VIDEO PAYLOAD (shared between fetch & sync)
    # =========================================================
    def _parse_video_payload(self, video):
        snippet = video.get('snippet') or {}
        stats = video.get('statistics') or {}
        status = video.get('status') or {}
        content = video.get('contentDetails') or {}
        topic = video.get('topicDetails') or {}
        recording = video.get('recordingDetails') or {}
        live = video.get('liveStreamingDetails') or {}

        thumb_url = self._get_best_thumbnail(snippet.get('thumbnails'))

        thumbnail_image = False
        if thumb_url:
            try:
                img = requests.get(thumb_url, timeout=10).content
                thumbnail_image = base64.b64encode(img)
            except Exception:
                pass

        tags = snippet.get('tags') or []

        duration = content.get('duration')
        duration_seconds = self._parse_duration_seconds(duration)

        vals = {
            # snippet
            'name': snippet.get('title'),
            'description': snippet.get('description'),
            'published_at': self._parse_datetime(snippet.get('publishedAt')),
            'channel_youtube_id': snippet.get('channelId'),
            'channel_title': snippet.get('channelTitle'),
            'tags': ', '.join(tags) if tags else False,
            'category_id': snippet.get('categoryId'),
            'default_language': snippet.get('defaultLanguage'),
            'default_audio_language': snippet.get('defaultAudioLanguage'),
            'live_broadcast_content': snippet.get('liveBroadcastContent'),

            # thumbnails
            'thumbnail': thumbnail_image,
            'thumbnail_url': thumb_url,

            # statistics
            'view_count': int(stats.get('viewCount', 0) or 0),
            'like_count': int(stats.get('likeCount', 0) or 0),
            'dislike_count': int(stats.get('dislikeCount', 0) or 0),
            'comment_count': int(stats.get('commentCount', 0) or 0),
            'favorite_count': int(stats.get('favoriteCount', 0) or 0),

            # contentDetails
            'duration': duration,
            'duration_seconds': duration_seconds,
            'definition': content.get('definition'),
            'dimension': content.get('dimension'),
            'caption': content.get('caption'),
            'licensed_content': bool(content.get('licensedContent')),
            'projection': content.get('projection'),

            # status
            'status': status.get('privacyStatus'),
            'privacy_status': status.get('privacyStatus'),
            'upload_status': status.get('uploadStatus'),
            'license': status.get('license'),
            'embeddable': bool(status.get('embeddable', True)),
            'public_stats_viewable': bool(status.get('publicStatsViewable', True)),
            'made_for_kids': bool(status.get('madeForKids')),
            'self_declared_made_for_kids': bool(status.get('selfDeclaredMadeForKids')),
            'publish_at': self._parse_datetime(status.get('publishAt')),
            'is_short': self._is_short(duration_seconds),

            # topic
            'topic_categories': '\n'.join(topic.get('topicCategories') or []) or False,

            # recording
            'recording_date': self._parse_datetime(recording.get('recordingDate')),

            # live
            'actual_start_time': self._parse_datetime(live.get('actualStartTime')),
            'actual_end_time': self._parse_datetime(live.get('actualEndTime')),
            'scheduled_start_time': self._parse_datetime(live.get('scheduledStartTime')),
            'scheduled_end_time': self._parse_datetime(live.get('scheduledEndTime')),
            'concurrent_viewers': int(live.get('concurrentViewers', 0) or 0),
        }
        return vals

    # =========================================================
    # HELPERS
    # =========================================================
    def _get_account(self):
        self.ensure_one()
        if self.playlist_id and self.playlist_id.channel_id:
            return self.playlist_id.channel_id.google_account_id
        return False

    def _get_best_thumbnail(self, thumbnails):
        if not thumbnails:
            return False
        for key in ('maxres', 'standard', 'high', 'medium', 'default'):
            if key in thumbnails:
                return thumbnails[key].get('url')
        return False

    def _parse_duration_seconds(self, duration):
        if not duration:
            return 0
        match = ISO8601_DURATION_RE.fullmatch(duration)
        if not match:
            return 0
        hours = int(match.group('hours') or 0)
        minutes = int(match.group('minutes') or 0)
        seconds = int(match.group('seconds') or 0)
        return hours * 3600 + minutes * 60 + seconds

    def _is_short(self, duration_seconds):
        if not duration_seconds:
            return False
        return 0 < duration_seconds <= 60

    def _parse_datetime(self, value):
        if not value:
            return False
        # YouTube returns RFC3339; Odoo stores naive UTC datetimes
        from datetime import datetime
        value = value.replace('Z', '+00:00')
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return False
        if dt.tzinfo is not None:
            dt = dt.astimezone(tz=None).replace(tzinfo=None)
        return dt

    def _format_datetime_rfc3339(self, dt):
        if not dt:
            return False
        return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')

    # =========================================================
    # RESUMABLE UPLOAD (ENTRY)
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
            raise UserError("No Google account linked (attach this video to a playlist -> channel -> account)")
        account._ensure_token()

        if not self.upload_url:
            self.upload_url = self._initiate_upload(account)

        self._resume_upload()

        # After successful upload: set custom thumbnail and add to playlist.
        if self.youtube_id:
            if self.custom_thumbnail:
                try:
                    self._upload_thumbnail(account)
                except Exception:
                    # Upload of thumbnail is non-fatal
                    pass

            if self.playlist_id and self.playlist_id.youtube_id:
                try:
                    self._add_to_playlist(account, self.playlist_id.youtube_id)
                except Exception:
                    pass

            # Refresh metadata from YouTube so stats/status are up-to-date
            try:
                self.action_fetch_video_by_id()
            except Exception:
                pass

    # =========================================================
    # INITIATE UPLOAD
    # =========================================================
    def _initiate_upload(self, account):
        url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"

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
            # YouTube requires privacyStatus=private when scheduling
            status['privacyStatus'] = 'private'
            status['publishAt'] = self._format_datetime_rfc3339(self.publish_at)

        body = {'snippet': snippet, 'status': status}

        if self.recording_date:
            body['recordingDetails'] = {
                'recordingDate': self._format_datetime_rfc3339(self.recording_date),
            }

        return body

    # =========================================================
    # RESUME UPLOAD
    # =========================================================
    def _resume_upload(self):
        chunk_size = 1024 * 1024 * 10  # 10MB

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

    # =========================================================
    # GET UPLOADED BYTES
    # =========================================================
    def _get_uploaded_bytes(self):
        headers = {
            'Content-Range': f'bytes */{self.file_size}',
        }

        res = requests.put(self.upload_url, headers=headers, timeout=60)

        if res.status_code == 308:
            return self._parse_range(res)

        return 0

    # =========================================================
    # PARSE RANGE
    # =========================================================
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
            raise UserError("No Google account linked to this video")
        self._upload_thumbnail(account)

    # =========================================================
    # PLAYLIST ATTACH
    # =========================================================
    def _add_to_playlist(self, account, playlist_youtube_id):
        self.ensure_one()
        if not self.youtube_id or not playlist_youtube_id:
            return

        account._ensure_token()
        url = "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"
        headers = {
            'Authorization': f'Bearer {account.access_token}',
            'Content-Type': 'application/json',
        }
        body = {
            'snippet': {
                'playlistId': playlist_youtube_id,
                'resourceId': {
                    'kind': 'youtube#video',
                    'videoId': self.youtube_id,
                },
            }
        }

        res = requests.post(url, headers=headers, json=body, timeout=30)
        if res.status_code not in (200, 201):
            raise UserError(f"Failed to add to playlist: {res.text}")

    # =========================================================
    # CREATE/UPDATE FROM PLAYLISTITEMS LIST
    # =========================================================
    def create_or_update_from_api(self, playlist, data):
        snippet = data.get('snippet', {})

        if snippet.get('title') in ('Private video', 'Deleted video'):
            return

        if 'resourceId' not in snippet:
            return

        video_id = snippet['resourceId'].get('videoId')
        if not video_id:
            return

        existing = self.search([('youtube_id', '=', video_id)], limit=1)

        thumbnails = snippet.get('thumbnails', {})
        thumb_url = self._get_best_thumbnail(thumbnails)

        thumbnail_image = False
        if thumb_url:
            try:
                img = requests.get(thumb_url, timeout=10).content
                thumbnail_image = base64.b64encode(img)
            except Exception:
                pass

        vals = {
            'name': snippet.get('title'),
            'youtube_id': video_id,
            'playlist_id': playlist.id,
            'description': snippet.get('description'),
            'published_at': self._parse_datetime(snippet.get('publishedAt')),
            'channel_youtube_id': snippet.get('channelId'),
            'channel_title': snippet.get('channelTitle'),

            'thumbnail': thumbnail_image,
            'thumbnail_url': thumb_url,
        }

        if existing:
            existing.write(vals)
            record = existing
        else:
            record = self.create(vals)

        # Fetch richer stats/status/contentDetails for the video
        try:
            record.action_fetch_video_by_id()
        except Exception:
            pass

        return record
