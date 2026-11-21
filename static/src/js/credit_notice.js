/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

/** The low / no credit notice shown once each time the backend loads. */
export class CreditNoticeDialog extends Component {
    static template = "isd_credit_app.CreditNoticeDialog";
    static components = { Dialog };
    static props = ["notice", "onHideToday", "onRequest", "close"];

    setup() {
        this.state = useState({ hideToday: false });
    }

    get title() {
        return this.props.notice.level === "empty" ? _t("Credit has run out") : _t("Credit is running low");
    }

    async finish(request = false) {
        if (this.state.hideToday) {
            await this.props.onHideToday();
        }
        this.props.close();
        if (request) {
            this.props.onRequest();
        }
    }
}

export const creditNoticeService = {
    dependencies: ["orm", "dialog", "action"],
    start(env, { orm, dialog, action }) {
        // Let the web client draw first: the notice is not worth slowing it down
        setTimeout(async () => {
            let notice;
            try {
                notice = await orm.call("isd.credit.wallet", "get_notice", []);
            } catch {
                return;
            }
            if (!notice) {
                return;
            }
            dialog.add(CreditNoticeDialog, {
                notice,
                onHideToday: () => orm.call("isd.credit.wallet", "hide_notice_today", []),
                onRequest: () => action.doAction("isd_credit_app.action_topup_new"),
            });
        }, 500);
    },
};

registry.category("services").add("isd_credit_notice", creditNoticeService);
