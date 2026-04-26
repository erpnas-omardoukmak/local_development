"""``youtube.video`` model — represents a YouTube **Episode** in the
Damma Dashboard hierarchy: channel → playlist (program) → video (episode) →
shorts (reels).

Inherits all the YouTube-API surface from :mod:`youtube_media_mixin` and adds
the structural relations specific to videos:

- ``playlist_id`` (parent program)
- ``short_ids`` (children reels)
- ``analytics_ids`` (per-day analytics)
- helpers to attach to a YouTube playlist after upload
- ``action_convert_to_short_of`` — convert a synced video into a short under a
  specific episode.
"""
import base64

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

from . import _helpers


class YouTubeVideo(models.Model):
    _name = 'youtube.video'
    _inherit = ['youtube.media.mixin']
    _description = 'YouTube Video (Episode)'
    _order = 'published_at desc, id desc'

    # =========================================================
    # Structural
    # =========================================================
    playlist_id = fields.Many2one('youtube.playlist', ondelete='set null')

    short_ids = fields.One2many('youtube.short', 'video_id', string='Shorts')
    short_count = fields.Integer(compute='_compute_short_count')

    analytics_ids = fields.One2many(
        'youtube.video.analytics',
        'video_id',
        string='Analytics',
    )

    # Default content type for videos
    content_type = fields.Selection(default='episode')
    platform_format = fields.Selection(default='long_video')

    # Related Damma fields from the parent playlist (program)
    program_code = fields.Char(
        related='playlist_id.program_code',
        store=True,
        readonly=False,
    )
    program_name = fields.Char(
        related='playlist_id.program_name',
        store=True,
        readonly=False,
    )

    # =========================================================
    # COMPUTED
    # =========================================================
    @api.depends('short_ids')
    def _compute_short_count(self):
        for rec in self:
            rec.short_count = len(rec.short_ids)

    # =========================================================
    # ACCOUNT RESOLUTION
    # =========================================================
    def _get_account(self):
        self.ensure_one()
        if self.playlist_id and self.playlist_id.channel_id:
            return self.playlist_id.channel_id.google_account_id
        return False

    # =========================================================
    # POST-UPLOAD HOOK: attach to playlist
    # =========================================================
    def _post_upload_hook(self, account):
        super()._post_upload_hook(account)
        if self.playlist_id and self.playlist_id.youtube_id:
            try:
                self._add_to_playlist(account, self.playlist_id.youtube_id)
            except Exception:
                pass

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
            return False
        if 'resourceId' not in snippet:
            return False
        video_id = snippet['resourceId'].get('videoId')
        if not video_id:
            return False

        existing = self.search([('youtube_id', '=', video_id)], limit=1)

        thumb_url = _helpers.get_best_thumbnail(snippet.get('thumbnails', {}))
        thumbnail_image = _helpers.download_thumbnail(thumb_url)
        published_at = _helpers.parse_datetime(snippet.get('publishedAt'))

        vals = {
            'name': snippet.get('title'),
            'youtube_id': video_id,
            'playlist_id': playlist.id,
            'description': snippet.get('description'),
            'published_at': published_at,
            'publish_day': _helpers.publish_day_from_datetime(published_at),
            'channel_youtube_id': snippet.get('channelId'),
            'channel_title': snippet.get('channelTitle'),
            'thumbnail_url': thumb_url,
        }
        if thumbnail_image:
            vals['thumbnail'] = thumbnail_image

        if existing:
            existing.write(vals)
            record = existing
        else:
            record = self.create(vals)

        # Pull the richer metadata
        try:
            record._fetch_one()
        except Exception:
            pass

        # Auto-promote synced items to youtube.short if they're shorts.
        # The user keeps the option to convert manually too.
        if record.duration_seconds and _helpers.is_short_duration(record.duration_seconds):
            try:
                record._auto_split_into_short()
            except Exception:
                pass

        return record

    # =========================================================
    # SHORTS PROMOTION
    # =========================================================
    def _auto_split_into_short(self):
        """If this synced video looks like a Short (<= 60s) and we don't yet
        have it as a ``youtube.short``, create the short row but keep the video
        row in place. The user can later attach it to a parent episode and
        delete this video using ``action_convert_to_short_of``.
        """
        self.ensure_one()
        Short = self.env['youtube.short']
        existing = Short.search([('youtube_id', '=', self.youtube_id)], limit=1)
        if existing:
            return existing

        return Short.create(self._copy_to_short_vals())

    def _copy_to_short_vals(self):
        """Return a vals dict suitable for creating a ``youtube.short`` from
        this video. Caller is expected to set ``video_id`` + ``reel_number``
        explicitly when known.
        """
        self.ensure_one()
        copy_fields = [
            'name', 'youtube_id', 'description', 'tags', 'category_id',
            'default_language', 'default_audio_language', 'published_at',
            'publish_day', 'channel_youtube_id', 'channel_title',
            'live_broadcast_content',
            'thumbnail', 'thumbnail_url',
            'view_count', 'like_count', 'dislike_count', 'comment_count',
            'favorite_count',
            'duration', 'duration_seconds', 'definition', 'dimension',
            'caption', 'licensed_content', 'projection',
            'status', 'privacy_status', 'upload_status', 'license',
            'embeddable', 'public_stats_viewable', 'made_for_kids',
            'self_declared_made_for_kids', 'publish_at', 'is_short',
            'topic_categories', 'recording_date',
            'actual_start_time', 'actual_end_time',
            'scheduled_start_time', 'scheduled_end_time', 'concurrent_viewers',
            'program_code', 'program_name', 'asset_code', 'base_episode_code',
            'display_name', 'week_label', 'week_number', 'year',
            'topic', 'guest', 'hook',
            'reach', 'shares', 'saves', 'watch_time_min',
            'avg_view_duration_sec', 'avg_pct_viewed', 'retention_30s_pct',
            'followers_gained',
        ]
        vals = {f: self[f] for f in copy_fields}
        vals['platform'] = 'youtube'
        vals['platform_format'] = 'short'
        vals['content_type'] = 'short'
        return vals

    def action_convert_to_short_of(self):
        """Action wizard entry: open a tiny wizard letting the user pick the
        parent episode + reel_number, then convert this row into a
        ``youtube.short`` under that episode and delete this ``youtube.video``
        row."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'youtube.video.to.short.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_source_video_id': self.id},
        }

    # =========================================================
    # ANALYTICS ENTRY
    # =========================================================
    def action_fetch_analytics(self):
        from datetime import date, timedelta

        for rec in self:
            end = date.today()
            start = end - timedelta(days=30)
            self.env['youtube.video.analytics'].fetch_analytics(rec, start, end)
