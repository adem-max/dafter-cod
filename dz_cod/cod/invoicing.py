"""Accounting of COD orders (DECISIONS.md, "COD accounting", from the SCF
advice of 21 October 2026).

- Livrée: the Delivery Note (out of "Chez transporteur", cod/stock.py), the
  invoice made from it (the legal Facture DZ, payment mode
  "Contre-remboursement", dated the delivery), and a Payment Entry that pays
  it into the courier's account 4671n: the buyer paid the courier, who now
  owes us that money (cod/accounts.py). The buyer owes nothing any more.
- A Versement then clears the courier's account in one Journal Entry
  (settlement_entry): the bank receives the net, the fees the courier kept
  go to its supplier account (its monthly invoice books them as 6241
  Transport sur ventes, with the TVA), each parcel's collection is credited
  to 4671n. An accepted short payment writes the rest off to 65882, money
  collected beyond what was due goes to 75882, and money for a parcel that
  matches no paid order waits in 4781 "Versements à identifier".

An order returned before delivery is never invoiced: nothing to undo.
Switched off with COD Settings' "Facturer à la livraison".
"""

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.party import get_party_account
from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
from frappe import _
from frappe.utils import flt

from dz_cod.cod import settlement as rules
from dz_cod.cod.accounts import courier_account
from dz_cod.cod.stock import set_posting_date
from dz_cod.dz_cod.doctype.cod_settings.cod_settings import get_settings

# dz_core's Sales Invoice field "Mode de paiement"
PAYMENT_MODE = "Contre-remboursement"

# COD Settings fields of the accounts a Versement needs, with their labels
SETTLEMENT_ACCOUNTS = {
	"settlement_difference_account": "Compte des écarts sur versements (pertes)",
	"settlement_gain_account": "Compte des écarts sur versements (gains)",
	"unmatched_settlement_account": "Compte des versements à identifier",
}
VOUCHER_TYPES = {"Bank": "Bank Entry", "Cash": "Cash Entry"}


# ------------------------------------------------------------ Livrée


def invoice_delivered_order(order, posting_date=None):
	"""The order's invoice, made from its delivery note, submitted, linked on
	the order (dz_sales_invoice) and paid into the courier's account
	(dz_payment_entry). Once per order. Returns the invoice's name."""
	if not get_settings().invoice_on_delivery or not order.dz_delivery_note or order.dz_sales_invoice:
		return None
	# The workflow checked who may mark it delivered (a Stock User may, with no
	# right on invoices): ERPNext's mapper checks "create" on the target it is
	# given, and that check honours the target's ignore_permissions flag
	target = frappe.new_doc("Sales Invoice")
	target.flags.ignore_permissions = True
	invoice = make_sales_invoice(order.dz_delivery_note, target_doc=target)
	set_posting_date(invoice, posting_date)
	invoice.due_date = invoice.posting_date  # paid to the courier on delivery
	invoice.dz_payment_mode = PAYMENT_MODE
	invoice.flags.ignore_permissions = True
	invoice.insert()
	invoice.submit()
	order.db_set("dz_sales_invoice", invoice.name)
	order.db_set("dz_payment_entry", pay_to_courier(order, invoice))
	return invoice.name


def pay_to_courier(order, invoice):
	"""The buyer paid the courier: the invoice is paid, into the courier's
	account 4671n. Returns the Payment Entry's name."""
	# ERPNext's builder refuses a user who may not create payments (a Stock
	# User marking the order delivered), with no flag to skip it. Only the
	# builder runs as Administrator: it returns an unsaved document, which is
	# then inserted and submitted as the real user, so its owner and the audit
	# trail name who marked the order delivered.
	user = frappe.session.user
	try:
		frappe.set_user("Administrator")
		payment = get_payment_entry("Sales Invoice", invoice.name)
	finally:
		frappe.set_user(user)
	payment.paid_to = courier_account(order.dz_courier, order.company)
	payment.paid_to_account_currency = frappe.get_cached_value("Account", payment.paid_to, "account_currency")
	payment.mode_of_payment = None
	payment.posting_date = invoice.posting_date
	payment.reference_no = order.dz_tracking_number or order.name
	payment.reference_date = invoice.posting_date
	payment.remarks = _("Encaissé par {0} à la livraison de la commande {1}").format(
		order.dz_courier, order.name
	)
	payment.flags.ignore_permissions = True
	payment.insert()
	payment.submit()
	return payment.name


