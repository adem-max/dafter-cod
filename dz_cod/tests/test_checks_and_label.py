"""Integration tests: phone warnings, return-rate minimum sample, webhook
template refresh, and the "Bordereau COD" label with its barcode.

Run: bench --site <site> run-tests --module dz_cod.tests.test_checks_and_label
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from dz_cod.cod import states as S
from dz_cod.cod.barcode import PATTERNS, START_B, STOP, code128_modules, code128_svg
from dz_cod.cod.phone_checks import refused_parcels
from dz_cod.setup.webhooks import PAYLOAD, fingerprint_key, setup_webhooks, webhook_name
from dz_cod.tests import helpers as h

RISKY_PHONE = "0661000111"


def returned_order(**values):
	order = h.make_order(**values)
	return h.act(order, S.ACTION_CONFIRM, S.ACTION_PREPARE, S.ACTION_SHIP, S.ACTION_RETURN)


def warnings():
	return " ".join(str(m) for m in frappe.get_message_log())


class TestPhoneChecks(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()

	def setUp(self):
		frappe.clear_messages()
		frappe.db.set_single_value("COD Settings", "refused_warning_threshold", 1)

	def test_refused_parcels_warn_on_a_new_order(self):
		first = returned_order(dz_phone=RISKY_PHONE)
		self.assertEqual(refused_parcels(RISKY_PHONE), [first.name])

		frappe.clear_messages()
		h.make_order(dz_phone=RISKY_PHONE)
		self.assertIn(first.name, warnings())  # the warning links the refused order

	def test_the_second_phone_counts_too_and_zero_turns_it_off(self):
		refused = returned_order(dz_phone="0661000222")
		frappe.clear_messages()
		h.make_order(dz_phone="0555999888", dz_phone_2="0661000222")
		self.assertIn(refused.name, warnings())

		frappe.db.set_single_value("COD Settings", "refused_warning_threshold", 0)
		frappe.clear_messages()
		h.make_order(dz_phone="0661000222")
		self.assertNotIn(refused.name, warnings())

	def test_no_warning_for_a_clean_phone(self):
		h.make_order(dz_phone="0770123123")
		# ERPNext may add its own notices (e.g. "Item Price added"); none of ours
		self.assertFalse([m for m in frappe.get_message_log() if m.get("indicator") == "orange"])

	def test_duplicate_customer_phone_is_reported(self):
		def customer(name, phone):
			doc = frappe.new_doc("Customer")
			doc.update({"customer_name": name, "customer_type": "Individual", "dz_phone": phone})
			return doc.insert()

		first = customer("Client Doublon A", "+213 550 11 22 33")
		self.assertEqual(first.dz_phone, "0550112233")  # normalized like on orders
		frappe.clear_messages()
		customer("Client Doublon B", "0550112233")
		self.assertIn(first.name, warnings())  # the warning links the existing customer


class TestReturnRateMinimum(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()

	def test_small_samples_have_no_rate_and_sort_last(self):
		from dz_cod.dz_cod.report.cod_return_rate import cod_return_rate

		returned_order()
		period = {"from_date": add_days(today(), -1), "to_date": today(), "group_by": "Produit"}

		_columns, rows, *_ = cod_return_rate.execute(dict(period, min_parcels=5))
		row = next(r for r in rows if r["name"] == h.ITEM)
		self.assertGreaterEqual(row["orders"], 1)
		if row["orders"] < 5:
			self.assertIsNone(row["return_rate"])
			self.assertTrue(all(r["return_rate"] is None for r in rows[rows.index(row) :]))

		_columns, rows, *_ = cod_return_rate.execute(dict(period, min_parcels=1))
		row = next(r for r in rows if r["name"] == h.ITEM)
		self.assertIsNotNone(row["return_rate"])


class TestWebhookTemplates(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()
		setup_webhooks()

	def test_an_untouched_template_is_refreshed_but_url_and_enabled_are_kept(self):
		name = webhook_name(S.SHIPPED)
		frappe.db.set_value("Webhook", name, {"request_url": "https://n8n.client.dz/hook", "enabled": 1})
		# Pretend an older app version wrote an older template, and remember it as ours
		frappe.db.set_value("Webhook", name, "webhook_json", '{"old": true}')
		condition = frappe.db.get_value("Webhook", name, "condition")
		from dz_cod.setup.webhooks import fingerprint

		frappe.db.set_default(fingerprint_key(name), fingerprint(condition, '{"old": true}'))

		setup_webhooks()
		webhook = frappe.get_doc("Webhook", name)
		self.assertEqual(webhook.webhook_json, PAYLOAD)
		self.assertEqual(webhook.request_url, "https://n8n.client.dz/hook")
		self.assertEqual(webhook.enabled, 1)

	def test_a_template_edited_on_the_site_is_left_alone(self):
		name = webhook_name(S.DELIVERED)
		frappe.db.set_value("Webhook", name, "webhook_json", '{"edited": "by the client"}')
		setup_webhooks()
		self.assertEqual(frappe.db.get_value("Webhook", name, "webhook_json"), '{"edited": "by the client"}')


class TestLabel(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()

	def test_code128_round_trip_and_checksum(self):
		text = "MOCK-SAL-ORD-2026-00012"
		modules = code128_modules(text)
		# start + one pattern per character + checksum (11 modules each) + stop (13)
		self.assertEqual(len(modules), 11 * (len(text) + 2) + 13)
		self.assertTrue(modules.startswith(PATTERNS[START_B]) and modules.endswith(STOP))
		values = [PATTERNS.index(modules[i : i + 11]) for i in range(11, 11 * (len(text) + 1), 11)]
		self.assertEqual("".join(chr(v + 32) for v in values), text)
		checksum = PATTERNS.index(modules[11 * (len(text) + 1) : 11 * (len(text) + 2)])
		self.assertEqual(checksum, (START_B + sum(i * v for i, v in enumerate(values, 1))) % 103)
		self.assertTrue(code128_svg(text).startswith("<svg"))
		self.assertEqual(code128_svg(""), "")

	def test_label_prints_tracking_amount_and_recipient(self):
		order = h.act(h.make_order(), S.ACTION_CONFIRM, S.ACTION_PREPARE, S.ACTION_SHIP)
		html = frappe.get_print("Sales Order", order.name, print_format="Bordereau COD", no_letterhead=1)
		self.assertIn("<svg", html)
		self.assertIn(order.dz_tracking_number, html)
		self.assertIn(order.dz_phone, html)
		self.assertIn(frappe.utils.fmt_money(order.dz_cod_amount, currency="DZD"), html)
