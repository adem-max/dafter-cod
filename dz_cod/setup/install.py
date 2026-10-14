"""Run after `bench install-app dz_cod` and after every `bench migrate`.

Everything here is safe to run many times: it creates what is missing and
never overwrites data the user changed (rates, webhook URLs, settings).
"""

import os

import frappe

from dz_cod.setup.custom_fields import setup_custom_fields
from dz_cod.setup.webhooks import setup_webhooks
from dz_cod.setup.wilayas import WILAYAS, ZONE_RATES, wilaya_docname
from dz_cod.setup.workflow import setup_workflow


def after_install():
	setup_all()


def after_migrate():
	setup_all()


def setup_all():
	setup_custom_fields()
	setup_workflow()
	setup_wilayas()
	setup_webhooks()
	setup_selling_settings()
	setup_home_block()
	frappe.db.commit()


def setup_wilayas():
	"""Create the 69 wilayas with example rates. Existing ones are left alone."""
	# First pass: create the wilayas; second pass: link the 2026 ones to their parent
	codes_to_names = {code: wilaya_docname(code, name) for code, name, _zone, _parent in WILAYAS}

	for code, name, zone, _parent in WILAYAS:
		if frappe.db.exists("DZ Wilaya", {"code": code}):
			continue
		home, stopdesk = ZONE_RATES[zone]
		doc = frappe.new_doc("DZ Wilaya")
		doc.update(
			{
				"code": code,
				"wilaya_name": name,
				"zone": zone,
				"enabled": 1,
				"stopdesk_available": 1,
				"home_rate": home,
				"stopdesk_rate": stopdesk,
				# By default we charge the customer what the courier charges us
				"home_courier_cost": home,
				"stopdesk_courier_cost": stopdesk,
			}
		)
		doc.insert(ignore_permissions=True)

	for code, _name, _zone, parent in WILAYAS:
		if parent and not frappe.db.get_value("DZ Wilaya", codes_to_names[code], "parent_wilaya"):
			frappe.db.set_value("DZ Wilaya", codes_to_names[code], "parent_wilaya", codes_to_names[parent])


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
