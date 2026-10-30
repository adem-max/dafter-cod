"""Courier Settlement ("Versement"): money paid to us by a delivery company.

How it is used:
1. The courier sends a statement: a list of parcels, with the cash collected
   and its fee for each one, and transfers the net total.
2. Create a Versement, choose the courier, then either click
   "Charger les commandes livrées" (pre-fills one line per delivered order)
   or upload the courier's statement as CSV in the table.
3. Save: every line is matched to its order and gets a status
   (OK / Écart / Inconnue / Déjà réglée / Invalide), and the summary shows
   what is paid, what is disputed and what is missing.
   If an earlier Versement already paid part of the order (an Écart line not
   accepted), the line shows it in "Déjà versé" and only the rest is expected.
4. Submit: every OK line (and every Écart line you ticked "Accepter") moves
   its order to "Réglée". The others stay "Livrée" and keep showing in the
   "Encours transporteurs" report. One Journal Entry books the money: the
   bank, the courier's fees, and each order's invoice (cod/invoicing.py).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.workflow import apply_workflow
from frappe.utils import flt

from dz_cod.cod import settlement as rules
from dz_cod.cod import states as S
from dz_cod.cod.invoicing import cancel_settlement_entry, check_settlement_accounts, settlement_entry

ORDER_FIELDS = [
	"name",
	"workflow_state",
	"dz_courier",
	"dz_cod_amount",
	"dz_courier_fee",
	"dz_tracking_number",
]


class CourierSettlement(Document):
	def validate(self):
		if not self.bank_account:
			self.bank_account = frappe.db.get_single_value("COD Settings", "settlement_bank_account")
		self.match_lines()
		self.compute_summary()

	def before_submit(self):
		check_settlement_accounts(self)

	def on_submit(self):
		paid_lines = [line for line in self.items if rules.is_paid(line.status, line.accept_difference)]
		for line in paid_lines:
			order = frappe.get_doc("Sales Order", line.sales_order)
			order.flags.dz_event_date = self.posting_date
			apply_workflow(order, S.ACTION_SETTLE)
			frappe.db.set_value("Sales Order", order.name, "dz_settlement", self.name)
		self.db_set("journal_entry", settlement_entry(self))

	def before_cancel(self):
		"""Refuse when a later Versement settled an order on the rest of the
		money of this one: cancelling this one would leave it paid short."""
		for line in self.items:
			if not line.sales_order or line.status == rules.ALREADY_SETTLED:
				continue
			if rules.is_paid(line.status, line.accept_difference):
				continue
			settled_by = frappe.db.get_value("Sales Order", line.sales_order, "dz_settlement")
			if not settled_by:
				continue
			counted = frappe.db.get_value(
				"Courier Settlement Item",
				{"parent": settled_by, "sales_order": line.sales_order},
				"already_received",
			)
			if flt(counted):
				message = _("Ligne {0} : annulez d'abord {1}, qui a réglé {2} en comptant cette ligne.")
				frappe.throw(message.format(line.idx, settled_by, line.sales_order))

	def on_cancel(self):
		"""Put the orders paid by this settlement back to "Livrée".

		A Workflow cannot go backwards, so we write the fields directly.
		"""
		cancel_settlement_entry(self)  # the invoices are due again
		for name in frappe.get_all("Sales Order", filters={"dz_settlement": self.name}, pluck="name"):
			frappe.db.set_value(
				"Sales Order",
				name,
				{"workflow_state": S.DELIVERED, "dz_settlement": None, "dz_settled_on": None},
			)
			frappe.get_doc("Sales Order", name).add_comment(
				"Comment", _("Versement {0} annulé : retour à l'état {1}.").format(self.name, S.DELIVERED)
			)

	# ------------------------------------------------------------ matching

	def match_lines(self):
		"""Find the order of each line and decide its status."""
		tolerance = flt(frappe.db.get_single_value("COD Settings", "settlement_tolerance"))

		matches = [(line, self.find_order(line)) for line in self.items]
		seen_orders = set()
		for line, order in matches:
			if order and order.name in seen_orders:
				frappe.throw(
					_("Ligne {0} : la commande {1} apparaît deux fois.").format(line.idx, order.name)
				)
			if order:
				seen_orders.add(order.name)
		received = get_amounts_received(seen_orders, exclude_settlement=self.name)

		for line, order in matches:
			line.net_amount = flt(line.collected_amount) - flt(line.courier_fee)
			expected_net = 0
			if order:
				line.sales_order = order.name
				line.tracking_number = line.tracking_number or order.dz_tracking_number
				line.expected_amount = flt(order.dz_cod_amount)
				line.expected_fee = flt(order.dz_courier_fee)
				line.already_received = received.get(order.name, 0)
				expected_net = rules.remaining_due(
					line.expected_amount - line.expected_fee, line.already_received
				)
				line.difference = line.net_amount - expected_net
			else:
				line.expected_amount = line.expected_fee = line.already_received = line.difference = 0

			line.status = rules.line_status(
				order_state=order.workflow_state if order else None,
				order_courier=order.dz_courier if order else None,
				settlement_courier=self.courier,
				net_paid=line.net_amount,
				expected_net=expected_net,
				tolerance=tolerance,
			)

	def find_order(self, line):
		"""The line's order, by order name or else by tracking number: on this
		Versement's courier first, then on any courier, so another courier's
		parcel still shows as "Invalide" instead of going unnoticed (two
		couriers can number parcels alike; review of 27 October 2026, 2.4)."""
		if line.sales_order:
			tries = [{"name": line.sales_order}]
		elif line.tracking_number:
			tracking = {"dz_tracking_number": line.tracking_number.strip(), "docstatus": 1}
			tries = [{**tracking, "dz_courier": self.courier}, tracking]
		else:
			return None
		for filters in tries:
			orders = frappe.get_all("Sales Order", filters=filters, fields=ORDER_FIELDS, limit=1)
			if orders:
				return orders[0]
		return None

	# ------------------------------------------------------------- summary

	def compute_summary(self):
		self.total_collected = sum(flt(line.collected_amount) for line in self.items)
		self.total_fees = sum(flt(line.courier_fee) for line in self.items)
		self.total_net = self.total_collected - self.total_fees
		self.difference_received = flt(self.amount_received) - self.total_net if self.amount_received else 0

		self.paid_count = self.paid_amount = self.disputed_count = self.disputed_amount = 0
		for line in self.items:
			if rules.is_paid(line.status, line.accept_difference):
				self.paid_count += 1
				self.paid_amount += line.net_amount
			else:
				self.disputed_count += 1
				self.disputed_amount += rules.disputed_amount(line.status, line.net_amount, line.difference)

		missing = self.get_missing_orders()
		self.missing_count = len(missing)
		self.missing_amount = sum(
			rules.remaining_due(flt(o.dz_cod_amount) - flt(o.dz_courier_fee), o.already_received)
			for o in missing
		)

	def get_missing_orders(self):
		"""Orders this courier delivered up to the settlement date, not in this
		settlement and not paid yet, each with its `already_received`."""
		in_this_settlement = [line.sales_order for line in self.items if line.sales_order]
		filters = {
			"docstatus": 1,
			"workflow_state": S.DELIVERED,
			"dz_courier": self.courier,
			"dz_delivered_on": ["<=", self.posting_date],
		}
		if in_this_settlement:
			filters["name"] = ["not in", in_this_settlement]
		orders = frappe.get_all("Sales Order", filters=filters, fields=ORDER_FIELDS)
		received = get_amounts_received([o.name for o in orders], exclude_settlement=self.name)
		for order in orders:
			order.already_received = received.get(order.name, 0)
		return orders

	@frappe.whitelist()
	def load_delivered_orders(self):
		"""Button "Charger les commandes livrées": one line per missing order,
		pre-filled with what is still due (edit only the exceptions)."""
		for order in self.get_missing_orders():
			collected, fee = rules.prefill_amounts(
				flt(order.dz_cod_amount), flt(order.dz_courier_fee), order.already_received
			)
			self.append(
				"items",
				{
					"sales_order": order.name,
					"tracking_number": order.dz_tracking_number,
					"collected_amount": collected,
					"courier_fee": fee,
				},
			)
		self.validate()


def get_amounts_received(orders, exclude_settlement=None):
	"""{order: net already received} (dz_cod/cod/received.py)."""
	from dz_cod.cod.received import received

	return {order: amounts.net for order, amounts in received(orders, exclude=exclude_settlement).items()}
