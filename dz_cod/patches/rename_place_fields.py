"""DZ Commune's Yalidine fields become courier-neutral (October 2026, the
communes of every connector live side by side): yalidine_id -> courier_id,
yalidine_wilaya_name -> courier_wilaya_name.

Runs before the doctypes are synced: the columns are renamed with their
values, instead of new empty columns next to the old ones. Then
name_places_by_connector gives the records their connector and new names."""

import frappe

RENAMED = {"yalidine_id": "courier_id", "yalidine_wilaya_name": "courier_wilaya_name"}


def execute():
	if not frappe.db.table_exists("DZ Commune"):
		return
	for old, new in RENAMED.items():
		if frappe.db.has_column("DZ Commune", old) and not frappe.db.has_column("DZ Commune", new):
			frappe.db.rename_column("DZ Commune", old, new)
