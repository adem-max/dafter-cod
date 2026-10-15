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

DELIVERY_TYPES = "Domicile\nStop desk"
ORDER_SOURCES = "\nInstagram\nFacebook\nSite web\nWhatsApp\nTikTok\nTéléphone\nAutre"


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
	# --- Section 1: who and where to deliver (filled when taking the order) ---
	{
		"fieldname": "dz_delivery_section",
		"label": "Livraison COD",
		"fieldtype": "Section Break",
		"insert_after": "delivery_date",
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
		"fieldname": "dz_commune",
		"label": "Commune",
		"fieldtype": "Data",
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
		"fieldname": "dz_manual_shipping",
		"label": "Tarif de livraison manuel",
		"description": "Cochez pour saisir vous-même les frais (livraison offerte, remise...).",
		"fieldtype": "Check",
		"insert_after": "dz_delivery_type",
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
		"dz_courier_fee",
		"Frais transporteur prévus",
		"Currency",
		"dz_tracking_number",
		options="currency",
		description="Montant que le transporteur devrait retenir (d'après la grille de la wilaya).",
	),
	after_submit_readonly(
		"dz_delivery_note", "Bon de livraison", "Link", "dz_courier_fee", options="Delivery Note"
	),
	after_submit_readonly(
		"dz_return_note", "Bon de retour", "Link", "dz_delivery_note", options="Delivery Note"
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
]

CUSTOMER_FIELDS = [
	{
		"fieldname": "dz_section",
		"label": "Coordonnées COD",
		"fieldtype": "Section Break",
		"insert_after": "customer_group",
	},
	{
		"fieldname": "dz_phone",
		"label": "Téléphone",
		"fieldtype": "Data",
		"options": "Phone",
		"insert_after": "dz_section",
		"in_standard_filter": 1,
		"in_global_search": 1,
	},
	{
		"fieldname": "dz_wilaya",
		"label": "Wilaya",
		"fieldtype": "Link",
		"options": "DZ Wilaya",
		"insert_after": "dz_phone",
		"in_standard_filter": 1,
	},
	{"fieldname": "dz_column", "fieldtype": "Column Break", "insert_after": "dz_wilaya"},
	{"fieldname": "dz_commune", "label": "Commune", "fieldtype": "Data", "insert_after": "dz_column"},
	{"fieldname": "dz_address", "label": "Adresse", "fieldtype": "Small Text", "insert_after": "dz_commune"},
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
		"options": "Manuel\nMock\nYalidine",
		"default": "Manuel",
		"description": "Manuel : vous saisissez le n° de suivi. Mock : simulation hors ligne pour les tests.",
		"insert_after": "dz_courier_section",
	},
	{"fieldname": "dz_api_id", "label": "API ID", "fieldtype": "Data", "insert_after": "dz_courier_adapter"},
	{"fieldname": "dz_api_token", "label": "API Token", "fieldtype": "Password", "insert_after": "dz_api_id"},
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
	create_custom_fields(
		{
			"Sales Order": SALES_ORDER_FIELDS,
			"Customer": CUSTOMER_FIELDS,
			"Supplier": SUPPLIER_FIELDS,
			"Stock Entry": STOCK_ENTRY_FIELDS,
		},
		update=True,
	)
	setup_list_properties()


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
