from odoo import models, fields, api
from datetime import date, timedelta
import requests


class YouTubeVideoAnalytics(models.Model):
    _name = 'youtube.video.analytics'
    _description = 'YouTube Video Analytics'
    _order = 'date desc'

    video_id = fields.Many2one('youtube.video', required=True, ondelete='cascade')
    date = fields.Date(required=True)

    # Core metrics
    views = fields.Integer()
    likes = fields.Integer()
    comments = fields.Integer()

    # Advanced metrics (Analytics API)
    estimated_minutes_watched = fields.Float()
    average_view_duration = fields.Float()
    subscribers_gained = fields.Integer()
    subscribers_lost = fields.Integer()

    # Derived
    engagement_rate = fields.Float(compute="_compute_engagement")

    @api.depends('views', 'likes', 'comments')
    def _compute_engagement(self):
        for rec in self:
            if rec.views:
                rec.engagement_rate = (rec.likes + rec.comments) / rec.views
            else:
                rec.engagement_rate = 0.0

    _sql_constraints = [
        ('video_date_unique', 'unique(video_id, date)', 'Analytics already exists for this date!')
    ]

    # ==========================================
    # FETCH ANALYTICS FROM YOUTUBE
    # ==========================================
    def fetch_analytics(self, video, start_date, end_date):
        account = video._get_account()
        if not account:
            return

        account._ensure_token()

        url = "https://youtubeanalytics.googleapis.com/v2/reports"

        params = {
            'ids': 'channel==MINE',
            'startDate': start_date.strftime('%Y-%m-%d'),
            'endDate': end_date.strftime('%Y-%m-%d'),
            'metrics': ','.join([
                'views',
                'likes',
                'comments',
                'estimatedMinutesWatched',
                'averageViewDuration',
                'subscribersGained',
                'subscribersLost',
            ]),
            'dimensions': 'day',
            'filters': f'video=={video.youtube_id}',
        }

        headers = {
            'Authorization': f'Bearer {account.access_token}'
        }

        res = requests.get(url, headers=headers, params=params, timeout=60).json()
        print('res=====================', res)
        if 'rows' not in res:
            return

        for row in res['rows']:
            rec_date = row[0]

            vals = {
                'video_id': video.id,
                'date': rec_date,
                'views': int(row[1]),
                'likes': int(row[2]),
                'comments': int(row[3]),
                'estimated_minutes_watched': float(row[4]),
                'average_view_duration': float(row[5]),
                'subscribers_gained': int(row[6]),
                'subscribers_lost': int(row[7]),
            }

            existing = self.search([
                ('video_id', '=', video.id),
                ('date', '=', rec_date)
            ], limit=1)

            if existing:
                existing.write(vals)
            else:
                self.create(vals)
