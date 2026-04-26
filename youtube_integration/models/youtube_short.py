"""``youtube.short`` model — represents a YouTube **Reel/Short** in the Damma
Dashboard hierarchy: channel → playlist (program) → video (episode) →
**shorts (reels)**.

Shorts are O2M to ``youtube.video``. They share the entire YouTube-API surface
(YouTube treats them as regular videos under 60 seconds), so the model inherits
``youtube.media.mixin`` and only adds:

- ``video_id`` — parent episode (M2O, required)
- ``reel_number`` — 1, 2, 3 ... within the parent episode
"""
from odoo import api, fields, models


class YouTubeShort(models.Model):
    _name = 'youtube.short'
    _inherit = ['youtube.media.mixin']
    _description = 'YouTube Short (Reel)'
    _order = 'video_id, reel_number, published_at desc, id desc'

    # =========================================================
    # Structural
    # =========================================================
    video_id = fields.Many2one(
        'youtube.video',
        string='Parent Episode',
        required=True,
        ondelete='cascade',
        index=True,
    )

    reel_number = fields.Integer(default=1)

    # Defaults that make sense for a Short
    content_type = fields.Selection(default='short')
    platform = fields.Selection(default='youtube')
    platform_format = fields.Selection(default='short')
    is_short = fields.Boolean(default=True)

    # Related fields propagated from the parent episode for dashboard reporting.
    playlist_id = fields.Many2one(
        related='video_id.playlist_id',
        store=True,
        index=True,
        string='Program Playlist',
    )
    program_code = fields.Char(
        related='video_id.program_code',
        store=True,
        readonly=False,
    )
    program_name = fields.Char(
        related='video_id.program_name',
        store=True,
        readonly=False,
    )
    base_episode_code = fields.Char(
        related='video_id.base_episode_code',
        store=True,
        readonly=False,
    )

    _sql_constraints = [
        (
            'reel_unique_per_video',
            'unique(video_id, reel_number)',
            'Reel number must be unique within the same parent episode.',
        ),
    ]

    # =========================================================
    # ACCOUNT RESOLUTION
    # =========================================================
    def _get_account(self):
        self.ensure_one()
        if self.video_id:
            return self.video_id._get_account()
        return False

    # =========================================================
    # SHORT-SPECIFIC NAMING / DEFAULTS
    # =========================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('display_name') and vals.get('video_id') and vals.get('reel_number'):
                video = self.env['youtube.video'].browse(vals['video_id'])
                if video.base_episode_code:
                    vals['display_name'] = (
                        f"{video.base_episode_code} | R{vals['reel_number']}"
                    )
        return super().create(vals_list)
