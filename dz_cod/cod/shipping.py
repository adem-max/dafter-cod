"""Shipping charges: look up the rate table and add the fee to the order.

The rate table is the list of wilayas (doctype "DZ Wilaya", from dz_core): this
app gives each wilaya a home-delivery rate and a stop-desk rate, plus what the
courier keeps (custom fields, setup/custom_fields.py).

The fee is added to the order as a line in the standard "Taxes and Charges"
table (type "Actual"), exactly like ERPNext's own Shipping Rule does. This way
the order total, the delivery note and the stock/accounting entries all
include it without extra code.
"""

import frappe
from frappe import _
from frappe.utils import flt

from dz_cod.dz_cod.doctype.cod_settings.cod_settings import get_settings

SHIPPING_DESCRIPTION = "Frais de livraison"
STOP_DESK = "Stop desk"


def get_rates(wilaya, delivery_type):
	"""Return (customer_rate, courier_cost) for a wilaya and delivery type.

	Returns (0, 0) when no wilaya is chosen yet.
	"""
	if not wilaya:
		return 0, 0
	doc = frappe.get_cached_doc("DZ Wilaya", wilaya)
	if not doc.enabled:
		frappe.throw(_("La wilaya {0} n'est pas livrable.").format(doc.name))

	if delivery_type == STOP_DESK:
		if not doc.stopdesk_available:
			frappe.throw(_("Pas de stop desk disponible dans la wilaya {0}.").format(doc.name))
		return doc.stopdesk_rate, doc.stopdesk_courier_cost

	return doc.home_rate, doc.home_courier_cost


def apply_shipping_charge(order):
	"""Set the delivery fee on a draft order and put it in the taxes table."""
	if not order.dz_manual_shipping:
		customer_rate, _courier_cost = get_rates(order.dz_wilaya, order.dz_delivery_type)
		order.dz_shipping_charge = customer_rate

	set_shipping_row(order, flt(order.dz_shipping_charge))


def set_shipping_row(order, amount):
	"""Create, update or remove our line in the "Taxes and Charges" table."""
	account = get_settings().shipping_income_account
	if not account:
		frappe.throw(_("Choisissez le compte des frais de livraison dans les Paramètres COD."))

	row = None
	for tax in order.get("taxes"):
		if tax.account_head == account:
			row = tax

	if amount <= 0:
		# No fee (free delivery): remove our line if it exists
		if row:
			order.remove(row)
		return

	if not row:
		row = order.append(
			"taxes",
			{"charge_type": "Actual", "account_head": account, "description": SHIPPING_DESCRIPTION},
		)
	row.tax_amount = amount
