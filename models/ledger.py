# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

KINDS = [
    ('consume', 'Used'),
    ('grant', 'Plan Started'),
    ('reset', 'New Period'),
    ('topup', 'Top-up'),
    ('adjust', 'Adjustment'),
]


class CreditLedger(models.Model):
    """Every credit movement, one line each. Lines are never changed or removed:
    a correction is a new Adjustment line."""
    _name = 'isd.credit.ledger'
    _description = 'Credit Ledger'
    _order = 'date desc, id desc'
    _rec_name = 'description'

    wallet_id = fields.Many2one('isd.credit.wallet', required=True, index=True, ondelete='restrict', readonly=True)
    company_id = fields.Many2one(related='wallet_id.company_id', store=True, index=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True, index=True, readonly=True)
    user_id = fields.Many2one('res.users', string='User', index=True, readonly=True, ondelete='restrict')
    rule_id = fields.Many2one('isd.credit.rule', string='Price', index=True, readonly=True, ondelete='set null')
    module_id = fields.Many2one(related='rule_id.module_id', store=True, string='Module')
    operation = fields.Selection(related='rule_id.operation', store=True)
    kind = fields.Selection(KINDS, required=True, index=True, readonly=True)
    description = fields.Char(readonly=True)
    res_model = fields.Char(string='Model', readonly=True)
    res_id = fields.Many2oneReference(string='Record', model_field='res_model', readonly=True)
    qty = fields.Integer(string='Quantity', default=1, readonly=True)
    credits = fields.Integer(readonly=True, help='Positive: credit added. Negative: credit used.')
    used = fields.Integer(compute='_compute_used', store=True, help='Credit used, as a positive number')
    system_delta = fields.Integer(string='System Credit', readonly=True)
    topup_delta = fields.Integer(string='Purchased Credit', readonly=True)
    balance_after = fields.Integer(string='Balance After', readonly=True)
    topup_id = fields.Many2one('isd.credit.topup', string='Top-up', readonly=True, ondelete='restrict')

    @api.depends('kind', 'credits')
    def _compute_used(self):
        for line in self:
            line.used = -line.credits if line.kind == 'consume' else 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'balance_after' not in vals and vals.get('wallet_id'):
                vals['balance_after'] = self.env['isd.credit.wallet'].sudo().browse(vals['wallet_id']).balance
        return super().create(vals_list)

    def write(self, vals):
        # Only stored computed fields may be filled in by the ORM itself
        if set(vals) - {'used', 'company_id', 'module_id', 'operation'}:
            raise UserError(_('Credit ledger lines cannot be changed. Add an adjustment instead.'))
        return super().write(vals)

    def unlink(self):
        raise UserError(_('Credit ledger lines cannot be deleted. Add an adjustment instead.'))

    def action_open_record(self):
        self.ensure_one()
        if not self.res_model or not self.res_id or self.res_model not in self.env:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }
