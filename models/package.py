# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

CURRENCY_DOMAIN = [('name', 'in', ('VND', 'USD'))]


class CreditPackage(models.Model):
    """A top-up offer, e.g. 1,000 credits for 500,000 VND."""
    _name = 'isd.credit.package'
    _description = 'Credit Package'
    _order = 'sequence, currency_id, credits, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    credits = fields.Integer(required=True)
    currency_id = fields.Many2one('res.currency', required=True, domain=CURRENCY_DOMAIN,
                                  default=lambda self: self.env.ref('base.VND', raise_if_not_found=False))
    price = fields.Monetary(required=True, currency_field='currency_id')
    description = fields.Text(translate=True)

    @api.constrains('credits', 'price')
    def _check_amounts(self):
        for package in self:
            if package.credits <= 0 or package.price < 0:
                raise ValidationError(_('A package needs a positive number of credits and a price.'))
