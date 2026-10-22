"""The accounts and records COD needs on top of dz_core's SCF set-up
(DECISIONS.md, "COD accounting", from the SCF advice of 21 October 2026).

- Each courier holds the cash it collects for us until it pays it over: a
  claim on the courier, in its own account 4671n "Transporteur X -
  encaissements à reverser" (under 4671). Typed Cash in ERPNext only so a
  Payment Entry can use it; the SCF reports show it in class 4.
- Couriers are service suppliers: their group pays from 40162 (advances
  40916), so their monthly invoice (6241 Transport sur ventes + TVA) and the
  fees they withhold from a Versement meet on their supplier account.
- The Versements: short payments to 65882, overpayments to 75882 (gains and
  losses never netted), unidentified receipts to 4781.
- The delivery fee is an item line (FEE_ITEM), taxed like the goods: its
  group credits 7088 "Autres produits d'activités annexes".
- Parcels in the courier's hands sit in the "Chez transporteur" warehouse.
"""

import frappe
from dz_core.setup.accounts import account_by_number, first_account
from dz_core.setup.parties import set_supplier_group_accounts
from frappe.utils.nestedset import get_root_of

COURIER_GROUP = "Transporteurs"
COURIER_ACCOUNTS_GROUP = "4671"  # Transporteurs : encaissements à reverser
COURIER_ACCOUNT_NAME = "Transporteur {} - encaissements à reverser"

FEE_ITEM = "FRAIS-LIVRAISON"
FEE_ITEM_NAME = "Frais de livraison"
FEE_GROUP = "Frais de livraison facturés"
SHIPPING_INCOME = "7088"  # Autres produits d'activités annexes

IN_TRANSIT_WAREHOUSE = "Chez transporteur"

# COD Settings field -> SCF numbers, in order of preference
SETTLEMENT_ACCOUNTS = {
	"settlement_difference_account": ("65882", "6588"),  # Écarts de règlement (pertes)
	"settlement_gain_account": ("75882", "7588"),  # Écarts de règlement (gains)
	"unmatched_settlement_account": ("4781",),  # Versements à identifier
}


def settlement_accounts(company):
	"""{COD Settings field: account} to book the Versements and the fee."""
	accounts = {field: first_account(company, numbers) for field, numbers in SETTLEMENT_ACCOUNTS.items()}
	accounts["settlement_bank_account"] = frappe.get_cached_value("Company", company, "default_bank_account")
	accounts["shipping_income_account"] = account_by_number(company, SHIPPING_INCOME)
	return accounts


def courier_account(courier, company):
	"""The courier's 4671n account, made the first time it is needed and kept
	on the courier (Supplier field dz_cod_account)."""
	account = frappe.db.get_value("Supplier", courier, "dz_cod_account")
	if account and frappe.db.get_value("Account", account, "company") == company:
		return account
	group = frappe.db.get_value(
		"Account", {"company": company, "account_number": COURIER_ACCOUNTS_GROUP, "is_group": 1}
	)
	if not group:
		frappe.throw(f"Compte {COURIER_ACCOUNTS_GROUP} introuvable : lancez la mise en place SCF (dz_core).")
	name = COURIER_ACCOUNT_NAME.format(frappe.db.get_value("Supplier", courier, "supplier_name"))
	# a courier made again under the same name (the demo reload) gets its account back
	account = frappe.db.get_value(
		"Account", {"company": company, "parent_account": group, "account_name": name, "is_group": 0}
	)
	if account:
		frappe.db.set_value("Supplier", courier, "dz_cod_account", account)
		return account
	numbers = frappe.get_all("Account", filters={"parent_account": group}, pluck="account_number")
	number = next(
		f"{COURIER_ACCOUNTS_GROUP}{n}" for n in range(1, 100) if f"{COURIER_ACCOUNTS_GROUP}{n}" not in numbers
	)
	account = (
		frappe.get_doc(
			{
				"doctype": "Account",
				"company": company,
				"account_name": name,
				"account_number": number,
				"parent_account": group,
				"account_type": "Cash",  # so a Payment Entry may pay into it
			}
		)
		.insert(ignore_permissions=True)
		.name
	)
	frappe.db.set_value("Supplier", courier, "dz_cod_account", account)
	return account


def setup_cod_accounts(company):
	"""Courier group accounts, the delivery fee item and the in-transit
	warehouse. Safe to run again."""
	if not frappe.db.exists("Supplier Group", COURIER_GROUP):
		frappe.get_doc(
			{
				"doctype": "Supplier Group",
				"supplier_group_name": COURIER_GROUP,
				"parent_supplier_group": get_root_of("Supplier Group"),
			}
		).insert(ignore_permissions=True)
	set_supplier_group_accounts(company, COURIER_GROUP, "40162", "40916")
	ensure_fee_item(company)
	return in_transit_warehouse(company)


def ensure_fee_item(company):
	"""The delivery fee item (non-stock) and its group, crediting 7088 (an
	account already set on the group for the company is kept)."""
	from dz_core.setup.item_groups import fill
	from dz_core.setup.tax import set_group_tax

	if not frappe.db.exists("Item Group", FEE_GROUP):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": FEE_GROUP,
				"parent_item_group": get_root_of("Item Group"),
			}
		).insert(ignore_permissions=True)
	fill(company, FEE_GROUP, {"income_account": SHIPPING_INCOME})
	set_group_tax(company, FEE_GROUP)  # taxed like the goods: 19 % (CTCA art. 15)
	if not frappe.db.exists("Item", FEE_ITEM):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": FEE_ITEM,
				"item_name": FEE_ITEM_NAME,
				"item_group": FEE_GROUP,
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"include_item_in_manufacturing": 0,
			}
		).insert(ignore_permissions=True)
	return FEE_ITEM


def in_transit_warehouse(company):
	"""The company's "Chez transporteur" warehouse, created if missing."""
	abbr = frappe.get_cached_value("Company", company, "abbr")
	name = f"{IN_TRANSIT_WAREHOUSE} - {abbr}"
	if not frappe.db.exists("Warehouse", name):
		root = frappe.db.get_value(
			"Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ["is", "not set"]}
		)
		frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": IN_TRANSIT_WAREHOUSE,
				"company": company,
				"parent_warehouse": root,
			}
		).insert(ignore_permissions=True)
	return name
