"""The welcome guide on the COD home page: remember, per user, whether it is
open, collapsed or hidden (see setup/home_block/home.js)."""

import frappe

GUIDE_KEY = "dz_cod_home_guide"
GUIDE_STATES = ("open", "collapsed", "hidden")


@frappe.whitelist()
def set_guide_state(state):
	if state not in GUIDE_STATES:
		frappe.throw(f"Unknown state: {state}")
	# Saved for the logged-in user only
	frappe.defaults.set_user_default(GUIDE_KEY, state)
