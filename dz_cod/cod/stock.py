"""Stock movements of a COD order (DECISIONS.md, "COD accounting").

Planning analogy:
- Confirmation = material allocation: ERPNext adds the order quantity to
  "reserved qty" of the item in the warehouse (done by ERPNext itself when the
  Sales Order is submitted). The stock is still on the shelf, but promised.
- Shipment = transfer to a holding location: a Material Transfer moves the
  parcel to the "Chez transporteur" warehouse. Still our stock, not sold:
  with inventory accounts per item the transfer posts nothing.
- Delivery = material issue: the Delivery Note takes the parcel out of
  "Chez transporteur", with the lots the shipment moved, and releases the
  reservation. The sale, its TVA and its cost belong to that day.
- Return before delivery = transfer into a quarantine location: the parcel
  goes from "Chez transporteur" to the RETURNS warehouse, unchecked. No sale
  to undo.
- Inspection = quality decision: good pieces are transferred back to the main
  warehouse, damaged pieces are written off (Material Issue, to the item
  group's expense account: 7245 own products, 6571 resold goods).

Orders shipped before 0.3.0 kept a Delivery Note made at shipment and a
return Delivery Note: their inspection still reads it (dz_return_note).
"""

import frappe
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
from frappe import _
from frappe.utils import flt, today

from dz_cod.cod import states as S
from dz_cod.cod.accounts import in_transit_warehouse
from dz_cod.dz_cod.doctype.cod_settings.cod_settings import get_settings


def set_posting_date(doc, posting_date):
	"""Use a given date instead of today (only the demo loader does this)."""
	if posting_date and str(posting_date) != today():
		doc.set_posting_time = 1
		doc.posting_date = posting_date


def transit_warehouse(company):
	return get_settings().get("in_transit_warehouse") or in_transit_warehouse(company)


def is_stock_item(item_code):
	return frappe.get_cached_value("Item", item_code, "is_stock_item")


def check_available_stock(order):
	"""At confirmation: is there enough free stock (on hand - already reserved)?

	Returns a list of messages, empty if everything is available.
	"""
	needed = {}  # (item, warehouse) -> quantity this order needs
	for row in order.items:
		if is_stock_item(row.item_code):
			key = (row.item_code, row.warehouse)
			needed[key] = needed.get(key, 0) + flt(row.stock_qty)

	problems = []
	transit = transit_warehouse(order.company)
	for (item_code, warehouse), qty in needed.items():
		actual, reserved = frappe.db.get_value(
			"Bin", {"item_code": item_code, "warehouse": warehouse}, ["actual_qty", "reserved_qty"]
		) or (0, 0)
		# A shipped parcel left the shelf but stays reserved here until it is
		# delivered: it is in "Chez transporteur", count it back
		in_transit = flt(
			frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": transit}, "actual_qty")
		)
		available = flt(actual) - flt(reserved) + in_transit
		if available < qty:
			problems.append(_("{0} : besoin {1}, disponible {2}").format(item_code, qty, max(available, 0)))
	return problems


# ------------------------------------------------ shipment, delivery, return


def ship_order(order, posting_date=None):
	"""Expédiée: move the parcel's goods to "Chez transporteur". Returns the
	Stock Entry name (None for an order without stock items)."""
	transit = transit_warehouse(order.company)
	lines = [
		(row.item_code, row.stock_qty, row.warehouse, transit, None)
		for row in order.items
		if is_stock_item(row.item_code)
	]
	if not lines:
		return None
	return make_stock_entry(order, "Material Transfer", lines, posting_date=posting_date)


def shipped_lots(stock_entry, warehouse):
	"""{item_code: [(lot, qty)]} that a stock entry brought into a warehouse."""
	lots = {}
	for item_code, batch_no, qty in frappe.db.sql(
		"""SELECT sle.item_code, sbe.batch_no, SUM(ABS(sbe.qty))
		FROM `tabStock Ledger Entry` sle
		JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = sle.serial_and_batch_bundle
		WHERE sle.voucher_type = 'Stock Entry' AND sle.voucher_no = %s AND sle.warehouse = %s
			AND sle.actual_qty > 0 AND sle.is_cancelled = 0 AND IFNULL(sbe.batch_no, '') != ''
		GROUP BY sle.item_code, sbe.batch_no""",
		(stock_entry, warehouse),
	):
		lots.setdefault(item_code, []).append([batch_no, flt(qty)])
	return lots


