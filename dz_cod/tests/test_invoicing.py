"""COD accounting (dz_cod/cod/invoicing.py): an order is invoiced when it
becomes Livrée, and a Versement is booked in one Journal Entry.

Run: bench --site <site> run-tests --module dz_cod.tests.test_invoicing
"""

import frappe
from frappe import _
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, getdate

from dz_cod.cod import states as S
from dz_cod.cod.invoicing import PAYMENT_MODE, invoice_delivered_order
from dz_cod.cod.shipping import SHIPPING_DESCRIPTION
from dz_cod.tests import helpers as h
from dz_cod.tests.test_settlement import delivered_order, new_settlement


def cod_setting(field, value):
	frappe.db.set_single_value("COD Settings", field, value)
	frappe.clear_document_cache("COD Settings", "COD Settings")


def outstanding(order):
	invoice = frappe.db.get_value("Sales Order", order.name, "dz_sales_invoice")
	return flt(frappe.db.get_value("Sales Invoice", invoice, "outstanding_amount"))


def entry_amounts(name):
	"""{account: debit - credit} of a Journal Entry, customers' lines left out."""
	amounts = {}
	for row in frappe.get_doc("Journal Entry", name).accounts:
		if not row.party:
			amounts[row.account] = amounts.get(row.account, 0) + row.debit - row.credit
	return amounts


class TestInvoiceAtDelivery(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()

	def test_livree_makes_the_invoice(self):
		order = delivered_order()
		self.assertTrue(order.dz_sales_invoice)
		invoice = frappe.get_doc("Sales Invoice", order.dz_sales_invoice)
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(invoice.customer, order.customer)
		self.assertEqual(flt(invoice.rounded_total or invoice.grand_total), flt(order.dz_cod_amount))
		self.assertEqual(invoice.dz_payment_mode, PAYMENT_MODE)
		self.assertEqual(getdate(invoice.posting_date), getdate(order.dz_delivered_on))
		self.assertEqual(getdate(invoice.due_date), getdate(invoice.posting_date))
		fee = [tax for tax in invoice.taxes if tax.description == SHIPPING_DESCRIPTION]
		self.assertEqual(flt(fee[0].tax_amount), 400)  # the delivery fee, Alger home delivery
		self.assertEqual(frappe.db.get_value("Sales Order", order.name, "per_billed"), 100)
		self.assertIsNone(invoice_delivered_order(order))  # once per order

	def test_no_invoice_before_delivery_or_when_switched_off(self):
		returned = h.act(h.make_order(), S.ACTION_CONFIRM, S.ACTION_PREPARE, S.ACTION_SHIP, S.ACTION_RETURN)
		self.assertFalse(returned.dz_sales_invoice)
		cod_setting("invoice_on_delivery", 0)
		try:
			self.assertFalse(delivered_order().dz_sales_invoice)
		finally:
			cod_setting("invoice_on_delivery", 1)


class TestSettlementEntry(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()

	def line(self, order, gap=0, accept=0):
		return {
			"sales_order": order.name,
			"collected_amount": order.dz_cod_amount + gap,
			"courier_fee": order.dz_courier_fee,
			"accept_difference": accept,
		}

	def test_a_versement_is_booked_then_cancelled(self):
		ok, short_ok, short_open, over = (delivered_order() for _ in range(4))
		settlement = new_settlement(
			[
				self.line(ok),
				self.line(short_ok, gap=-500, accept=1),  # paid short, accepted: written off
				self.line(short_open, gap=-300),  # paid short, not accepted: 300 still due
				self.line(over, gap=200, accept=1),  # paid 200 too much
				{"tracking_number": "INCONNU-0001", "collected_amount": 1000, "courier_fee": 100},
			]
		)
		settlement.amount_received = settlement.total_net + 50  # the transfer is 50 DA above the statement
		settlement.save()
		settlement.submit()

		self.assertTrue(settlement.journal_entry)
		entry = frappe.get_doc("Journal Entry", settlement.journal_entry)
		self.assertEqual(entry.docstatus, 1)
		self.assertEqual([outstanding(o) for o in (ok, short_ok, short_open, over)], [0, 0, 300, 0])

		settings = frappe.get_cached_doc("COD Settings")
		amounts = entry_amounts(entry.name)
		self.assertAlmostEqual(amounts[settlement.bank_account], settlement.amount_received, 2)
		self.assertAlmostEqual(amounts[settings.courier_fee_account], settlement.total_fees, 2)
		# 500 written off, 200 received too much
		self.assertAlmostEqual(amounts[settings.settlement_difference_account], 500 - 200, 2)
		# the unknown parcel and the 50 DA: to check with the courier
		self.assertAlmostEqual(amounts[settings.unmatched_settlement_account], -1050, 2)
		states = [
			frappe.db.get_value("Sales Order", o.name, "workflow_state")
			for o in (ok, short_ok, short_open, over)
		]
		self.assertEqual(states, [S.SETTLED, S.SETTLED, S.DELIVERED, S.SETTLED])

		settlement.cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", entry.name, "docstatus"), 2)
		self.assertEqual(outstanding(ok), flt(ok.dz_cod_amount))
		self.assertEqual(frappe.db.get_value("Sales Order", ok.name, "workflow_state"), S.DELIVERED)

	def test_missing_accounts_are_named(self):
		account = frappe.db.get_single_value("COD Settings", "courier_fee_account")
		cod_setting("courier_fee_account", None)
		try:
			order = delivered_order()
			settlement = new_settlement([self.line(order)])
			with self.assertRaises(frappe.ValidationError) as error:
				settlement.submit()
			# Compared in the active language: another test may have switched it
			self.assertIn(_("Compte des frais transporteurs"), str(error.exception))
			# refused before anything moved
			self.assertEqual(frappe.db.get_value("Sales Order", order.name, "workflow_state"), S.DELIVERED)
		finally:
			cod_setting("courier_fee_account", account)

	def test_settlement_bank_follows_the_company_bank(self):
		from dz_core.setup.accounts import account_by_number

		from dz_cod.patches import settlement_bank_follows_company

		bank = frappe.db.get_single_value("COD Settings", "settlement_bank_account")
		company = frappe.db.get_single_value("COD Settings", "company")
		try:
			# the bank the setup wizard had picked (5176 Société de bourse) is replaced
			wizard_bank = frappe.db.get_value("Account", {"company": company, "account_number": "5176"})
			cod_setting(
				"settlement_bank_account", wizard_bank
			)  # disabled since 0.3.0, so not by account_by_number
			settlement_bank_follows_company.execute()
			self.assertEqual(
				frappe.db.get_single_value("COD Settings", "settlement_bank_account"),
				frappe.db.get_value("Company", company, "default_bank_account"),
			)
			# a bank someone chose is kept
			ccp = account_by_number(company, "5171")
			cod_setting("settlement_bank_account", ccp)
			settlement_bank_follows_company.execute()
			self.assertEqual(frappe.db.get_single_value("COD Settings", "settlement_bank_account"), ccp)
		finally:
			cod_setting("settlement_bank_account", bank)
