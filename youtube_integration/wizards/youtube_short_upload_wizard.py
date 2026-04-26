"""Wizard to upload a YouTube **Short** linked to an existing parent episode.

Mirrors the regular video upload wizard but creates a ``youtube.short`` row
under the chosen parent ``youtube.video``.
"""
import os

from odoo import api, fields, models
from odoo.exceptions import UserError


class YouTubeShortUploadWizard(models.TransientModel):
    _name = 'youtube.short.upload.wizard'
    _description = 'YouTube Short Upload Wizard'

    # Parent linkage
    parent_video_id = fields.Many2one(
        'youtube.video',
        string='Parent Episode',
        required=True,
    )
    google_account_id = fields.Many2one(
        'google.account',
        compute='_compute_account',
        store=False,
    )
    reel_number = fields.Integer(default=1, required=True)

    # File
    video_file_path = fields.Char(
        string='Video File Path',
        required=True,
        help='Absolute path on the Odoo server to the short file (vertical, <= 60s).',
    )

    # Snippet
    title = fields.Char(required=True)
    description = fields.Text()
    tags = fields.Char(help='Comma separated tags. #shorts is recommended.')
    category_id = fields.Char(string='Category ID', default='22')
    default_language = fields.Char()
    default_audio_language = fields.Char()

    # Damma editorial
    topic = fields.Char()
    guest = fields.Char()
    hook = fields.Char()

    # Status
    privacy_status = fields.Selection(
        [
            ('public', 'Public'),
            ('unlisted', 'Unlisted'),
            ('private', 'Private'),
        ],
        default='private',
        required=True,
    )
    license = fields.Selection(
        [
            ('youtube', 'Standard YouTube License'),
            ('creativeCommon', 'Creative Commons'),
        ],
        default='youtube',
    )
    embeddable = fields.Boolean(default=True)
    public_stats_viewable = fields.Boolean(default=True)
    self_declared_made_for_kids = fields.Boolean()

    publish_at = fields.Datetime(
        string='Scheduled Publish At',
        help='If set, the short stays private until this UTC time.',
    )

    custom_thumbnail = fields.Binary(string='Custom Thumbnail')
    custom_thumbnail_filename = fields.Char()

    # ---------------- Computed ----------------
    @api.depends('parent_video_id')
    def _compute_account(self):
        for rec in self:
            account = False
            if rec.parent_video_id:
                account = rec.parent_video_id._get_account()
            rec.google_account_id = account or False

    @api.onchange('parent_video_id')
    def _onchange_parent_video_id(self):
        if self.parent_video_id:
            existing = self.env['youtube.short'].search_count([
                ('video_id', '=', self.parent_video_id.id),
            ])
            self.reel_number = existing + 1
            if not self.title and self.parent_video_id.base_episode_code:
                self.title = (
                    f"{self.parent_video_id.base_episode_code} | R{self.reel_number}"
                )

    # ---------------- Action ----------------
    def action_upload(self):
        self.ensure_one()
        if not self.video_file_path or not os.path.exists(self.video_file_path):
            raise UserError("Short file not found at the given path")
        if self.publish_at and self.privacy_status != 'private':
            raise UserError("Scheduled publish requires Privacy Status = Private")

        account = self.parent_video_id._get_account()
        if not account:
            raise UserError(
                "The parent episode has no Google account linked "
                "(playlist → channel → account)."
            )

        existing = self.env['youtube.short'].search([
            ('video_id', '=', self.parent_video_id.id),
            ('reel_number', '=', self.reel_number),
        ], limit=1)
        if existing:
            raise UserError(
                f"Reel number {self.reel_number} already exists for this episode."
            )

        vals = {
            'name': self.title,
            'description': self.description,
            'tags': self.tags,
            'category_id': self.category_id,
            'default_language': self.default_language,
            'default_audio_language': self.default_audio_language,
            'privacy_status': self.privacy_status,
            'license': self.license,
            'embeddable': self.embeddable,
            'public_stats_viewable': self.public_stats_viewable,
            'self_declared_made_for_kids': self.self_declared_made_for_kids,
            'publish_at': self.publish_at,
            'video_file_path': self.video_file_path,
            'custom_thumbnail': self.custom_thumbnail,
            'custom_thumbnail_filename': self.custom_thumbnail_filename,
            'video_id': self.parent_video_id.id,
            'reel_number': self.reel_number,
            'topic': self.topic,
            'guest': self.guest,
            'hook': self.hook,
        }

        short = self.env['youtube.short'].create(vals)
        short.action_upload_video_resumable()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'youtube.short',
            'res_id': short.id,
            'view_mode': 'form',
            'target': 'current',
        }
