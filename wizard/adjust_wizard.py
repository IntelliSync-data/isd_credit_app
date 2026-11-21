# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class CreditAdjustWizard(models.TransientModel):
    """ISD corrects a balance by hand, with the reason on the ledger."""
    _name = 'isd.credit.adjust.wizard'
    _description = 'Adjust Credit'

    wallet_id = fields.Many2one('isd.credit.wallet', required=True, ondelete='cascade')
    part = fields.Selection([('system', 'System Credit'), ('topup', 'Purchased Credit')],
                            default='system', required=True)
    credits = fields.Integer(required=True, help='Positive adds credit, negative takes it away')
    reason = fields.Char(required=True)

    def action_apply(self):
        self.ensure_one()
        wallet = self.wallet_id
        wallet._check_vendor()
        if not self.credits:
            raise UserError(_('Enter the number of credits to add or take away.'))
        current = wallet.system_balance if self.part == 'system' else wallet.topup_balance
        if current + self.credits < 0:
            raise UserError(_('That would take this part below zero (it has %s).', current))
        values = {'system': self.credits} if self.part == 'system' else {'topup': self.credits}
        wallet._add('adjust', description=_('Adjustment: %s', self.reason), **values)
        return {'type': 'ir.actions.act_window_close'}
