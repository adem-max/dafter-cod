"""COD orders of batch-tracked products (a food or cosmetics producer who
also sells online): a line that needs more than one lot ships, comes back
into Retours with its lots, and goes back to stock after the inspection.

Run: bench --site <site> run-tests --module dz_cod.tests.test_lots
"""

import frappe
from erpnext.stock.doctype.batch.batch import get_batch_qty
from frappe.tests import IntegrationTestCase
from frappe.utils import random_string

from dz_cod.cod import states as S
from dz_cod.cod.stock import inspect_return
from dz_cod.tests import helpers as h

PER_LOT = 3


def lots_of(doctype, name):
	"""{lot: qty} that a submitted stock document moved."""
	moved = {}
	for entry in frappe.get_all(
		"Serial and Batch Entry",
		filters={"parent": ["in", bundles(doctype, name)]},
		fields=["batch_no", "qty"],
	):
		moved[entry.batch_no] = moved.get(entry.batch_no, 0) + abs(entry.qty)
	return moved


def bundles(doctype, name):
	child = {"Delivery Note": "Delivery Note Item", "Stock Entry": "Stock Entry Detail"}[doctype]
	return frappe.get_all(
		child,
		filters={"parent": name, "serial_and_batch_bundle": ["is", "set"]},
		pluck="serial_and_batch_bundle",
	)


class TestLots(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()
		frappe.db.set_single_value("Stock Settings", "enable_serial_and_batch_no_for_item", 1)
		tag = random_string(5).upper()
		cls.item = f"DZ-TEST-MIEL-{tag}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": cls.item,
				"item_name": "Miel de test",
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}),
				"stock_uom": "Pièce",
				"is_stock_item": 1,
				"has_batch_no": 1,
				"valuation_rate": 500,
			}
		).insert()
		cls.lots = [f"LOT-A-{tag}", f"LOT-B-{tag}"]
		receipt = frappe.new_doc("Stock Entry")
		receipt.update({"stock_entry_type": "Material Receipt", "company": h.D.COMPANY})
		for lot in cls.lots:
			frappe.get_doc({"doctype": "Batch", "batch_id": lot, "item": cls.item}).insert()
			receipt.append(
				"items",
				{
					"item_code": cls.item,
					"qty": PER_LOT,
					"basic_rate": 500,
					"t_warehouse": h.main_warehouse(),
					"use_serial_batch_fields": 1,
					"batch_no": lot,
				},
			)
		receipt.insert()
		receipt.submit()

	def order(self, qty):
		"""A COD order of the batch-tracked item, shipped."""
		order = h.make_order(qty=qty, item=self.item)
		return h.act(order, S.ACTION_CONFIRM, S.ACTION_PREPARE, S.ACTION_SHIP)

	def test_a_line_takes_several_lots_and_comes_back_with_them(self):
		order = self.order(PER_LOT + 2)  # more than one lot holds
		shipped = lots_of("Delivery Note", order.dz_delivery_note)
		self.assertEqual(sum(shipped.values()), PER_LOT + 2)
		self.assertEqual(set(shipped), set(self.lots))

		order = h.act(order, S.ACTION_RETURN)
		self.assertEqual(lots_of("Delivery Note", order.dz_return_note), shipped)
		for lot, qty in shipped.items():
			self.assertEqual(get_batch_qty(lot, h.returns_warehouse()), qty)

		inspect_return(order.name, [{"item_code": self.item, "good_qty": PER_LOT + 1, "damaged_qty": 1}])
		self.assertEqual(sum(get_batch_qty(lot, h.returns_warehouse()) for lot in self.lots), 0)
		self.assertEqual(sum(get_batch_qty(lot, h.main_warehouse()) for lot in self.lots), 2 * PER_LOT - 1)
