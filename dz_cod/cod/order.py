"""Sales Order hooks: what happens at each step of the COD order life cycle.

The Workflow (setup/workflow.py) decides WHO may move an order and WHERE to.
This file decides WHAT HAPPENS when it moves. It is wired in hooks.py
("doc_events" for "Sales Order").

    Nouvelle ──Confirmer──> Confirmée ──Préparer──> Préparée ──Expédier──> Expédiée
       │  ▲                     │                     │                   │     │
       │  └─ Injoignable        └─────Annuler─────────┘          Livrée <─┘     └─> Retournée
       └──Annuler──> Annulée            │                          │
                          Annulée après confirmation           Réglée

How ERPNext sees it:
- Nouvelle / Injoignable / Annulée: the Sales Order is a DRAFT (docstatus 0).
- Confirmer = SUBMIT the Sales Order. ERPNext reserves the stock.
- Other moves on a submitted order = "update after submit". We look at which
  state the order just entered and act (create delivery note, return, ...).
- Annulée après confirmation = CANCEL the Sales Order. ERPNext un-reserves.
"""

import frappe
from dz_core.phone import is_valid_phone, normalize_phone
from frappe import _
from frappe.utils import flt, today

from dz_cod.cod import states as S
from dz_cod.cod import stock
from dz_cod.cod.phone_checks import warn_refused_parcels
from dz_cod.cod.shipping import apply_shipping_charge, get_rates
from dz_cod.couriers import get_adapter
from dz_cod.dz_cod.doctype.cod_settings.cod_settings import get_settings


def event_date(order):
	"""Date of the current step: today, unless the demo loader set another one
	in order.flags.dz_event_date (to create history in the past)."""
	return order.flags.get("dz_event_date") or today()


# ---------------------------------------------------------------- draft order


def before_validate(order, method=None):
	"""Runs on every save of a draft order, before ERPNext computes totals."""
	if order.docstatus != 0:
		return

	settings = get_settings()
	order.dz_phone = normalize_phone(order.dz_phone)
	order.dz_phone_2 = normalize_phone(order.dz_phone_2)
	if not order.dz_courier:
		order.dz_courier = settings.default_courier

	# Every line ships from the main warehouse unless the user chose another
	if not order.set_warehouse:
		order.set_warehouse = settings.main_warehouse
	for row in order.items:
		if not row.warehouse:
			row.warehouse = order.set_warehouse

	apply_shipping_charge(order)


def validate(order, method=None):
	"""Runs after ERPNext computed the totals: store the amount to collect,
	and warn if this phone already had parcels sent back."""
	if order.docstatus == 0:
		order.dz_cod_amount = flt(order.rounded_total or order.grand_total)
		if not order.flags.get("dz_event_date"):  # the demo loader replays history quietly
			warn_refused_parcels(order)


# ------------------------------------------------------------ confirmation


def before_submit(order, method=None):
	"""Confirmer: check the order is complete before reserving stock."""
	check_delivery_details(order)
	if not order.flags.get("dz_event_date"):
		warn_refused_parcels(order)
	if order.dz_courier:
		# e.g. Yalidine: the commune must be one the courier knows
		get_adapter(order.dz_courier).check_order(order)

	problems = stock.check_available_stock(order)
	if problems:
		message = _("Stock insuffisant :") + "<br>" + "<br>".join(problems)
		if get_settings().block_confirmation_without_stock:
			frappe.throw(message, title=_("Confirmation impossible"))
		frappe.msgprint(message, title=_("Attention"), indicator="orange")

	_customer_rate, courier_cost = get_rates(order.dz_wilaya, order.dz_delivery_type)
	order.dz_courier_fee = courier_cost
	order.dz_confirmed_on = event_date(order)


def check_delivery_details(order):
	"""The courier needs a valid phone and a full address."""
	missing = []
	if not is_valid_phone(order.dz_phone):
		missing.append(_("un numéro de téléphone valide (ex. 0555123456)"))
	if not order.dz_wilaya:
		missing.append(_("la wilaya"))
	if order.dz_delivery_type == "Domicile" and not (order.dz_commune and order.dz_address):
		missing.append(_("la commune et l'adresse (livraison à domicile)"))
	if missing:
		frappe.throw(_("Impossible de confirmer, il manque : {0}").format(", ".join(missing)))


# ------------------------------------------------ moves after confirmation


def before_update_after_submit(order, method=None):
	"""Checks and dates, BEFORE a submitted order is saved in its new state."""
	if not order.has_value_changed("workflow_state"):
		return

	state = order.workflow_state
	if state == S.SHIPPED:
		prepare_shipment(order)
		order.dz_shipped_on = event_date(order)
	elif state == S.DELIVERED:
		order.dz_delivered_on = event_date(order)
	elif state == S.RETURNED:
		order.dz_returned_on = event_date(order)
	elif state == S.SETTLED:
		order.dz_settled_on = event_date(order)


def on_update_after_submit(order, method=None):
	"""Stock movements, AFTER the order is saved in its new state."""
	if not order.has_value_changed("workflow_state"):
		return

	state = order.workflow_state
	if state == S.SHIPPED:
		delivery_note = stock.create_delivery_note(order, event_date(order))
		order.db_set("dz_delivery_note", delivery_note)
	elif state == S.RETURNED:
		return_note = stock.create_return(order, event_date(order))
		order.db_set("dz_return_note", return_note)
		stock.close_order(order.name)


def prepare_shipment(order):
	"""Expédier: we need a courier and a tracking number."""
	if not order.dz_courier:
		frappe.throw(_("Choisissez le transporteur avant d'expédier."))

	if not order.dz_tracking_number:
		# Ask the courier connector (returns None for the "Manuel" connector)
		order.dz_tracking_number = get_adapter(order.dz_courier).create_shipment(order)

	if not order.dz_tracking_number:
		frappe.throw(_("Saisissez le n° de suivi du colis avant d'expédier."))


@frappe.whitelist()
def set_shipping_details(sales_order, courier, tracking_number=None, stopdesk_id=None):
	"""Called by the "Expédier" button (sales_order.js) to save the courier,
	tracking number and stop desk office just before the workflow action runs."""
	order = frappe.get_doc("Sales Order", sales_order)
	order.check_permission("write")
	if order.workflow_state != S.PREPARED:
		frappe.throw(_("La commande doit être à l'état {0}.").format(S.PREPARED))
	values = {"dz_courier": courier, "dz_tracking_number": (tracking_number or "").strip() or None}
	if stopdesk_id:
		values["dz_stopdesk_id"] = stopdesk_id
	order.db_set(values)
