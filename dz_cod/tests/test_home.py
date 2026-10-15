"""Integration tests: the COD home page (welcome guide state, landing after
login) and the Commandes list layout.

Run: bench --site <site> run-tests --module dz_cod.tests.test_home
"""

import frappe
from frappe.apps import get_default_path
from frappe.tests import IntegrationTestCase

from dz_cod.cod.home import GUIDE_KEY, set_guide_state
from dz_cod.setup.custom_fields import setup_custom_fields
from dz_cod.setup.new_client import make_cod_the_home_page


class TestLanding(IntegrationTestCase):
	def test_login_opens_the_cod_home_page(self):
		make_cod_the_home_page()
		frappe.db.set_value("User", frappe.session.user, "default_app", "")
		self.assertEqual(get_default_path(), "/desk/cod")

	def test_orders_list_shows_cod_fields_first(self):
		setup_custom_fields()
		frappe.clear_cache(doctype="Sales Order")
		meta = frappe.get_meta("Sales Order")
		columns = [f.fieldname for f in meta.fields if f.in_list_view]
		filters = [f.fieldname for f in meta.fields if f.in_standard_filter]
		self.assertIn("dz_wilaya", columns)
		self.assertIn("dz_phone", columns)
		self.assertNotIn("delivery_date", columns)
		self.assertNotIn("billing_status", filters)
		self.assertNotIn("company", filters)


class TestHomeGuide(IntegrationTestCase):
	def test_state_is_saved_for_the_user(self):
		for state in ("collapsed", "hidden", "open"):
			set_guide_state(state)
			self.assertEqual(frappe.defaults.get_user_default(GUIDE_KEY), state)

	def test_unknown_state_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			set_guide_state("deleted")
