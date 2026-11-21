# -*- coding: utf-8 -*-
from collections import defaultdict

from lxml import etree

from odoo import _, api, fields, models, tools
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval

OPERATIONS = [
    ('create', 'Create'),
    ('write', 'Edit'),
    ('unlink', 'Delete'),
    ('button', 'Button'),
    ('server_action', 'Server Action'),
    ('report', 'Print Report'),
    ('named', 'Named Action'),
]
THIS_MODULE = 'isd_credit_app'
ISD_AUTHOR = 'IntelliSync'


class CreditRule(models.Model):
    """One line of the price list: an action, and what it costs."""
    _name = 'isd.credit.rule'
    _description = 'Credit Price'
    _order = 'module_id, sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    isd_only = fields.Boolean(string='ISD Modules Only', default=True,
                              help='Only offer the modules made by IntelliSyncData')
    module_id = fields.Many2one('ir.module.module', string='Module', required=True, ondelete='cascade',
                                domain="[('id', 'in', allowed_module_ids)]")
    operation = fields.Selection(OPERATIONS, required=True, default='create')
    model_id = fields.Many2one('ir.model', string='Model', ondelete='cascade',
                               domain="[('id', 'in', allowed_model_ids)]")
    model = fields.Char(related='model_id.model', string='Model Name', store=True, index=True)
    write_field_ids = fields.Many2many(
        'ir.model.fields', string='Only When Editing',
        domain="[('model_id', '=', model_id), ('store', '=', True)]",
        help='Edits count only when one of these fields changes. Empty: any edit counts.')
    button_name = fields.Char(string='Button', help='The method the button calls, e.g. action_confirm')
    available_buttons = fields.Char(compute='_compute_available_buttons')
    server_action_id = fields.Many2one('ir.actions.server', string='Server Action', ondelete='cascade',
                                       domain="[('id', 'in', allowed_server_action_ids)]")
    report_id = fields.Many2one('ir.actions.report', string='Report', ondelete='cascade',
                                domain="[('id', 'in', allowed_report_ids)]")
    action_code = fields.Char(string='Action Code', help="The code a module charges with, e.g. ai_chatbot.ai_reply")
    credits = fields.Integer(required=True, default=1, help='0 tracks the action without charging for it')
    domain = fields.Char(string='Only When', help='Charge only records that match this filter')
    description = fields.Text(translate=True)

    allowed_module_ids = fields.Many2many('ir.module.module', compute='_compute_allowed')
    allowed_model_ids = fields.Many2many('ir.model', compute='_compute_allowed')
    allowed_server_action_ids = fields.Many2many('ir.actions.server', compute='_compute_allowed')
    allowed_report_ids = fields.Many2many('ir.actions.report', compute='_compute_allowed')

    # ------------------------------------------------------ module filters
    @api.depends('isd_only', 'module_id', 'model_id')
    def _compute_allowed(self):
        Module = self.env['ir.module.module'].sudo()
        for rule in self:
            # Installed modules: a module installed later shows up by itself.
            # This one never charges for itself.
            domain = [('state', '=', 'installed'), ('name', '!=', THIS_MODULE)]
            if rule.isd_only:
                domain.append(('author', 'ilike', ISD_AUTHOR))
            rule.allowed_module_ids = Module.search(domain)
            models_, actions, reports = self._module_records(rule.module_id.name)
            rule.allowed_model_ids = models_
            rule.allowed_server_action_ids = actions | (
                self.env['ir.actions.server'].sudo().search([('model_id', '=', rule.model_id.id)])
                if rule.model_id else self.env['ir.actions.server'])
            rule.allowed_report_ids = reports

    def _module_records(self, module_name):
        """The models, server actions and reports a module defines or extends."""
        empty = (self.env['ir.model'], self.env['ir.actions.server'], self.env['ir.actions.report'])
        if not module_name:
            return empty
        data = self.env['ir.model.data'].sudo().search([
            ('module', '=', module_name),
            ('model', 'in', ('ir.model', 'ir.actions.server', 'ir.actions.report'))])
        ids = defaultdict(list)
        for row in data:
            ids[row.model].append(row.res_id)
        return (self.env['ir.model'].browse(ids['ir.model']),
                self.env['ir.actions.server'].browse(ids['ir.actions.server']),
                self.env['ir.actions.report'].browse(ids['ir.actions.report']))

    @api.depends('model_id')
    def _compute_available_buttons(self):
        """The object buttons on the model's views, as a hint for the Button field."""
        for rule in self:
            names = set()
            if rule.model_id:
                for view in self.env['ir.ui.view'].sudo().search([('model', '=', rule.model_id.model)]):
                    try:
                        arch = etree.fromstring(view.arch_db or '<x/>')
                    except etree.XMLSyntaxError:
                        continue
                    for button in arch.iter('button'):
                        if button.get('type') == 'object' and button.get('name'):
                            names.add(button.get('name'))
            rule.available_buttons = ', '.join(sorted(names))

    @api.onchange('module_id')
    def _onchange_module(self):
        if self.model_id and self.model_id not in self.allowed_model_ids:
            self.model_id = False

    @api.constrains('operation', 'model_id', 'button_name', 'server_action_id', 'report_id', 'action_code',
                    'credits', 'domain')
    def _check_target(self):
        for rule in self:
            if rule.credits < 0:
                raise ValidationError(_('A price cannot be negative.'))
            op = rule.operation
            if op in ('create', 'write', 'unlink', 'button') and not rule.model_id:
                raise ValidationError(_('"%s": choose the model.', rule.name))
            if op == 'button' and not rule.button_name:
                raise ValidationError(_('"%s": enter the button.', rule.name))
            if op == 'server_action' and not rule.server_action_id:
                raise ValidationError(_('"%s": choose the server action.', rule.name))
            if op == 'report' and not rule.report_id:
                raise ValidationError(_('"%s": choose the report.', rule.name))
            if op == 'named' and not rule.action_code:
                raise ValidationError(_('"%s": enter the action code.', rule.name))
            if rule.domain:
                try:
                    safe_eval(rule.domain)
                except Exception:
                    raise ValidationError(_('"%s": the filter is not valid.', rule.name))

    # ---------------------------------------------------------- price index
    @api.model
    @tools.ormcache()
    def _index(self):
        """Every active price, keyed for a quick lookup on each action:

        {'crud': {model: {operation: (...)}}, 'button': {(model, method): (...)},
         'server_action': {action_id: (...)}, 'report': {report_id: (...)}, 'named': {code: (...)}}
        where each entry is (rule_id, credits, domain, field_names).
        """
        index = {'crud': defaultdict(lambda: defaultdict(list)), 'button': defaultdict(list),
                 'server_action': defaultdict(list), 'report': defaultdict(list), 'named': defaultdict(list)}
        for rule in self.sudo().search([]):
            entry = (rule.id, rule.credits, rule.domain or False, tuple(rule.write_field_ids.mapped('name')))
            if rule.operation in ('create', 'write', 'unlink'):
                index['crud'][rule.model][rule.operation].append(entry)
            elif rule.operation == 'button':
                index['button'][(rule.model, rule.button_name)].append(entry)
            elif rule.operation == 'server_action':
                index['server_action'][rule.server_action_id.id].append(entry)
            elif rule.operation == 'report':
                index['report'][rule.report_id.id].append(entry)
            else:
                index['named'][rule.action_code].append(entry)
        # Plain dicts and tuples: the cache hands the same object to everyone
        return {
            'crud': {m: {op: tuple(v) for op, v in ops.items()} for m, ops in index['crud'].items()},
            'button': {k: tuple(v) for k, v in index['button'].items()},
            'server_action': {k: tuple(v) for k, v in index['server_action'].items()},
            'report': {k: tuple(v) for k, v in index['report'].items()},
            'named': {k: tuple(v) for k, v in index['named'].items()},
        }

    @api.model_create_multi
    def create(self, vals_list):
        rules = super().create(vals_list)
        self.env.registry.clear_cache()
        return rules

    def write(self, vals):
        res = super().write(vals)
        self.env.registry.clear_cache()
        return res

    def unlink(self):
        res = super().unlink()
        self.env.registry.clear_cache()
        return res

    # -------------------------------------------------------------- charge
    @api.model
    def _charge(self, entries, records, qty=None, label=None):
        """Charge each priced entry for the records it applies to, wallet by wallet."""
        Wallet = self.env['isd.credit.wallet']
        for rule_id, credits, domain, _fields in entries:
            if not credits:
                continue
            rule = self.sudo().browse(rule_id)
            matched = records
            if domain and records:
                matched = records.sudo().filtered_domain(safe_eval(domain))
            if records is not None and not matched:
                continue
            for company, group in self._by_company(matched):
                count = qty if qty is not None else max(len(group), 1)
                text = label or rule.name
                if count > 1:
                    text = '%s × %s' % (text, count)
                Wallet._get_wallet(company)._spend(credits * count, text, rule=rule, records=group, qty=count)

    @api.model
    def _by_company(self, records):
        """Split records by the wallet that pays: one group when there is a single wallet."""
        Wallet = self.env['isd.credit.wallet']
        if records is None or not Wallet._per_company() or 'company_id' not in records._fields:
            return [(None, records)]
        groups = defaultdict(lambda: records.browse())
        for record in records:
            groups[record.company_id or self.env.company] |= record
        return list(groups.items())

    @api.model
    def _charge_crud(self, records, operation, vals=None):
        if not records or self.env['isd.credit.wallet']._exempt():
            return
        entries = self._index()['crud'].get(records._name, {}).get(operation)
        if not entries:
            return
        if operation == 'write' and vals:
            changed = set(vals)
            entries = tuple(e for e in entries if not e[3] or changed.intersection(e[3]))
        self._charge(entries, records)

    @api.model
    def _charge_button(self, model, method, ids):
        if self.env['isd.credit.wallet']._exempt():
            return
        entries = self._index()['button'].get((model, method))
        if entries:
            self._charge(entries, self.env[model].browse(ids).exists())

    @api.model
    def _charge_server_action(self, action, records):
        if self.env['isd.credit.wallet']._exempt():
            return
        entries = self._index()['server_action'].get(action.id)
        if entries:
            self._charge(entries, records if records else None, qty=None if records else 1)

    @api.model
    def _charge_report(self, report, res_ids):
        if self.env['isd.credit.wallet']._exempt():
            return
        entries = self._index()['report'].get(report.id)
        if entries:
            records = self.env[report.model].browse(res_ids or []).exists() if report.model else None
            self._charge(entries, records if records else None, qty=None if records else 1)

    @api.model
    def get_form_hint(self, model):
        """What saving a record of `model` costs: {'create': n, 'write': n}, or False."""
        if model not in self.env or self.env['isd.credit.wallet']._exempt():
            return False
        ops = self._index()['crud'].get(model, {})
        costs = {op: sum(e[1] for e in ops.get(op, ())) for op in ('create', 'write')}
        return costs if any(costs.values()) else False
