"""Integration tests: courier connectors, hourly status sync, webhooks, reports.
(The Yalidine connector has its own file: test_yalidine.py.)

Run: bench --site <site> run-tests --module dz_cod.tests.test_couriers_and_webhooks
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from dz_cod.cod import states as S
from dz_cod.couriers import get_adapter
from dz_cod.couriers.base import DELIVERED, RETURNED
from dz_cod.couriers.mock import set_mock_status
from dz_cod.couriers.sync import sync_shipped_orders
from dz_cod.setup.webhooks import webhook_name
from dz_cod.tests import helpers as h


def shipped_order():
	return h.act(h.make_order(), S.ACTION_CONFIRM, S.ACTION_PREPARE, S.ACTION_SHIP)


class TestCourierSync(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()
		frappe.db.set_single_value("COD Settings", "auto_sync_courier_status", 1)

	def test_mock_statuses_move_the_orders(self):
		delivered, returned, travelling = shipped_order(), shipped_order(), shipped_order()
		set_mock_status(delivered.dz_tracking_number, DELIVERED)
		set_mock_status(returned.dz_tracking_number, RETURNED)

		# The sync commits after each order; keep the test data rollback-able
		with patch("frappe.db.commit"):
			sync_shipped_orders()

		state = lambda order: frappe.db.get_value("Sales Order", order.name, "workflow_state")  # noqa: E731
		self.assertEqual(state(delivered), S.DELIVERED)
		self.assertEqual(state(returned), S.RETURNED)
		self.assertEqual(state(travelling), S.SHIPPED)

	def test_manual_adapter_gives_no_tracking(self):
		self.assertIsNone(get_adapter(h.MANUAL_COURIER).create_shipment(h.make_order()))

	def test_zr_express_is_coming_soon_and_works_like_manual(self):
		# A courier can already be set to "ZR Express": tracking typed by hand,
		# no status from the courier, until the real connector is built
		options = frappe.get_meta("Supplier").get_field("dz_courier_adapter").options.split("\n")
		self.assertIn("ZR Express", options)
		frappe.db.set_value("Supplier", h.MANUAL_COURIER, "dz_courier_adapter", "ZR Express")
		frappe.clear_document_cache("Supplier", h.MANUAL_COURIER)
		try:
			adapter = get_adapter(h.MANUAL_COURIER)
			self.assertTrue(adapter.coming_soon)
			self.assertIsNone(adapter.create_shipment(h.make_order()))
			self.assertEqual(adapter.get_status("ZR-123"), "unknown")
		finally:
			# The cached courier would outlive the rollback: put it back
			frappe.db.set_value("Supplier", h.MANUAL_COURIER, "dz_courier_adapter", "Manuel")
			frappe.clear_document_cache("Supplier", h.MANUAL_COURIER)


class TestWebhooks(IntegrationTestCase):
	"""Webhooks are queued during the save and sent after the commit.
	We only check what gets queued (no network call)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()
		for state in (S.CONFIRMED, S.SHIPPED):
			frappe.db.set_value("Webhook", webhook_name(state), "enabled", 1)
		frappe.client_cache.delete_value("webhooks")

	def queued(self):
		return [item.webhook.name for item in getattr(frappe.local, "_webhook_queue", None) or []]

	def setUp(self):
		frappe.local._webhook_queue = []

	def test_webhook_fires_once_per_state_change(self):
		order = h.act(h.make_order(), S.ACTION_CONFIRM)
		self.assertIn(webhook_name(S.CONFIRMED), self.queued())

		order = h.act(order, S.ACTION_PREPARE, S.ACTION_SHIP)
		self.assertEqual(self.queued().count(webhook_name(S.SHIPPED)), 1)

		# Saving the order again without changing its state does not fire again
		frappe.local._webhook_queue = []
		order.dz_tracking_number = order.dz_tracking_number + "-B"
		order.save()
		self.assertNotIn(webhook_name(S.SHIPPED), self.queued())

	def test_payload_is_valid_json(self):
		from frappe.integrations.doctype.webhook.webhook import get_webhook_data

		order = shipped_order()
		data = get_webhook_data(order, frappe.get_doc("Webhook", webhook_name(S.SHIPPED)))
		self.assertEqual(data["event"], S.SHIPPED)
		self.assertEqual(data["tracking_number"], order.dz_tracking_number)
		self.assertEqual(data["items"][0]["item_code"], h.ITEM)
		self.assertEqual(data["cod_amount"], order.dz_cod_amount)


class TestReports(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()

	def test_reports_run_and_count_our_orders(self):
		from dz_cod.dz_cod.report.cod_courier_outstanding import cod_courier_outstanding
		from dz_cod.dz_cod.report.cod_daily_orders import cod_daily_orders
		from dz_cod.dz_cod.report.cod_return_rate import cod_return_rate

		returned = h.act(shipped_order(), S.ACTION_RETURN)
		delivered = h.act(shipped_order(), S.ACTION_DELIVER)
		period = {"from_date": add_days(today(), -1), "to_date": today()}

		_columns, rows, *_ = cod_daily_orders.execute(period)
		self.assertGreaterEqual(rows[0]["total"], 2)

		_columns, rows, *_ = cod_return_rate.execute(dict(period, group_by="Produit"))
		row = next(r for r in rows if r["name"] == h.ITEM)
		self.assertGreaterEqual(row["returned"], 1)
		self.assertGreaterEqual(row["delivered"], 1)

		_columns, rows, *_ = cod_courier_outstanding.execute({"detail": 1, "courier": h.MOCK_COURIER})
		names = [r["name"] for r in rows]
		self.assertIn(delivered.name, names)
		self.assertNotIn(returned.name, names)
