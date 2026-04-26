"""Convert a synced ``youtube.video`` row into a ``youtube.short`` under a
specific parent episode."""
from odoo import api, fields, models
from odoo.exceptions import UserError


class YouTubeVideoToShortWizard(models.TransientModel):
    _name = 'youtube.video.to.short.wizard'
    _description = 'Convert YouTube Video to Short'

    source_video_id = fields.Many2one(
        'youtube.video',
        required=True,
        string='Source video',
        help='The synced video that should be re-classified as a short.',
    )

    parent_video_id = fields.Many2one(
        'youtube.video',
        required=True,
        string='Parent Episode',
        help='The episode this short belongs to.',
    )

    reel_number = fields.Integer(default=1, required=True)

    delete_source = fields.Boolean(
        default=True,
        string='Delete source video',
        help='Remove the source ``youtube.video`` row after creating the short.',
    )

    @api.onchange('parent_video_id')
    def _onchange_parent_video_id(self):
        if self.parent_video_id:
            existing = self.env['youtube.short'].search_count([
                ('video_id', '=', self.parent_video_id.id),
            ])
            self.reel_number = existing + 1

    def action_convert(self):
        self.ensure_one()
        if self.parent_video_id == self.source_video_id:
            raise UserError("Parent episode must be different from the source video.")

        vals = self.source_video_id._copy_to_short_vals()
        vals['video_id'] = self.parent_video_id.id
        vals['reel_number'] = self.reel_number

        Short = self.env['youtube.short']
        existing = Short.search([
            ('youtube_id', '=', self.source_video_id.youtube_id),
        ], limit=1) if self.source_video_id.youtube_id else Short

        if existing:
            existing.write(vals)
            short = existing
        else:
            short = Short.create(vals)

        if self.delete_source:
            self.source_video_id.unlink()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'youtube.short',
            'res_id': short.id,
            'view_mode': 'form',
            'target': 'current',
        }
