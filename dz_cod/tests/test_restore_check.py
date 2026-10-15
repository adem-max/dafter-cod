"""Integration tests: what scripts/restore_test.sh compares after a restore.

Run: bench --site <site> run-tests --module dz_cod.tests.test_restore_check
"""

import frappe
from cryptography.fernet import Fernet
from frappe.tests import IntegrationTestCase
from frappe.utils.password import set_encrypted_password

from dz_cod.setup.restore_check import summary


class TestRestoreCheck(IntegrationTestCase):
	def test_summary_counts_records(self):
		result = summary()
		self.assertEqual(result["Sales Order"], frappe.db.count("Sales Order"))
		self.assertIn("last_order", result)

	def test_a_password_from_another_key_is_reported(self):
		set_encrypted_password("Supplier", "Restore check", "token", "dz_api_token")
		before = summary()
		self.assertEqual(before["passwords_unreadable"], 0)

		# Same stored value, but this site now has another encryption key,
		# as after a restore without the original site_config
		original_key = frappe.local.conf.encryption_key
		frappe.local.conf.encryption_key = Fernet.generate_key().decode()
		try:
			after = summary()
		finally:
			frappe.local.conf.encryption_key = original_key
		self.assertEqual(after["passwords_unreadable"], 1)
		self.assertEqual(after["passwords"], before["passwords"])
