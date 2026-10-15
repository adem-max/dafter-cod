// Courier (Supplier) form: Yalidine imports, see dz_cod/couriers/yalidine_import.py

frappe.ui.form.on("Supplier", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.dz_courier_adapter !== "Yalidine") {
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
});

function start_import(frm, what) {
	frappe
		.call("dz_cod.couriers.yalidine_import.start_import", { courier: frm.doc.name, what })
		.then((r) => frappe.show_alert({ message: r.message, indicator: "blue" }, 10));
}
