"""Optional features per client site (dz_cod/features.py).

The test site has "dz_features": "all" (dz_cod's before_tests; the mechanism
is dz_core's), so every other test runs with everything on. Here the key is
patched in frappe.local.conf for one test at a time, and apply_features()
puts the records back afterwards.

Run: bench --site <site> run-tests --module dz_cod.tests.test_features
"""

from unittest.mock import patch

import frappe
from dz_core.features import boot
from frappe.tests import IntegrationTestCase

from dz_cod import features as F
from dz_cod.cod import states as S
from dz_cod.couriers import get_adapter
from dz_cod.couriers.base import ManualAdapter
from dz_cod.setup.webhooks import setup_webhooks, webhook_name
from dz_cod.tests import helpers as h


def only(*names):
	"""Patch the site's list for the duration of a `with` block."""
	return patch.dict(frappe.local.conf, {F.CONFIG_KEY: list(names)})


class TestFeatureList(IntegrationTestCase):
	def test_missing_key_means_the_base_only(self):
		with patch.dict(frappe.local.conf, {}):
			frappe.local.conf.pop(F.CONFIG_KEY, None)
			self.assertEqual(F.enabled(), set())

	def test_all_means_every_feature(self):
		with patch.dict(frappe.local.conf, {F.CONFIG_KEY: F.ALL}):
			self.assertEqual(F.enabled(), set(F.FEATURES))

	def test_explicit_list_is_followed_and_unknown_names_ignored(self):
		with only():
			self.assertEqual(F.enabled(), set())
		with only("phone_checks", "teleportation"):
			self.assertEqual(F.enabled(), {"phone_checks"})

	def test_requires_feature_refuses_with_the_offer_message(self):
		@F.requires_feature("courier_api")
		def action():
			return "done"

		with only("courier_api"):
			self.assertEqual(action(), "done")
		with only(), self.assertRaises(F.FeatureNotEnabled):
			action()

	def test_boot_lists_the_features(self):
		bootinfo = frappe._dict()
		with only("labels_reports"):
			boot(bootinfo)
		self.assertEqual(bootinfo.dz_features, ["labels_reports"])


class TestFeatureGuards(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()
		setup_webhooks()

	def tearDown(self):
		F.apply_features()  # back to "all", the test site's setting

	def test_reports_and_label_follow_labels_reports(self):
		with only():
			F.apply_features()
			self.assertEqual(frappe.db.get_value("Report", "COD Return Rate", "disabled"), 1)
			self.assertEqual(frappe.db.get_value("Report", "COD Daily Orders", "disabled"), 1)
			self.assertEqual(frappe.db.get_value("Print Format", "Bordereau COD", "disabled"), 1)
			# Encours transporteurs is base
			self.assertEqual(frappe.db.get_value("Report", "COD Courier Outstanding", "disabled"), 0)
		F.apply_features()
		self.assertEqual(frappe.db.get_value("Report", "COD Return Rate", "disabled"), 0)
		self.assertEqual(frappe.db.get_value("Print Format", "Bordereau COD", "disabled"), 0)

	def test_a_switched_off_report_cannot_be_ticked_back_on(self):
		"""Review of 27 October 2026, 4.5. Outside developer mode Frappe already
		refuses any change to a standard report, but not to a print format:
		there dz_core's keep_switched_off is the gate (found 30 October 2026).
		It also holds in developer mode. Called directly first: saving a
		standard report in developer mode would write its JSON into the app's
		folder."""
		from dz_core.features import keep_switched_off

		with only():
			F.apply_features()
			for doctype, name in (("Report", "COD Return Rate"), ("Print Format", "Bordereau COD")):
				doc = frappe.get_doc(doctype, name)
				doc.disabled = 0
				with self.subTest(doctype=doctype):
					with self.assertRaises(F.FeatureNotEnabled):
						keep_switched_off(doc)
					with (
						patch.dict(frappe.local.conf, {"developer_mode": 0}),
						self.assertRaises((frappe.ValidationError, F.FeatureNotEnabled)),
					):
						doc.save()  # the report: Frappe refuses; the print format: dz_core
		with only("labels_reports"):
			doc = frappe.get_doc("Report", "COD Return Rate")
			doc.disabled = 0
			self.assertIsNone(keep_switched_off(doc))  # in the offer: allowed

	def test_webhooks_are_switched_off_then_restored(self):
		name = webhook_name(S.SHIPPED)
		frappe.db.set_value("Webhook", name, "enabled", 1)
		with only():
			F.apply_features()
			self.assertEqual(frappe.db.get_value("Webhook", name, "enabled"), 0)
			webhook = frappe.get_doc("Webhook", name)
			webhook.enabled = 1
			with self.assertRaises(F.FeatureNotEnabled):
				webhook.save()
		F.apply_features()
		self.assertEqual(frappe.db.get_value("Webhook", name, "enabled"), 1)

	def test_phone_warnings_off_but_phones_still_normalized(self):
		frappe.db.set_single_value("COD Settings", "refused_warning_threshold", 1)
		refused = h.act(
			h.make_order(dz_phone="0661000333"),
			S.ACTION_CONFIRM,
			S.ACTION_PREPARE,
			S.ACTION_SHIP,
			S.ACTION_RETURN,
		)
		with only():
			frappe.clear_messages()
			order = h.make_order(dz_phone="+213 661 00 03 33")
			self.assertEqual(order.dz_phone, "0661000333")
			self.assertNotIn(refused.name, " ".join(str(m) for m in frappe.get_message_log()))

	def test_api_couriers_fall_back_to_manual_and_cannot_be_chosen(self):
		frappe.db.set_value("Supplier", h.MANUAL_COURIER, "dz_courier_adapter", "Yalidine")
		frappe.clear_document_cache("Supplier", h.MANUAL_COURIER)
		try:
			with only():
				self.assertIsInstance(get_adapter(h.MANUAL_COURIER), ManualAdapter)
				supplier = frappe.get_doc("Supplier", h.MANUAL_COURIER)
				with self.assertRaises(F.FeatureNotEnabled):
					supplier.save()
		finally:
			frappe.db.set_value("Supplier", h.MANUAL_COURIER, "dz_courier_adapter", "Manuel")
			frappe.clear_document_cache("Supplier", h.MANUAL_COURIER)

	def test_courier_sync_and_imports_refused(self):
		from dz_cod.couriers import sync
		from dz_cod.couriers.places import commune_names
		from dz_cod.couriers.yalidine_import import start_import

		frappe.db.set_single_value("COD Settings", "auto_sync_courier_status", 1)
		with only(), patch.object(sync, "sync_courier") as sync_courier:
			sync.sync_shipped_orders()
			sync_courier.assert_not_called()
			self.assertEqual(commune_names(h.ALGER), [])
			with self.assertRaises(F.FeatureNotEnabled):
				start_import(h.MANUAL_COURIER, "fees")

	def test_yalidine_webhook_answers_403_and_stores_nothing(self):
		from dz_cod.couriers import yalidine_webhook

		before = frappe.db.count("Courier Webhook Event")
		frappe.local.request = frappe._dict(method="POST", args={}, headers={}, get_data=lambda: b"{}")
		try:
			with only():
				response = yalidine_webhook.receive()
		finally:
			del frappe.local.request
		self.assertEqual(response.status_code, 403)
		self.assertEqual(frappe.db.count("Courier Webhook Event"), before)
