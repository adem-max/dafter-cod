"""Create (or update) the "Commande COD" Workflow on Sales Order.

Think of the workflow as a routing in manufacturing:
- each STATE is an operation the order sits at (Nouvelle, Confirmée, ...)
- each TRANSITION is the move from one operation to the next, with a button
  name (the action) and the role allowed to press it.

This file only DESCRIBES the workflow. What happens on each move (create the
delivery note, return stock, ...) is coded in dz_cod/cod/order.py.

A Frappe workflow covers every Sales Order of the site, so direct sales
(cod/channel.py) have their own short path: Nouvelle ──Valider──> Validée,
then ERPNext's usual delivery note and invoice. The COD buttons only show on
COD orders and "Valider" only on direct sales (transition conditions).
"""

import frappe

from dz_cod.cod import states as S
from dz_cod.cod.channel import DIRECT

WORKFLOW_NAME = "Commande COD"

# Role names (standard ERPNext roles, no custom roles)
SALES = "Sales User"
STOCK = "Stock User"
ACCOUNTS = "Accounts User"
MANAGER = "Sales Manager"

# (state, docstatus, colour, role allowed to edit the order in this state)
# docstatus: 0 = draft (editable), 1 = submitted (stock reserved), 2 = cancelled
STATES = [
	(S.NEW, 0, "Primary", SALES),
	(S.UNREACHABLE, 0, "Warning", SALES),
	# The first submitted state: an order submitted outside the workflow (by
	# code, like a producer's import) lands here, not in a COD state
	(S.VALIDATED, 1, "Info", SALES),
	(S.CONFIRMED, 1, "Info", STOCK),
	(S.PREPARED, 1, "Info", STOCK),
	(S.SHIPPED, 1, "Primary", STOCK),
	(S.DELIVERED, 1, "Success", ACCOUNTS),
	(S.SETTLED, 1, "Success", ACCOUNTS),
	(S.RETURNED, 1, "Danger", STOCK),
	(S.CANCELLED, 0, "Inverse", MANAGER),
	(S.CANCELLED_AFTER_CONFIRMATION, 2, "Inverse", MANAGER),
]

# The "Pas de réponse" button is hidden once the maximum number of calls
# (COD Settings > max_call_attempts) is reached.
CALLS_LEFT = (
	"(doc.dz_call_attempts or 0) < "
	"int(frappe.db.get_value('COD Settings', 'COD Settings', 'max_call_attempts') or 3)"
)

# Which channel a button is for (cod/channel.py)
COD_SALE = f'doc.dz_channel != "{DIRECT}"'
DIRECT_SALE = f'doc.dz_channel == "{DIRECT}"'

# (from state, action button, to state, role, condition)
TRANSITIONS = [
	(S.NEW, S.ACTION_CONFIRM, S.CONFIRMED, SALES, COD_SALE),
	(S.NEW, S.ACTION_NO_ANSWER, S.UNREACHABLE, SALES, f"{COD_SALE} and {CALLS_LEFT}"),
	(S.NEW, S.ACTION_VALIDATE, S.VALIDATED, SALES, DIRECT_SALE),
	(S.NEW, S.ACTION_CANCEL, S.CANCELLED, SALES, None),
	(S.UNREACHABLE, S.ACTION_CONFIRM, S.CONFIRMED, SALES, COD_SALE),
	(S.UNREACHABLE, S.ACTION_NO_ANSWER, S.UNREACHABLE, SALES, f"{COD_SALE} and {CALLS_LEFT}"),
	(S.UNREACHABLE, S.ACTION_VALIDATE, S.VALIDATED, SALES, DIRECT_SALE),
	(S.UNREACHABLE, S.ACTION_CANCEL, S.CANCELLED, SALES, None),
	(S.VALIDATED, S.ACTION_CANCEL, S.CANCELLED_AFTER_CONFIRMATION, SALES, None),
	(S.CONFIRMED, S.ACTION_PREPARE, S.PREPARED, STOCK, None),
	(S.CONFIRMED, S.ACTION_CANCEL, S.CANCELLED_AFTER_CONFIRMATION, SALES, None),
	(S.PREPARED, S.ACTION_SHIP, S.SHIPPED, STOCK, None),
	(S.PREPARED, S.ACTION_CANCEL, S.CANCELLED_AFTER_CONFIRMATION, SALES, None),
	(S.SHIPPED, S.ACTION_DELIVER, S.DELIVERED, STOCK, None),
	(S.SHIPPED, S.ACTION_RETURN, S.RETURNED, STOCK, None),
	(S.DELIVERED, S.ACTION_SETTLE, S.SETTLED, ACCOUNTS, None),
]


def setup_workflow():
	"""Create the workflow. Safe to run many times (it rebuilds it)."""
	for state, _docstatus, style, _role in STATES:
		ensure_record("Workflow State", state, {"workflow_state_name": state, "style": style})

	for action in {t[1] for t in TRANSITIONS}:
		ensure_record("Workflow Action Master", action, {"workflow_action_name": action})

	if frappe.db.exists("Workflow", WORKFLOW_NAME):
		workflow = frappe.get_doc("Workflow", WORKFLOW_NAME)
	else:
		workflow = frappe.new_doc("Workflow")
		workflow.workflow_name = WORKFLOW_NAME

	workflow.document_type = "Sales Order"
	workflow.workflow_state_field = "workflow_state"
	workflow.is_active = 1
	workflow.send_email_alert = 0

	workflow.states = []
	for state, docstatus, _style, role in STATES:
		row = {"state": state, "doc_status": str(docstatus), "allow_edit": role, "send_email": 0}
		if state == S.UNREACHABLE:
			# Each time the order enters "Injoignable", add 1 to the call counter
			row.update(
				{
					"update_field": "dz_call_attempts",
					"update_value": "(doc.dz_call_attempts or 0) + 1",
					"evaluate_as_expression": 1,
				}
			)
		workflow.append("states", row)

	workflow.transitions = []
	for from_state, action, to_state, role, condition in TRANSITIONS:
		workflow.append(
			"transitions",
			{
				"state": from_state,
				"action": action,
				"next_state": to_state,
				"allowed": role,
				# Small teams: the person who created the order may also move it
				"allow_self_approval": 1,
				"condition": condition,
			},
		)

	workflow.save(ignore_permissions=True)


def ensure_record(doctype, name, values):
	"""Create a simple master record if it does not exist yet."""
	if not frappe.db.exists(doctype, name):
		doc = frappe.new_doc(doctype)
		doc.update(values)
		doc.insert(ignore_permissions=True)
