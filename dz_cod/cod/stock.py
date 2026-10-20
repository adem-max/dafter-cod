"""Stock movements of a COD order.

Planning analogy:
- Confirmation = material allocation: ERPNext adds the order quantity to
  "reserved qty" of the item in the warehouse (done by ERPNext itself when the
  Sales Order is submitted). The stock is still on the shelf, but promised.
- Shipment = material issue: a Delivery Note takes the stock out of the main
  warehouse and releases the reservation.
- Return = receipt into a quarantine location: a return Delivery Note brings
  the parcel back into the RETURNS warehouse (not the main one), because
  nobody has checked it yet.
- Inspection = quality decision: good pieces are transferred back to the main
  warehouse, damaged pieces are written off (Material Issue).
"""

import frappe
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_return
from frappe import _
from frappe.utils import flt, today

from dz_cod.cod import states as S
from dz_cod.dz_cod.doctype.cod_settings.cod_settings import get_settings


def set_posting_date(doc, posting_date):
	"""Use a given date instead of today (only the demo loader does this)."""
	if posting_date and str(posting_date) != today():
		doc.set_posting_time = 1
		doc.posting_date = posting_date


def check_available_stock(order):
	"""At confirmation: is there enough free stock (on hand - already reserved)?

	Returns a list of messages, empty if everything is available.
	"""
	needed = {}  # (item, warehouse) -> quantity this order needs
	for row in order.items:
		if frappe.get_cached_value("Item", row.item_code, "is_stock_item"):
			key = (row.item_code, row.warehouse)
			needed[key] = needed.get(key, 0) + flt(row.stock_qty)

	problems = []
	for (item_code, warehouse), qty in needed.items():
		actual, reserved = frappe.db.get_value(
			"Bin", {"item_code": item_code, "warehouse": warehouse}, ["actual_qty", "reserved_qty"]
		) or (0, 0)
		available = flt(actual) - flt(reserved)
		if available < qty:
			problems.append(_("{0} : besoin {1}, disponible {2}").format(item_code, qty, max(available, 0)))
	return problems


def create_delivery_note(order, posting_date=None):
	"""Shipment: create and submit the Delivery Note for the whole order."""
	dn = make_delivery_note(order.name)
	set_posting_date(dn, posting_date)
	dn.transporter = order.dz_courier
	dn.lr_no = order.dz_tracking_number
	dn.lr_date = posting_date or today()
	let_erpnext_pick_lots(dn)
	# The workflow already checked that the user may ship this order
	dn.flags.ignore_permissions = True
	dn.insert()
	dn.submit()
	return dn.name


def let_erpnext_pick_lots(doc):
	"""Lines of batch-tracked items (a food producer selling online): with the
	line's "use serial / batch fields" on, ERPNext 16 fills in ONE lot when the
	document is saved, and refuses a line that one lot cannot cover. Off, its
	own outward bundle (Stock Settings, on by default) takes the lots oldest
	first, as many as the line needs."""
	for row in doc.items:
		if frappe.get_cached_value("Item", row.item_code, "has_batch_no"):
			row.batch_no = None
			row.use_serial_batch_fields = 0


def create_return(order, posting_date=None):
	"""Return: bring the whole parcel back into the returns warehouse."""
	if not order.dz_delivery_note:
		frappe.throw(_("Pas de bon de livraison pour la commande {0}.").format(order.name))

	returns_warehouse = get_settings().returns_warehouse
	ret = make_sales_return(order.dz_delivery_note)
	set_posting_date(ret, posting_date)
	for row in ret.items:
		row.warehouse = returns_warehouse
	ret.flags.ignore_permissions = True
	ret.insert()
	ret.submit()
	return ret.name


def close_order(order_name):
	"""Close the Sales Order so ERPNext never reserves stock for it again."""
	order = frappe.get_doc("Sales Order", order_name)
	if order.status != "Closed":
		order.update_status("Closed")


@frappe.whitelist()
def get_returned_items(sales_order):
	"""Items and quantities waiting for inspection, for the inspection dialog."""
	order = frappe.get_doc("Sales Order", sales_order)
	order.check_permission("read")
	if not order.dz_return_note:
		return []
	ret = frappe.get_doc("Delivery Note", order.dz_return_note)
	# Return notes have negative quantities: turn them positive
	return [
		{"item_code": row.item_code, "item_name": row.item_name, "qty": abs(row.qty)} for row in ret.items
	]


@frappe.whitelist()
def inspect_return(sales_order, items, posting_date=None):
	"""Record the inspection of a returned parcel.

	`items` is a list of {"item_code": ..., "good_qty": ..., "damaged_qty": ...}.
	Good pieces go back to the main warehouse, damaged ones are written off.
	"""
	frappe.has_permission("Stock Entry", "create", throw=True)
	items = frappe.parse_json(items)
	order = frappe.get_doc("Sales Order", sales_order)

	if order.workflow_state != S.RETURNED:
		frappe.throw(_("La commande {0} n'est pas retournée.").format(order.name))
	if order.dz_return_inspected:
		frappe.throw(_("Le retour de la commande {0} est déjà inspecté.").format(order.name))

	# Check that every returned piece is either good or damaged, no more, no less
	returned = {}
	for row in get_returned_items(order.name):
		returned[row["item_code"]] = returned.get(row["item_code"], 0) + row["qty"]
	declared = {}
	for row in items:
		declared[row["item_code"]] = flt(row.get("good_qty")) + flt(row.get("damaged_qty"))
	if returned != declared:
		frappe.throw(_("Les quantités inspectées doivent correspondre exactement aux quantités retournées."))

	settings = get_settings()
	good = [row for row in items if flt(row.get("good_qty")) > 0]
	damaged = [row for row in items if flt(row.get("damaged_qty")) > 0]

	if good:
		make_stock_entry(
			order,
			"Material Transfer",
			[(row["item_code"], row["good_qty"]) for row in good],
			source=settings.returns_warehouse,
			target=settings.main_warehouse,
			posting_date=posting_date,
		)
	if damaged:
		make_stock_entry(
			order,
			"Material Issue",
			[(row["item_code"], row["damaged_qty"]) for row in damaged],
			source=settings.returns_warehouse,
			target=None,
			posting_date=posting_date,
		)

	order.db_set("dz_return_inspected", 1)
	order.add_comment(
		"Comment",
		_("Retour inspecté : {0} remis en stock, {1} mis au rebut.").format(
			sum(flt(r.get("good_qty")) for r in items), sum(flt(r.get("damaged_qty")) for r in items)
		),
	)


def make_stock_entry(order, entry_type, lines, source, target, posting_date=None):
	"""Create and submit one Stock Entry linked to the order."""
	entry = frappe.new_doc("Stock Entry")
	entry.stock_entry_type = entry_type
	entry.company = order.company
	entry.dz_sales_order = order.name
	set_posting_date(entry, posting_date)
	for item_code, qty in lines:
		entry.append(
			"items", {"item_code": item_code, "qty": qty, "s_warehouse": source, "t_warehouse": target}
		)
	let_erpnext_pick_lots(entry)
	entry.insert()
	entry.submit()
	return entry.name
