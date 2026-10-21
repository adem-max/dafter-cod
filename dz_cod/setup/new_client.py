"""Prepare a fresh client site in one command (docs/DEPLOY.md, section 13).

Run once, right after `bench new-site` and `install-app dz_cod` (which also
installs dz_core, the base it runs on):

    bench --site erp.client1.com execute dz_cod.setup.new_client.prepare \
        --kwargs "{'company': 'Client One', 'abbr': 'C1', 'courier': 'Yalidine',
                   'features': ['courier_api', 'labels_reports'],
                   'sector': 'Confection', 'tax_regime': 'IFU'}"

dz_core does the base first: setup wizard (French, Algeria, DZD), sector
template, the Matières premières / Travaux en cours / Produits finis
warehouses, and the tax regime (IFU = no TVA by default, which replaces the
old "remove the default 19 % VAT" step) and the SCF set-up (chart, default
accounts, accounts per item group). Then this adds the COD part: the Retours
and "Chez transporteur" warehouses, the delivery fee item, the couriers'
supplier group and accounts (cod/accounts.py), COD Settings (orders leave
from dz_core's Produits finis), one courier, and the client's optional features
(none given = base only; see dz_cod/features.py and docs/FEATURES.md).
Products, stock, users and the wilaya rate card stay manual: they differ per
client (products and stock can come from dz_core's import workbook).
Safe to run twice: whatever already exists is skipped.
"""

import frappe
from frappe.utils.nestedset import get_root_of

from dz_cod.cod.accounts import COURIER_GROUP, settlement_accounts, setup_cod_accounts

RETURNS_WAREHOUSE = "Retours"


def prepare(company, abbr, courier=None, features=None, sector="Confection", tax_regime="IFU"):
	from dz_core.setup.new_client import prepare as prepare_core

	from dz_cod.features import set_features

	if isinstance(features, str):  # "a,b" from the command line
		features = [name.strip() for name in features.split(",") if name.strip()]
	set_features(list(features or []))
	prepare_core(company, abbr, sector, tax_regime)
	# Orders leave from dz_core's finished goods warehouse
	main = frappe.db.get_single_value("DZ Core Settings", "finished_goods_warehouse")
	returns = create_returns_warehouse(company, abbr)
	in_transit = setup_cod_accounts(company)
	if courier:
		create_courier(courier)

	settings = frappe.get_doc("COD Settings")
	settings.update(
		{
			"company": company,
			"main_warehouse": main,
			"returns_warehouse": returns,
			"in_transit_warehouse": in_transit,
			"max_call_attempts": settings.max_call_attempts or 3,
			"default_courier": courier or settings.default_courier,
		}
	)
	# The fee's and the Versements' accounts: keep the ones chosen for this company
	for field, account in settlement_accounts(company).items():
		chosen = settings.get(field)
		if not chosen or frappe.db.get_value("Account", chosen, "company") != company:
			settings.set(field, account)
	settings.save()
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


def create_returns_warehouse(company, abbr):
	"""Returned parcels wait here for inspection (the other warehouses come from dz_core)."""
	full_name = f"{RETURNS_WAREHOUSE} - {abbr}"
	if not frappe.db.exists("Warehouse", full_name):
		root = frappe.db.get_value(
			"Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ["is", "not set"]}
		)
		frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": RETURNS_WAREHOUSE,
				"company": company,
				"parent_warehouse": root,
			}
		).insert()
	return full_name


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
