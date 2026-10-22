"""The Versements were booked to the bank the setup wizard had put in the
Company's defaults (5176 "Société de bourse"). Since 21 October 2026 dz_core
puts 5121 "Comptes bancaires : Dinars" there (dz_core setup/accounts.py):
COD Settings follows, unless someone chose another bank."""

import frappe
from dz_core.setup.accounts import REPLACEABLE, set_default_accounts


def execute():
	company = frappe.db.get_single_value("COD Settings", "company")
	current = frappe.db.get_single_value("COD Settings", "settlement_bank_account")
	if not company or not current:
		return
	if frappe.db.get_value("Account", current, "account_number") not in REPLACEABLE["default_bank_account"]:
		return
	set_default_accounts(company)  # done by dz_core's patch already, unless it was skipped
	bank = frappe.db.get_value("Company", company, "default_bank_account")
	if bank and bank != current:
		frappe.db.set_single_value("COD Settings", "settlement_bank_account", bank)
