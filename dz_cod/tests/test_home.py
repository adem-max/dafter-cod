"""Integration tests: the per-user state of the welcome guide on the COD home page.

Run: bench --site <site> run-tests --module dz_cod.tests.test_home
"""

import frappe
from frappe.tests import IntegrationTestCase

from dz_cod.cod.home import GUIDE_KEY, set_guide_state


class TestHomeGuide(IntegrationTestCase):
	def test_state_is_saved_for_the_user(self):
		for state in ("collapsed", "hidden", "open"):
			set_guide_state(state)
			self.assertEqual(frappe.defaults.get_user_default(GUIDE_KEY), state)

	def test_unknown_state_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			set_guide_state("deleted")
