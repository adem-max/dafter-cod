"""Hourly job: ask each courier where our shipped parcels are.

If the courier says "delivered" the order moves to Livrée, if it says
"returned" it moves to Retournée. Uses the normal workflow actions, so the
same checks, stock movements and webhooks run as when a person clicks.

Each courier is asked about all its parcels at once (get_statuses): a
connector like Yalidine then needs one call per 50 parcels, not one per order.

Disabled unless "Synchroniser les statuts automatiquement" is ticked in
COD Settings.
"""

import frappe
from frappe.model.workflow import apply_workflow

from dz_cod.cod import states as S
from dz_cod.couriers import get_adapter
from dz_cod.couriers.base import DELIVERED, RETURNED
from dz_cod.features import is_enabled

# Courier status -> workflow button to press
ACTIONS = {DELIVERED: S.ACTION_DELIVER, RETURNED: S.ACTION_RETURN}


def sync_shipped_orders():
	if not is_enabled("courier_api"):  # optional feature, dz_cod/features.py
		return
	if not frappe.db.get_single_value("COD Settings", "auto_sync_courier_status"):
		return

	orders = frappe.get_all(
		"Sales Order",
		filters={"docstatus": 1, "workflow_state": S.SHIPPED, "dz_tracking_number": ["is", "set"]},
		fields=["name", "dz_courier", "dz_tracking_number"],
	)
	by_courier = {}
	for order in orders:
		by_courier.setdefault(order.dz_courier, []).append(order)
	for courier, courier_orders in by_courier.items():
		sync_courier(courier, courier_orders)


def sync_courier(courier, orders):
	"""Ask one courier about its parcels. An error here must not stop the other couriers."""
	try:
		statuses = get_adapter(courier).get_statuses([order.dz_tracking_number for order in orders])
		frappe.db.commit()  # keep what the connector wrote on the orders (courier's own status)
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"Synchronisation transporteur : {courier}")
		return
	for order in orders:
		apply_status(order, statuses.get(order.dz_tracking_number))


def apply_status(order, status):
	"""Move one order. An error on one order must not stop the others."""
	action = ACTIONS.get(status)
	if not action:
		return
	try:
		apply_workflow(frappe.get_doc("Sales Order", order.name), action)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"Synchronisation transporteur : {order.name}")
