"""Integration tests: the COD order life cycle on a real ERPNext site.

Run: bench --site <site> run-tests --module dz_cod.tests.test_order_flow
"""

import frappe
from frappe.model.workflow import WorkflowTransitionError, get_transitions
from frappe.tests import IntegrationTestCase

from dz_cod.cod import states as S
from dz_cod.cod.accounts import FEE_ITEM
from dz_cod.cod.stock import check_available_stock, inspect_return
from dz_cod.tests import helpers as h


def fee_lines(order):
	return [row for row in order.items if row.item_code == FEE_ITEM]


class TestShippingRate(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()

	def test_home_delivery_rate_is_added_to_the_total(self):
		order = h.make_order(qty=2)
		self.assertEqual(order.dz_shipping_charge, 400)
		self.assertEqual(order.dz_cod_amount, 2 * h.ITEM_PRICE + 400)
		# the fee is an item line, taxed like the goods (cod/shipping.py)
		lines = fee_lines(order)
		self.assertEqual(len(lines), 1)
		self.assertEqual(lines[0].amount, 400)
		self.assertFalse([t for t in order.taxes if t.charge_type == "Actual"])

	def test_stop_desk_rate(self):
		order = h.make_order(dz_delivery_type="Stop desk")
		self.assertEqual(order.dz_shipping_charge, 250)

	def test_rate_follows_a_change_of_wilaya(self):
		order = h.make_order()
		order.dz_wilaya = "31 - Oran"
		order.save()
		oran_rate = frappe.db.get_value("DZ Wilaya", "31 - Oran", "home_rate")
		self.assertEqual(order.dz_shipping_charge, oran_rate)
		self.assertEqual(len(fee_lines(order)), 1)

	def test_manual_rate_is_kept_and_zero_removes_the_line(self):
		order = h.make_order(dz_manual_shipping=1, dz_shipping_charge=0)
		self.assertEqual(order.dz_shipping_charge, 0)
		self.assertEqual(order.dz_cod_amount, h.ITEM_PRICE)
		self.assertFalse(fee_lines(order))

	def test_wilaya_not_delivered(self):
		frappe.db.set_value("DZ Wilaya", "11 - Tamanrasset", "enabled", 0)
		frappe.clear_document_cache("DZ Wilaya", "11 - Tamanrasset")
		with self.assertRaises(frappe.ValidationError):
			h.make_order(dz_wilaya="11 - Tamanrasset")


class TestConfirmation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()

	def test_confirm_reserves_stock(self):
		reserved_before = h.bin_qty(h.main_warehouse(), "reserved_qty")
		order = h.act(h.make_order(qty=3), S.ACTION_CONFIRM)
		self.assertEqual(order.workflow_state, S.CONFIRMED)
		self.assertEqual(order.docstatus, 1)
		self.assertEqual(h.bin_qty(h.main_warehouse(), "reserved_qty"), reserved_before + 3)
		self.assertEqual(order.dz_courier_fee, 350)  # from the wilaya rate table
		self.assertTrue(order.dz_confirmed_on)

	def test_cannot_confirm_without_valid_phone(self):
		order = h.make_order(dz_phone="12")
		with self.assertRaises(frappe.ValidationError):
			h.act(order, S.ACTION_CONFIRM)

	def test_cannot_confirm_home_delivery_without_address(self):
		# An empty address is re-filled from the customer: use a customer without one
		frappe.db.set_value("Customer", h.CUSTOMER, "dz_address", None)
		order = h.make_order(dz_address="")
		with self.assertRaises(frappe.ValidationError):
			h.act(order, S.ACTION_CONFIRM)

	def test_block_confirmation_when_stock_is_short(self):
		frappe.db.set_single_value("COD Settings", "block_confirmation_without_stock", 1)
		frappe.clear_document_cache("COD Settings", "COD Settings")
		order = h.make_order(qty=h.STOCK_QTY + 50)
		with self.assertRaises(frappe.ValidationError):
			h.act(order, S.ACTION_CONFIRM)
		frappe.db.set_single_value("COD Settings", "block_confirmation_without_stock", 0)
		frappe.clear_document_cache("COD Settings", "COD Settings")

	def test_unanswered_calls_are_counted_and_limited(self):
		order = h.make_order()
		order = h.act(order, S.ACTION_NO_ANSWER, S.ACTION_NO_ANSWER, S.ACTION_NO_ANSWER)
		self.assertEqual(order.workflow_state, S.UNREACHABLE)
		self.assertEqual(order.dz_call_attempts, 3)
		# Maximum reached (3): the button is gone, only Confirmer / Annuler remain
		actions = {t.action for t in get_transitions(order)}
		self.assertNotIn(S.ACTION_NO_ANSWER, actions)
		with self.assertRaises(WorkflowTransitionError):
			h.act(order, S.ACTION_NO_ANSWER)
		self.assertEqual(h.act(order, S.ACTION_CONFIRM).workflow_state, S.CONFIRMED)

	def test_cancel_a_draft_order(self):
		order = h.act(h.make_order(), S.ACTION_CANCEL)
		self.assertEqual(order.workflow_state, S.CANCELLED)
		self.assertEqual(order.docstatus, 0)

	def test_cancel_after_confirmation_releases_stock(self):
		reserved_before = h.bin_qty(h.main_warehouse(), "reserved_qty")
		order = h.act(h.make_order(qty=2), S.ACTION_CONFIRM, S.ACTION_PREPARE, S.ACTION_CANCEL)
		self.assertEqual(order.workflow_state, S.CANCELLED_AFTER_CONFIRMATION)
		self.assertEqual(order.docstatus, 2)
		self.assertEqual(h.bin_qty(h.main_warehouse(), "reserved_qty"), reserved_before)

	def test_illegal_jump_is_refused(self):
		order = h.make_order()
		with self.assertRaises(WorkflowTransitionError):
			h.act(order, S.ACTION_SHIP)  # cannot ship an order nobody confirmed


class TestShipmentAndReturn(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()

	def ship(self, qty=1, courier=h.MOCK_COURIER):
		order = h.make_order(qty=qty, courier=courier)
		return h.act(order, S.ACTION_CONFIRM, S.ACTION_PREPARE, S.ACTION_SHIP)

	def test_ship_moves_the_parcel_to_the_courier_then_delivery_takes_it_out(self):
		stock_before = h.bin_qty(h.main_warehouse())
		reserved_before = h.bin_qty(h.main_warehouse(), "reserved_qty")
		transit_before = h.bin_qty(h.transit_warehouse())
		order = self.ship(qty=2)

		self.assertEqual(order.workflow_state, S.SHIPPED)
		self.assertEqual(order.dz_tracking_number, f"MOCK-{order.name}")  # given by the mock courier
		# still our stock, at the courier, still reserved: not sold yet
		self.assertEqual(frappe.db.get_value("Stock Entry", order.dz_shipment_entry, "docstatus"), 1)
		self.assertFalse(order.dz_delivery_note)
		self.assertEqual(h.bin_qty(h.main_warehouse()), stock_before - 2)
		self.assertEqual(h.bin_qty(h.transit_warehouse()), transit_before + 2)
		self.assertEqual(h.bin_qty(h.main_warehouse(), "reserved_qty"), reserved_before + 2)

		order = h.act(order, S.ACTION_DELIVER)
		dn = frappe.get_doc("Delivery Note", order.dz_delivery_note)
		self.assertEqual(dn.docstatus, 1)
		self.assertEqual(dn.transporter, h.MOCK_COURIER)
		self.assertEqual(dn.lr_no, order.dz_tracking_number)
		self.assertEqual(
			{row.warehouse for row in dn.items if row.item_code == h.ITEM}, {h.transit_warehouse()}
		)
		self.assertEqual(h.bin_qty(h.transit_warehouse()), transit_before)
		self.assertEqual(h.bin_qty(h.main_warehouse(), "reserved_qty"), reserved_before)

	def test_parcels_at_the_courier_still_count_as_available(self):
		h.set_stock(h.STOCK_QTY)
		stock = h.bin_qty(h.main_warehouse()) - h.bin_qty(h.main_warehouse(), "reserved_qty")
		self.ship(qty=2)  # off the shelf, still reserved until delivered
		order = h.make_order(qty=stock - 2)
		self.assertEqual(check_available_stock(order), [])

	def test_manual_courier_needs_a_tracking_number(self):
		order = h.make_order(courier=h.MANUAL_COURIER)
		order = h.act(order, S.ACTION_CONFIRM, S.ACTION_PREPARE)
		with self.assertRaises(frappe.ValidationError):
			h.act(order, S.ACTION_SHIP)

		frappe.db.set_value("Sales Order", order.name, "dz_tracking_number", "YAL-123456")
		order = h.act(order, S.ACTION_SHIP)
		self.assertEqual(order.workflow_state, S.SHIPPED)

	def test_delivery_sets_the_date(self):
		order = h.act(self.ship(), S.ACTION_DELIVER)
		self.assertEqual(order.workflow_state, S.DELIVERED)
		self.assertTrue(order.dz_delivered_on)

	def test_return_goes_to_returns_warehouse_then_inspection(self):
		returns_before = h.bin_qty(h.returns_warehouse())
		main_before = h.bin_qty(h.main_warehouse())
		order = h.act(self.ship(qty=3), S.ACTION_RETURN)

		self.assertEqual(order.workflow_state, S.RETURNED)
		self.assertEqual(order.status, "Closed")  # never reserves stock again
		self.assertEqual(h.bin_qty(h.returns_warehouse()), returns_before + 3)
		self.assertEqual(h.bin_qty(h.main_warehouse()), main_before - 3)
		self.assertEqual(frappe.db.get_value("Stock Entry", order.dz_return_entry, "docstatus"), 1)
		self.assertFalse(order.dz_delivery_note)  # never sold: nothing to reverse

		# Wrong total (2 instead of 3 pieces) is refused
		with self.assertRaises(frappe.ValidationError):
			inspect_return(order.name, [{"item_code": h.ITEM, "good_qty": 2, "damaged_qty": 0}])

		inspect_return(order.name, [{"item_code": h.ITEM, "good_qty": 2, "damaged_qty": 1}])
		self.assertEqual(h.bin_qty(h.returns_warehouse()), returns_before)  # returns shelf emptied
		self.assertEqual(h.bin_qty(h.main_warehouse()), main_before - 1)  # 2 back, 1 written off
		self.assertTrue(frappe.db.get_value("Sales Order", order.name, "dz_return_inspected"))

		# A second inspection of the same parcel is refused
		with self.assertRaises(frappe.ValidationError):
			inspect_return(order.name, [{"item_code": h.ITEM, "good_qty": 3, "damaged_qty": 0}])

	def test_inspection_adds_up_rows_and_refuses_bad_quantities(self):
		"""Review of 27 October 2026, 2.1: rows of one item overwrote each other
		(two rows of 3 passed for a parcel of 3, then moved 6), and a negative
		or unreadable quantity got through."""
		order = h.act(self.ship(qty=3), S.ACTION_RETURN)
		returns_before = h.bin_qty(h.returns_warehouse())
		for items in (
			[{"item_code": h.ITEM, "good_qty": 3}, {"item_code": h.ITEM, "good_qty": 3}],
			[{"item_code": h.ITEM, "good_qty": 5, "damaged_qty": -2}],
			[{"item_code": h.ITEM, "good_qty": "abc", "damaged_qty": 3}],
		):
			with self.subTest(items=items), self.assertRaises(frappe.ValidationError):
				inspect_return(order.name, items)
		self.assertEqual(h.bin_qty(h.returns_warehouse()), returns_before)

		# two rows of the same item, adding up to the parcel, are fine
		inspect_return(
			order.name,
			[{"item_code": h.ITEM, "good_qty": 1}, {"item_code": h.ITEM, "good_qty": 1, "damaged_qty": 1}],
		)
		self.assertEqual(h.bin_qty(h.returns_warehouse()), returns_before - 3)
