# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.dataset import DataSet


class CreditDataSet(DataSet):
    """Every button click of the web client goes through here: charge the priced ones."""

    @http.route()
    def call_button(self, model, method, args, kwargs, path=None):
        ids = args[0] if args and isinstance(args[0], list) else []
        if model in request.env and ids:
            request.env['isd.credit.rule']._charge_button(model, method, ids)
        return super().call_button(model, method, args, kwargs, path=path)
