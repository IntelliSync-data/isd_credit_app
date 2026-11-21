/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/** The credit balance in the top bar, with the user's own usage and limits. */
export class CreditSystray extends Component {
    static template = "isd_credit_app.CreditSystray";
    static components = { Dropdown, DropdownItem };
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ status: false });
        onWillStart(() => this.load());
    }

    async load() {
        try {
            this.state.status = await this.orm.call("isd.credit.wallet", "get_status", []);
        } catch {
            this.state.status = false;
        }
    }

    get level() {
        const status = this.state.status;
        if (status.balance <= 0) {
            return "text-danger";
        }
        return status.balance <= status.threshold ? "text-warning" : "";
    }

    format(value) {
        return (value || 0).toLocaleString();
    }

    open(xmlid) {
        this.action.doAction(xmlid);
    }
}

registry.category("systray").add("isd_credit_app.CreditSystray", { Component: CreditSystray }, { sequence: 30 });
