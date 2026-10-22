"""Report "Commandes par jour (COD)": how many orders per day, in each state.

One row per order date, one column per workflow state. Read a row as:
"of the orders taken that day, how many are now in each state".
COD orders only: direct sales (cod/channel.py) are left out.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from dz_cod.cod import states as S
from dz_cod.cod.channel import DIRECT


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.company = filters.company or frappe.db.get_single_value("COD Settings", "company")
	columns = get_columns()
	rows = get_rows(filters)
	return columns, rows, None, get_chart(rows), get_summary(rows)


def get_columns():
	columns = [{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 110}]
	for state in S.ALL_STATES:
		columns.append({"fieldname": scrub(state), "label": _(state), "fieldtype": "Int", "width": 95})
	columns += [
		{"fieldname": "total", "label": _("Total"), "fieldtype": "Int", "width": 80},
		{"fieldname": "amount", "label": _("Montant (hors annulées)"), "fieldtype": "Currency", "width": 140},
	]
	return columns


def scrub(state):
	"""Column name for a state: "Nouvelle" -> "state_0", "Injoignable" -> "state_1"...
	(plain names: accents and spaces are not welcome in column names)"""
	return f"state_{S.ALL_STATES.index(state)}"


def get_rows(filters):
	# Plain SQL: count the orders per day and state
	counts = frappe.db.sql(
		"""
		SELECT transaction_date AS date, workflow_state AS state,
			COUNT(*) AS count, SUM(dz_cod_amount) AS amount
		FROM `tabSales Order`
		WHERE company = %(company)s
			AND transaction_date BETWEEN %(from_date)s AND %(to_date)s
			AND workflow_state IN %(states)s
			AND IFNULL(dz_channel, '') != %(direct)s
			AND (%(courier)s = '' OR dz_courier = %(courier)s)
		GROUP BY transaction_date, workflow_state
		ORDER BY transaction_date DESC
		""",
		{
			"company": filters.company,
			"from_date": filters.from_date,
			"to_date": filters.to_date,
			"courier": filters.courier or "",
			"states": S.ALL_STATES,
			"direct": DIRECT,
		},
		as_dict=True,
	)

	cancelled = (S.CANCELLED, S.CANCELLED_AFTER_CONFIRMATION)
	rows = {}  # date -> row
	for line in counts:
		row = rows.setdefault(line.date, {"date": line.date, "total": 0, "amount": 0})
		row[scrub(line.state)] = line.count
		row["total"] += line.count
		if line.state not in cancelled:
			row["amount"] += flt(line.amount)
	return sorted(rows.values(), key=lambda row: getdate(row["date"]), reverse=True)


def get_chart(rows):
	"""Stacked bars: one bar per day, one colour per state."""
	rows = sorted(rows, key=lambda row: getdate(row["date"]))
	return {
		"data": {
			"labels": [str(row["date"]) for row in rows],
			"datasets": [
				{"name": _(state), "values": [row.get(scrub(state), 0) for row in rows]}
				for state in S.ALL_STATES
			],
		},
		"type": "bar",
		"barOptions": {"stacked": 1},
	}


def get_summary(rows):
	def total(*states):
		return sum(row.get(scrub(state), 0) for row in rows for state in states)

	all_orders = sum(row["total"] for row in rows)
	confirmed = total(
		S.CONFIRMED, S.PREPARED, S.SHIPPED, S.DELIVERED, S.SETTLED, S.RETURNED, S.CANCELLED_AFTER_CONFIRMATION
	)
	cancelled = total(S.CANCELLED, S.CANCELLED_AFTER_CONFIRMATION)
	return [
		{"label": _("Commandes"), "value": all_orders, "datatype": "Int", "indicator": "blue"},
		{
			"label": _("Taux de confirmation"),
			"value": percent(confirmed, all_orders),
			"datatype": "Percent",
			"indicator": "green",
		},
		{
			"label": _("Taux d'annulation"),
			"value": percent(cancelled, all_orders),
			"datatype": "Percent",
			"indicator": "red",
		},
	]


def percent(part, whole):
	return round(100 * part / whole, 1) if whole else 0
