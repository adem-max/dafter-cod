"""dz_cod's checks in dz_core's report "Clôture du mois" (hook
dz_closing_checks, dz_core/closing.py): the couriers' accounts.

- Each courier's 4671n account must equal what it still owes for the parcels
  it delivered up to the month end: their amount to collect, less what the
  Versements up to that day collected, nothing for a parcel a Versement
  settled (Réglée).
- A courier whose supplier account has a debit balance kept fees in
  Versements whose invoice is not entered yet (6241 + TVA).
"""

import frappe
from dz_core.closing import balance, row
from erpnext.accounts.party import get_party_account
from frappe import _
from frappe.utils import flt


def checks(company, start, end):
	rows = []
	for courier, account in frappe.get_all(
		"Supplier", filters={"dz_cod_account": ["is", "set"]}, fields=["name", "dz_cod_account"], as_list=True
	):
		if frappe.db.get_value("Account", account, "company") != company:
			continue
		owed = balance(company, [account], end)
		expected = still_owed(courier, company, end)
		rows.append(
			row(
				_("{0} : encaissements à reverser égaux aux colis livrés non réglés").format(courier),
				owed - expected,
				abs(owed - expected) < 0.01,
				_(
					"Écart entre le compte {0} et les colis livrés non réglés : voyez les versements du transporteur."
				).format(account),
			)
		)
		payable = get_party_account("Supplier", courier, company)
		fees = frappe.db.sql(
			"""SELECT SUM(debit - credit) FROM `tabGL Entry` WHERE company = %s AND account = %s
			AND party_type = 'Supplier' AND party = %s AND is_cancelled = 0 AND posting_date <= %s""",
			(company, payable, courier, end),
		)[0][0]
		rows.append(
			row(
				_("{0} : frais retenus couverts par ses factures").format(courier),
				flt(fees),
				flt(fees) <= 0.01,
				_("Saisissez la facture du transporteur pour ses frais retenus (6241 et la TVA)."),
			)
		)
	return rows


def still_owed(courier, company, end):
	"""What the courier owes for its parcels delivered up to `end`: their
	amount to collect, less what Versements up to `end` booked against them
	(cod/received.py), nothing for a parcel a Versement settled by then."""
	from dz_cod.cod.received import received

	orders = frappe.db.sql(
		"""SELECT so.name, so.dz_cod_amount FROM `tabSales Order` so
		WHERE so.company = %(company)s AND so.dz_courier = %(courier)s
			AND IFNULL(so.dz_payment_entry, '') != '' AND so.dz_delivered_on <= %(end)s
			AND NOT EXISTS (
				SELECT 1 FROM `tabCourier Settlement` settled
				WHERE settled.name = so.dz_settlement AND settled.docstatus = 1 AND settled.posting_date <= %(end)s
			)""",
		{"company": company, "courier": courier, "end": end},
		as_dict=True,
	)
	before = received([order.name for order in orders], until=end)
	return flt(
		sum(
			flt(order.dz_cod_amount) - (before[order.name].gross if order.name in before else 0)
			for order in orders
		)
	)
