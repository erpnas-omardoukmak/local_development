from odoo import models, fields


class YouTubeVideoStats(models.Model):
    _name = 'youtube.video.stats'
    _description = 'YouTube Video Daily Stats'
    _order = 'date desc'

    video_id = fields.Many2one('youtube.video', required=True, ondelete='cascade')
    date = fields.Date(required=True, index=True)

    views = fields.Integer()
    likes = fields.Integer()
    comments = fields.Integer()

    watch_time = fields.Float(help="Minutes watched")
    avg_view_duration = fields.Float(help="Seconds")

    # optional dimensions (future dashboards)
    country = fields.Char()
    device_type = fields.Char()
