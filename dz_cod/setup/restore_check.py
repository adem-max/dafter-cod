"""What scripts/restore_test.sh compares between a live site and its restored copy.

    bench --site <site> execute dz_cod.setup.restore_check.summary

prints one JSON object: how many records of each kind, the date of the last
order, and whether every stored password can be decrypted (it can only if the
site has the right encryption_key, see docs/DEPLOY.md step 9).
"""

import frappe
from frappe.utils.password import decrypt

COUNTED = [
	"Sales Order",
	"Delivery Note",
	"Courier Settlement",
	"Customer",
	"Item",
	"Stock Ledger Entry",
	"File",
	"User",
]


def summary():
	result = {doctype: frappe.db.count(doctype) for doctype in COUNTED}
	last = frappe.get_all("Sales Order", fields=["creation"], order_by="creation desc", limit=1)
	result["last_order"] = str(last[0].creation) if last else ""
	result["passwords"], result["passwords_unreadable"] = check_passwords()
	return result


def check_passwords():
	"""(stored passwords, how many cannot be decrypted with this site's key)."""
	rows = frappe.db.sql("select password from `__Auth` where encrypted = 1", as_dict=True)
	unreadable = 0
	for row in rows:
		try:
			decrypt(row.password)
		except Exception:
			unreadable += 1
	frappe.clear_messages()  # decrypt() leaves an error message per failure
	return len(rows), unreadable
