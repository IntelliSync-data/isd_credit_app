# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.addons.base.models.res_partner import _tz_get


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    isd_credit_wallet_scope = fields.Selection(
        [('database', 'One wallet for the whole database'), ('company', 'One wallet per company')],
        string='Credit Wallets', default='database', config_parameter='isd_credit_app.wallet_scope')
    isd_credit_warning_threshold = fields.Integer(
        string='Warn Below', config_parameter='isd_credit_app.warning_threshold',
        help='Everyone sees a notice when the credit is at or below this')
    isd_credit_timezone = fields.Selection(
        _tz_get, string='Credit Time Zone', default='Asia/Ho_Chi_Minh', config_parameter='isd_credit_app.timezone',
        help="Periods, limits and \"Don't show again today\" follow the customer's day in this zone")
    isd_credit_price_vnd = fields.Float(
        string='Price per Credit (VND)', config_parameter='isd_credit_app.price_per_credit_vnd',
        help='For top-ups of any number of credits, outside the packages')
    isd_credit_price_usd = fields.Float(
        string='Price per Credit (USD)', config_parameter='isd_credit_app.price_per_credit_usd')

    @api.model
    def get_values(self):
        res = super().get_values()
        res['isd_credit_timezone'] = res.get('isd_credit_timezone') or 'Asia/Ho_Chi_Minh'
        return res
