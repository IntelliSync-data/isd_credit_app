# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .wallet import period_bounds

LIMIT_PERIODS = [('day', 'Day'), ('week', 'Week'), ('month', 'Month')]


class CreditLimit(models.Model):
    """How much one employee, or each member of a group, may spend per period.

    No limit: everyone draws on the shared wallet. A limit only splits the
    wallet, it never adds credit.
    """
    _name = 'isd.credit.limit'
    _description = 'Credit Limit'
    _order = 'user_id, group_id, id'

    name = fields.Char(compute='_compute_name')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company',
                                 help='With one wallet per company: the company the limit applies in. Empty: all.')
    user_id = fields.Many2one('res.users', string='Employee', domain=[('share', '=', False)], ondelete='cascade')
    group_id = fields.Many2one('res.groups', string='Group', ondelete='cascade',
                               help='Each member of the group gets this limit, unless they have their own')
    mode = fields.Selection([('limit', 'Up to a number of credits'), ('forbid', 'No charged actions')],
                            default='limit', required=True)
    period = fields.Selection(LIMIT_PERIODS, default='day', required=True)
    max_credits = fields.Integer(string='Credits per Period')
    used = fields.Integer(string='Used This Period', compute='_compute_usage')
    remaining = fields.Integer(compute='_compute_usage')

    @api.depends('user_id', 'group_id', 'mode', 'max_credits', 'period')
    def _compute_name(self):
        for limit in self:
            who = limit.user_id.name or limit.group_id.full_name or '?'
            if limit.mode == 'forbid':
                limit.name = _('%s: no charged actions', who)
            else:
                limit.name = _('%(who)s: %(max)s credits per %(period)s', who=who, max=limit.max_credits,
                               period=limit._period_label())

    def _period_label(self):
        return dict(self._fields['period']._description_selection(self.env)).get(self.period, '').lower()

    def _compute_usage(self):
        for limit in self:
            used = limit._used(limit.user_id) if limit.user_id else 0
            limit.used = used
            limit.remaining = max(limit.max_credits - used, 0) if limit.mode == 'limit' else 0

    @api.constrains('user_id', 'group_id', 'max_credits', 'mode')
    def _check_target(self):
        for limit in self:
            if bool(limit.user_id) == bool(limit.group_id):
                raise ValidationError(_('A limit is for one employee or one group.'))
            if limit.mode == 'limit' and limit.max_credits < 0:
                raise ValidationError(_('The limit cannot be negative.'))

    def _used(self, user):
        """Credit `user` spent in this limit's current period (in its company, if any)."""
        self.ensure_one()
        Wallet = self.env['isd.credit.wallet']
        start, _end = period_bounds(self.period, Wallet._local_now())
        domain = [('kind', '=', 'consume'), ('user_id', '=', user.id), ('date', '>=', Wallet._to_utc(start))]
        if self.company_id:
            domain.append(('company_id', '=', self.company_id.id))
        groups = self.env['isd.credit.ledger'].sudo()._read_group(domain, aggregates=['used:sum'])
        return groups[0][0] or 0 if groups else 0

    @api.model
    def _applicable(self, user, company=None):
        """The user's own limits; without any, the limits of their groups."""
        Limit = self.sudo()
        company_domain = ['|', ('company_id', '=', False), ('company_id', '=', company.id)] if company else []
        own = Limit.search([('user_id', '=', user.id)] + company_domain)
        if own:
            return own
        return Limit.search([('group_id', 'in', user.groups_id.ids)] + company_domain)

    @api.model
    def _check_user(self, user, credits, company=None):
        """Raise when spending `credits` more would take `user` past a limit."""
        for limit in self._applicable(user, company):
            if limit.mode == 'forbid':
                raise UserError(_('You are not allowed to use charged actions. Please contact your manager.'))
            used = limit._used(user)
            if used + credits > limit.max_credits:
                period = limit._period_label()
                raise UserError(_(
                    'You have used %(used)s/%(max)s credits this %(period)s; this needs %(need)s more. '
                    'Please contact your manager.', used=used, max=limit.max_credits, period=period, need=credits))

    @api.model
    def get_my_status(self):
        """For the current user: their usage and their tightest limit."""
        user = self.env.user
        Wallet = self.env['isd.credit.wallet']
        start, _end = period_bounds('month', Wallet._local_now())
        groups = self.env['isd.credit.ledger'].sudo()._read_group(
            [('kind', '=', 'consume'), ('user_id', '=', user.id), ('date', '>=', Wallet._to_utc(start))],
            aggregates=['used:sum'])
        status = {'used_month': groups[0][0] or 0 if groups else 0, 'limits': []}
        for limit in self._applicable(user, self.env.company if Wallet._per_company() else None):
            used = limit._used(user)
            status['limits'].append({
                'name': limit.name, 'mode': limit.mode, 'period': limit.period,
                'max': limit.max_credits, 'used': used, 'remaining': max(limit.max_credits - used, 0),
            })
        return status
