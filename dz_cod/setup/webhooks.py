"""Webhooks sent to n8n (or any URL) when an order reaches a key state.

They use ERPNext's built-in Webhook feature (search "Webhook" in the desk).
We only CREATE them, DISABLED, with a placeholder URL. To use them:
1. open Webhook "COD - Confirmée" (and the others),
2. replace the URL with your n8n webhook URL,
3. tick "Enabled" and save.

Your URL, the Enabled tick and the headers are never touched on `bench migrate`.
Only the JSON template and the condition are refreshed when a new version of
the app changes them, and only if nobody edited them on this site: we keep a
fingerprint of what we last wrote (refresh_template below). A template you
changed by hand is left alone and noted in the Error Log.
Example payloads: docs/WEBHOOKS.md.

Note: in the template write doc["items"], not doc.items (that would be the
Python dictionary method "items" and the webhook would fail).

How the condition works: `doc.has_value_changed("workflow_state")` is true
only during the save where the state changed, so the webhook fires once per
move, not every time someone edits the order.
"""

import hashlib

import frappe

from dz_cod.cod import states as S

PLACEHOLDER_URL = "https://n8n.example.com/webhook/dz-cod"

# The JSON body sent to n8n (Jinja template, `doc` is the Sales Order)
PAYLOAD = """{
  "event": "{{ doc.workflow_state }}",
  "order": "{{ doc.name }}",
  "order_date": "{{ doc.transaction_date }}",
  "customer": "{{ doc.customer }}",
  "customer_name": {{ doc.customer_name | tojson }},
  "phone": "{{ doc.dz_phone or '' }}",
  "phone_2": "{{ doc.dz_phone_2 or '' }}",
  "wilaya": {{ (doc.dz_wilaya or '') | tojson }},
  "commune": {{ (doc.dz_commune or '') | tojson }},
  "address": {{ (doc.dz_address or '') | tojson }},
  "delivery_type": "{{ doc.dz_delivery_type or '' }}",
  "source": "{{ doc.dz_source or '' }}",
  "shipping_charge": {{ doc.dz_shipping_charge or 0 }},
  "cod_amount": {{ doc.dz_cod_amount or 0 }},
  "courier": {{ (doc.dz_courier or '') | tojson }},
  "tracking_number": "{{ doc.dz_tracking_number or '' }}",
  "call_attempts": {{ doc.dz_call_attempts or 0 }},
  "items": [{% for row in doc["items"] %}
    {"item_code": {{ row.item_code | tojson }}, "item_name": {{ row.item_name | tojson }}, "qty": {{ row.qty }}, "rate": {{ row.rate }}}{% if not loop.last %},{% endif %}{% endfor %}
  ]
}"""

# (state, document event). Confirmer = submit, the others = update after submit.
WEBHOOKS = [
	(S.CONFIRMED, "on_submit"),
	(S.SHIPPED, "on_update_after_submit"),
	(S.DELIVERED, "on_update_after_submit"),
	(S.RETURNED, "on_update_after_submit"),
]


def webhook_name(state):
	return f"COD - {state}"


def webhook_condition(state, event):
	if event == "on_submit":
		return f'doc.workflow_state == "{state}"'
	return f'doc.workflow_state == "{state}" and doc.has_value_changed("workflow_state")'


def fingerprint(condition, payload):
	"""Short hash of what we wrote, to tell later whether someone edited it."""
	return hashlib.sha256(f"{condition}\n{payload}".encode()).hexdigest()[:16]


def fingerprint_key(name):
	return f"dz_cod_webhook_template::{name}"


def setup_webhooks():
	"""Create the four webhooks (disabled) if they do not exist yet, and
	refresh the template of the existing ones (refresh_template)."""
	for state, event in WEBHOOKS:
		name = webhook_name(state)
		condition = webhook_condition(state, event)
		if frappe.db.exists("Webhook", name):
			refresh_template(name, condition)
			continue

		webhook = frappe.new_doc("Webhook")
		webhook.update(
			{
				"webhook_doctype": "Sales Order",
				"webhook_docevent": event,
				"condition": condition,
				"enabled": 0,
				"request_url": PLACEHOLDER_URL,
				"request_method": "POST",
				"request_structure": "JSON",
				"webhook_json": PAYLOAD,
			}
		)
		webhook.append("webhook_headers", {"key": "Content-Type", "value": "application/json"})
		webhook.insert(ignore_permissions=True, set_name=name)
		frappe.db.set_default(fingerprint_key(name), fingerprint(condition, PAYLOAD))


def refresh_template(name, condition):
	"""Bring an existing webhook's template and condition to this version of
	the app, unless someone edited them on this site. URL, Enabled and
	headers are never touched."""
	current = frappe.db.get_value("Webhook", name, ["condition", "webhook_json"], as_dict=True)
	on_site = fingerprint(current.condition or "", current.webhook_json or "")
	latest = fingerprint(condition, PAYLOAD)
	key = fingerprint_key(name)

	if on_site == latest:
		frappe.db.set_default(key, latest)  # up to date (also adopts sites made before fingerprints)
		return

	if on_site != frappe.db.get_default(key):
		# Edited by hand (or never fingerprinted): keep it, say so once
		noted = f"{key}::noted"
		if frappe.db.get_default(noted) != on_site:
			frappe.log_error(
				title=f"dz_cod: webhook {name} not updated",
				message=f"The template of webhook {name} was changed on this site, so the new version "
				"shipped with dz_cod was not applied. Compare it with PAYLOAD in "
				"dz_cod/setup/webhooks.py and update it by hand if needed.",
			)
			frappe.db.set_default(noted, on_site)
		return

	webhook = frappe.get_doc("Webhook", name)
	webhook.condition = condition
	webhook.webhook_json = PAYLOAD
	webhook.save(ignore_permissions=True)
	frappe.db.set_default(key, latest)
