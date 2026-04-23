{
    'name': 'YouTube Integration',
    'version': '0.2',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/google_account_views.xml',
        'views/youtube_channel_views.xml',
        'views/youtube_playlist_views.xml',
        'views/youtube_video_views.xml',
    ],
    'installable': True,
    'application': True,
}