// Extra behaviour on the Sales Order form for COD orders.
// 1. Before "Expédier": ask for the courier and tracking number.
// 2. On a returned order: a button to record the inspection of the parcel.
// 3. Commune and stop desk pick lists (imported from the courier, e.g. Yalidine).
// 4. The channel (COD or direct sale, dz_cod/cod/channel.py): the customer's
//    usual one, else the default of COD Settings.

const DIRECT_SALE = "Vente directe";

// Offices of the order's wilaya (and of its parent wilaya for the 2026 wilayas)
const stopdesk_query = (frm) => ({
	query: "dz_cod.couriers.places.stopdesk_query",
	filters: { wilaya: frm.doc.dz_wilaya },
});

frappe.ui.form.on("Sales Order", {
	setup(frm) {
		frm.set_query("dz_courier", () => ({ filters: { is_transporter: 1 } }));
		frm.set_query("dz_stopdesk_id", () => stopdesk_query(frm));
		// All the wilaya's communes: a name outside the list is refused. Nothing
		// imported = empty list = free text.
		frm.set_query("dz_commune", () => ({
			query: "dz_cod.couriers.places.commune_names",
			params: { wilaya: frm.doc.dz_wilaya },
		}));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.dz_channel) {
			frappe.db
				.get_single_value("COD Settings", "default_channel")
				.then(
					(channel) =>
						channel && !frm.doc.dz_channel && frm.set_value("dz_channel", channel)
				);
		}
	},

	customer(frm) {
		if (frm.doc.docstatus !== 0 || !frm.doc.customer) return;
		frappe.db.get_value("Customer", frm.doc.customer, "dz_channel").then((r) => {
			const channel = r.message && r.message.dz_channel;
			if (channel) frm.set_value("dz_channel", channel);
		});
	},

	refresh(frm) {
		if (frm.doc.workflow_state === "Retournée" && !frm.doc.dz_return_inspected) {
			frm.add_custom_button(__("Inspecter le retour"), () => inspect_return(frm));
		}
		// Optional features this site has (dz_cod/features.py)
		const has = (feature) => (frappe.boot.dz_features || []).includes(feature);
		if (frm.doc.dz_label_url && has("courier_api")) {
			frm.add_custom_button(__("Étiquette du transporteur"), () =>
				window.open(frm.doc.dz_label_url, "_blank", "noopener")
			);
		}
		// Our own 100 x 150 mm label (print format "Bordereau COD"), for couriers
		// whose API gives no label (Manuel, ZR Express...)
		if (
			frm.doc.docstatus === 1 &&
			frm.doc.dz_channel !== DIRECT_SALE &&
			has("labels_reports")
		) {
			frm.add_custom_button(__("Bordereau"), () => {
				const params = new URLSearchParams({
					doctype: frm.doc.doctype,
					name: frm.doc.name,
					format: "Bordereau COD",
					no_letterhead: 1,
					trigger_print: 1,
				});
				window.open(`/printview?${params}`, "_blank", "noopener");
			});
		}
	},

	// Runs when a workflow button is clicked, before the action is applied.
	// Returning a Promise makes Frappe wait for it.
	before_workflow_action(frm) {
		if (frm.selected_workflow_action !== "Expédier") {
			return;
		}
		// Frappe greys out the screen while a workflow action runs. Lift that
		// while our dialog is open, otherwise nobody can click in it.
		frappe.dom.unfreeze();
		return new Promise((resolve, reject) => {
			let shipped = false; // closing the dialog without shipping cancels the action
			const dialog = new frappe.ui.Dialog({
				title: __("Expédier la commande"),
				fields: [
					{
						fieldname: "courier",
						label: __("Transporteur"),
						fieldtype: "Link",
						options: "Supplier",
						reqd: 1,
						default: frm.doc.dz_courier,
						get_query: () => ({ filters: { is_transporter: 1 } }),
					},
					{
						fieldname: "tracking_number",
						label: __("N° de suivi"),
						fieldtype: "Data",
						default: frm.doc.dz_tracking_number,
						description: __(
							"Laissez vide si le transporteur est connecté (le numéro sera demandé automatiquement)."
						),
					},
					{
						fieldname: "stopdesk_id",
						label: __("Bureau stop desk"),
						fieldtype: "Link",
						options: "DZ Stop Desk",
						default: frm.doc.dz_stopdesk_id,
						hidden: frm.doc.dz_delivery_type !== "Stop desk",
						get_query: () => stopdesk_query(frm),
					},
				],
				primary_action_label: __("Expédier"),
				primary_action(values) {
					frappe
						.call("dz_cod.cod.order.set_shipping_details", {
							sales_order: frm.doc.name,
							courier: values.courier,
							tracking_number: values.tracking_number,
							stopdesk_id: values.stopdesk_id,
						})
						.then(() => {
							shipped = true;
							dialog.hide();
							frappe.dom.freeze(); // Frappe unfreezes when the action is done
							resolve();
						});
				},
			});
			dialog.onhide = () => {
				if (!shipped) reject();
			};
			dialog.show();
		});
	},
});

function inspect_return(frm) {
	frappe.call("dz_cod.cod.stock.get_returned_items", { sales_order: frm.doc.name }).then((r) => {
		// One row per returned item: by default everything is in good condition
		const rows = (r.message || []).map((row) => ({
			item_code: row.item_code,
			item_name: row.item_name,
			good_qty: row.qty,
			damaged_qty: 0,
		}));

		const dialog = new frappe.ui.Dialog({
			title: __("Inspection du retour"),
			size: "large",
			fields: [
				{
					fieldtype: "HTML",
					options: `<p>${__(
						"Indiquez pour chaque article combien de pièces sont en bon état (remises en stock) et combien sont abîmées (mises au rebut)."
					)}</p>`,
				},
				{
					fieldname: "items",
					fieldtype: "Table",
					cannot_add_rows: true,
					in_place_edit: true,
					data: rows,
					fields: [
						{
							fieldname: "item_code",
							label: __("Code"),
							fieldtype: "Data",
							read_only: 1,
							in_list_view: 1,
						},
						{
							fieldname: "item_name",
							label: __("Article"),
							fieldtype: "Data",
							read_only: 1,
							in_list_view: 1,
						},
						{
							fieldname: "good_qty",
							label: __("Bon état"),
							fieldtype: "Float",
							in_list_view: 1,
						},
						{
							fieldname: "damaged_qty",
							label: __("Abîmé"),
							fieldtype: "Float",
							in_list_view: 1,
						},
					],
				},
			],
			primary_action_label: __("Valider l'inspection"),
			primary_action(values) {
				frappe
					.call("dz_cod.cod.stock.inspect_return", {
						sales_order: frm.doc.name,
						items: values.items,
					})
					.then(() => {
						dialog.hide();
						frm.reload_doc();
					});
			},
		});
		dialog.show();
	});
}
