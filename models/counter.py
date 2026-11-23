# -*- coding: utf-8 -*-
from odoo import fields, models


class CreditCounter(models.Model):
    """How many actions of a "credits per N" price wait for the next charge."""
    _name = 'isd.credit.counter'
    _description = 'Credit Counter'

    wallet_id = fields.Many2one('isd.credit.wallet', required=True, ondelete='cascade', index=True)
    rule_id = fields.Many2one('isd.credit.rule', required=True, ondelete='cascade', index=True)
    count = fields.Integer()

    _sql_constraints = [
        ('wallet_rule_unique', 'unique(wallet_id, rule_id)', 'One counter per wallet and price.'),
    ]
