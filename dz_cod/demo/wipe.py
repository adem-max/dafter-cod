"""Wipe the demo data so the loader can start again from a clean shop.

    bench --site demo.localhost execute dz_cod.demo.wipe.run
    bench --site demo.localhost execute dz_cod.demo.loader.load

It cancels and deletes every transaction of the demo company (settlements
and their Journal Entries, the couriers' collections, invoices, stock
entries, delivery notes, orders),
then the demo customers, couriers and items. The company, its warehouses and
accounts and the COD Settings are kept (the loader reuses them).

Even simpler, for a total reset, drop the demo site and create it again
(see docs/DEMO.md).

`full=1` also deletes the ledger lines of what it removes (dz_core's
ledger_lines_deleted), then applies dz_core's SCF set-up again: a shop demo
built before 0.3.0 moves to inventory accounts per item and the full chart
changes without dropping the site.

Refuses to run if the site contains orders of another company.
"""

import frappe
from dz_core.demo.loader import demo_accounting
from dz_core.demo.wipe import BATCH, commit_when_workers_keep_up, forget_books, ledger_lines_deleted

from dz_cod.demo import data as D
from dz_cod.demo.loader import check_site_is_for_demo


def run(full=0):
	check_site_is_for_demo()
	with ledger_lines_deleted(int(full)):
		remove_everything()
	forget_books(D.COMPANY)  # the wiped story's audit trail and archives
	if int(full):
		for line in demo_accounting(D.COMPANY, None):
			print(f"   {line}")
		frappe.db.commit()
	print("Démo effacée. Relancez : bench --site <site> execute dz_cod.demo.loader.load")


def remove_everything():
	company = {"company": D.COMPANY}

	print("Versements et leurs écritures...")
	entries = frappe.get_all(
		"Courier Settlement", filters=dict(company, journal_entry=["is", "set"]), pluck="journal_entry"
	)
	remove("Courier Settlement", company)  # cancelling a Versement cancels its Journal Entry
	remove("Journal Entry", {"name": ["in", entries]})

	print("Encaissements des transporteurs...")
	remove("Payment Entry", company)  # each paid a delivered order's invoice into 4671n

	print("Factures des commandes livrées...")
	remove("Sales Invoice", company)

	print("Expéditions, livraisons, retours et inspections...")
	# Returned orders are "Closed": ERPNext refuses to touch their delivery notes until reopened
	for name in frappe.get_all("Sales Order", filters=dict(company, status="Closed"), pluck="name"):
		frappe.get_doc("Sales Order", name).update_status("Draft")
	# A parcel's stock moves through two doctypes (shipment, delivery note,
	# return, inspection): undone latest first, so no cancel leaves a later
	# move short of stock "Chez transporteur"
	moves = [
		(move.posting_date, move.posting_time, move.creation, doctype, move.name)
		for doctype, filters in (
			("Stock Entry", dict(company, dz_sales_order=["is", "set"])),
			("Delivery Note", company),
		)
		for move in frappe.get_all(
			doctype, filters=filters, fields=["name", "posting_date", "posting_time", "creation"]
		)
	]
	remove_documents([(doctype, name) for *_when, doctype, name in sorted(moves, reverse=True)])

	print("Commandes...")
	remove("Sales Order", company)

	print("Stock d'ouverture...")
	remove("Stock Entry", company)
	frappe.db.delete("Repost Item Valuation", company)

	print("Clients, transporteurs, articles...")
	for name in frappe.get_all("Customer", filters={"customer_group": D.CUSTOMER_GROUP}, pluck="name"):
		frappe.delete_doc("Customer", name, force=True)
	frappe.db.set_single_value("COD Settings", "default_courier", None)
	for courier in D.COURIERS:
		if frappe.db.exists("Supplier", courier):
			frappe.delete_doc("Supplier", courier, force=True)
	brand_items = {"brand": ["in", D.BRANDS]}
	frappe.db.delete(
		"Item Price", {"item_code": ["in", frappe.get_all("Item", filters=brand_items, pluck="name")]}
	)
	# Variants first, then templates (a template cannot go while it has variants)
	for has_variants in (0, 1):
		for filters in (
			dict(brand_items, has_variants=has_variants),
			{"item_code": ["like", "BLANK%"], "has_variants": has_variants},
		):
			for name in frappe.get_all("Item", filters=filters, pluck="name"):
				frappe.delete_doc("Item", name, force=True)

	frappe.db.commit()


def remove(doctype, filters):
	"""Cancel (if submitted) then delete every document matching the filters,
	newest first so stock is always given back in the reverse order it moved."""
	names = frappe.get_all(doctype, filters=filters, pluck="name", order_by="creation desc")
	remove_documents([(doctype, name) for name in names])


def remove_documents(documents):
	"""Cancel (if submitted) then delete the (doctype, name) documents, in this order."""
	for doctype, name in documents:
		doc = frappe.get_doc(doctype, name)
		if doc.docstatus == 1:
			doc.flags.ignore_links = True
			doc.cancel()
	for count, (doctype, name) in enumerate(documents, 1):
		frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		if count % BATCH == 0:
			commit_when_workers_keep_up()  # Frappe's clean-up jobs, 1,000 at most
	commit_when_workers_keep_up()
