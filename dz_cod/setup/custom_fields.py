"""Custom fields added to standard ERPNext doctypes.

All our fields start with "dz_" so you can always tell them apart from
ERPNext's own fields (and find them with a simple search).

`allow_on_submit: 1` means the field can still change after the order is
confirmed (submitted). Fields filled during shipping, delivery or settlement
need it.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from dz_cod.cod.channel import COD, DIRECT

DELIVERY_TYPES = "Domicile\nStop desk"
ORDER_SOURCES = "\nInstagram\nFacebook\nSite web\nWhatsApp\nTikTok\nTéléphone\nAutre"
# Empty first: a new order takes its customer's channel, else COD Settings' default (cod/channel.py)
CHANNELS = f"\n{COD}\n{DIRECT}"
# The COD sections of an order are hidden on a direct sale
ONLY_COD = f"eval:doc.dz_channel != '{DIRECT}'"


def after_submit_readonly(fieldname, label, fieldtype, insert_after, **extra):
	"""A read-only field that our code fills after the order is submitted."""
	field = {
		"fieldname": fieldname,
		"label": label,
		"fieldtype": fieldtype,
		"insert_after": insert_after,
		"read_only": 1,
		"allow_on_submit": 1,
		"no_copy": 1,
	}
	field.update(extra)
	return field


SALES_ORDER_FIELDS = [
	{
		"fieldname": "dz_channel",
		"label": "Canal",
		"fieldtype": "Select",
		"options": CHANNELS,
		"insert_after": "order_type",
		"in_standard_filter": 1,
		"description": "Vente directe : livraison et facture habituelles d'ERPNext, sans les contrôles COD.",
	},
	# --- Section 1: who and where to deliver (filled when taking the order) ---
	{
		"fieldname": "dz_delivery_section",
		"label": "Livraison COD",
		"fieldtype": "Section Break",
		"insert_after": "delivery_date",
		"depends_on": ONLY_COD,
	},
	{
		"fieldname": "dz_phone",
		"label": "Téléphone",
		"fieldtype": "Data",
		"options": "Phone",
		"insert_after": "dz_delivery_section",
		"fetch_from": "customer.dz_phone",
		"fetch_if_empty": 1,
		"in_standard_filter": 1,
		"in_list_view": 1,
	},
	{
		"fieldname": "dz_phone_2",
		"label": "Téléphone 2",
		"fieldtype": "Data",
		"options": "Phone",
		"insert_after": "dz_phone",
	},
	{
		"fieldname": "dz_source",
		"label": "Source de la commande",
		"fieldtype": "Select",
		"options": ORDER_SOURCES,
		"insert_after": "dz_phone_2",
		"in_standard_filter": 1,
	},
	{"fieldname": "dz_column_1", "fieldtype": "Column Break", "insert_after": "dz_source"},
	{
		"fieldname": "dz_wilaya",
		"label": "Wilaya",
		"fieldtype": "Link",
		"options": "DZ Wilaya",
		"insert_after": "dz_column_1",
		"fetch_from": "customer.dz_wilaya",
		"fetch_if_empty": 1,
		"in_standard_filter": 1,
		"in_list_view": 1,
	},
	{
		# Autocomplete: free text, or a pick list once the courier's communes
		# are imported (Yalidine refuses names it does not know)
		"fieldname": "dz_commune",
		"label": "Commune",
		"fieldtype": "Autocomplete",
		"insert_after": "dz_wilaya",
		"fetch_from": "customer.dz_commune",
		"fetch_if_empty": 1,
	},
	{
		"fieldname": "dz_address",
		"label": "Adresse",
		"fieldtype": "Small Text",
		"insert_after": "dz_commune",
		"fetch_from": "customer.dz_address",
		"fetch_if_empty": 1,
	},
	{"fieldname": "dz_column_2", "fieldtype": "Column Break", "insert_after": "dz_address"},
	{
		"fieldname": "dz_delivery_type",
		"label": "Type de livraison",
		"fieldtype": "Select",
		"options": DELIVERY_TYPES,
		"default": "Domicile",
		"insert_after": "dz_column_2",
		"in_standard_filter": 1,
	},
	{
		"fieldname": "dz_stopdesk_id",
		"label": "Bureau stop desk",
		"description": "Bureau du transporteur où le client retire son colis.",
		"fieldtype": "Link",
		"options": "DZ Stop Desk",
		"insert_after": "dz_delivery_type",
		"depends_on": 'eval:doc.dz_delivery_type=="Stop desk"',
		"allow_on_submit": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "dz_manual_shipping",
		"label": "Tarif de livraison manuel",
		"description": "Cochez pour saisir vous-même les frais (livraison offerte, remise...).",
		"fieldtype": "Check",
		"insert_after": "dz_stopdesk_id",
	},
	{
		"fieldname": "dz_shipping_charge",
		"label": "Frais de livraison",
		"fieldtype": "Currency",
		"options": "currency",
		"insert_after": "dz_manual_shipping",
		"read_only_depends_on": "eval:!doc.dz_manual_shipping",
	},
	{
		"fieldname": "dz_cod_amount",
		"label": "Montant à encaisser",
		"description": "Total que le livreur doit encaisser auprès du client (articles + livraison).",
		"fieldtype": "Currency",
		"options": "currency",
		"insert_after": "dz_shipping_charge",
		"read_only": 1,
		"in_list_view": 1,
		"bold": 1,
	},
	# --- Section 2: follow-up (filled by the workflow) ---
	{
		"fieldname": "dz_tracking_section",
		"label": "Suivi COD",
		"fieldtype": "Section Break",
		"insert_after": "dz_cod_amount",
		"collapsible": 1,
		"depends_on": ONLY_COD,
	},
	after_submit_readonly("dz_call_attempts", "Appels sans réponse", "Int", "dz_tracking_section"),
	{
		"fieldname": "dz_courier",
		"label": "Transporteur",
		"fieldtype": "Link",
		"options": "Supplier",
		"insert_after": "dz_call_attempts",
		"allow_on_submit": 1,
		"in_standard_filter": 1,
	},
	{
		"fieldname": "dz_tracking_number",
		"label": "N° de suivi",
		"fieldtype": "Data",
		"insert_after": "dz_courier",
		"allow_on_submit": 1,
		"no_copy": 1,
		"in_standard_filter": 1,
	},
	after_submit_readonly(
		"dz_label_url", "Étiquette du transporteur", "Data", "dz_tracking_number", options="URL"
	),
	after_submit_readonly(
		"dz_courier_fee",
		"Frais transporteur prévus",
		"Currency",
		"dz_label_url",
		options="currency",
		description="Montant que le transporteur devrait retenir (d'après la grille de la wilaya).",
	),
	after_submit_readonly(
		"dz_delivery_note", "Bon de livraison", "Link", "dz_courier_fee", options="Delivery Note"
	),
	# Made when the order becomes Livrée (cod/invoicing.py)
	after_submit_readonly("dz_sales_invoice", "Facture", "Link", "dz_delivery_note", options="Sales Invoice"),
	after_submit_readonly(
		"dz_return_note", "Bon de retour", "Link", "dz_sales_invoice", options="Delivery Note"
	),
	after_submit_readonly("dz_return_inspected", "Retour inspecté", "Check", "dz_return_note"),
	after_submit_readonly(
		"dz_settlement", "Versement", "Link", "dz_return_inspected", options="Courier Settlement"
	),
	{"fieldname": "dz_column_3", "fieldtype": "Column Break", "insert_after": "dz_settlement"},
	after_submit_readonly("dz_confirmed_on", "Confirmée le", "Date", "dz_column_3"),
	after_submit_readonly("dz_shipped_on", "Expédiée le", "Date", "dz_confirmed_on"),
	after_submit_readonly("dz_delivered_on", "Livrée le", "Date", "dz_shipped_on"),
	after_submit_readonly("dz_returned_on", "Retournée le", "Date", "dz_delivered_on"),
	after_submit_readonly("dz_settled_on", "Réglée le", "Date", "dz_returned_on"),
	# What the courier itself says (Yalidine sync or webhook), word for word
	after_submit_readonly(
		"dz_courier_status",
		"Statut chez le transporteur",
		"Data",
		"dz_settled_on",
		description="Ex. « Retour vers vendeur » : le colis revient, mais n'est pas encore arrivé.",
	),
	after_submit_readonly(
		"dz_courier_status_on", "Statut transporteur mis à jour le", "Datetime", "dz_courier_status"
	),
	after_submit_readonly(
		"dz_courier_payment_status", "Paiement chez le transporteur", "Data", "dz_courier_status_on"
	),
	after_submit_readonly(
		"dz_courier_payment_id", "N° de paiement transporteur", "Data", "dz_courier_payment_status"
	),
]

# The section, the phone and the wilaya are dz_core's (every client has them);
# commune and address are the delivery details orders copy
CUSTOMER_FIELDS = [
	{"fieldname": "dz_column", "fieldtype": "Column Break", "insert_after": "dz_wilaya"},
	{"fieldname": "dz_commune", "label": "Commune", "fieldtype": "Data", "insert_after": "dz_column"},
	{"fieldname": "dz_address", "label": "Adresse", "fieldtype": "Small Text", "insert_after": "dz_commune"},
	{
		"fieldname": "dz_channel",
		"label": "Canal habituel",
		"fieldtype": "Select",
		"options": CHANNELS,
		"insert_after": "dz_address",
		"description": "Vide : le canal par défaut des Paramètres COD.",
	},
]

# Courier settings live on the Supplier (a courier is a supplier with
# "Is Transporter" ticked).
SUPPLIER_FIELDS = [
	{
		"fieldname": "dz_courier_section",
		"label": "Intégration transporteur (COD)",
		"fieldtype": "Section Break",
		"insert_after": "is_transporter",
		"depends_on": "eval:doc.is_transporter",
		"collapsible": 1,
	},
	{
		"fieldname": "dz_courier_adapter",
		"label": "Connecteur",
		"fieldtype": "Select",
		"options": "Manuel\nMock\nYalidine\nZR Express",
		"default": "Manuel",
		"description": "Manuel : vous saisissez le n° de suivi. Mock : simulation hors ligne pour les tests. "
		"Yalidine : colis, statuts et tarifs par l'API Yalidine. "
		"ZR Express : bientôt disponible, saisie manuelle en attendant.",
		"insert_after": "dz_courier_section",
	},
	{"fieldname": "dz_api_id", "label": "API ID", "fieldtype": "Data", "insert_after": "dz_courier_adapter"},
	{"fieldname": "dz_api_token", "label": "API Token", "fieldtype": "Password", "insert_after": "dz_api_id"},
	{"fieldname": "dz_courier_column", "fieldtype": "Column Break", "insert_after": "dz_api_token"},
	{
		"fieldname": "dz_from_wilaya",
		"label": "Wilaya de départ",
		"description": "Wilaya où vous remettez les colis au transporteur.",
		"fieldtype": "Link",
		"options": "DZ Wilaya",
		"insert_after": "dz_courier_column",
	},
	{
		"fieldname": "dz_webhook_secret",
		"label": "Clé secrète webhook",
		"description": "Copiée du tableau de bord Webhooks du transporteur (voir docs/COURIER_INTEGRATION.md).",
		"fieldtype": "Password",
		"insert_after": "dz_from_wilaya",
	},
]

STOCK_ENTRY_FIELDS = [
	{
		"fieldname": "dz_sales_order",
		"label": "Commande (retour)",
		"description": "Commande retournée dont ce mouvement traite l'inspection.",
		"fieldtype": "Link",
		"options": "Sales Order",
		"insert_after": "stock_entry_type",
		"read_only": 1,
	},
]


# The list of wilayas is dz_core's (doctype DZ Wilaya); the rate table is ours.
# Filled with example rates by setup/wilayas.py.
DZ_WILAYA_FIELDS = [
	{
		"fieldname": "enabled",
		"label": "Livrable",
		"fieldtype": "Check",
		"default": "1",
		"description": "Décocher si vous ne livrez pas dans cette wilaya.",
		"insert_after": "parent_wilaya",
		"in_list_view": 1,
	},
	{
		"fieldname": "zone",
		"label": "Zone tarifaire",
		"fieldtype": "Int",
		"insert_after": "enabled",
		"in_standard_filter": 1,
	},
	{
		"fieldname": "rates_section",
		"label": "Tarifs de livraison (DA)",
		"fieldtype": "Section Break",
		"insert_after": "zone",
	},
	{
		"fieldname": "home_rate",
		"label": "Tarif domicile",
		"fieldtype": "Currency",
		"options": "DZD",
		"non_negative": 1,
		"description": "Prix facturé au client pour une livraison à domicile.",
		"insert_after": "rates_section",
		"in_list_view": 1,
	},
	{
		"fieldname": "stopdesk_rate",
		"label": "Tarif stop desk",
		"fieldtype": "Currency",
		"options": "DZD",
		"non_negative": 1,
		"description": "Prix facturé au client pour un retrait au bureau du transporteur.",
		"insert_after": "home_rate",
		"in_list_view": 1,
	},
	{
		"fieldname": "stopdesk_available",
		"label": "Stop desk disponible",
		"fieldtype": "Check",
		"default": "1",
		"insert_after": "stopdesk_rate",
	},
	{"fieldname": "column_break_rates", "fieldtype": "Column Break", "insert_after": "stopdesk_available"},
	{
		"fieldname": "home_courier_cost",
		"label": "Coût transporteur domicile",
		"fieldtype": "Currency",
		"options": "DZD",
		"non_negative": 1,
		"description": "Ce que le transporteur vous retient par colis livré à domicile.",
		"insert_after": "column_break_rates",
	},
	{
		"fieldname": "stopdesk_courier_cost",
		"label": "Coût transporteur stop desk",
		"fieldtype": "Currency",
		"options": "DZD",
		"non_negative": 1,
		"description": "Ce que le transporteur vous retient par colis livré en stop desk.",
		"insert_after": "home_courier_cost",
	},
]

# ERPNext's own Sales Order fields that mean little for a COD seller: hide them
# from the Commandes list filters and columns, so orders start higher up.
# (fieldname, property, value)
SALES_ORDER_PROPERTIES = [
	("company", "in_standard_filter", 0),
	("customer", "in_standard_filter", 0),  # "Nom du client" already filters by customer
	("delivery_status", "in_standard_filter", 0),
	("billing_status", "in_standard_filter", 0),
	("advance_payment_status", "in_standard_filter", 0),
	("delivery_date", "in_list_view", 0),  # planned date, not the COD delivery
	("grand_total", "in_list_view", 0),  # "Montant à encaisser" is shown instead
	("per_delivered", "in_list_view", 0),
	("per_billed", "in_list_view", 0),
]


def setup_custom_fields():
	"""Create or update all custom fields. Safe to run many times."""
	switch_commune_to_autocomplete()
	create_custom_fields(
		{
			"Sales Order": SALES_ORDER_FIELDS,
			"Customer": CUSTOMER_FIELDS,
			"Supplier": SUPPLIER_FIELDS,
			"Stock Entry": STOCK_ENTRY_FIELDS,
			"DZ Wilaya": DZ_WILAYA_FIELDS,
		},
		update=True,
	)
	setup_list_properties()


def switch_commune_to_autocomplete():
	"""Sales Order "Commune" was a Data field before the Yalidine pick list.
	Frappe refuses Data -> Autocomplete in a Custom Field (not in its list of
	allowed changes), although both are the same database column
	(varchar 140): nothing stored changes. So the type is switched directly."""
	name = "Sales Order-dz_commune"
	if frappe.db.get_value("Custom Field", name, "fieldtype") == "Data":
		frappe.db.set_value("Custom Field", name, "fieldtype", "Autocomplete")


def setup_list_properties():
	"""Apply SALES_ORDER_PROPERTIES once. A property the user already changed
	(Customize Form) keeps the user's value."""
	for fieldname, prop, value in SALES_ORDER_PROPERTIES:
		if frappe.db.exists(
			"Property Setter", {"doc_type": "Sales Order", "field_name": fieldname, "property": prop}
		):
			continue
		make_property_setter(
			"Sales Order", fieldname, prop, value, "Check", validate_fields_for_doctype=False
		)
