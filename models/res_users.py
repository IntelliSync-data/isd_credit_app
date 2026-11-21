# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # The local date the user ticked "Don't show again today" on the credit notice
    isd_credit_hidden_on = fields.Char(copy=False)
