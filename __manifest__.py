# -*- coding: utf-8 -*-
{
    'name': 'Credit (by ISD)',
    'version': '18.0.1.0.0',
    'category': 'ISD Modules',
    'summary': 'Charge the system in credits: a credit allowance per period, a price per action, '
               'top-up requests, per-user limits and low-credit warnings',
    'description': """
Credit-based billing for the ISD modules running in a hosted Odoo.

* One wallet for the database, or one per company
* System credit granted per period (reset, roll over with a cap, or none) and
  purchased credit that never expires; system credit is spent first
* A price list: create, edit, delete, button, server action, report or a named
  action, on any installed module, each with its credit cost
* Running out blocks the action; a warning for everyone below a threshold
* Managers limit their own staff, and request top-ups (cash, VND or USD) that
  ISD approves
* An append-only ledger of every credit movement
    """,
    'author': 'IntelliSyncData',
    'website': 'https://intellisyncdata.com',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/cron_data.xml',
        'data/mail_templates.xml',
        'views/topup_views.xml',
        'views/ledger_views.xml',
        'views/wallet_views.xml',
        'views/rule_views.xml',
        'views/limit_views.xml',
        'views/package_views.xml',
        'wizard/adjust_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'isd_credit_app/static/src/js/*.js',
            'isd_credit_app/static/src/xml/*.xml',
        ],
    },
    'installable': True,
    'application': True,
}
