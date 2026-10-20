// Paramètres COD form.

frappe.ui.form.on("COD Settings", {
	setup(frm) {
		// Accounts of the COD company only, never a group
		const accounts = (filters) => () => ({
			filters: { company: frm.doc.company, is_group: 0, ...filters },
		});
		frm.set_query(
			"settlement_bank_account",
			accounts({ account_type: ["in", ["Bank", "Cash"]] })
		);
		for (const field of [
			"courier_fee_account",
			"settlement_difference_account",
			"unmatched_settlement_account",
		]) {
			frm.set_query(field, accounts({}));
		}
	},

	refresh(frm) {
		// Settings of optional features this site doesn't have stay hidden
		// (dz_core/features.py, frappe.boot.dz_features)
		const has = (feature) => (frappe.boot.dz_features || []).includes(feature);
		frm.toggle_display("refused_warning_threshold", has("phone_checks"));
		frm.toggle_display("auto_sync_courier_status", has("courier_api"));

		// Brings back the welcome guide on the COD home page for the current
		// user, after they closed it with ✕ (see setup/home_block/home.js).
		frm.add_custom_button(__("Réafficher le guide d'accueil"), () => {
			frappe.xcall("dz_cod.cod.home.set_guide_state", { state: "open" }).then(() => {
				frappe.defaults.set_user_default_local("dz_cod_home_guide", "open");
				frappe.show_alert({
					message: __("Le guide est de retour sur la page Accueil COD."),
					indicator: "green",
				});
			});
		});
	},
});
