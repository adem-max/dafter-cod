"""Who may move a COD order (review of 27 October 2026, 1.2).

Frappe's workflow checks who may press a button, then saves the order, and
saving a submitted document wants WRITE and SUBMIT on it (Frappe's
"update after submit", Document.check_docstatus_transition). ERPNext gives
Stock User and Accounts User only read, so a single-role user could not
press "Préparer" or have a Versement mark orders "Réglée". So:

1. `grant_write` gives both roles write and submit on Sales Order (Custom
   DocPerm, done again on every migrate, like dz_core's delete locks). Once
   Custom DocPerm exists for Sales Order, ERPNext's own later permission
   changes no longer reach it: accepted in DECISIONS.md (decision D1).
2. `sales_order`, a has_permission hook, narrows those rights again: a user
   without a sales role may write or submit only an order already submitted
   whose state (as saved, before the step) their role owns in the workflow
   (setup/workflow.py STATES), so never submit a draft. Frappe's hooks can
   only narrow, never widen.
3. `check_change_after_submit` refuses any change from those users beyond the
   shipping fields and the workflow, including ERPNext's "Update Items"; and
   from every user, a change to Daftar's read-only fields (review of 31
   October 2026, C).
"""

import frappe
from frappe import _
from frappe.permissions import setup_custom_perms, update_permission_property
from frappe.utils import cstr, flt, get_datetime

from dz_cod.setup.workflow import ACCOUNTS, STATES, STOCK

SALES_ROLES = {"Sales User", "Sales Manager", "System Manager"}
GRANTED = (STOCK, ACCOUNTS)
# role -> submitted states whose orders it moves on
OWNED = {
	role: {state for state, docstatus, _style, owner in STATES if owner == role and docstatus == 1}
	for role in GRANTED
}


RIGHTS = ("write", "submit")
# What a user may change on a submitted order: what "Expédier" asks for
# (cod/order.set_shipping_details). Daftar's other dz_ fields there are
# read-only: written by the code (db_set, or the order hooks that run after
# the check), never by a user. "Read only" only hides a field in the form, the
# API would take it: an Accounts User could point dz_settlement at another
# Versement and hide an unpaid parcel from the month's courier check.
EDITABLE = {"dz_courier", "dz_tracking_number", "dz_stopdesk_id"}
# (doctype, role, rights given). "Marquer livrée" makes the delivery note,
# the invoice and its payment to the courier (cod/invoicing.py). ERPNext
# wants the user to at least select the customer's account (accounts/party.py
# account_perm_check: select only, the right ERPNext gives Stock Manager and
# Delivery User), and the payment reads its invoice (payment_entry.py
# get_reference_details): read only, never create or change an invoice.
GRANTS = [
	("Sales Order", STOCK, RIGHTS),
	("Sales Order", ACCOUNTS, RIGHTS),
	("Account", STOCK, ("select",)),
	("Sales Invoice", STOCK, ("read",)),
]


def grant_write():
	"""Give the rights of GRANTS (Custom DocPerm, permlevel 0), never taking
	any away. Returns the (doctype, role) changed."""
	changed = []
	for doctype, role, rights in GRANTS:
		setup_custom_perms(doctype)
		row = frappe.db.get_value(
			"Custom DocPerm",
			{"parent": doctype, "role": role, "permlevel": 0},
			["name", *rights],
			as_dict=True,
		)
		if row and all(row.get(right) for right in rights):
			continue
		if not row:
			frappe.get_doc(
				{
					"doctype": "Custom DocPerm",
					"parent": doctype,
					"parenttype": "DocType",
					"parentfield": "permissions",
					"role": role,
					"permlevel": 0,
				}
			).insert(ignore_permissions=True)
		for right in rights:
			update_permission_property(doctype, role, 0, right, 1, validate=False)
		changed.append((doctype, role))
	for doctype in {doctype for doctype, _role in changed}:
		frappe.clear_cache(doctype=doctype)
	return changed


def limited(user=None):
	"""True for a user whose write right on orders comes only from grant_write."""
	return not SALES_ROLES & set(frappe.get_roles(user))


def sales_order(doc, ptype=None, user=None, debug=False):
	"""has_permission hook. False refuses; True leaves Frappe's own answer
	(frappe.permissions.has_controller_permissions takes None as a refusal)."""
	if ptype not in RIGHTS or not doc or not limited(user):
		return True
	name = doc if isinstance(doc, str) else doc.name
	if not name or (not isinstance(doc, str) and doc.is_new()):
		return False
	saved = frappe.db.get_value("Sales Order", name, ["docstatus", "workflow_state"], as_dict=True)
	if not saved or saved.docstatus != 1:
		return False
	roles = set(frappe.get_roles(user))
	return any(saved.workflow_state in OWNED[role] for role in GRANTED if role in roles)


def check_change_after_submit(order):
	"""before_update_after_submit, before the order hooks set their dates.
	Nobody changes Daftar's read-only fields; a limited user changes only
	EDITABLE and the workflow state, never ERPNext's own fields or the lines
	(an edit through the API or "Update Items")."""
	before = order.get_doc_before_save()
	if not before or frappe.flags.in_patch or frappe.flags.in_migrate:
		return
	is_limited = limited()
	for field in order.meta.fields:
		name = field.fieldname
		if (
			not field.allow_on_submit
			or field.fieldtype in ("Table", "Table MultiSelect")
			or name in EDITABLE
			or name == "workflow_state"
		):
			continue
		if not is_limited and not (name.startswith("dz_") and field.read_only):
			continue
		if not same(field.fieldtype, order.get(name), before.get(name)):
			frappe.throw(
				_("Vous ne pouvez pas modifier le champ {0} de la commande.").format(_(field.label)),
				frappe.PermissionError,
			)
	if not is_limited:
		return

	def lines(doc):
		return [(row.item_code, row.qty, row.rate) for row in doc.get("items")]

	if lines(order) != lines(before):
		frappe.throw(_("Vous ne pouvez pas modifier les articles de la commande."), frappe.PermissionError)


def same(fieldtype, value, saved):
	"""The form sends dates and numbers back as text: compare them as values."""
	if fieldtype in ("Date", "Datetime"):
		return (get_datetime(value) if value else None) == (get_datetime(saved) if saved else None)
	if fieldtype in ("Int", "Float", "Currency", "Percent", "Check"):
		return flt(value) == flt(saved)
	return cstr(value) == cstr(saved)
