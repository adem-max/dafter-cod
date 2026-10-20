"""Direct sales next to COD orders (dz_cod/cod/channel.py): a producer who
also sells online takes wholesale orders on the same site. They skip the COD
checks, delivery fee and life cycle: Nouvelle -> Valider -> Validée, then
ERPNext's own delivery note and invoice.

Run: bench --site <site> run-tests --module dz_cod.tests.test_channel
"""

import json
from unittest.mock import patch

import frappe
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
from frappe.model.workflow import get_transitions
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from dz_cod.cod import states as S
from dz_cod.cod.channel import COD, DIRECT
from dz_cod.cod.shipping import SHIPPING_DESCRIPTION
from dz_cod.dz_cod.report.cod_daily_orders import cod_daily_orders
from dz_cod.patches import set_channel_on_existing_orders
from dz_cod.tests import helpers as h

WHOLESALER = "Grossiste Test (vente directe)"


def direct_order():
	"""A draft order of a customer whose usual channel is the direct sale:
	no phone, wilaya or address."""
	order = frappe.new_doc("Sales Order")
	order.update(
		{
			"company": h.D.COMPANY,
			"customer": WHOLESALER,
			"transaction_date": today(),
			"delivery_date": today(),
		}
	)
	order.append("items", {"item_code": h.ITEM, "qty": 2, "rate": h.ITEM_PRICE, "delivery_date": today()})
	order.insert()
	return order


def fee_lines(order):
	return [tax for tax in order.get("taxes") if tax.description == SHIPPING_DESCRIPTION]


def actions(order):
	return {transition.action for transition in get_transitions(order)}


class TestDirectSale(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()
		if not frappe.db.exists("Customer", WHOLESALER):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": WHOLESALER,
					"customer_type": "Company",
					"dz_channel": DIRECT,
				}
			).insert()

	def test_the_customer_gives_the_channel(self):
		self.assertEqual(direct_order().dz_channel, DIRECT)
		# a customer without a usual channel: the default of COD Settings
		self.assertEqual(h.make_order().dz_channel, COD)

	def test_a_direct_sale_skips_the_cod_checks_and_follows_erpnext(self):
		order = direct_order()
		self.assertEqual((order.dz_shipping_charge, order.dz_cod_amount), (0, 0))
		self.assertFalse(fee_lines(order))
		self.assertEqual(actions(order), {S.ACTION_VALIDATE, S.ACTION_CANCEL})

		order = h.act(order, S.ACTION_VALIDATE)  # no phone, wilaya or address: no COD check
		self.assertEqual((order.docstatus, order.workflow_state), (1, S.VALIDATED))
		self.assertFalse(order.dz_delivery_note)

		# ERPNext's own delivery note and invoice
		delivery = frappe.get_doc(make_delivery_note(order.name))
		delivery.insert()
		delivery.submit()
		invoice = frappe.get_doc(make_sales_invoice(delivery.name))
		invoice.insert()
		invoice.submit()
		order.reload()
		self.assertEqual((order.status, order.workflow_state), ("Completed", S.VALIDATED))

	def test_cod_orders_keep_their_buttons(self):
		self.assertEqual(actions(h.make_order()), {S.ACTION_CONFIRM, S.ACTION_NO_ANSWER, S.ACTION_CANCEL})

	def test_a_draft_switched_to_direct_drops_the_delivery_fee(self):
		order = h.make_order()  # Alger, home delivery: 400 DA
		self.assertEqual(order.dz_shipping_charge, 400)
		order.dz_channel = DIRECT
		order.save()
		self.assertEqual((order.dz_shipping_charge, order.dz_cod_amount), (0, 0))
		self.assertFalse(fee_lines(order))

	def test_an_order_submitted_by_code_lands_in_validee(self):
		order = direct_order()
		order.submit()
		self.assertEqual(order.workflow_state, S.VALIDATED)

	def test_cod_counter_and_daily_report_leave_direct_sales_out(self):
		card = frappe.get_doc("Number Card", "COD To Confirm")
		filters = json.loads(card.filters_json)
		report_filters = {"company": h.D.COMPANY, "from_date": today(), "to_date": today()}

		def counted():
			_columns, rows, *_rest = cod_daily_orders.execute(report_filters)
			today_row = next((row for row in rows if str(row["date"]) == today()), {})
			return frappe.db.count("Sales Order", filters), today_row.get(cod_daily_orders.scrub(S.NEW), 0)

		before = counted()
		direct_order()
		self.assertEqual(counted(), before)
		h.make_order()
		self.assertEqual(counted(), (before[0] + 1, before[1] + 1))

	def test_orders_made_before_the_channel_are_cod(self):
		order = h.make_order()
		frappe.db.set_value("Sales Order", order.name, "dz_channel", None)
		with patch.object(set_channel_on_existing_orders, "setup_custom_fields"):  # no DDL in a test
			set_channel_on_existing_orders.execute()
		self.assertEqual(frappe.db.get_value("Sales Order", order.name, "dz_channel"), COD)
