"""Report "Encours transporteurs (COD)": how much cash each courier still owes us.

"Owed" = orders in state Livrée: the courier collected the cash from the
customer but has not paid us yet (no Versement marked them Réglée).
Each amount is NET: cash to collect minus the courier's expected fee.

"En litige" = a Versement already listed the order but the line was not
accepted (wrong amount, ...): follow it up with the courier.
"Sur la route" = orders still Expédiée: cash that should come later.

Tick "Détail par commande" to see one line per order (to send the list to
the courier, for example).
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, today

from dz_cod.cod import states as S
from dz_cod.cod.settlement import is_paid


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.company = filters.company or frappe.db.get_single_value("COD Settings", "company")
	orders = get_orders(filters)
	if filters.detail:
		return get_detail_columns(), get_detail_rows(orders), None, None, get_summary(orders)
	return get_summary_columns(), get_summary_rows(orders), None, None, get_summary(orders)


def get_orders(filters):
	"""Delivered-not-paid and still-on-the-road orders, with their dispute flag."""
	orders = frappe.db.sql(
		"""
		SELECT name, customer_name, dz_courier AS courier, dz_wilaya AS wilaya, dz_tracking_number,
			workflow_state AS state, dz_shipped_on, dz_delivered_on,
			dz_cod_amount, dz_courier_fee, dz_cod_amount - dz_courier_fee AS net
		FROM `tabSales Order`
		WHERE company = %(company)s
			AND docstatus = 1
			AND workflow_state IN %(states)s
			AND (%(courier)s = '' OR dz_courier = %(courier)s)
		ORDER BY dz_delivered_on, dz_shipped_on
		""",
		{"company": filters.company, "courier": filters.courier or "", "states": [S.DELIVERED, S.SHIPPED]},
		as_dict=True,
	)

	disputes = get_disputes()
	for order in orders:
		order.dispute = disputes.get(order.name)
	return orders


def get_disputes():
	"""{order: settlement} for orders listed in a submitted Versement without being paid."""
	lines = frappe.db.sql(
		"""
		SELECT line.sales_order, line.status, line.accept_difference, settlement.name AS settlement
		FROM `tabCourier Settlement Item` line
		JOIN `tabCourier Settlement` settlement ON settlement.name = line.parent
		WHERE settlement.docstatus = 1 AND line.sales_order IS NOT NULL
		""",
		as_dict=True,
	)
	return {
		line.sales_order: line.settlement
		for line in lines
		if not is_paid(line.status, line.accept_difference)
	}


# ------------------------------------------------------------ summary view


def get_summary_columns():
	return [
		{
			"fieldname": "courier",
			"label": _("Transporteur"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 200,
		},
		{"fieldname": "delivered_count", "label": _("Livrées non réglées"), "fieldtype": "Int", "width": 140},
		{"fieldname": "delivered_net", "label": _("Montant dû (net)"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "disputed_count", "label": _("Dont en litige"), "fieldtype": "Int", "width": 110},
		{"fieldname": "disputed_net", "label": _("Montant en litige"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "oldest", "label": _("Plus ancienne livraison"), "fieldtype": "Date", "width": 150},
		{"fieldname": "oldest_days", "label": _("Jours d'attente"), "fieldtype": "Int", "width": 110},
		{"fieldname": "road_count", "label": _("Sur la route"), "fieldtype": "Int", "width": 100},
		{"fieldname": "road_net", "label": _("Montant sur la route"), "fieldtype": "Currency", "width": 150},
	]


def get_summary_rows(orders):
	rows = {}
	for order in orders:
		row = rows.setdefault(
			order.courier,
			{
				"courier": order.courier,
				"delivered_count": 0,
				"delivered_net": 0,
				"disputed_count": 0,
				"disputed_net": 0,
				"oldest": None,
				"road_count": 0,
				"road_net": 0,
			},
		)
		if order.state == S.SHIPPED:
			row["road_count"] += 1
			row["road_net"] += flt(order.net)
			continue

		row["delivered_count"] += 1
		row["delivered_net"] += flt(order.net)
		if order.dispute:
			row["disputed_count"] += 1
			row["disputed_net"] += flt(order.net)
		if order.dz_delivered_on and (not row["oldest"] or order.dz_delivered_on < row["oldest"]):
			row["oldest"] = order.dz_delivered_on

	for row in rows.values():
		row["oldest_days"] = date_diff(today(), row["oldest"]) if row["oldest"] else 0
	return sorted(rows.values(), key=lambda row: -row["delivered_net"])


# ------------------------------------------------------------- detail view


def get_detail_columns():
	return [
		{
			"fieldname": "name",
			"label": _("Commande"),
			"fieldtype": "Link",
			"options": "Sales Order",
			"width": 170,
		},
		{
			"fieldname": "courier",
			"label": _("Transporteur"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 170,
		},
		{"fieldname": "dz_tracking_number", "label": _("N° de suivi"), "fieldtype": "Data", "width": 190},
		{"fieldname": "customer_name", "label": _("Client"), "fieldtype": "Data", "width": 160},
		{"fieldname": "wilaya", "label": _("Wilaya"), "fieldtype": "Data", "width": 130},
		{"fieldname": "state_label", "label": _("État"), "fieldtype": "Data", "width": 90},
		{"fieldname": "dz_delivered_on", "label": _("Livrée le"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days", "label": _("Jours"), "fieldtype": "Int", "width": 70},
		{"fieldname": "dz_cod_amount", "label": _("À encaisser"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "dz_courier_fee", "label": _("Frais prévus"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "net", "label": _("Net dû"), "fieldtype": "Currency", "width": 120},
		{
			"fieldname": "dispute",
			"label": _("En litige (versement)"),
			"fieldtype": "Link",
			"options": "Courier Settlement",
			"width": 160,
		},
	]


def get_detail_rows(orders):
	for order in orders:
		order.days = date_diff(today(), order.dz_delivered_on or order.dz_shipped_on)
		order.state_label = _(order.state)  # shown in the user's language
	return orders


def get_summary(orders):
	delivered = [o for o in orders if o.state == S.DELIVERED]
	disputed = [o for o in delivered if o.dispute]
	return [
		{
			"label": _("Montant dû (net)"),
			"value": sum(flt(o.net) for o in delivered),
			"datatype": "Currency",
			"indicator": "orange",
		},
		{
			"label": _("Dont en litige"),
			"value": sum(flt(o.net) for o in disputed),
			"datatype": "Currency",
			"indicator": "red",
		},
		{
			"label": _("Sur la route"),
			"value": sum(flt(o.net) for o in orders if o.state == S.SHIPPED),
			"datatype": "Currency",
			"indicator": "blue",
		},
	]
