{
    'name': 'YouTube Integration',
    'version': '0.3',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'views/google_account_views.xml',
        'views/youtube_channel_views.xml',
        'views/youtube_playlist_views.xml',
        'views/youtube_video_views.xml',
        'views/youtube_analytics_views.xml',
        'wizards/youtube_video_upload_wizard_views.xml',
        'wizards/youtube_playlist_upload_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
}
