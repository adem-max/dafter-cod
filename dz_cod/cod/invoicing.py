"""Accounting of COD orders (DECISIONS.md, "COD accounting").

- Livrée: the order is invoiced from its delivery note (ERPNext's
  make_sales_invoice, as dz_core's demo engine does), dated the delivery and
  due that day, payment mode "Contre-remboursement": the customer paid the
  courier. It is the legal invoice (Facture DZ), and dz_core's sales reports
  and home page count it.
- A Versement then books what the courier paid in one Journal Entry
  (settlement_entry): the bank and the courier's fees on the debit side, each
  customer's invoice credited with what the courier collected. A line paid
  short but accepted is written off to the differences account; money for a
  parcel that matches no invoiced order waits in "Versements à identifier".

An order returned before delivery is never invoiced: nothing to undo.
Switched off with COD Settings' "Facturer à la livraison".
"""

import frappe
from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
from frappe import _
from frappe.utils import flt

from dz_cod.cod import settlement as rules
from dz_cod.cod.stock import set_posting_date
from dz_cod.dz_cod.doctype.cod_settings.cod_settings import get_settings

# dz_core's Sales Invoice field "Mode de paiement"
PAYMENT_MODE = "Contre-remboursement"

# A Versement line is booked against its order's invoice when it is OK or a
# difference; Inconnue, Invalide and Déjà réglée wait in the unmatched account
INVOICED_STATUSES = (rules.OK, rules.GAP)

# COD Settings fields of the accounts a Versement needs, with their labels
SETTLEMENT_ACCOUNTS = {
	"courier_fee_account": "Compte des frais transporteurs",
	"settlement_difference_account": "Compte des écarts sur versements",
	"unmatched_settlement_account": "Compte des versements à identifier",
}
VOUCHER_TYPES = {"Bank": "Bank Entry", "Cash": "Cash Entry"}


# ------------------------------------------------------------ Livrée: the invoice


def invoice_delivered_order(order, posting_date=None):
	"""The order's invoice, made from its delivery note, submitted and linked on
	the order (dz_sales_invoice). Once per order. Returns its name."""
	if not get_settings().invoice_on_delivery or not order.dz_delivery_note or order.dz_sales_invoice:
		return None
	invoice = frappe.get_doc(make_sales_invoice(order.dz_delivery_note))
	set_posting_date(invoice, posting_date)
	invoice.due_date = invoice.posting_date  # paid to the courier on delivery
	invoice.dz_payment_mode = PAYMENT_MODE
	invoice.flags.ignore_permissions = True  # the workflow checked who may mark it delivered
	invoice.insert()
	invoice.submit()
	order.db_set("dz_sales_invoice", invoice.name)
	return invoice.name


# ------------------------------------------------------------ the Versement


def settlement_entry(settlement):
	"""Book a submitted Versement in one Journal Entry. Returns its name, or
	None when invoicing is off or there is nothing to book."""
	settings = get_settings()
	if not settings.invoice_on_delivery:
		return None
	accounts = settlement_accounts(settings, settlement)
	plain = {}  # account -> amount (debit > 0, credit < 0)
	against_invoices = []  # (invoice, amount) on the customer's receivable

	def book(account, amount):
		plain[account] = plain.get(account, 0) + amount

	for line in settlement.items:
		collected = flt(line.collected_amount)
		invoice = invoice_of(line)
		if not invoice:
			book(accounts.unmatched, -collected)  # a parcel we cannot match: to check
			continue
		due = flt(invoice.outstanding_amount)
		paid = min(collected, due)
		against_invoices.append((invoice, -paid))
		book(accounts.difference, -(collected - paid))  # collected more than the invoice
		if rules.is_paid(line.status, line.accept_difference) and due - paid > 0:
			against_invoices.append((invoice, -(due - paid)))  # accepted short: written off
			book(accounts.difference, due - paid)

	received = flt(settlement.amount_received) if settlement.amount_received else flt(settlement.total_net)
	book(accounts.bank, received)
	book(accounts.fees, sum(flt(line.courier_fee) for line in settlement.items))
	# The transfer differs from the statement's net total: to check as well
	book(accounts.unmatched, -(received - flt(settlement.total_net)))

	cost_center = frappe.get_cached_value("Company", settlement.company, "cost_center")
	rows = [{"account": account, **sides(amount)} for account, amount in plain.items()]
	rows += [
		{
			"account": invoice.debit_to,
			"party_type": "Customer",
			"party": invoice.customer,
			"reference_type": "Sales Invoice",
			"reference_name": invoice.name,
			**sides(amount),
		}
		for invoice, amount in against_invoices
	]
	rows = [row for row in rows if row["debit_in_account_currency"] or row["credit_in_account_currency"]]
	if not rows:
		return None

	entry = frappe.new_doc("Journal Entry")
	entry.update(
		{
			"voucher_type": VOUCHER_TYPES.get(
				frappe.db.get_value("Account", accounts.bank, "account_type"), "Journal Entry"
			),
			"company": settlement.company,
			"posting_date": settlement.posting_date,
			"cheque_no": settlement.reference or settlement.name,
			"cheque_date": settlement.posting_date,
			"user_remark": _("Versement {0} de {1}").format(settlement.name, settlement.courier),
		}
	)
	for row in rows:
		entry.append("accounts", {**row, "cost_center": cost_center})
	entry.flags.ignore_permissions = True  # the Versement's own permission was checked
	entry.insert()
	entry.submit()
	return entry.name


def cancel_settlement_entry(settlement):
	"""Cancelling a Versement cancels its Journal Entry: the invoices are due again."""
	if (
		settlement.journal_entry
		and frappe.db.get_value("Journal Entry", settlement.journal_entry, "docstatus") == 1
	):
		entry = frappe.get_doc("Journal Entry", settlement.journal_entry)
		entry.flags.ignore_permissions = True
		entry.cancel()


def check_settlement_accounts(settlement):
	"""Before a Versement is submitted: refuse it while an account is missing,
	before any order moves."""
	settings = get_settings()
	if settings.invoice_on_delivery:
		settlement_accounts(settings, settlement)


def settlement_accounts(settings, settlement):
	missing = [label for field, label in SETTLEMENT_ACCOUNTS.items() if not settings.get(field)]
	bank = settlement.bank_account or settings.settlement_bank_account
	if not bank:
		missing.insert(0, "Compte des versements")
	if missing:
		frappe.throw(
			_("Renseignez dans les Paramètres COD : {0}.").format(", ".join(_(label) for label in missing))
		)
	return frappe._dict(
		bank=bank,
		fees=settings.courier_fee_account,
		difference=settings.settlement_difference_account,
		unmatched=settings.unmatched_settlement_account,
	)


def invoice_of(line):
	"""The submitted invoice of the line's order, when the line is booked against it."""
	if line.status not in INVOICED_STATUSES or not line.sales_order:
		return None
	name = frappe.db.get_value("Sales Order", line.sales_order, "dz_sales_invoice")
	if not name:
		return None
	return frappe.db.get_value(
		"Sales Invoice",
		{"name": name, "docstatus": 1},
		["name", "customer", "debit_to", "outstanding_amount"],
		as_dict=True,
	)


def sides(amount):
	"""Debit for an amount above 0, credit below."""
	amount = flt(amount, 2)
	return {"debit_in_account_currency": max(amount, 0), "credit_in_account_currency": max(-amount, 0)}
