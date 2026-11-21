# -*- coding: utf-8 -*-
import logging
from datetime import datetime, time, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)

PERIODS = [
    ('day', 'Day'), ('week', 'Week'), ('month', 'Month'),
    ('quarter', 'Quarter'), ('year', 'Year'), ('once', 'Once (no period)'),
]
DEFAULT_TZ = 'Asia/Ho_Chi_Minh'


def period_bounds(period, moment):
    """(start, end) of the calendar period holding `moment`, both naive local datetimes.

    end is None for 'once'. A week starts on Monday.
    """
    day = moment.date()
    if period == 'day':
        start = day
        end = day + timedelta(days=1)
    elif period == 'week':
        start = day - timedelta(days=day.weekday())
        end = start + timedelta(days=7)
    elif period == 'month':
        start = day.replace(day=1)
        end = start + relativedelta(months=1)
    elif period == 'quarter':
        start = day.replace(month=3 * ((day.month - 1) // 3) + 1, day=1)
        end = start + relativedelta(months=3)
    elif period == 'year':
        start = day.replace(month=1, day=1)
        end = start + relativedelta(years=1)
    else:
        return None, None
    return datetime.combine(start, time.min), datetime.combine(end, time.min)


class CreditWallet(models.Model):
    """The credit of the whole system, or of one company.

    Two balances: system credit, granted per period under the contract, and
    purchased credit, which never expires. Spending takes system credit first.
    """
    _name = 'isd.credit.wallet'
    _description = 'Credit Wallet'
    _inherit = ['mail.thread']
    _rec_name = 'display_label'

    company_id = fields.Many2one('res.company', string='Company', index=True,
                                 help='Empty: the one wallet of the whole database')
    display_label = fields.Char(compute='_compute_display_label')
    system_balance = fields.Integer(string='System Credit', readonly=True, tracking=True)
    topup_balance = fields.Integer(string='Purchased Credit', readonly=True, tracking=True)
    balance = fields.Integer(string='Total Credit', compute='_compute_balance')

    # The plan agreed in the contract
    allowance = fields.Integer(string='Credit per Period', tracking=True)
    period = fields.Selection(PERIODS, default='month', required=True, tracking=True)
    reset_mode = fields.Selection([
        ('reset', 'Reset to the allowance'),
        ('rollover', 'Add the allowance, up to a cap'),
        ('none', 'No reset'),
    ], default='reset', required=True, tracking=True,
        help='What happens to unused system credit when a new period starts')
    rollover_cap = fields.Integer(string='Cap', tracking=True,
                                  help='With "Add the allowance", system credit never goes above this. 0: no cap.')
    contract_end = fields.Date(string='Contract Ends', tracking=True,
                               help='No new period is granted after this date')
    active_plan = fields.Boolean(string='Plan Running', readonly=True, copy=False)
    next_reset = fields.Datetime(string='Next Period Starts', readonly=True, copy=False)

    is_vendor = fields.Boolean(compute='_compute_is_vendor')
    ledger_count = fields.Integer(compute='_compute_ledger_count')

    # So each warning email goes out once per crossing
    low_notified = fields.Boolean(readonly=True, copy=False)
    empty_notified = fields.Boolean(readonly=True, copy=False)

    _sql_constraints = [
        ('company_unique', 'unique(company_id)', 'A company has one wallet.'),
    ]

    @api.depends('company_id')
    def _compute_display_label(self):
        for wallet in self:
            wallet.display_label = (_('Credit Wallet - %s', wallet.company_id.name) if wallet.company_id
                                    else _('Credit Wallet'))

    def _compute_is_vendor(self):
        is_vendor = self.env.user.has_group('isd_credit_app.group_credit_vendor')
        for wallet in self:
            wallet.is_vendor = is_vendor

    def _compute_ledger_count(self):
        counts = dict(self.env['isd.credit.ledger']._read_group(
            [('wallet_id', 'in', self.ids)], ['wallet_id'], ['__count']))
        for wallet in self:
            wallet.ledger_count = counts.get(wallet, 0)

    @api.depends('system_balance', 'topup_balance')
    def _compute_balance(self):
        for wallet in self:
            wallet.balance = wallet.system_balance + wallet.topup_balance

    @api.constrains('allowance', 'rollover_cap')
    def _check_amounts(self):
        for wallet in self:
            if wallet.allowance < 0 or wallet.rollover_cap < 0:
                raise ValidationError(_('Credit amounts cannot be negative.'))

    # ---------------------------------------------------------- settings
    @api.model
    def _param(self, key, default=False):
        return self.env['ir.config_parameter'].sudo().get_param('isd_credit_app.' + key, default)

    @api.model
    def _per_company(self):
        return self._param('wallet_scope', 'database') == 'company'

    @api.model
    def _threshold(self):
        try:
            return int(self._param('warning_threshold', '0') or 0)
        except ValueError:
            return 0

    @api.model
    def _tz(self):
        return pytz.timezone(self._param('timezone', DEFAULT_TZ) or DEFAULT_TZ)

    @api.model
    def _local_now(self):
        return datetime.now(pytz.utc).astimezone(self._tz()).replace(tzinfo=None)

    @api.model
    def _to_utc(self, local):
        return self._tz().localize(local).astimezone(pytz.utc).replace(tzinfo=None)

    # ------------------------------------------------------------ wallets
    @api.model
    def _get_wallet(self, company=None):
        """The wallet that pays for an action in `company` (or the current one)."""
        Wallet = self.sudo()
        if self._per_company():
            company = company or self.env.company
            wallet = Wallet.search([('company_id', '=', company.id)], limit=1)
            if not wallet:
                wallet = Wallet.create({'company_id': company.id})
        else:
            wallet = Wallet.search([('company_id', '=', False)], limit=1)
            if not wallet:
                wallet = Wallet.create({})
        return wallet

    def _lock(self):
        """Hold this wallet's row until the transaction ends, so two people
        spending at the same moment can never take more than there is."""
        self.env.cr.execute('SELECT id FROM isd_credit_wallet WHERE id IN %s FOR UPDATE', (tuple(self.ids),))
        self.invalidate_recordset(['system_balance', 'topup_balance'])

    # ------------------------------------------------------------ charging
    @api.model
    def _exempt(self):
        """Nobody pays while modules install, for the system's own work, or for ISD."""
        env = self.env
        if env.context.get('isd_credit_skip') or env.context.get('install_mode') or not self.pool.ready:
            return True
        if env.uid == SUPERUSER_ID:
            return True
        return env.user.has_group('isd_credit_app.group_credit_vendor')

    def _spend(self, credits, description, rule=None, records=None, qty=1, user=None):
        """Take `credits` from this wallet, or raise if there is not enough.

        Runs in the caller's transaction: if the action fails afterwards, the
        credit comes back with the rollback.
        """
        self.ensure_one()
        if credits <= 0:
            return self.env['isd.credit.ledger']
        user = user or self.env.user
        self._lock()
        if self.balance < credits:
            raise UserError(_(
                'Not enough credit: this needs %(need)s credits and the system has %(left)s left. '
                'Please ask your manager to top up.', need=credits, left=max(self.balance, 0)))
        self.env['isd.credit.limit']._check_user(user, credits, self.company_id)
        from_system = min(self.system_balance, credits)
        from_topup = credits - from_system
        self.sudo().write({
            'system_balance': self.system_balance - from_system,
            'topup_balance': self.topup_balance - from_topup,
        })
        line = self.env['isd.credit.ledger'].sudo().create({
            'wallet_id': self.id,
            'kind': 'consume',
            'user_id': user.id,
            'rule_id': rule.id if rule else False,
            'description': description,
            'res_model': records._name if records else False,
            'res_id': records.id if records and len(records) == 1 else False,
            'qty': qty,
            'credits': -credits,
            'system_delta': -from_system,
            'topup_delta': -from_topup,
        })
        self._check_thresholds()
        return line

    def _add(self, kind, system=0, topup=0, description='', user=None, topup_id=None):
        """Grant system credit and/or add purchased credit, with a ledger line."""
        self.ensure_one()
        self._lock()
        self.sudo().write({
            'system_balance': self.system_balance + system,
            'topup_balance': self.topup_balance + topup,
        })
        self.env['isd.credit.ledger'].sudo().create({
            'wallet_id': self.id,
            'kind': kind,
            'user_id': (user or self.env.user).id,
            'description': description,
            'credits': system + topup,
            'system_delta': system,
            'topup_delta': topup,
            'topup_id': topup_id,
        })
        self._check_thresholds()

    def _check_thresholds(self):
        """Email the managers and ISD the first time credit runs low, and when it runs out."""
        threshold = self._threshold()
        for wallet in self.sudo():
            if wallet.balance > threshold and (wallet.low_notified or wallet.empty_notified):
                wallet.write({'low_notified': False, 'empty_notified': False})
            elif wallet.balance <= 0 and not wallet.empty_notified:
                wallet.write({'empty_notified': True, 'low_notified': True})
                wallet._notify('isd_credit_app.mail_template_credit_empty')
            elif 0 < wallet.balance <= threshold and not wallet.low_notified:
                wallet.write({'low_notified': True})
                wallet._notify('isd_credit_app.mail_template_credit_low')

    def _recipients(self):
        groups = self.env.ref('isd_credit_app.group_credit_manager') | self.env.ref('isd_credit_app.group_credit_vendor')
        users = groups.sudo().users.filtered(lambda u: u.active and u.email)
        if self.company_id:
            users = users.filtered(lambda u: self.company_id in u.company_ids
                                   or u.has_group('isd_credit_app.group_credit_vendor'))
        return users

    def _notify(self, template_xmlid):
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        emails = ','.join(self._recipients().mapped('email'))
        if template and emails:
            try:
                template.sudo().send_mail(self.id, email_values={'email_to': emails})
            except Exception:
                _logger.exception('isd_credit_app: could not queue the credit warning email')

    def _check_vendor(self):
        if not (self.env.su or self.env.user.has_group('isd_credit_app.group_credit_vendor')):
            raise AccessError(_('Only ISD can change the credit plan or balance.'))

    # ------------------------------------------------------------ periods
    def action_start_plan(self):
        """Grant the first period now and schedule the next one."""
        self._check_vendor()
        for wallet in self:
            if wallet.allowance <= 0:
                raise UserError(_('Set the credit per period first.'))
            grant = wallet.allowance
            if wallet.reset_mode == 'reset' or wallet.period == 'once':
                grant = wallet.allowance - wallet.system_balance
            wallet._add('grant', system=grant, description=_('Plan started: %s credits', wallet.allowance))
            wallet.sudo().write({'active_plan': True, 'next_reset': wallet._compute_next_reset()})

    def action_stop_plan(self):
        self._check_vendor()
        self.sudo().write({'active_plan': False, 'next_reset': False})

    def action_apply_now(self):
        """A plan changed mid-period: apply it now instead of at the next period."""
        self._check_vendor()
        for wallet in self:
            if not wallet.active_plan:
                raise UserError(_('Start the plan first.'))
            wallet._apply_period()

    def _compute_next_reset(self):
        self.ensure_one()
        _start, end = period_bounds(self.period, self._local_now())
        return self._to_utc(end) if end else False

    def _apply_period(self):
        """Start a new period: reset, roll over, or leave as is, per the plan."""
        self.ensure_one()
        ended = self.contract_end and fields.Date.context_today(self) > self.contract_end
        allowance = 0 if ended else self.allowance
        if self.reset_mode == 'reset':
            delta = allowance - self.system_balance
            label = _('New period: system credit reset to %s', allowance)
        elif self.reset_mode == 'rollover':
            target = self.system_balance + allowance
            if self.rollover_cap:
                target = min(target, self.rollover_cap)
            delta = max(target - self.system_balance, 0)
            label = _('New period: %s credits added', delta)
        else:
            delta, label = 0, _('New period: no reset')
        if delta:
            self._add('reset', system=delta, description=label)
        self.sudo().next_reset = self._compute_next_reset()

    @api.model
    def _cron_periods(self):
        now = fields.Datetime.now()
        for wallet in self.sudo().search([('active_plan', '=', True), ('next_reset', '!=', False),
                                          ('next_reset', '<=', now)]):
            try:
                with self.env.cr.savepoint():
                    wallet._apply_period()
            except Exception:
                _logger.exception('isd_credit_app: period reset failed for wallet %s', wallet.id)

    # ------------------------------------------------------ public helpers
    @api.model
    def consume(self, code, qty=1, record=None):
        """Charge a named action that a module declares, e.g. consume('ai_chatbot.ai_reply').

        Does nothing when no active rule prices the code.
        """
        if self._exempt():
            return False
        Rule = self.env['isd.credit.rule']
        for rule_id, credits, _domain, _fields in Rule._index().get('named', {}).get(code, ()):
            rule = Rule.sudo().browse(rule_id)
            company = record.company_id if record is not None and 'company_id' in record._fields and record.company_id else None
            self._get_wallet(company)._spend(credits * qty, rule.name, rule=rule, records=record, qty=qty)
        return True

    @api.model
    def get_notice(self):
        """What the low-credit box should say to the current user, or False."""
        if self.env.user.share:
            return False
        today = fields.Date.to_string(self._local_now().date())
        if self.env.user.sudo().isd_credit_hidden_on == today:
            return False
        wallet = self._get_wallet()
        threshold = self._threshold()
        if wallet.balance > threshold:
            return False
        return {
            'level': 'empty' if wallet.balance <= 0 else 'low',
            'balance': max(wallet.balance, 0),
            'threshold': threshold,
            'can_request': self.env.user.has_group('isd_credit_app.group_credit_manager'),
        }

    @api.model
    def get_status(self):
        """For the systray: the balance, and the user's own usage and limits."""
        if self.env.user.share:
            return False
        wallet = self._get_wallet()
        status = self.env['isd.credit.limit'].get_my_status()
        status.update({
            'balance': wallet.balance,
            'system_balance': wallet.system_balance,
            'topup_balance': wallet.topup_balance,
            'next_reset': fields.Datetime.to_string(wallet.next_reset) if wallet.next_reset else False,
            'threshold': self._threshold(),
            'is_manager': self.env.user.has_group('isd_credit_app.group_credit_manager'),
        })
        return status

    @api.model
    def hide_notice_today(self):
        self.env.user.sudo().isd_credit_hidden_on = fields.Date.to_string(self._local_now().date())
        return True

    def action_adjust(self):
        self.ensure_one()
        self._check_vendor()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'isd.credit.adjust.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_wallet_id': self.id},
        }

    @api.model
    def action_open_overview(self):
        """The wallet that pays here, or the list of them with one wallet per company."""
        if self._per_company() and len(self.env.companies) > 1:
            for company in self.env.companies:
                self._get_wallet(company)
            return {
                'type': 'ir.actions.act_window',
                'name': _('Credit'),
                'res_model': self._name,
                'view_mode': 'list,form',
                'domain': [('company_id', 'in', self.env.companies.ids)],
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Credit'),
            'res_model': self._name,
            'res_id': self._get_wallet().id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def action_view_ledger(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('isd_credit_app.action_ledger')
        action['domain'] = [('wallet_id', '=', self.id)]
        return action
