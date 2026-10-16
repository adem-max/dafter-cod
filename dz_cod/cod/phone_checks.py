"""Warnings based on the customer's phone number. They never block anything:
the operator reads them and decides (decided with Adem, October 2026).

1. Refused parcels: when an order's phone already had parcels sent back
   (state Retournée), say how many, at save and at "Confirmer". The number
   from which we warn is in COD Settings (0 = never warn).
2. Duplicate customers: when a customer is saved with a phone that another
   customer already has, say which one(s), with a link.
"""

import frappe
from frappe import _
from frappe.utils import get_link_to_form

from dz_cod.cod import states as S
from dz_cod.cod.phone import normalize_phone
from dz_cod.features import is_enabled


def refused_parcels(phone, exclude_order=None):
	"""Orders sent back (Retournée) whose main or second phone is `phone`."""
	if not phone:
		return []
	filters = [["workflow_state", "=", S.RETURNED]]
	if exclude_order:
		filters.append(["name", "!=", exclude_order])
	return frappe.get_all(
		"Sales Order",
		filters=filters,
		or_filters=[["dz_phone", "=", phone], ["dz_phone_2", "=", phone]],
		pluck="name",
		order_by="dz_returned_on desc",
	)


def warn_refused_parcels(order):
	"""Called from order.validate (draft orders) and order.before_submit."""
	if not is_enabled("phone_checks"):  # optional feature, dz_cod/features.py
		return
	threshold = frappe.db.get_single_value("COD Settings", "refused_warning_threshold")
	if not threshold:
		return
	refused = refused_parcels(order.dz_phone, exclude_order=order.name)
	if order.dz_phone_2 and order.dz_phone_2 != order.dz_phone:
		refused += [name for name in refused_parcels(order.dz_phone_2, order.name) if name not in refused]
	if len(refused) < threshold:
		return
	links = ", ".join(get_link_to_form("Sales Order", name) for name in refused[:5])
	frappe.msgprint(
		_("Ce numéro a déjà {0} colis refusé(s) : {1}. Vérifiez avec le client avant d'expédier.").format(
			len(refused), links
		),
		title=_("Client à risque"),
		indicator="orange",
	)


def warn_duplicate_customer(customer, method=None):
	"""Customer "validate" hook (hooks.py): another customer has this phone."""
	customer.dz_phone = normalize_phone(customer.dz_phone)  # always (base)
	if not is_enabled("phone_checks"):
		return
	if not customer.dz_phone or not (customer.is_new() or customer.has_value_changed("dz_phone")):
		return
	others = frappe.get_all(
		"Customer",
		filters={"dz_phone": customer.dz_phone, "name": ["!=", customer.name or ""]},
		fields=["name", "customer_name"],
		limit=5,
	)
	if not others:
		return
	links = ", ".join(get_link_to_form("Customer", other.name, other.customer_name) for other in others)
	frappe.msgprint(
		_("Le numéro {0} est déjà utilisé par : {1}. S'il s'agit du même client, utilisez sa fiche.").format(
			customer.dz_phone, links
		),
		title=_("Client peut-être en double"),
		indicator="orange",
	)
