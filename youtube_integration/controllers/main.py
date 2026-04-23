from odoo import http
from odoo.http import request


class YouTubeController(http.Controller):

    @http.route('/youtube/callback', type='http', auth='user')
    def youtube_callback(self, **kwargs):
        code = kwargs.get('code')
        state = kwargs.get('state')

        if not code:
            return "Missing authorization code"

        if not state:
            return "Missing state"

        account = request.env['google.account'].sudo().browse(int(state))

        if not account.exists():
            return "Invalid account"

        try:
            account.exchange_code(code)
        except Exception as e:
            return f"Error: {str(e)}"

        # return "YouTube account connected successfully!"
        return request.redirect('#')
