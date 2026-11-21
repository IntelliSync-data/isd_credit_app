# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged

WAIT = """
const wait = (selector) => new Promise((resolve, reject) => {
    let tries = 0;
    const timer = setInterval(() => {
        if (document.querySelector(selector)) {
            clearInterval(timer);
            resolve();
        } else if (++tries > 150) {
            clearInterval(timer);
            reject(new Error('missing ' + selector));
        }
    }, 100);
});
"""


@tagged('post_install', '-at_install')
class TestCreditUi(HttpCase):

    def test_notice_and_systray(self):
        self.env['ir.config_parameter'].sudo().set_param('isd_credit_app.warning_threshold', '10')
        self.browser_js('/odoo/credit-price-list', WAIT + """
            Promise.all([wait('.o_isd_credit_systray'), wait('.modal #isd_credit_hide_today')])
                .then(() => console.log('test successful'))
                .catch((error) => console.error(error.message));
        """, login='admin')

    def test_form_hint(self):
        self.env['isd.credit.rule'].create({
            'name': 'New contact', 'module_id': self.env.ref('base.module_base').id, 'operation': 'create',
            'model_id': self.env.ref('base.model_res_partner').id, 'credits': 2,
        })
        self.env['ir.config_parameter'].sudo().set_param('isd_credit_app.warning_threshold', '0')
        user = self.env['res.users'].create({
            'name': 'Hint User', 'login': 'hint_user', 'password': 'hint_user_pw1',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id, self.env.ref('base.group_partner_manager').id])],
        })
        self.assertTrue(user)
        self.browser_js('/odoo/action-base.action_partner_form/new', WAIT + """
            wait('.o_isd_credit_hint')
                .then(() => document.querySelector('.o_isd_credit_hint').textContent.includes('2')
                    ? console.log('test successful') : console.error('wrong price in the hint'))
                .catch((error) => console.error(error.message));
        """, login='hint_user')
