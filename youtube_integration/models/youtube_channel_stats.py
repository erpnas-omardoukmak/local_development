from odoo import models, fields


class YouTubeChannelStats(models.Model):
    _name = 'youtube.channel.stats'
    _description = 'YouTube Channel Daily Stats'
    _order = 'date desc'

    channel_id = fields.Many2one('youtube.channel', required=True, ondelete='cascade')
    date = fields.Date(required=True, index=True)

    views = fields.Integer()
    subscribers_gained = fields.Integer()
    subscribers_lost = fields.Integer()
    watch_time = fields.Float()
