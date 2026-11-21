# -*- coding: utf-8 -*-
from odoo import api, models

CHARGED_KEY = 'isd_credit_report_charged'


class IrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

    def run(self):
        Rule = self.env['isd.credit.rule']
        ctx = self.env.context
        for action in self:
            records = None
            model = action.sudo().model_id.model
            ids = ctx.get('active_ids') or ([ctx['active_id']] if ctx.get('active_id') else [])
            if model and ids and ctx.get('active_model', model) == model:
                records = self.env[model].browse(ids).exists()
            Rule._charge_server_action(action, records)
        return super().run()


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _isd_credit_charge(self, report_ref, res_ids):
        if self.env.context.get(CHARGED_KEY):
            return self
        report = self._get_report(report_ref)
        self.env['isd.credit.rule']._charge_report(report, res_ids)
        return self.with_context(**{CHARGED_KEY: True})

    @api.model
    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        return super(IrActionsReport, self._isd_credit_charge(report_ref, res_ids))._render_qweb_pdf(
            report_ref, res_ids=res_ids, data=data)

    @api.model
    def _render_qweb_text(self, report_ref, docids, data=None):
        return super(IrActionsReport, self._isd_credit_charge(report_ref, docids))._render_qweb_text(
            report_ref, docids, data=data)
