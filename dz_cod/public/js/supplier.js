// Courier (Supplier) form: Yalidine imports, see dz_cod/couriers/yalidine_import.py,
// and the "coming soon" notice for ZR Express (dz_cod/couriers/zrexpress.py)

// API connectors are an optional feature (dz_cod/features.py)
const has_courier_api = () => (frappe.boot.dz_features || []).includes("courier_api");

frappe.ui.form.on("Supplier", {
	refresh(frm) {
		if (!has_courier_api()) {
			// Only "Manuel" to choose (plus the current value, so it still shows)
			const options = ["Manuel", "Mock"];
			if (frm.doc.dz_courier_adapter && !options.includes(frm.doc.dz_courier_adapter)) {
				options.push(frm.doc.dz_courier_adapter);
			}
			frm.set_df_property("dz_courier_adapter", "options", options.join("\n"));
		}
		show_coming_soon(frm);
		if (frm.is_new() || frm.doc.dz_courier_adapter !== "Yalidine" || !has_courier_api()) {
			return;
		}
		frm.add_custom_button(
			__("Importer les tarifs Yalidine"),
			() =>
				frappe.confirm(
					__(
						"Les coûts transporteur de chaque wilaya seront remplacés par les tarifs de votre compte Yalidine. Les tarifs facturés aux clients ne changent pas. Continuer ?"
					),
					() => start_import(frm, "fees")
				),
			"Yalidine"
		);
		frm.add_custom_button(
			__("Importer communes et bureaux Yalidine"),
			() => start_import(frm, "places"),
			"Yalidine"
		);
	},

	dz_courier_adapter(frm) {
		show_coming_soon(frm);
	},
});

function show_coming_soon(frm) {
	if (frm.doc.dz_courier_adapter === "ZR Express") {
		frm.set_intro(
			__(
				"Connecteur ZR Express : bientôt disponible. En attendant, saisissez le n° de suivi à l'expédition et passez les commandes en Livrée ou Retournée à la main."
			),
			"orange"
		);
	} else {
		frm.set_intro();
	}
}

function start_import(frm, what) {
	frappe
		.call("dz_cod.couriers.yalidine_import.start_import", { courier: frm.doc.name, what })
		.then((r) => frappe.show_alert({ message: r.message, indicator: "blue" }, 10));
}
