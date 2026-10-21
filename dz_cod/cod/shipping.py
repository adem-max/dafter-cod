"""Shipping charges: look up the rate table and add the fee to the order.

The rate table is the list of wilayas (doctype "DZ Wilaya", from dz_core): this
app gives each wilaya a home-delivery rate and a stop-desk rate, plus what the
courier keeps (custom fields, setup/custom_fields.py).

The fee is an item line on the order (FEE_ITEM, a non-stock service item,
cod/accounts.py), taxed by the order's tax template like the goods: a fee
re-billed for a third-party courier stays in the TVA base (CTCA art. 15, SCF
advice of 21 October 2026), so 19 % on the régime réel and nothing on IFU.
Its group credits 7088. Until 0.3.0 it was a charge row after the TVA in
"Taxes and Charges": a draft saved again loses that row and gets the line.
"""

import frappe
from frappe import _
from frappe.utils import flt, today

from dz_cod.cod.accounts import FEE_ITEM, FEE_ITEM_NAME, ensure_fee_item

SHIPPING_DESCRIPTION = "Frais de livraison"  # the charge row of orders made before 0.3.0
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
	"""Set the delivery fee on a draft order and put it on its fee line."""
	if not order.dz_manual_shipping:
		customer_rate, _courier_cost = get_rates(order.dz_wilaya, order.dz_delivery_type)
		order.dz_shipping_charge = customer_rate
	remove_legacy_row(order)
	set_fee_line(order, flt(order.dz_shipping_charge))


def remove_shipping_row(order):
	"""A direct sale has no COD delivery fee: drop the line this app added while
	the draft was a COD order."""
	remove_legacy_row(order)
	set_fee_line(order, 0)
	order.dz_shipping_charge = 0


def remove_legacy_row(order):
	"""The charge row of a draft made before 0.3.0 (a fee typed by hand has its own wording)."""
	for tax in list(order.get("taxes")):
		if tax.charge_type == "Actual" and tax.description == SHIPPING_DESCRIPTION:
			order.remove(tax)


def fee_lines(order):
	return [row for row in order.get("items") if row.item_code == FEE_ITEM]


def set_fee_line(order, amount):
	"""Create, update or remove the fee line (one per order)."""
	lines = fee_lines(order)
	if amount <= 0:
		# No fee (free delivery): remove our line if it exists
		for row in lines:
			order.remove(row)
		return
	if not lines:
		ensure_fee_item(order.company)
		lines = [order.append("items", {"item_code": FEE_ITEM})]
	for extra in lines[1:]:
		order.remove(extra)
	lines[0].update(
		{
			"item_name": FEE_ITEM_NAME,
			"qty": 1,
			"uom": "Nos",
			"stock_uom": "Nos",
			"conversion_factor": 1,
			"price_list_rate": amount,
			"rate": amount,
			"delivery_date": order.delivery_date or today(),
		}
	)
