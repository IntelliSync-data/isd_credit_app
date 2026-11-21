# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .package import CURRENCY_DOMAIN

STATES = [
    ('draft', 'Draft'),
    ('submitted', 'Submitted'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('cancelled', 'Cancelled'),
]
# What only ISD may set: the customer asks, ISD decides
VENDOR_FIELDS = {'state', 'received_amount', 'approved_by_id', 'approved_on', 'reject_reason'}
# What freezes once the request is sent
REQUEST_FIELDS = {'package_id', 'credits', 'currency_id', 'amount', 'payment_method', 'company_id'}


class CreditTopup(models.Model):
    """A request for more credit, paid in cash, that ISD approves."""
    _name = 'isd.credit.topup'
    _description = 'Credit Top-up'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Reference', readonly=True, copy=False, default='/')
    state = fields.Selection(STATES, default='draft', required=True, tracking=True, readonly=True, copy=False)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self._default_company(),
                                 help='The company whose wallet receives the credit. Empty: the shared wallet.')
    requested_by_id = fields.Many2one('res.users', string='Requested By', default=lambda self: self.env.user,
                                      readonly=True)
    package_id = fields.Many2one('isd.credit.package', string='Package',
                                 domain="[('currency_id', '=', currency_id)]")
    credits = fields.Integer(required=True, tracking=True)
    currency_id = fields.Many2one('res.currency', required=True, domain=CURRENCY_DOMAIN, tracking=True,
                                  default=lambda self: self.env.ref('base.VND', raise_if_not_found=False))
    amount = fields.Monetary(string='Amount to Pay', currency_field='currency_id',
                             compute='_compute_amount', store=True, readonly=False, tracking=True)
    payment_method = fields.Selection([('cash', 'Cash')], default='cash', required=True)
    note = fields.Text()
    receipt = fields.Binary(attachment=True, copy=False)
    receipt_name = fields.Char()
    received_amount = fields.Monetary(currency_field='currency_id', tracking=True, copy=False)
    reject_reason = fields.Text(tracking=True, copy=False)
    approved_by_id = fields.Many2one('res.users', string='Decided By', readonly=True, copy=False)
    approved_on = fields.Datetime(string='Decided On', readonly=True, copy=False)
    is_vendor = fields.Boolean(compute='_compute_is_vendor')

    @api.model
    def _default_company(self):
        return self.env.company if self.env['isd.credit.wallet']._per_company() else False

    def _compute_is_vendor(self):
        is_vendor = self.env.user.has_group('isd_credit_app.group_credit_vendor')
        for topup in self:
            topup.is_vendor = is_vendor

    @api.onchange('package_id')
    def _onchange_package(self):
        if self.package_id:
            self.credits = self.package_id.credits
            self.currency_id = self.package_id.currency_id

    @api.depends('package_id', 'credits', 'currency_id')
    def _compute_amount(self):
        Wallet = self.env['isd.credit.wallet']
        for topup in self:
            package = topup.package_id
            if package and package.credits == topup.credits and package.currency_id == topup.currency_id:
                topup.amount = package.price
            else:
                try:
                    unit = float(Wallet._param('price_per_credit_%s' % (topup.currency_id.name or '').lower(), 0) or 0)
                except ValueError:
                    unit = 0
                topup.amount = topup.currency_id.round(topup.credits * unit) if topup.currency_id else 0

    @api.constrains('credits')
    def _check_credits(self):
        for topup in self:
            if topup.credits <= 0:
                raise ValidationError(_('Enter how many credits to buy.'))

    # ----------------------------------------------------------- guards
    def _is_vendor(self):
        return self.env.su or self.env.user.has_group('isd_credit_app.group_credit_vendor')

    def _check_vendor(self):
        if not self._is_vendor():
            raise AccessError(_('Only ISD can approve or reject a top-up.'))

    @api.model_create_multi
    def create(self, vals_list):
        if not self._is_vendor():
            for vals in vals_list:
                if VENDOR_FIELDS & set(vals):
                    raise AccessError(_('Only ISD can approve or reject a top-up.'))
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('isd.credit.topup') or '/'
        return super().create(vals_list)

    def write(self, vals):
        # The flow methods write as superuser; a client can never get here with su
        if not self.env.su:
            if VENDOR_FIELDS & set(vals):
                self._check_vendor()
            if REQUEST_FIELDS & set(vals) and any(t.state not in ('draft', 'submitted') for t in self):
                raise UserError(_('A top-up that was approved, rejected or cancelled cannot change.'))
            if REQUEST_FIELDS & set(vals) and not self._is_vendor() and any(t.state != 'draft' for t in self):
                raise UserError(_('Set the request back to draft to change it.'))
        return super().write(vals)

    def unlink(self):
        if any(t.state == 'approved' for t in self):
            raise UserError(_('An approved top-up cannot be deleted.'))
        return super().unlink()

    def _flow(self):
        return self.sudo()

    # ------------------------------------------------------------- flow
    def action_submit(self):
        vendors = self.env.ref('isd_credit_app.group_credit_vendor').sudo().users.filtered(
            lambda u: u.active and not u.share and u.id != self.env.ref('base.user_root').id)
        for topup in self:
            if topup.state != 'draft':
                raise UserError(_('Only a draft request can be sent.'))
            topup._flow().write({'state': 'submitted'})
            for vendor in vendors:
                topup.sudo().activity_schedule(
                    'mail.mail_activity_data_todo', user_id=vendor.id,
                    summary=_('Approve top-up %s', topup.name),
                    note=_('%(credits)s credits, %(amount)s %(currency)s in cash', credits=topup.credits,
                           amount=topup.amount, currency=topup.currency_id.name))
            topup.sudo().message_post(
                body=_('Top-up requested: %(credits)s credits for %(amount)s %(currency)s.',
                       credits=topup.credits, amount=topup.amount, currency=topup.currency_id.name),
                partner_ids=vendors.partner_id.ids, subtype_xmlid='mail.mt_comment')
        return True

    def action_approve(self):
        self._check_vendor()
        Wallet = self.env['isd.credit.wallet']
        for topup in self:
            if topup.state != 'submitted':
                raise UserError(_('Only a submitted request can be approved.'))
            received = topup.received_amount or topup.amount
            Wallet._get_wallet(topup.company_id or None)._add(
                'topup', topup=topup.credits, description=_('Top-up %s', topup.name), topup_id=topup.id)
            topup._flow().write({'state': 'approved', 'received_amount': received,
                                 'approved_by_id': self.env.user.id, 'approved_on': fields.Datetime.now()})
            topup._done_activities()
            topup._tell_requester(_('Your top-up %(name)s is approved: %(credits)s credits were added.',
                                    name=topup.name, credits=topup.credits))
        return True

    def action_reject(self):
        self._check_vendor()
        for topup in self:
            if topup.state != 'submitted':
                raise UserError(_('Only a submitted request can be rejected.'))
            if not topup.reject_reason:
                raise UserError(_('Write why the request is rejected first.'))
            topup._flow().write({'state': 'rejected', 'approved_by_id': self.env.user.id,
                                 'approved_on': fields.Datetime.now()})
            topup._done_activities()
            topup._tell_requester(_('Your top-up %(name)s was rejected: %(reason)s',
                                    name=topup.name, reason=topup.reject_reason))
        return True

    def action_cancel(self):
        for topup in self:
            if topup.state not in ('draft', 'submitted'):
                raise UserError(_('Only a request that is not decided yet can be cancelled.'))
            topup._flow().write({'state': 'cancelled'})
            topup._done_activities()
        return True

    def action_draft(self):
        for topup in self:
            if topup.state not in ('submitted', 'cancelled'):
                raise UserError(_('Only a sent or cancelled request can go back to draft.'))
            topup._flow().write({'state': 'draft'})
            topup._done_activities()
        return True

    def _done_activities(self):
        self.sudo().activity_unlink(['mail.mail_activity_data_todo'])

    def _tell_requester(self, body):
        partner = self.requested_by_id.partner_id
        self.sudo().message_post(body=body, partner_ids=partner.ids, subtype_xmlid='mail.mt_comment')
