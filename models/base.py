# -*- coding: utf-8 -*-
from odoo import api, models


class Base(models.AbstractModel):
    """Charge the priced creates, edits and deletes of any model.

    The price list sits in a cache, so a model with no price costs a dict
    lookup and nothing else.
    """
    _inherit = 'base'

    def _isd_credit_priced(self, operation):
        if self._name.startswith('isd.credit.') or self._transient and operation != 'create':
            return False
        registry = self.env.registry
        if 'isd.credit.rule' not in registry or not registry.ready:
            return False
        return bool(self.env['isd.credit.rule']._index()['crud'].get(self._name, {}).get(operation))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self._isd_credit_priced('create'):
            # One charge for the whole batch: not enough for all of it blocks all of it
            self.env['isd.credit.rule']._charge_crud(records, 'create')
        return records

    def write(self, vals):
        res = super().write(vals)
        if self and self._isd_credit_priced('write'):
            self.env['isd.credit.rule']._charge_crud(self, 'write', vals)
        return res

    def unlink(self):
        if self and self._isd_credit_priced('unlink'):
            # Before the records go, so the filter can still read them
            self.env['isd.credit.rule']._charge_crud(self.exists(), 'unlink')
        return super().unlink()
