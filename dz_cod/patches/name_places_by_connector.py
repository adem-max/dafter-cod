"""Communes and stop desks imported before October 2026 all came from Yalidine
and were named by Yalidine's id (1630, 163001). They get the connector
Yalidine and the names of every connector's records: Yalidine-1630,
Yalidine-163001.

Nothing links to a commune (the order keeps the commune's name as text), so
communes are renamed in SQL. Orders link to their stop desk: rename_doc
updates those links."""

import frappe

from dz_cod.couriers.places import record_name
from dz_cod.couriers.yalidine import CONNECTOR


def execute():
	for doctype in ("DZ Commune", "DZ Stop Desk"):
		frappe.db.sql(f"UPDATE `tab{doctype}` SET connector = %s WHERE IFNULL(connector, '') = ''", CONNECTOR)
	frappe.db.sql(
		"UPDATE `tabDZ Commune` SET name = CONCAT(connector, '-', courier_id) WHERE name = courier_id"
	)
	for desk in frappe.get_all("DZ Stop Desk", fields=["name", "connector", "center_id"]):
		new = record_name(desk.connector, desk.center_id)
		if desk.name != new:
			frappe.rename_doc(
				"DZ Stop Desk",
				desk.name,
				new,
				force=True,
				show_alert=False,
				rebuild_search=False,
			)
