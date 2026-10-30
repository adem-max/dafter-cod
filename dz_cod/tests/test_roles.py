"""Each role moves the orders of its own steps, with its own roles only
(dz_cod/cod/permissions.py; review of 27 October 2026, 1.2).

Run: bench --site <site> run-tests --module dz_cod.tests.test_roles
"""

import json

import frappe
from dz_core.tests.helpers import user_with_roles
from frappe.tests import IntegrationTestCase

from dz_cod.cod import states as S
from dz_cod.cod.permissions import grant_write
from dz_cod.tests import helpers as h
from dz_cod.tests.test_settlement import new_settlement, short_line


class TestRoles(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		grant_write()
		h.set_stock(h.STOCK_QTY)
		cls.stock_user = user_with_roles("Stock User")
		cls.accounts_user = user_with_roles("Accounts User")
		cls.sales_user = user_with_roles("Sales User")

	def test_a_stock_user_prepares_ships_and_delivers(self):
		order = h.act(h.make_order(), S.ACTION_CONFIRM)
		with self.set_user(self.stock_user):
			order = h.act(order, S.ACTION_PREPARE, S.ACTION_SHIP, S.ACTION_DELIVER)
		self.assertEqual(order.workflow_state, S.DELIVERED)
		# the invoice and its payment are made, in the name of who marked it delivered
		self.assertEqual(frappe.db.get_value("Sales Invoice", order.dz_sales_invoice, "docstatus"), 1)
		self.assertEqual(frappe.db.get_value("Payment Entry", order.dz_payment_entry, "owner"), self.stock_user)

	def test_an_accounts_user_settles_with_a_versement(self):
		order = h.act(h.make_order(), S.ACTION_CONFIRM, S.ACTION_PREPARE, S.ACTION_SHIP, S.ACTION_DELIVER)
		with self.set_user(self.accounts_user):
			new_settlement([short_line(order, short=0)]).submit()
		self.assertEqual(frappe.db.get_value("Sales Order", order.name, "workflow_state"), S.SETTLED)

	def test_a_stock_user_cannot_submit_a_draft(self):
		order = h.make_order()
		with self.set_user(self.stock_user), self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Sales Order", order.name).submit()

	def test_a_stock_user_cannot_edit_a_draft(self):
		order = h.make_order()
		with self.set_user(self.stock_user), self.assertRaises(frappe.PermissionError):
			order = frappe.get_doc("Sales Order", order.name)
			order.items[0].qty = 5
			order.save()

	def test_a_stock_user_cannot_change_the_lines_of_a_confirmed_order(self):
		"""ERPNext's "Update Items" saves the order: the lines stay the sales team's."""
		from erpnext.controllers.accounts_controller import update_child_qty_rate

		order = h.act(h.make_order(), S.ACTION_CONFIRM)
		row = order.items[0]
		items = [
			{
				"docname": row.name,
				"item_code": row.item_code,
				"qty": 3,
				"rate": row.rate,
				"conversion_factor": row.conversion_factor,
				"delivery_date": str(row.delivery_date),
			}
		]
		with self.set_user(self.stock_user), self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
			update_child_qty_rate("Sales Order", json.dumps(items), order.name)
		# (a request that fails is rolled back as a whole; a test is not, so no DB check here)

	def test_a_sales_user_cannot_mark_an_order_settled(self):
		order = h.act(h.make_order(), S.ACTION_CONFIRM, S.ACTION_PREPARE, S.ACTION_SHIP, S.ACTION_DELIVER)
		with self.set_user(self.sales_user), self.assertRaises(frappe.ValidationError):
			h.act(order, S.ACTION_SETTLE)
