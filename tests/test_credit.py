# -*- coding: utf-8 -*-
from datetime import datetime
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.isd_credit_app.models.wallet import period_bounds


@tagged('post_install', '-at_install')
class TestCredit(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, lang='en_US', tracking_disable=True, mail_notrack=True))
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        cls.ICP.set_param('isd_credit_app.wallet_scope', 'database')
        cls.ICP.set_param('isd_credit_app.warning_threshold', '0')
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.employee = Users.create({
            'name': 'Credit Employee', 'login': 'credit_employee', 'lang': 'en_US', 'email': 'emp@example.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id, cls.env.ref('base.group_partner_manager').id])],
        })
        cls.colleague = Users.create({
            'name': 'Credit Colleague', 'login': 'credit_colleague', 'lang': 'en_US', 'email': 'col@example.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id, cls.env.ref('base.group_partner_manager').id])],
        })
        cls.manager = Users.create({
            'name': 'Credit Manager', 'login': 'credit_manager', 'lang': 'en_US', 'email': 'mgr@example.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('isd_credit_app.group_credit_manager').id])],
        })
        # The messages are checked in English, whatever languages the database has
        cls.env.ref('base.user_admin').lang = 'en_US'
        cls.base_module = cls.env.ref('base.module_base')
        cls.Wallet = cls.env['isd.credit.wallet']
        cls.Rule = cls.env['isd.credit.rule']
        cls.wallet = cls.Wallet._get_wallet()

    # ------------------------------------------------------------ helpers
    def _set_balance(self, system=0, topup=0, wallet=None):
        wallet = wallet or self.wallet
        wallet.sudo().write({'system_balance': system, 'topup_balance': topup,
                             'low_notified': False, 'empty_notified': False})

    def _price(self, operation, credits, **vals):
        values = {'name': 'Price %s' % operation, 'module_id': self.base_module.id, 'operation': operation,
                  'credits': credits}
        if operation in ('create', 'write', 'unlink', 'button'):
            values['model_id'] = self.env.ref('base.model_res_partner').id
        values.update(vals)
        return self.Rule.create(values)

    def _as(self, user, model):
        return self.env[model].with_user(user)

    # ------------------------------------------------------------ wallet
    def test_system_credit_spent_first(self):
        self._set_balance(system=3, topup=10)
        self._price('create', 2)
        self._as(self.employee, 'res.partner').create({'name': 'A'})
        self.assertEqual((self.wallet.system_balance, self.wallet.topup_balance), (1, 10))
        self._as(self.employee, 'res.partner').create({'name': 'B'})
        self.assertEqual((self.wallet.system_balance, self.wallet.topup_balance), (0, 9))
        line = self.env['isd.credit.ledger'].search([('wallet_id', '=', self.wallet.id)], limit=1)
        self.assertEqual((line.kind, line.credits, line.system_delta, line.topup_delta, line.balance_after),
                         ('consume', -2, -1, -1, 9))
        self.assertEqual(line.user_id, self.employee)

    def test_blocks_when_empty(self):
        self._set_balance(system=1)
        self._price('create', 2)
        with self.assertRaisesRegex(UserError, 'Not enough credit'):
            self._as(self.employee, 'res.partner').create({'name': 'Blocked'})

    def test_batch_is_all_or_nothing(self):
        self._set_balance(system=5)
        self._price('create', 2)
        count = self.env['res.partner'].search_count([])
        with self.assertRaisesRegex(UserError, 'needs 6 credits'):
            with self.env.cr.savepoint():
                self._as(self.employee, 'res.partner').create([{'name': 'B%s' % i} for i in range(3)])
        self.assertEqual(self.env['res.partner'].search_count([]), count)
        self.assertEqual(self.wallet.balance, 5)
        self._as(self.employee, 'res.partner').create([{'name': 'C1'}, {'name': 'C2'}])
        self.assertEqual(self.wallet.balance, 1)

    def test_failed_action_gives_credit_back(self):
        self._set_balance(system=10)
        self._price('create', 4)
        with self.assertRaises(ValueError):
            with self.env.cr.savepoint():
                self._as(self.employee, 'res.partner').create({'name': 'Rolled back'})
                raise ValueError('the action fails after the charge')
        self.wallet.invalidate_recordset()
        self.assertEqual(self.wallet.balance, 10)

    def test_exempt_vendor_and_superuser(self):
        self._set_balance(system=0)
        self._price('create', 5)
        self.env['res.partner'].create({'name': 'By the superuser'})
        self._as(self.env.ref('base.user_admin'), 'res.partner').create({'name': 'By ISD'})
        self.assertEqual(self.wallet.balance, 0)

    def test_zero_price_tracks_nothing_charged(self):
        self._set_balance(system=1)
        self._price('create', 0)
        self._as(self.employee, 'res.partner').create({'name': 'Free'})
        self.assertEqual(self.wallet.balance, 1)

    # -------------------------------------------------------- operations
    def test_write_only_on_chosen_fields(self):
        self._set_balance(system=10)
        partner = self.env['res.partner'].create({'name': 'P'})
        self._price('write', 3, write_field_ids=[(6, 0, self.env['ir.model.fields']._get('res.partner', 'phone').ids)])
        partner.with_user(self.employee).write({'name': 'P2'})
        self.assertEqual(self.wallet.balance, 10)
        partner.with_user(self.employee).write({'phone': '123'})
        self.assertEqual(self.wallet.balance, 7)

    def test_unlink_and_domain(self):
        self._set_balance(system=10)
        company = self.env['res.partner'].create({'name': 'Co', 'is_company': True})
        person = self.env['res.partner'].create({'name': 'Person'})
        self._price('unlink', 2, domain="[('is_company', '=', True)]")
        person.with_user(self.employee).unlink()
        self.assertEqual(self.wallet.balance, 10)
        company.with_user(self.employee).unlink()
        self.assertEqual(self.wallet.balance, 8)

    def test_button(self):
        self._set_balance(system=10)
        partner = self.env['res.partner'].create({'name': 'P'})
        self._price('button', 3, button_name='action_archive')
        self.Rule.with_user(self.employee)._charge_button('res.partner', 'action_archive', partner.ids)
        self.Rule.with_user(self.employee)._charge_button('res.partner', 'other_button', partner.ids)
        self.assertEqual(self.wallet.balance, 7)

    def test_server_action(self):
        self._set_balance(system=10)
        partners = self.env['res.partner'].create([{'name': 'S1'}, {'name': 'S2'}])
        action = self.env['ir.actions.server'].create({
            'name': 'Mark', 'model_id': self.env.ref('base.model_res_partner').id,
            'state': 'code', 'code': 'records.write({"comment": "done"})',
        })
        self._price('server_action', 2, server_action_id=action.id)
        action.with_user(self.employee).with_context(
            active_model='res.partner', active_ids=partners.ids).run()
        self.assertEqual(self.wallet.balance, 6)

    def test_report(self):
        self._set_balance(system=10)
        report = self.env['ir.actions.report'].create({
            'name': 'Partner Card', 'model': 'res.partner', 'report_type': 'qweb-pdf',
            'report_name': 'isd_credit_app.test_partner_card'})
        self._price('report', 3, report_id=report.id)
        partners = self.env['res.partner'].create([{'name': 'R1'}])
        Report = self.env['ir.actions.report'].with_user(self.employee)
        with patch.object(type(self.env['ir.actions.report']), '_render_qweb_html',
                          return_value=(b'<html/>', 'html')):
            Report._render_qweb_pdf(report.report_name, partners.ids)
        self.assertEqual(self.wallet.balance, 7)

    def test_named_action(self):
        self._set_balance(system=10)
        self._price('named', 4, action_code='test.named')
        self.Wallet.with_user(self.employee).consume('test.named', qty=2)
        self.Wallet.with_user(self.employee).consume('test.unpriced')
        self.assertEqual(self.wallet.balance, 2)

    def test_price_change_clears_cache(self):
        self._set_balance(system=10)
        rule = self._price('create', 1)
        self._as(self.employee, 'res.partner').create({'name': 'X'})
        rule.credits = 5
        self._as(self.employee, 'res.partner').create({'name': 'Y'})
        rule.active = False
        self._as(self.employee, 'res.partner').create({'name': 'Z'})
        self.assertEqual(self.wallet.balance, 4)

    def test_form_hint(self):
        self._price('create', 2)
        self._price('write', 1)
        self.assertEqual(self.Rule.with_user(self.employee).get_form_hint('res.partner'), {'create': 2, 'write': 1})
        self.assertFalse(self.Rule.with_user(self.employee).get_form_hint('res.country'))

    def test_module_choice_excludes_this_module(self):
        rule = self._price('create', 1)
        modules = rule.allowed_module_ids.mapped('name')
        self.assertNotIn('isd_credit_app', modules)
        rule.isd_only = False
        self.assertIn('base', rule.allowed_module_ids.mapped('name'))
        self.assertNotIn('isd_credit_app', rule.allowed_module_ids.mapped('name'))
        self.assertIn(self.env.ref('base.model_res_partner'), rule.allowed_model_ids)

    # ----------------------------------------------------------- periods
    def test_period_bounds(self):
        moment = datetime(2026, 11, 19, 15, 0)  # a Thursday
        self.assertEqual(period_bounds('week', moment), (datetime(2026, 11, 16), datetime(2026, 11, 23)))
        self.assertEqual(period_bounds('quarter', moment), (datetime(2026, 10, 1), datetime(2027, 1, 1)))
        self.assertEqual(period_bounds('once', moment), (None, None))

    def test_reset_modes(self):
        self.wallet.write({'allowance': 100, 'period': 'month', 'reset_mode': 'reset'})
        self._set_balance(system=0, topup=7)
        self.wallet.action_start_plan()
        self.assertEqual(self.wallet.system_balance, 100)
        self.assertTrue(self.wallet.next_reset)
        self._set_balance(system=30, topup=7)
        self.wallet._apply_period()
        self.assertEqual((self.wallet.system_balance, self.wallet.topup_balance), (100, 7))

        self.wallet.write({'reset_mode': 'rollover', 'rollover_cap': 250})
        self.wallet._apply_period()
        self.assertEqual(self.wallet.system_balance, 200)
        self.wallet._apply_period()
        self.assertEqual(self.wallet.system_balance, 250)

        self.wallet.reset_mode = 'none'
        self.wallet._apply_period()
        self.assertEqual(self.wallet.system_balance, 250)
        self.assertEqual(self.wallet.topup_balance, 7, 'purchased credit never expires')

    def test_contract_end_stops_grants(self):
        self.wallet.write({'allowance': 100, 'period': 'month', 'reset_mode': 'reset',
                           'contract_end': fields.Date.subtract(fields.Date.today(), days=1)})
        self._set_balance(system=40)
        self.wallet._apply_period()
        self.assertEqual(self.wallet.system_balance, 0)

    def test_cron_applies_due_periods(self):
        self.wallet.write({'allowance': 50, 'period': 'day', 'reset_mode': 'reset',
                           'active_plan': True, 'next_reset': fields.Datetime.subtract(fields.Datetime.now(), hours=1)})
        self._set_balance(system=3)
        self.Wallet._cron_periods()
        self.assertEqual(self.wallet.system_balance, 50)
        self.assertGreater(self.wallet.next_reset, fields.Datetime.now())

    # ------------------------------------------------------------ notice
    def test_notice_and_hide_today(self):
        self.ICP.set_param('isd_credit_app.warning_threshold', '200')
        self._set_balance(system=150)
        Wallet = self.Wallet.with_user(self.employee)
        notice = Wallet.get_notice()
        self.assertEqual((notice['level'], notice['balance'], notice['can_request']), ('low', 150, False))
        self.assertTrue(self.Wallet.with_user(self.manager).get_notice()['can_request'])
        Wallet.hide_notice_today()
        self.assertFalse(Wallet.get_notice())
        self.employee.sudo().isd_credit_hidden_on = '2000-01-01'
        self.assertTrue(Wallet.get_notice(), 'shows again the next day')
        self._set_balance(system=0)
        self.assertEqual(Wallet.get_notice()['level'], 'empty')
        self._set_balance(system=500)
        self.assertFalse(Wallet.get_notice())

    def test_threshold_email_once(self):
        self.ICP.set_param('isd_credit_app.warning_threshold', '5')
        self._set_balance(system=10)
        self._price('create', 3)
        with patch.object(type(self.Wallet), '_notify') as notify:
            self._as(self.employee, 'res.partner').create({'name': '1'})  # 7
            self._as(self.employee, 'res.partner').create({'name': '2'})  # 4: low
            self._as(self.employee, 'res.partner').create({'name': '3'})  # 1: still low
        self.assertEqual([c.args[0] for c in notify.call_args_list], ['isd_credit_app.mail_template_credit_low'])

    # ------------------------------------------------------------ limits
    def test_user_limit(self):
        self._set_balance(system=100)
        self._price('create', 3)
        self.env['isd.credit.limit'].create({'user_id': self.employee.id, 'period': 'day', 'max_credits': 5})
        self._as(self.employee, 'res.partner').create({'name': 'ok'})
        with self.assertRaisesRegex(UserError, '3/5'):
            self._as(self.employee, 'res.partner').create({'name': 'over'})
        self._as(self.colleague, 'res.partner').create({'name': 'others carry on'})
        self.assertEqual(self.wallet.balance, 94)

    def test_group_limit_and_own_limit_wins(self):
        self._set_balance(system=100)
        self._price('create', 3)
        Limit = self.env['isd.credit.limit']
        Limit.create({'group_id': self.env.ref('base.group_user').id, 'mode': 'forbid'})
        with self.assertRaisesRegex(UserError, 'not allowed'):
            self._as(self.colleague, 'res.partner').create({'name': 'forbidden'})
        Limit.create({'user_id': self.employee.id, 'period': 'month', 'max_credits': 10})
        self._as(self.employee, 'res.partner').create({'name': 'own limit applies'})
        status = Limit.with_user(self.employee).get_my_status()
        self.assertEqual(status['used_month'], 3)
        self.assertEqual(status['limits'][0]['remaining'], 7)

    # -------------------------------------------------------- companies
    def test_wallet_per_company(self):
        self.ICP.set_param('isd_credit_app.wallet_scope', 'company')
        company_b = self.env['res.company'].create({'name': 'Company B'})
        self.employee.write({'company_ids': [(4, company_b.id)]})
        wallet_a = self.Wallet._get_wallet(self.env.company)
        wallet_b = self.Wallet._get_wallet(company_b)
        self.assertNotEqual(wallet_a, wallet_b)
        self._set_balance(system=10, wallet=wallet_a)
        self._set_balance(system=10, wallet=wallet_b)
        self._price('create', 2)
        self._as(self.employee, 'res.partner').create([{'name': 'in B', 'company_id': company_b.id},
                                                      {'name': 'in B too', 'company_id': company_b.id},
                                                      {'name': 'in A', 'company_id': self.env.company.id}])
        self.assertEqual((wallet_a.balance, wallet_b.balance), (8, 6))

    # ---------------------------------------------------------- top-ups
    def test_topup_flow_vnd_and_usd(self):
        self.ICP.set_param('isd_credit_app.price_per_credit_usd', '0.02')
        package = self.env['isd.credit.package'].create({
            'name': '1000 credits', 'credits': 1000, 'price': 500000, 'currency_id': self.env.ref('base.VND').id})
        Topup = self.env['isd.credit.topup'].with_user(self.manager)
        vnd = Topup.create({'package_id': package.id, 'credits': 1000, 'currency_id': self.env.ref('base.VND').id})
        self.assertEqual(vnd.amount, 500000)
        self.assertTrue(vnd.name.startswith('TOP/'))
        usd = Topup.create({'credits': 500, 'currency_id': self.env.ref('base.USD').id})
        self.assertEqual(usd.amount, 10)

        self._set_balance(system=0, topup=0)
        vnd.action_submit()
        self.assertEqual(vnd.state, 'submitted')
        with self.assertRaises(AccessError):
            vnd.action_approve()
        with self.assertRaises(AccessError):
            vnd.write({'state': 'approved'})
        vnd_as_isd = vnd.with_user(self.env.ref('base.user_admin'))
        vnd_as_isd.received_amount = 500000
        vnd_as_isd.action_approve()
        self.assertEqual(vnd.state, 'approved')
        self.assertEqual((self.wallet.system_balance, self.wallet.topup_balance), (0, 1000))
        with self.assertRaises(UserError):
            vnd.write({'credits': 5000})

        usd.action_submit()
        usd_as_isd = usd.with_user(self.env.ref('base.user_admin'))
        with self.assertRaisesRegex(UserError, 'why'):
            usd_as_isd.action_reject()
        usd_as_isd.reject_reason = 'No cash received'
        usd_as_isd.action_reject()
        self.assertEqual(usd.state, 'rejected')
        self.assertEqual(self.wallet.topup_balance, 1000)

    def test_customer_cannot_add_credit(self):
        wallet = self.wallet.with_user(self.manager)
        with self.assertRaises(AccessError):
            wallet.write({'topup_balance': 99999})
        with self.assertRaises(AccessError):
            wallet.action_start_plan()
        with self.assertRaises(AccessError):
            wallet.action_adjust()
        with self.assertRaises(AccessError):
            self.env['isd.credit.topup'].with_user(self.manager).create({
                'credits': 10, 'state': 'approved', 'currency_id': self.env.ref('base.VND').id})
        with self.assertRaises(AccessError):
            self.Rule.with_user(self.manager).create({
                'name': 'free', 'module_id': self.base_module.id, 'operation': 'named',
                'action_code': 'x', 'credits': 0})

    def test_ledger_is_immutable_and_adjustments(self):
        self._set_balance(system=5)
        wizard = self.env['isd.credit.adjust.wizard'].create({
            'wallet_id': self.wallet.id, 'part': 'topup', 'credits': 20, 'reason': 'Gift'})
        wizard.action_apply()
        self.assertEqual(self.wallet.topup_balance, 20)
        line = self.env['isd.credit.ledger'].search([('kind', '=', 'adjust')], limit=1)
        self.assertIn('Gift', line.description)
        with self.assertRaises(UserError):
            line.write({'credits': 1000})
        with self.assertRaises(UserError):
            line.unlink()
        with self.assertRaises(UserError):
            self.env['isd.credit.adjust.wizard'].create({
                'wallet_id': self.wallet.id, 'part': 'system', 'credits': -6, 'reason': 'Too much'}).action_apply()

    def test_lock_takes_row_lock(self):
        queries = []
        execute = type(self.env.cr).execute

        def spy(cr, query, params=None, *args, **kwargs):
            queries.append(str(query))
            return execute(cr, query, params, *args, **kwargs)

        self._set_balance(system=5)
        with patch.object(type(self.env.cr), 'execute', spy):
            self.wallet._spend(1, 'locked')
        self.assertTrue(any('FOR UPDATE' in q for q in queries))
