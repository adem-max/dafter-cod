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

required_apps = ["erpnext"]

# Where to land after login. COD is docked on ERPNext's rail, so Frappe keeps
# it off the apps screen, but this route is used when COD is the site's
# default app (System Settings > default_app = dz_cod, set by new_client and
# the demo loader): sellers then open straight on the COD home page.
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
}

# Ask the couriers for parcel statuses every hour (only if enabled in COD Settings)
scheduler_events = {
	"hourly": ["dz_cod.couriers.sync.sync_shipped_orders"],
}

# Courier webhook events are kept 30 days (Log Settings), enough to spot an
# event delivered twice: Yalidine retries a delivery for 40 hours at most
default_log_clearing_doctypes = {"Courier Webhook Event": 30}
