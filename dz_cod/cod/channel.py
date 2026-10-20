"""Sales channel of an order: COD (sold online, confirmed by phone, shipped by
a courier who collects the cash) or a direct sale (wholesale, shop, an order
the seller delivers: ERPNext's usual delivery note and invoice).

Only COD orders go through this app's checks, delivery fee and life cycle;
a direct sale is validated ("Validée") and then follows ERPNext. A producer
who also sells online gets both on one site (DECISIONS.md, "Sales channel").
"""

import frappe

COD = "COD"
DIRECT = "Vente directe"


def is_cod(order):
	"""An order whose channel is not chosen yet counts as COD (the default)."""
	return order.get("dz_channel") != DIRECT


def default_channel(customer=None):
	"""The customer's usual channel, else the default of COD Settings, else COD."""
	return (
		(customer and frappe.db.get_value("Customer", customer, "dz_channel"))
		or frappe.db.get_single_value("COD Settings", "default_channel")
		or COD
	)