# ------------------------------------------------------------ the Versement


def settlement_entry(settlement):
	"""Book a submitted Versement in one Journal Entry. Returns its name, or
	None when invoicing is off or there is nothing to book."""
	settings = get_settings()
	if not settings.invoice_on_delivery:
		return None
	accounts = settlement_accounts(settings, settlement)
	plain = {}  # account -> amount (debit > 0, credit < 0)

	def book(account, amount):
		plain[account] = plain.get(account, 0) + amount

	for line in settlement.items:
		collected = flt(line.collected_amount)
		claim = courier_claim(line, settlement)
		if claim is None:
			book(accounts.unmatched, -collected)  # a parcel we cannot match: to check
			continue
		cleared = min(collected, max(claim, 0))
		book(accounts.courier, -cleared)
		book(accounts.gain, -(collected - cleared))  # collected more than the parcel was worth
		if rules.is_paid(line.status, line.accept_difference) and claim - cleared > 0:
			book(accounts.courier, -(claim - cleared))  # accepted short: written off
			book(accounts.loss, claim - cleared)

	received = flt(settlement.amount_received) if settlement.amount_received else flt(settlement.total_net)
	book(accounts.bank, received)
	# The transfer differs from the statement's net total: to check as well
	book(accounts.unmatched, -(received - flt(settlement.total_net)))

	cost_center = frappe.get_cached_value("Company", settlement.company, "cost_center")
	rows = [{"account": account, **sides(amount)} for account, amount in plain.items()]
	fees = sum(flt(line.courier_fee) for line in settlement.items)
	if fees:
		# what the courier kept, against the invoice it sends for its services
		rows.append(
			{
				"account": accounts.courier_payable,
				"party_type": "Supplier",
				"party": settlement.courier,
				**sides(fees),
			}
		)
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


def courier_claim(line, settlement):
	"""What the courier still owes on the line's parcel, before this line:
	the order's amount to collect minus what earlier Versements collected for
	it. None when the line is not booked against a paid order (Inconnue,
	Invalide, Déjà réglée, or an order delivered before invoicing)."""
	if line.status not in (rules.OK, rules.GAP) or not line.sales_order:
		return None
	order = frappe.db.get_value(
		"Sales Order", line.sales_order, ["dz_cod_amount", "dz_payment_entry"], as_dict=True
	)
	if not order or not order.dz_payment_entry:
		return None
	collected_before = frappe.db.sql(
		"""SELECT IFNULL(SUM(item.collected_amount), 0)
		FROM `tabCourier Settlement Item` item
		JOIN `tabCourier Settlement` cs ON cs.name = item.parent
		WHERE item.sales_order = %s AND cs.docstatus = 1 AND cs.name != %s""",
		(line.sales_order, settlement.name),
	)[0][0]
	return flt(order.dz_cod_amount) - flt(collected_before)


def cancel_settlement_entry(settlement):
	"""Cancelling a Versement cancels its Journal Entry: the courier owes the money again."""
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
		courier=courier_account(settlement.courier, settlement.company),
		courier_payable=get_party_account("Supplier", settlement.courier, settlement.company),
		loss=settings.settlement_difference_account,
		gain=settings.settlement_gain_account,
		unmatched=settings.unmatched_settlement_account,
	)


def sides(amount):
	"""Debit for an amount above 0, credit below."""
	amount = flt(amount, 2)
	return {"debit_in_account_currency": max(amount, 0), "credit_in_account_currency": max(-amount, 0)}
