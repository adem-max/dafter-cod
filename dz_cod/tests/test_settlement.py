"""Integration tests: courier settlement (Versement) matching.

Run: bench --site <site> run-tests --module dz_cod.tests.test_settlement
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from dz_cod.cod import settlement as rules
from dz_cod.cod import states as S
from dz_cod.demo import data as D
from dz_cod.dz_cod.report.cod_courier_outstanding import cod_courier_outstanding as outstanding
from dz_cod.tests import helpers as h


def delivered_order(qty=1):
	order = h.make_order(qty=qty)
	return h.act(order, S.ACTION_CONFIRM, S.ACTION_PREPARE, S.ACTION_SHIP, S.ACTION_DELIVER)


def short_line(order, short=500):
	return {
		"sales_order": order.name,
		"collected_amount": order.dz_cod_amount - short,
		"courier_fee": order.dz_courier_fee,
	}


def new_settlement(lines):
	settlement = frappe.new_doc("Courier Settlement")
	settlement.update({"courier": h.MOCK_COURIER, "company": D.COMPANY, "posting_date": today()})
	for line in lines:
		settlement.append("items", line)
	settlement.insert()
	return settlement


class TestSettlement(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()

	def test_matching_statuses_and_summary(self):
		ok = delivered_order()
		short = delivered_order()
		in_transit = h.act(h.make_order(), S.ACTION_CONFIRM, S.ACTION_PREPARE, S.ACTION_SHIP)
		forgotten = delivered_order()

		settlement = new_settlement(
			[
				# found by tracking number, full amount
				{
					"tracking_number": ok.dz_tracking_number,
					"collected_amount": ok.dz_cod_amount,
					"courier_fee": ok.dz_courier_fee,
				},
				# 500 DA short
				{
					"sales_order": short.name,
					"collected_amount": short.dz_cod_amount - 500,
					"courier_fee": short.dz_courier_fee,
				},
				# not delivered yet according to us
				{
					"sales_order": in_transit.name,
					"collected_amount": in_transit.dz_cod_amount,
					"courier_fee": 0,
				},
				# tracking number we do not know
				{"tracking_number": "NOPE-0001", "collected_amount": 1000, "courier_fee": 0},
			]
		)
		statuses = [line.status for line in settlement.items]
		self.assertEqual(statuses, [rules.OK, rules.GAP, rules.INVALID, rules.UNKNOWN])
		self.assertEqual(settlement.items[0].sales_order, ok.name)
		self.assertEqual(settlement.items[1].difference, -500)

		self.assertEqual(settlement.paid_count, 1)
		self.assertEqual(settlement.disputed_count, 3)
		# "forgotten" was delivered but is not in the statement
		missing = [o.name for o in settlement.get_missing_orders()]
		self.assertIn(forgotten.name, missing)
		self.assertNotIn(ok.name, missing)

		settlement.submit()
		self.assertEqual(frappe.db.get_value("Sales Order", ok.name, "workflow_state"), S.SETTLED)
		self.assertEqual(frappe.db.get_value("Sales Order", ok.name, "dz_settlement"), settlement.name)
		self.assertEqual(frappe.db.get_value("Sales Order", short.name, "workflow_state"), S.DELIVERED)

	def test_accepted_gap_is_paid_and_cancel_reverts(self):
		order = delivered_order()
		settlement = new_settlement(
			[
				{
					"sales_order": order.name,
					"collected_amount": order.dz_cod_amount - 100,
					"courier_fee": order.dz_courier_fee,
					"accept_difference": 1,
				}
			]
		)
		settlement.submit()
		self.assertEqual(frappe.db.get_value("Sales Order", order.name, "workflow_state"), S.SETTLED)

		settlement.cancel()
		values = frappe.db.get_value(
			"Sales Order", order.name, ["workflow_state", "dz_settlement"], as_dict=True
		)
		self.assertEqual(values.workflow_state, S.DELIVERED)
		self.assertIsNone(values.dz_settlement)

	def test_a_versement_is_audited_and_cannot_be_deleted(self):
		"""dz_core's audit trail and delete lock follow the Versement (hooks.py dz_no_delete)."""
		from dz_core.setup.permissions import lock_deletions, no_delete

		self.assertIn("Courier Settlement", no_delete())
		lock_deletions()
		user = frappe.db.exists("User", "versement@test.dz") or (
			frappe.get_doc(
				{
					"doctype": "User",
					"email": "versement@test.dz",
					"first_name": "Versement",
					"send_welcome_email": 0,
					"roles": [{"role": "Accounts User"}, {"role": "Accounts Manager"}],
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.assertFalse(frappe.has_permission("Courier Settlement", "delete", user=user))

		settlement = new_settlement([short_line(delivered_order(), short=0)])
		settlement.submit()
		operations = frappe.get_all(
			"DZ Audit Log",
			filters={"reference_doctype": "Courier Settlement", "reference_name": settlement.name},
			pluck="operation",
		)
		self.assertEqual(operations, ["Validation"])

	def test_order_paid_twice_is_flagged(self):
		order = delivered_order()
		line = {
			"sales_order": order.name,
			"collected_amount": order.dz_cod_amount,
			"courier_fee": order.dz_courier_fee,
		}
		new_settlement([line]).submit()
		second = new_settlement([line])
		self.assertEqual(second.items[0].status, rules.ALREADY_SETTLED)

	def test_same_order_twice_in_one_settlement_is_refused(self):
		order = delivered_order()
		line = {
			"sales_order": order.name,
			"collected_amount": order.dz_cod_amount,
			"courier_fee": order.dz_courier_fee,
		}
		with self.assertRaises(frappe.ValidationError):
			new_settlement([line, line])

	def test_load_delivered_orders_button(self):
		order = delivered_order()
		settlement = frappe.new_doc("Courier Settlement")
		settlement.update({"courier": h.MOCK_COURIER, "company": D.COMPANY, "posting_date": today()})
		settlement.load_delivered_orders()
		line = next(line for line in settlement.items if line.sales_order == order.name)
		self.assertEqual(line.status, rules.OK)
		self.assertEqual(line.net_amount, order.dz_cod_amount - order.dz_courier_fee)

	# --------------------------------------- a disputed line, then a second Versement

	def disputed_order(self, short=500):
		"""A delivered order paid `short` DA short in a submitted Versement."""
		order = delivered_order()
		first = new_settlement([short_line(order, short)])
		self.assertEqual(first.items[0].status, rules.GAP)
		first.submit()
		self.assertEqual(frappe.db.get_value("Sales Order", order.name, "workflow_state"), S.DELIVERED)
		return order, first

	def test_second_versement_expects_only_the_rest(self):
		order, _first = self.disputed_order()
		expected_net = order.dz_cod_amount - order.dz_courier_fee

		settlement = frappe.new_doc("Courier Settlement")
		settlement.update({"courier": h.MOCK_COURIER, "company": D.COMPANY, "posting_date": today()})
		settlement.load_delivered_orders()
		line = next(line for line in settlement.items if line.sales_order == order.name)
		# Pre-filled with the 500 still due, not the whole order again
		self.assertEqual(line.collected_amount, 500)
		self.assertEqual(line.courier_fee, 0)
		self.assertEqual(line.already_received, expected_net - 500)
		self.assertEqual(line.difference, 0)
		self.assertEqual(line.status, rules.OK)

		settlement.set("items", [line])  # leave the other tests' orders alone
		settlement.insert()
		settlement.submit()
		self.assertEqual(frappe.db.get_value("Sales Order", order.name, "workflow_state"), S.SETTLED)
		received = frappe.get_all(
			"Courier Settlement Item",
			filters={"sales_order": order.name, "docstatus": 1},
			pluck="net_amount",
		)
		self.assertEqual(sum(received), expected_net)  # paid once in total, not twice

	def test_whole_amount_again_after_dispute_is_a_gap(self):
		# The demo bug: the full amount paid again must not pass as OK
		order, _first = self.disputed_order()
		line = {
			"sales_order": order.name,
			"collected_amount": order.dz_cod_amount,
			"courier_fee": order.dz_courier_fee,
		}
		second = new_settlement([line])
		self.assertEqual(second.items[0].status, rules.GAP)
		self.assertEqual(second.items[0].difference, order.dz_cod_amount - order.dz_courier_fee - 500)

	def test_missing_amount_is_the_rest(self):
		order, _first = self.disputed_order()
		other = delivered_order()
		settlement = new_settlement(
			[
				{
					"sales_order": other.name,
					"collected_amount": other.dz_cod_amount,
					"courier_fee": other.dz_courier_fee,
				}
			]
		)
		missing = {o.name: o for o in settlement.get_missing_orders()}
		self.assertEqual(
			missing[order.name].already_received, order.dz_cod_amount - order.dz_courier_fee - 500
		)

	def test_cancel_first_versement_refused_while_second_counts_it(self):
		order, first = self.disputed_order()
		second = new_settlement([{"sales_order": order.name, "collected_amount": 500, "courier_fee": 0}])
		self.assertEqual(second.items[0].status, rules.OK)
		second.submit()

		first.reload()
		with self.assertRaises(frappe.ValidationError):
			first.cancel()

		# In the right order it works, and the order is back to Livrée
		second.reload()
		second.cancel()
		first.reload()
		first.cancel()
		self.assertEqual(frappe.db.get_value("Sales Order", order.name, "workflow_state"), S.DELIVERED)

	def test_outstanding_report_shows_the_gap(self):
		order, first = self.disputed_order()
		expected_net = order.dz_cod_amount - order.dz_courier_fee

		_columns, rows, *_rest = outstanding.execute({"courier": h.MOCK_COURIER, "detail": 1})
		row = next(row for row in rows if row.name == order.name)
		self.assertEqual(row.dispute, first.name)
		self.assertEqual(row.already_received, expected_net - 500)
		self.assertEqual(row.due, 500)

		summary = outstanding.get_summary_rows([row])[0]
		self.assertEqual(summary["delivered_net"], 500)
		self.assertEqual(summary["disputed_count"], 1)
		self.assertEqual(summary["disputed_net"], 500)  # the gap, not the whole order

	def test_home_card_shows_the_report_amount_due(self):
		# "Argent à recevoir" on the home page = the report's "Montant dû (net)",
		# so a disputed order counts only for the gap, not the whole order
		order = delivered_order()
		before = outstanding.get_amount_due_card()["value"]
		new_settlement([short_line(order, 500)]).submit()

		card = outstanding.get_amount_due_card()
		self.assertEqual(before - card["value"], order.dz_cod_amount - order.dz_courier_fee - 500)
		summary = outstanding.execute({})[4]
		self.assertEqual(card["value"], summary[0]["value"])  # Montant dû (net)

		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				outstanding.get_amount_due_card()
		finally:
			frappe.set_user("Administrator")
