"""A new online seller's site in one command: dz_cod.setup.new_client.prepare,
which the hub runs for every client who takes Vente en ligne. It runs
dz_core's prepare() first (sector, tax regime, warehouses), then adds the
returns warehouse, the delivery-fee account, COD Settings, the courier and the
client's features.

prepare() commits and writes the feature list into site_config.json: here the
commit is patched (the class rollback then undoes the database) and
site_config.json is put back afterwards.

Run: bench --site <site> run-tests --module dz_cod.tests.test_new_client
"""

from unittest.mock import patch

import frappe
from dz_core.setup.sectors import CLOTHING
from dz_core.setup.tax import IFU_NOTE
from frappe.tests import IntegrationTestCase
from frappe.utils import random_string

from dz_cod.setup import new_client

CHART = "Algerie - Plan Comptable General 2 avec code"


class TestNewClient(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.config_path = frappe.get_site_path("site_config.json")
		with open(cls.config_path) as f:
			cls.config = f.read()

	@classmethod
	def tearDownClass(cls):
		with open(cls.config_path, "w") as f:
			f.write(cls.config)
		frappe.local.conf = frappe._dict(frappe.get_site_config())
		super().tearDownClass()  # rolls the database back
		for doctype in ("COD Settings", "DZ Core Settings", "System Settings"):
			frappe.clear_document_cache(doctype, doctype)
		frappe.clear_cache()

	def test_prepare_sets_up_an_online_seller(self):
		tag = random_string(4).upper()
		company, abbr, courier = f"Boutique Test {tag}", f"B{tag}", f"Coursier {tag}"
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": company,
				"abbr": abbr,
				"default_currency": "DZD",
				"country": "Algeria",
				"chart_of_accounts": CHART,
			}
		).insert()

		def prepare():
			new_client.prepare(
				company, abbr, courier=courier, features=["phone_checks"], sector=CLOTHING, tax_regime="IFU"
			)

		with patch("frappe.db.commit"):
			prepare()
			core = frappe.get_doc("DZ Core Settings")
			self.assertEqual(
				(core.company, core.sector, core.tax_regime, core.invoice_note),
				(company, CLOTHING, "IFU", IFU_NOTE),
			)
			cod = frappe.get_doc("COD Settings")
			self.assertEqual(cod.company, company)
			# orders leave from dz_core's Produits finis
			self.assertEqual(cod.main_warehouse, core.finished_goods_warehouse)
			self.assertEqual(cod.returns_warehouse, f"{new_client.RETURNS_WAREHOUSE} - {abbr}")
			self.assertEqual(frappe.db.get_value("Warehouse", cod.returns_warehouse, "company"), company)
			self.assertEqual(cod.shipping_income_account, f"{new_client.SHIPPING_ACCOUNT} - {abbr}")
			self.assertEqual(
				frappe.db.get_value("Account", cod.shipping_income_account, ["company", "account_type"]),
				(company, "Income Account"),
			)
			self.assertEqual((cod.default_courier, cod.max_call_attempts), (courier, 3))
			self.assertEqual(
				frappe.db.get_value(
					"Supplier", courier, ["is_transporter", "dz_courier_adapter", "supplier_group"]
				),
				(1, "Manuel", new_client.COURIER_GROUP),
			)
			self.assertEqual(frappe.db.get_single_value("System Settings", "default_app"), "dz_cod")
			self.assertEqual(frappe.conf.get("dz_features"), ["phone_checks"])

			counted = ("Warehouse", "Account", "Supplier", "Item Group", "UOM")
			counts = {doctype: frappe.db.count(doctype) for doctype in counted}
			prepare()  # a second run adds nothing
			self.assertEqual({doctype: frappe.db.count(doctype) for doctype in counted}, counts)
