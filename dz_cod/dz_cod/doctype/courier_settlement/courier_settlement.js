// Versement form: one extra button to pre-fill the lines.
frappe.ui.form.on("Courier Settlement", {
	setup(frm) {
		// Only couriers (suppliers marked "Is Transporter") in the courier field
		frm.set_query("courier", () => ({ filters: { is_transporter: 1 } }));
		frm.set_query("bank_account", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
				account_type: ["in", ["Bank", "Cash"]],
			},
		}));
	},

	onload(frm) {
		// New Versement: company and bank account from COD Settings
		if (frm.is_new()) {
			for (const [field, setting] of [
				["company", "company"],
				["bank_account", "settlement_bank_account"],
			]) {
				if (!frm.doc[field]) {
					frappe.db
						.get_single_value("COD Settings", setting)
						.then((value) => value && frm.set_value(field, value));
				}
			}
		}
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.courier) {
			frm.add_custom_button(__("Charger les commandes livrées"), () => {
				frm.call("load_delivered_orders").then(() => frm.dirty());
			});
		}
	},

	// Show the button as soon as a courier is chosen (not only after saving)
	courier(frm) {
		frm.trigger("refresh");
	},
});