def deliver_order(order, posting_date=None):
	"""Livrée: the Delivery Note. For an order shipped through "Chez
	transporteur", out of that warehouse with the lots the shipment moved
	there, so the lot a buyer got is the lot that left. Returns its name."""
	dn = make_delivery_note(order.name)
	set_posting_date(dn, posting_date)
	dn.transporter = order.dz_courier
	dn.lr_no = order.dz_tracking_number
	dn.lr_date = posting_date or today()
	if order.get("dz_shipment_entry"):
		transit = transit_warehouse(order.company)
		for row in dn.items:
			if is_stock_item(row.item_code):
				row.warehouse = transit
		split_rows_by_lot(dn, shipped_lots(order.dz_shipment_entry, transit))
	else:
		let_erpnext_pick_lots(dn)
	# The workflow already checked that the user may mark this order delivered
	dn.flags.ignore_permissions = True
	dn.insert()
	dn.submit()
	return dn.name


def split_rows_by_lot(doc, lots):
	"""One row per lot for a batch-tracked line, taking the lots given (used
	up as rows take them); other lines unchanged. lots = {item: [[lot, qty]]}."""
	rows = []
	for row in doc.items:
		available = lots.get(row.item_code)
		if not available or not frappe.get_cached_value("Item", row.item_code, "has_batch_no"):
			rows.append(row)
			continue
		needed = flt(row.stock_qty)
		factor = flt(row.conversion_factor) or 1
		while needed > 0 and available:
			batch_no, qty = available[0]
			take = min(qty, needed)
			piece = row if take >= needed else frappe.copy_doc(row)
			piece.update(
				{
					"qty": take / factor,
					"stock_qty": take,
					"batch_no": batch_no,
					"use_serial_batch_fields": 1,
					"serial_and_batch_bundle": None,
				}
			)
			rows.append(piece)
			needed -= take
			available[0][1] -= take
			if available[0][1] <= 0:
				available.pop(0)
	doc.set("items", rows)


def return_order(order, posting_date=None):
	"""Retournée (before delivery): the parcel goes from "Chez transporteur" to
	the returns warehouse, with its lots. Returns the Stock Entry name."""
	if not order.get("dz_shipment_entry"):
		frappe.throw(_("La commande {0} n'a pas de mouvement d'expédition.").format(order.name))
	transit = transit_warehouse(order.company)
	returns = get_settings().returns_warehouse
	lots = shipped_lots(order.dz_shipment_entry, transit)
	lines = []
	for row in frappe.get_doc("Stock Entry", order.dz_shipment_entry).items:
		for batch_no, qty in lots.pop(row.item_code, None) or [[None, row.transfer_qty]]:
			lines.append((row.item_code, qty, transit, returns, batch_no))
	return make_stock_entry(order, "Material Transfer", lines, posting_date=posting_date)


def close_order(order_name):
	"""Close the Sales Order so ERPNext never reserves stock for it again."""
	order = frappe.get_doc("Sales Order", order_name)
	if order.status != "Closed":
		order.update_status("Closed")


# ------------------------------------------------------------ inspection


@frappe.whitelist()
def get_returned_items(sales_order):
	"""Items and quantities waiting for inspection, for the inspection dialog."""
	order = frappe.get_doc("Sales Order", sales_order)
	order.check_permission("read")
	if order.get("dz_return_entry"):
		returned = frappe.get_doc("Stock Entry", order.dz_return_entry)
		rows = [(row.item_code, row.item_name, row.transfer_qty) for row in returned.items]
	elif order.dz_return_note:  # shipped before 0.3.0: a return Delivery Note
		ret = frappe.get_doc("Delivery Note", order.dz_return_note)
		rows = [(row.item_code, row.item_name, abs(row.qty)) for row in ret.items]  # negative on a return
	else:
		return []
	totals = {}
	for item_code, item_name, qty in rows:
		line = totals.setdefault(item_code, {"item_code": item_code, "item_name": item_name, "qty": 0})
		line["qty"] += flt(qty)
	return list(totals.values())


