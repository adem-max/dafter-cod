"""Run after `bench install-app dz_cod` and after every `bench migrate`
(dz_core's own setup runs first: it is installed first).

Everything here is safe to run many times: it creates what is missing and
never overwrites data the user changed (rates, webhook URLs, settings).
"""

import os

import frappe

from dz_cod.cod.permissions import grant_write
from dz_cod.features import apply_features
from dz_cod.setup.custom_fields import setup_custom_fields
from dz_cod.setup.webhooks import setup_webhooks
from dz_cod.setup.wilayas import setup_wilaya_rates
from dz_cod.setup.workflow import setup_workflow


def after_install():
	setup_all()


def after_migrate():
	setup_all()


def setup_all():
	setup_custom_fields()
	setup_workflow()
	grant_write()  # Stock User and Accounts User move orders (cod/permissions.py)
	setup_wilaya_rates()  # the wilayas themselves come from dz_core
	setup_webhooks()
	setup_selling_settings()
	setup_home_block()
	setup_new_settings_defaults()
	setup_cod_accounting()
	# Last: migrate re-imports our reports and print formats (enabled); switch
	# off again what this site doesn't have (dz_cod/features.py)
	apply_features()
	frappe.db.commit()


def setup_new_settings_defaults():
	"""A field added to COD Settings after a site was created gets no default
	(Frappe only applies defaults to new documents). Set it once, only if it
	was never saved, so a value chosen later (even 0) is kept."""
	defaults = {"refused_warning_threshold": 1, "default_channel": "COD", "invoice_on_delivery": 1}
	for fieldname, value in defaults.items():
		saved = frappe.db.sql(
			"SELECT 1 FROM `tabSingles` WHERE doctype = 'COD Settings' AND field = %s", fieldname
		)
		if not saved:
			frappe.db.set_single_value("COD Settings", fieldname, value)


def setup_cod_accounting():
	"""What COD needs on top of dz_core's SCF set-up (cod/accounts.py): the
	couriers' group accounts, the delivery fee item, the "Chez transporteur"
	warehouse, and the fee's and Versements' accounts in COD Settings. Set
	where empty, on a site prepared before they existed; a choice is kept."""
	from dz_cod.cod.accounts import settlement_accounts, setup_cod_accounts

	company = frappe.db.get_single_value("COD Settings", "company")
	if not company or not frappe.db.exists("Account", {"company": company, "account_number": "4671"}):
		return  # no company yet, or dz_core's SCF set-up has not run on it
	values = {"in_transit_warehouse": setup_cod_accounts(company), **settlement_accounts(company)}
	for field, value in values.items():
		if value and not frappe.db.get_single_value("COD Settings", field):
			frappe.db.set_single_value("COD Settings", field, value)


def setup_selling_settings():
	"""A returned order must not keep stock reserved (belt and braces: we also
	close returned orders)."""
	frappe.db.set_single_value("Selling Settings", "dont_reserve_sales_order_qty_on_sales_return", 1)


def setup_home_block():
	"""The "life of an order" overview on the COD home page (Accueil).

	A Custom HTML Block cannot be shipped as a file like the rest of the page,
	so it is created here from setup/home_block/. It is ours: always refreshed.
	"""
	folder = os.path.join(os.path.dirname(__file__), "home_block")
	with open(os.path.join(folder, "home.html")) as f:
		html = f.read()
	with open(os.path.join(folder, "home.css")) as f:
		style = f.read()
	with open(os.path.join(folder, "home.js")) as f:
		script = f.read()

	if frappe.db.exists("Custom HTML Block", "COD Home"):
		block = frappe.get_doc("Custom HTML Block", "COD Home")
	else:
		block = frappe.new_doc("Custom HTML Block")
		block.name = "COD Home"
	block.update({"html": html, "style": style, "script": script, "private": 0})
	block.save(ignore_permissions=True)
