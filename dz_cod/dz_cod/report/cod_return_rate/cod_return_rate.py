"""Report "Taux de retour (COD)": which products and which wilayas come back.

Only parcels with a known outcome count in the rate:
    return rate = returned / (delivered + returned)
Parcels still on the road ("Expédiée") are shown in a separate column.

Grouping:
- Produit: the product (all sizes and colours together), counted in pieces
- Article: each size/colour variant, counted in pieces
- Wilaya: counted in orders

Small samples: a row needs at least "Minimum de colis" finished orders
(delivered + returned, default 5) to get a rate. Below that its rate stays
empty and it sorts last, so 2 returns out of 2 do not show as "100 %".
"""

import frappe
from frappe import _
from frappe.utils import cint

from dz_cod.cod import states as S

BY_PRODUCT = "Produit"
BY_VARIANT = "Article"
BY_WILAYA = "Wilaya"
DEFAULT_MIN_PARCELS = 5


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.company = filters.company or frappe.db.get_single_value("COD Settings", "company")
	group_by = filters.group_by or BY_PRODUCT
	min_parcels = cint(filters.min_parcels) if filters.min_parcels not in (None, "") else DEFAULT_MIN_PARCELS
	rows = get_rows(filters, group_by, min_parcels)
	return get_columns(group_by), rows, None, get_chart(rows)


def get_columns(group_by):
	unit = _("pièces") if group_by != BY_WILAYA else _("commandes")
	return [
		{"fieldname": "name", "label": _(group_by), "fieldtype": "Data", "width": 220},
		{"fieldname": "label", "label": _("Désignation"), "fieldtype": "Data", "width": 220},
		{
			"fieldname": "delivered",
			"label": _("Livrées ({0})").format(unit),
			"fieldtype": "Float",
			"precision": 0,
			"width": 130,
		},
		{
			"fieldname": "returned",
			"label": _("Retournées ({0})").format(unit),
			"fieldtype": "Float",
			"precision": 0,
			"width": 140,
		},
		{"fieldname": "return_rate", "label": _("Taux de retour"), "fieldtype": "Percent", "width": 120},
		{
			"fieldname": "orders",
			"label": _("Commandes (livrées + retournées)"),
			"fieldtype": "Int",
			"width": 120,
		},
		{
			"fieldname": "in_transit",
			"label": _("En transit ({0})").format(unit),
			"fieldtype": "Float",
			"precision": 0,
			"width": 130,
		},
	]


def get_rows(filters, group_by, min_parcels=DEFAULT_MIN_PARCELS):
	params = {
		"company": filters.company,
		"from_date": filters.from_date,
		"to_date": filters.to_date,
		"states": S.SHIPPED_OR_LATER,
	}
	# Orders that left the warehouse during the period (by shipping date)
	where = """
		so.company = %(company)s
		AND so.docstatus = 1
		AND so.workflow_state IN %(states)s
		AND so.dz_shipped_on BETWEEN %(from_date)s AND %(to_date)s
	"""

	if group_by == BY_WILAYA:
		lines = frappe.db.sql(
			f"""
			SELECT so.dz_wilaya AS name, so.dz_wilaya AS label, so.workflow_state AS state,
				COUNT(*) AS qty, COUNT(*) AS orders
			FROM `tabSales Order` so
			WHERE {where}
			GROUP BY so.dz_wilaya, so.workflow_state
			""",
			params,
			as_dict=True,
		)
	else:
		# Produit groups variants under their template (item.variant_of)
		key = "IFNULL(item.variant_of, soi.item_code)" if group_by == BY_PRODUCT else "soi.item_code"
		lines = frappe.db.sql(
			f"""
			SELECT {key} AS name, so.workflow_state AS state, SUM(soi.qty) AS qty,
				COUNT(DISTINCT so.name) AS orders
			FROM `tabSales Order` so
			JOIN `tabSales Order Item` soi ON soi.parent = so.name
			JOIN `tabItem` item ON item.name = soi.item_code
			WHERE {where}
			GROUP BY {key}, so.workflow_state
			""",
			params,
			as_dict=True,
		)

	rows = {}
	for line in lines:
		row = rows.setdefault(
			line.name, {"name": line.name, "delivered": 0, "returned": 0, "in_transit": 0, "orders": 0}
		)
		if line.state == S.RETURNED:
			row["returned"] += line.qty
			row["orders"] += line.orders
		elif line.state == S.SHIPPED:
			row["in_transit"] += line.qty
		else:  # Livrée or Réglée
			row["delivered"] += line.qty
			row["orders"] += line.orders

	for row in rows.values():
		row["label"] = (
			row["name"] if group_by == BY_WILAYA else frappe.db.get_value("Item", row["name"], "item_name")
		)
		finished = row["delivered"] + row["returned"]
		enough = finished and row["orders"] >= min_parcels
		# None = too few orders to judge: the cell stays empty
		row["return_rate"] = round(100 * row["returned"] / finished, 1) if enough else None

	# Rows with a rate first (worst first), then the small ones; biggest volume first
	return sorted(
		rows.values(),
		key=lambda row: (row["return_rate"] is None, -(row["return_rate"] or 0), -row["orders"]),
	)


def get_chart(rows):
	top = [row for row in rows if row["return_rate"] is not None][:15]
	return {
		"data": {
			"labels": [row["label"] for row in top],
			"datasets": [{"name": _("Taux de retour (%)"), "values": [row["return_rate"] for row in top]}],
		},
		"type": "bar",
	}
