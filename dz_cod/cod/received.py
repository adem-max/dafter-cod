"""What the Versements already booked for an order: one answer for the three
places that need it (review of 27 October 2026, 4.2).

- the Versement form's "Déjà versé" (net, courier_settlement.py);
- the courier's claim when a Versement is booked (gross, invoicing.py);
- the month close's check of each courier's 4671n account (gross, closing.py).

They used to compute it three ways: net or gross, the order's own courier or
any courier, every line or only booked ones. Counted here: the lines of
submitted Versements of the order's own courier with status OK or Écart, the
only lines booked against the order (the others go to 4781, to identify:
invoicing.make_settlement_entry).
"""

import frappe
from frappe.utils import flt

from dz_cod.cod import settlement as rules

BOOKED = (rules.OK, rules.GAP)


def received(orders, until=None, exclude=None):
	"""{order: frappe._dict(gross=collected, net=collected - fee)} for the
	orders that have any; Versements dated after `until`, and the Versement
	`exclude`, left out."""
	if not orders:
		return {}
	conditions = ""
	if until:
		conditions += " AND cs.posting_date <= %(until)s"
	if exclude:
		conditions += " AND cs.name != %(exclude)s"
	rows = frappe.db.sql(
		f"""SELECT item.sales_order, SUM(item.collected_amount) AS gross, SUM(item.net_amount) AS net
		FROM `tabCourier Settlement Item` item
		JOIN `tabCourier Settlement` cs ON cs.name = item.parent
		JOIN `tabSales Order` so ON so.name = item.sales_order
		WHERE cs.docstatus = 1 AND cs.courier = so.dz_courier AND item.status IN %(booked)s
			AND item.sales_order IN %(orders)s{conditions}
		GROUP BY item.sales_order""",
		{"orders": list(orders), "until": until, "exclude": exclude or "", "booked": BOOKED},
		as_dict=True,
	)
	return {row.sales_order: frappe._dict(gross=flt(row.gross), net=flt(row.net)) for row in rows}
