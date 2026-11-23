/** @odoo-module **/
import { onWillStart } from "@odoo/owl";
import { FormController } from "@web/views/form/form_controller";
import { patch } from "@web/core/utils/patch";

const hints = new Map();

/** "Saving this record costs 2 credits" above the forms of priced models. */
patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.creditHint = false;
        onWillStart(async () => {
            const model = this.props.resModel;
            if (!hints.has(model)) {
                hints.set(model, this.orm.call("isd.credit.rule", "get_form_hint", [model]).catch(() => false));
            }
            this.creditHint = await hints.get(model);
        });
    },

    get creditCost() {
        if (!this.creditHint) {
            return "";
        }
        return (this.model.root.isNew ? this.creditHint.create : this.creditHint.write) || "";
    },
});