@frappe.whitelist()
def inspect_return(sales_order, items, posting_date=None):
	"""Record the inspection of a returned parcel.

	`items` is a list of {"item_code": ..., "good_qty": ..., "damaged_qty": ...}.
	Good pieces go back to the main warehouse, damaged ones are written off.
	"""
	frappe.has_permission("Stock Entry", "create", throw=True)
	items = frappe.parse_json(items)
	# for_update: a second click waits here, then finds dz_return_inspected set
	order = frappe.get_doc("Sales Order", sales_order, for_update=True)

	if order.workflow_state != S.RETURNED:
		frappe.throw(_("La commande {0} n'est pas retournée.").format(order.name))
	if order.dz_return_inspected:
		frappe.throw(_("Le retour de la commande {0} est déjà inspecté.").format(order.name))

	# Every returned piece is either good or damaged, no more, no less. Rows of
	# the same item add up (they used to overwrite each other, and the stock
	# moves then took every row); a negative or non-numeric quantity is refused.
	returned = {}
	for row in get_returned_items(order.name):
		returned[row["item_code"]] = returned.get(row["item_code"], 0) + row["qty"]
	good, damaged = {}, {}
	for row in items:
		for field, totals in (("good_qty", good), ("damaged_qty", damaged)):
			qty = quantity(row.get(field))
			if qty:
				totals[row["item_code"]] = totals.get(row["item_code"], 0) + qty
	declared = {code: good.get(code, 0) + damaged.get(code, 0) for code in {*good, *damaged}}
	if {code: flt(qty) for code, qty in returned.items() if qty} != declared:
		frappe.throw(_("Les quantités inspectées doivent correspondre exactement aux quantités retournées."))

	settings = get_settings()
	if good:
		make_stock_entry(
			order,
			"Material Transfer",
			[
				(code, qty, settings.returns_warehouse, settings.main_warehouse, None)
				for code, qty in good.items()
			],
			posting_date=posting_date,
		)
	if damaged:
		make_stock_entry(
			order,
			"Material Issue",
			[(code, qty, settings.returns_warehouse, None, None) for code, qty in damaged.items()],
			posting_date=posting_date,
		)

	order.db_set("dz_return_inspected", 1)
	order.add_comment(
		"Comment",
		_("Retour inspecté : {0} remis en stock, {1} mis au rebut.").format(
			sum(good.values()), sum(damaged.values())
		),
	)


def quantity(value):
	"""A quantity typed in the inspection dialog: empty is 0; negative or not
	a number is refused (flt() would have read "abc" as 0 silently)."""
	if value in (None, ""):
		return 0
	try:
		qty = float(value)
	except (TypeError, ValueError):
		frappe.throw(_("Quantité invalide : {0}").format(value))
	if qty < 0:
		frappe.throw(_("Une quantité ne peut pas être négative : {0}").format(value))
	return qty


def let_erpnext_pick_lots(doc, keep_given=False):
	"""Lines of batch-tracked items (a food producer selling online): with the
	line's "use serial / batch fields" on, ERPNext 16 fills in ONE lot when the
	document is saved, and refuses a line that one lot cannot cover. Off, its
	own outward bundle (Stock Settings, on by default) takes the lots oldest
	first, as many as the line needs. keep_given: a line whose lot we chose
	(the parcel's own lot) keeps it."""
	for row in doc.items:
		if keep_given and row.get("batch_no"):
			continue
		if frappe.get_cached_value("Item", row.item_code, "has_batch_no"):
			row.batch_no = None
			row.use_serial_batch_fields = 0


def make_stock_entry(order, entry_type, lines, posting_date=None):
	"""Create and submit one Stock Entry linked to the order. lines =
	[(item_code, stock qty, source, target, lot or None)]: a lot given is
	used, otherwise ERPNext picks the lots (oldest first)."""
	entry = frappe.new_doc("Stock Entry")
	entry.stock_entry_type = entry_type
	entry.company = order.company
	entry.dz_sales_order = order.name
	set_posting_date(entry, posting_date)
	for item_code, qty, source, target, batch_no in lines:
		row = entry.append(
			"items",
			{
				"item_code": item_code,
				"qty": qty,
				"uom": frappe.get_cached_value("Item", item_code, "stock_uom"),
				"conversion_factor": 1,
				"s_warehouse": source,
				"t_warehouse": target,
			},
		)
		if batch_no:
			row.update({"batch_no": batch_no, "use_serial_batch_fields": 1})
	let_erpnext_pick_lots(entry, keep_given=True)
	entry.flags.ignore_permissions = True  # the workflow checked who may move the order
	entry.insert()
	entry.submit()
	return entry.name
