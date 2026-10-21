"""Shared test fixtures: a company, warehouses, one item with stock, one
customer and two couriers (one Mock, one Manuel).

The company and warehouses come from the demo loader's setup functions
(they are idempotent), so tests work on an empty site and on the demo site.
Everything a test class creates is rolled back at the end of the class
(Frappe's IntegrationTestCase does that).
"""

import frappe
from dz_core.setup.item_groups import MERCHANDISE_GROUP
from frappe.model.workflow import apply_workflow
from frappe.utils import today

from dz_cod.demo import data as D
from dz_cod.demo import loader

ITEM = "DZ-TEST-TSHIRT"
ITEM_PRICE = 2000
CUSTOMER = "Client Test COD"
MOCK_COURIER = "Transporteur Test (Mock)"
MANUAL_COURIER = "Transporteur Test (Manuel)"
ALGER = "16 - Alger"
STOCK_QTY = 100


def setup_fixtures():
	loader.setup_company()
	loader.setup_settings()
	loader.ensure("UOM", "Pièce", {"uom_name": "Pièce", "must_be_whole_number": 1})
	loader.ensure(
		"Supplier Group",
		D.SUPPLIER_GROUP,
		{
			"supplier_group_name": D.SUPPLIER_GROUP,
			"parent_supplier_group": frappe.utils.nestedset.get_root_of("Supplier Group"),
		},
	)
	for name, adapter in ((MOCK_COURIER, "Mock"), (MANUAL_COURIER, "Manuel")):
		loader.ensure(
			"Supplier",
			name,
			{
				"supplier_name": name,
				"supplier_group": D.SUPPLIER_GROUP,
				"is_transporter": 1,
				"dz_courier_adapter": adapter,
			},
		)

	if not frappe.db.exists("Item", ITEM):
		item = frappe.new_doc("Item")
		item.update(
			{
				"item_code": ITEM,
				"item_name": "T-shirt de test",
				# a group with accounts: inventory accounts are per item (group)
				"item_group": MERCHANDISE_GROUP,
				"stock_uom": "Pièce",
				"is_stock_item": 1,
				"valuation_rate": 800,
			}
		)
		item.insert()

	if not frappe.db.exists("Customer", CUSTOMER):
		customer = frappe.new_doc("Customer")
		customer.update(
			{
				"customer_name": CUSTOMER,
				"customer_type": "Individual",
				"dz_phone": "0555123456",
				"dz_wilaya": ALGER,
				"dz_commune": "Kouba",
				"dz_address": "Rue des tests, n° 1",
			}
		)
		customer.insert()

	# Known wilaya rates for the tests (Alger: 400 home / 250 stop desk)
	frappe.db.set_value(
		"DZ Wilaya",
		ALGER,
		{
			"enabled": 1,
			"stopdesk_available": 1,
			"home_rate": 400,
			"stopdesk_rate": 250,
			"home_courier_cost": 350,
			"stopdesk_courier_cost": 200,
		},
	)
	frappe.clear_document_cache("DZ Wilaya", ALGER)
	frappe.db.set_single_value("COD Settings", {"max_call_attempts": 3, "settlement_tolerance": 0})
	frappe.clear_document_cache("COD Settings", "COD Settings")

	set_stock(STOCK_QTY)


def before_tests():
	"""hooks.py before_tests: the fixtures are kept on the test site (company,
	COD Settings, couriers, stock), so a fresh site (CI) is like test.localhost.
	dz_core's suite runs on the same site, and every sales order there goes
	through dz_cod, which needs COD Settings. The test site has every feature
	("all"): a site without a list would have the base only."""
	from dz_cod.features import ALL, set_features

	setup_fixtures()
	set_features(ALL)
	frappe.db.commit()


def main_warehouse():
	return frappe.db.get_single_value("COD Settings", "main_warehouse")


def transit_warehouse():
	return frappe.db.get_single_value("COD Settings", "in_transit_warehouse")


def returns_warehouse():
	return frappe.db.get_single_value("COD Settings", "returns_warehouse")


def bin_qty(warehouse, field="actual_qty"):
	return frappe.db.get_value("Bin", {"item_code": ITEM, "warehouse": warehouse}, field) or 0


def set_stock(qty):
	"""Receive enough pieces so that the main warehouse holds `qty`.

	Counted from the stock ledger, not the Bin: a Delivery Note checks the
	ledger, and once (15 Oct 2026) a Bin showing enough stock let a test ship
	from an empty ledger ("Insufficient Stock"). Not reproduced since."""
	from erpnext.stock.utils import get_stock_balance

	missing = qty - get_stock_balance(ITEM, main_warehouse())
	if missing <= 0:
		return
	entry = frappe.new_doc("Stock Entry")
	entry.update({"stock_entry_type": "Material Receipt", "company": D.COMPANY})
	entry.append(
		"items", {"item_code": ITEM, "qty": missing, "basic_rate": 800, "t_warehouse": main_warehouse()}
	)
	entry.insert()
	entry.submit()


def make_order(qty=1, courier=MOCK_COURIER, item=ITEM, **values):
	"""A new draft COD order (state Nouvelle) of one line."""
	order = frappe.new_doc("Sales Order")
	order.update(
		{
			"company": D.COMPANY,
			"customer": CUSTOMER,
			"transaction_date": today(),
			"delivery_date": today(),
			"dz_phone": "0555123456",
			"dz_wilaya": ALGER,
			"dz_commune": "Kouba",
			"dz_address": "Rue des tests, n° 1",
			"dz_delivery_type": "Domicile",
			"dz_courier": courier,
		}
	)
	order.update(values)
	order.append("items", {"item_code": item, "qty": qty, "rate": ITEM_PRICE, "delivery_date": today()})
	order.insert()
	return order


def act(order, *actions):
	"""Press one or more workflow buttons, then return the fresh order."""
	for action in actions:
		apply_workflow(frappe.get_doc("Sales Order", order.name), action)
	return frappe.get_doc("Sales Order", order.name)
