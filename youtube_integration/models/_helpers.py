"""Shared helpers for the youtube_integration module.

These utilities are used by both ``youtube.video`` and ``youtube.short`` (and
their wizards), so they live in a small standalone module to avoid duplication.
"""
import base64
import re
from datetime import datetime, timezone

import requests


ISO8601_DURATION_RE = re.compile(
    r'PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?'
)

WEEKDAY_NAMES = [
    'Monday', 'Tuesday', 'Wednesday', 'Thursday',
    'Friday', 'Saturday', 'Sunday',
]


def utcnow():
    """Return a naive UTC datetime (Odoo stores naive UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_datetime(value):
    """Parse an RFC3339 datetime returned by Google APIs into a naive UTC datetime."""
    if not value:
        return False
    value = value.replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return False
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def format_datetime_rfc3339(dt):
    if not dt:
        return False
    return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')


def parse_duration_seconds(duration):
    if not duration:
        return 0
    match = ISO8601_DURATION_RE.fullmatch(duration)
    if not match:
        return 0
    hours = int(match.group('hours') or 0)
    minutes = int(match.group('minutes') or 0)
    seconds = int(match.group('seconds') or 0)
    return hours * 3600 + minutes * 60 + seconds


def is_short_duration(duration_seconds):
    if not duration_seconds:
        return False
    return 0 < duration_seconds <= 60


def get_best_thumbnail(thumbnails):
    if not thumbnails:
        return False
    for key in ('maxres', 'standard', 'high', 'medium', 'default'):
        if key in thumbnails:
            return thumbnails[key].get('url')
    return False


def download_thumbnail(thumb_url, timeout=10):
    if not thumb_url:
        return False
    try:
        img = requests.get(thumb_url, timeout=timeout).content
        return base64.b64encode(img)
    except Exception:
        return False


def publish_day_from_datetime(dt):
    if not dt:
        return False
    return WEEKDAY_NAMES[dt.weekday()]


def parse_video_payload(video):
    """Translate a YouTube ``videos.list`` item dict into Odoo field values.

    Returns a flat dict that's a subset of fields shared between
    ``youtube.video`` and ``youtube.short``. Caller is responsible for adding
    model-specific extras (e.g. parent links).
    """
    snippet = video.get('snippet') or {}
    stats = video.get('statistics') or {}
    status = video.get('status') or {}
    content = video.get('contentDetails') or {}
    topic = video.get('topicDetails') or {}
    recording = video.get('recordingDetails') or {}
    live = video.get('liveStreamingDetails') or {}

    thumb_url = get_best_thumbnail(snippet.get('thumbnails'))
    thumbnail_image = download_thumbnail(thumb_url)

    tags = snippet.get('tags') or []
    duration = content.get('duration')
    duration_seconds = parse_duration_seconds(duration)
    published_at = parse_datetime(snippet.get('publishedAt'))

    return {
        # snippet
        'name': snippet.get('title'),
        'description': snippet.get('description'),
        'published_at': published_at,
        'publish_day': publish_day_from_datetime(published_at),
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
        'publish_at': parse_datetime(status.get('publishAt')),
        'is_short': is_short_duration(duration_seconds),

        # topic
        'topic_categories': '\n'.join(topic.get('topicCategories') or []) or False,

        # recording
        'recording_date': parse_datetime(recording.get('recordingDate')),

        # live
        'actual_start_time': parse_datetime(live.get('actualStartTime')),
        'actual_end_time': parse_datetime(live.get('actualEndTime')),
        'scheduled_start_time': parse_datetime(live.get('scheduledStartTime')),
        'scheduled_end_time': parse_datetime(live.get('scheduledEndTime')),
        'concurrent_viewers': int(live.get('concurrentViewers', 0) or 0),
    }
