import os
import base64
import requests
import re

from odoo import models, fields


class YouTubeVideo(models.Model):
    _name = 'youtube.video'
    _description = 'YouTube Video'

    # -------------------------------
    # Basic Info
    # -------------------------------
    name = fields.Char()
    youtube_id = fields.Char()

    playlist_id = fields.Many2one('youtube.playlist')

    description = fields.Text()

    # -------------------------------
    # Media
    # -------------------------------
    video_file_path = fields.Char()

    thumbnail = fields.Binary()
    thumbnail_url = fields.Char()

    # -------------------------------
    # Statistics
    # -------------------------------
    view_count = fields.Integer()
    like_count = fields.Integer()
    comment_count = fields.Integer()
    favorite_count = fields.Integer()

    # -------------------------------
    # Meta
    # -------------------------------
    status = fields.Char()
    is_short = fields.Boolean()

    # -------------------------------
    # Upload tracking
    # -------------------------------
    upload_url = fields.Text()
    upload_progress = fields.Integer(default=0)
    file_size = fields.Integer()

    # =========================================================
    # FETCH VIDEO BY ID
    # =========================================================
    def action_fetch_video_by_id(self):
        self.ensure_one()

        if not self.youtube_id:
            raise Exception("No YouTube ID provided")

        account = self.playlist_id.channel_id.google_account_id
        account._ensure_token()

        url = "https://www.googleapis.com/youtube/v3/videos"

        headers = {
            'Authorization': f'Bearer {account.access_token}'
        }

        params = {
            'part': 'snippet,statistics,status,contentDetails',
            'id': self.youtube_id
        }

        res = requests.get(url, headers=headers, params=params).json()

        if not res.get('items'):
            raise Exception("Video not found")

        video = res['items'][0]

        snippet = video.get('snippet', {})
        stats = video.get('statistics', {})
        status = video.get('status', {})
        content = video.get('contentDetails', {})

        # Thumbnail
        thumb_url = self._get_best_thumbnail(snippet.get('thumbnails'))

        thumbnail_image = False
        if thumb_url:
            try:
                img = requests.get(thumb_url, timeout=10).content
                thumbnail_image = base64.b64encode(img)
            except Exception:
                pass

        self.write({
            'name': snippet.get('title'),
            'description': snippet.get('description'),

            'thumbnail': thumbnail_image,
            'thumbnail_url': thumb_url,

            'view_count': int(stats.get('viewCount', 0)),
            'like_count': int(stats.get('likeCount', 0)),
            'comment_count': int(stats.get('commentCount', 0)),
            'favorite_count': int(stats.get('favoriteCount', 0)),

            'status': status.get('privacyStatus'),
            'is_short': self._is_short(content.get('duration')),
        })

    # =========================================================
    # THUMBNAIL HELPER
    # =========================================================
    def _get_best_thumbnail(self, thumbnails):
        if not thumbnails:
            return False

        for key in ['maxres', 'standard', 'high', 'medium', 'default']:
            if key in thumbnails:
                return thumbnails[key].get('url')

        return False

    # =========================================================
    # SHORTS DETECTION
    # =========================================================
    def _is_short(self, duration):
        if not duration:
            return False

        match = re.search(r'PT(\d+)S', duration)
        if match:
            return int(match.group(1)) <= 60

        return False

    # =========================================================
    # RESUMABLE UPLOAD (ENTRY)
    # =========================================================
    def action_upload_video_resumable(self):
        self.ensure_one()

        if not self.video_file_path:
            raise Exception("No file path provided")

        if not os.path.exists(self.video_file_path):
            raise Exception("File does not exist")

        self.file_size = os.path.getsize(self.video_file_path)

        account = self.playlist_id.channel_id.google_account_id
        account._ensure_token()

        # Initiate if needed
        if not self.upload_url:
            self.upload_url = self._initiate_upload(account)

        # Resume upload
        self._resume_upload()

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

        body = {
            "snippet": {
                "title": self.name,
                "description": self.description or "",
            },
            "status": {
                "privacyStatus": "private"
            }
        }

        res = requests.post(url, headers=headers, json=body)

        if res.status_code not in (200, 201):
            raise Exception(res.text)

        return res.headers.get('Location')

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

                res = requests.put(self.upload_url, headers=headers, data=chunk)

                if res.status_code in (200, 201):
                    # Upload finished
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
                    raise Exception(f"Upload failed: {res.text}")

    # =========================================================
    # GET UPLOADED BYTES
    # =========================================================
    def _get_uploaded_bytes(self):
        headers = {
            'Content-Range': f'bytes */{self.file_size}',
        }

        res = requests.put(self.upload_url, headers=headers)

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

    def create_or_update_from_api(self, playlist, data):
        snippet = data.get('snippet', {})

        # Skip invalid videos
        if snippet.get('title') in ('Private video', 'Deleted video'):
            return

        if 'resourceId' not in snippet:
            return

        video_id = snippet['resourceId'].get('videoId')
        if not video_id:
            return

        existing = self.search([('youtube_id', '=', video_id)], limit=1)

        # Thumbnail
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

            'thumbnail': thumbnail_image,
            'thumbnail_url': thumb_url,
        }

        if existing:
            existing.write(vals)
        else:
            self.create(vals)