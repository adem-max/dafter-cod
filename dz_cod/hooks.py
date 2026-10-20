"""Frappe reads this file to know how the dz_cod app plugs into ERPNext.

Only the hooks we actually use are listed. For all possible hooks see
https://docs.frappe.io/framework/user/en/python-api/hooks
"""

app_name = "dz_cod"
app_title = "DZ COD"
app_publisher = "Adem"
app_description = "COD e-commerce starter kit for Algerian online sellers on ERPNext"
app_email = "adembenlecheb1@gmail.com"
app_license = "mit"

# dz_core is the base every client gets (setup wizard, sector, tax regime,
# invoices, import workbook, wilayas, phone numbers, backups); dz_cod adds the
# online-sales part on top
required_apps = ["erpnext", "dz_core"]

# Where to land after login. COD is docked on ERPNext's rail, so Frappe keeps
# it off the apps screen, but this route is used when COD is the site's
# default app (System Settings > default_app = dz_cod, set by new_client and
# the demo loader): sellers then open straight on the COD home page. Frappe 16
# alone sends desk users to /desk; dz_core's get_website_user_home_page hook
# sends them to the default app's route.
add_to_apps_screen = [
	{
		"name": "dz_cod",
		"logo": "/assets/dz_cod/images/cod-logo.svg",
		"title": "COD",
		"route": "/desk/cod",
		"has_permission": "erpnext.check_app_permission",
	}
]

# Create custom fields, workflow, wilayas and webhooks
after_install = "dz_cod.setup.install.after_install"
after_migrate = "dz_cod.setup.install.after_migrate"

# Extra buttons on the Sales Order form (Expédier dialog, return inspection)
# and on the courier (Yalidine imports)
doctype_js = {"Sales Order": "public/js/sales_order.js", "Supplier": "public/js/supplier.js"}

# The COD order life cycle: see dz_cod/cod/order.py
doc_events = {
	"Sales Order": {
		"before_validate": "dz_cod.cod.order.before_validate",
		"validate": "dz_cod.cod.order.validate",
		"before_submit": "dz_cod.cod.order.before_submit",
		"before_update_after_submit": "dz_cod.cod.order.before_update_after_submit",
		"on_update_after_submit": "dz_cod.cod.order.on_update_after_submit",
	},
	# Warn when another customer already has this phone (dz_cod/cod/phone_checks.py)
	"Customer": {"validate": "dz_cod.cod.phone_checks.warn_duplicate_customer"},
	# Optional features (dz_cod/features.py): API connectors and COD webhooks
	"Supplier": {"validate": "dz_cod.features.check_courier_connector"},
	"Webhook": {"validate": "dz_cod.features.check_webhook"},
}

# Our optional features. dz_core switches them per site (dz-features command,
# frappe.boot.dz_features in the browser, the hub's offers)
dz_features = ["dz_cod.features.FEATURES"]

# Ask the couriers for parcel statuses every hour (only if enabled in COD Settings)
scheduler_events = {
	"hourly": ["dz_cod.couriers.sync.sync_shipped_orders"],
}

# code128_svg() in print formats: the barcode on the "Bordereau COD" label
jinja = {"methods": ["dz_cod.cod.barcode.code128_svg"]}

# What dz_core's restore drill (scripts/restore_test.sh) also compares on a COD site
dz_restore_check_counted = ["Sales Order", "Courier Settlement"]
dz_restore_check_last = ["Sales Order"]

# Courier webhook events are kept 30 days (Log Settings), enough to spot an
# event delivered twice: Yalidine retries a delivery for 40 hours at most
default_log_clearing_doctypes = {"Courier Webhook Event": 30}
