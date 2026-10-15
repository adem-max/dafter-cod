"""Prepare a fresh client site in one command (docs/DEPLOY.md, section 13).

Run once, right after `bench new-site` and `install-app dz_cod`:

    bench --site erp.client1.com execute dz_cod.setup.new_client.prepare \
        --kwargs "{'company': 'Client One', 'abbr': 'C1', 'courier': 'Yalidine'}"

It does the setup wizard (French, Algeria, DZD), the two warehouses, the
delivery-fee account, COD Settings, one courier, and removes the default 19 % VAT.
Products, stock, users and the wilaya rate card stay manual: they differ per client.
Safe to run twice: whatever already exists is skipped.
"""

import frappe
from frappe.utils import today
from frappe.utils.nestedset import get_root_of

MAIN_WAREHOUSE = "Stock principal"
RETURNS_WAREHOUSE = "Retours"
SHIPPING_ACCOUNT = "Frais de livraison facturés"
COURIER_GROUP = "Transporteurs"


def prepare(company, abbr, courier=None):
	run_setup_wizard(company, abbr)
	main, returns = create_warehouses(company, abbr)
	account = create_shipping_account(company, abbr)
	if courier:
		create_courier(courier)

	settings = frappe.get_doc("COD Settings")
	settings.update(
		{
			"company": company,
			"main_warehouse": main,
			"returns_warehouse": returns,
			"shipping_income_account": account,
			"max_call_attempts": settings.max_call_attempts or 3,
			"default_courier": courier or settings.default_courier,
		}
	)
	settings.save()
	frappe.db.set_single_value("Stock Settings", "default_warehouse", main)
	remove_default_vat(company)
	make_cod_the_home_page()
	frappe.db.commit()
	print(f"{company} is ready. Next: products, opening stock, users, wilaya rates.")


def make_cod_the_home_page():
	"""After login, open the COD home page instead of ERPNext's app list
	(route from add_to_apps_screen in hooks.py). A user can still pick another
	default app for themselves."""
	from frappe.core.doctype.system_settings.system_settings import clear_system_settings_cache

	frappe.db.set_single_value("System Settings", "default_app", "dz_cod")
	# System Settings are cached per process: drop the copies so it applies now
	clear_system_settings_cache()
	frappe.local.system_settings = None


def run_setup_wizard(company, abbr):
	if frappe.is_setup_complete():
		return
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	year = today()[:4]
	setup_complete(
		{
			"language": "Français",
			"lang": "Français",
			"country": "Algeria",
			"timezone": "Africa/Algiers",
			"currency": "DZD",
			"company_name": company,
			"company_abbr": abbr,
			"chart_of_accounts": "Algerie - Plan Comptable General 2 avec code",
			"fy_start_date": f"{year}-01-01",
			"fy_end_date": f"{year}-12-31",
			"setup_demo": 0,
		}
	)
	# Saving the document (not just the value) also sets every user's default company
	defaults = frappe.get_doc("Global Defaults")
	defaults.update({"default_company": company, "default_currency": "DZD", "country": "Algeria"})
	defaults.save()


def create_warehouses(company, abbr):
	root = frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ["is", "not set"]}
	)
	names = []
	for name in (MAIN_WAREHOUSE, RETURNS_WAREHOUSE):
		full_name = f"{name} - {abbr}"
		if not frappe.db.exists("Warehouse", full_name):
			frappe.get_doc(
				{"doctype": "Warehouse", "warehouse_name": name, "company": company, "parent_warehouse": root}
			).insert()
		names.append(full_name)
	return names


def create_shipping_account(company, abbr):
	name = f"{SHIPPING_ACCOUNT} - {abbr}"
	if not frappe.db.exists("Account", name):
		income_root = frappe.db.get_value(
			"Account",
			{"company": company, "root_type": "Income", "is_group": 1, "parent_account": ["is", "not set"]},
		)
		frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": SHIPPING_ACCOUNT,
				"company": company,
				"parent_account": income_root,
				"account_type": "Income Account",
			}
		).insert()
	return name


def create_courier(courier):
	if not frappe.db.exists("Supplier Group", COURIER_GROUP):
		frappe.get_doc(
			{
				"doctype": "Supplier Group",
				"supplier_group_name": COURIER_GROUP,
				"parent_supplier_group": get_root_of("Supplier Group"),
			}
		).insert()
	if not frappe.db.exists("Supplier", courier):
		# "Manuel": no API, the tracking number is typed when shipping
		frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": courier,
				"supplier_group": COURIER_GROUP,
				"is_transporter": 1,
				"dz_courier_adapter": "Manuel",
			}
		).insert()


def remove_default_vat(company):
	"""The wizard makes "Algeria TVA 19%" the default; the order form would add it to every order."""
	for name in frappe.get_all(
		"Sales Taxes and Charges Template", {"company": company, "is_default": 1}, pluck="name"
	):
		frappe.db.set_value("Sales Taxes and Charges Template", name, "is_default", 0)
