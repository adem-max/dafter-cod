# Written from Yalidine's webhook docs (verbatim copy, September 2026) and
# tested with the docs' example payloads only. Before going live, run
# Yalidine's webhook test page against this URL (docs/COURIER_INTEGRATION.md, Y7).
"""Receiver of Yalidine webhooks (push instead of hourly polling).

URL to declare in the Yalidine Webhooks dashboard:
    https://<client site>/api/method/dz_cod.couriers.yalidine_webhook.receive

- GET with `subscribe` and `crc_token`: Yalidine checks we own the URL (when
  the webhook is created and then from time to time). We answer the token as
  plain text, otherwise Yalidine disables the webhook.
- POST: a JSON body {"type": ..., "events": [...]}, signed in the header
  X-YALIDINE-SIGNATURE = HMAC-SHA256(raw body, webhook secret key). The secret
  is the field "Clé secrète webhook" of the Yalidine courier. A body whose
  signature matches no Yalidine courier is refused (400) and not stored.
- Each event has an event_id: it is stored as a Courier Webhook Event (the id
  is the record name), so an event delivered twice is handled once.
- Yalidine wants an answer within 10 seconds: we only store the events and
  answer 200; a background job applies them (process_events).

Orders are only moved to Livrée / Retournée when "Synchroniser les statuts
automatiquement" is ticked in COD Settings, like the hourly sync. Yalidine's
own words are always written on the order (Statut chez le transporteur).
"""

import hashlib
import hmac
import json

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils.password import get_decrypted_password
from werkzeug.wrappers import Response

from dz_cod.cod import states as S
from dz_cod.couriers.base import DELIVERED, RETURNED
from dz_cod.couriers.yalidine import map_status, update_order, with_reason
from dz_cod.features import MESSAGE, is_enabled

ACTIONS = {DELIVERED: S.ACTION_DELIVER, RETURNED: S.ACTION_RETURN}
PENDING, DONE, IGNORED, ERROR = "En attente", "Traité", "Ignoré", "Erreur"


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def receive(**kwargs):
	if not is_enabled("courier_api"):
		# Not in this client's offer: refuse quietly (no Error Log for each retry)
		return text_response(MESSAGE, 403)
	request = frappe.request
	if request.method == "GET":
		return crc_answer(request.args)
	status, text = handle_delivery(request.get_data(), request.headers.get("X-YALIDINE-SIGNATURE"))
	return text_response(text, status)


def text_response(text, status=200):
	return Response(text, status=status, mimetype="text/plain")


def crc_answer(args):
	if "subscribe" in args and args.get("crc_token"):
		return text_response(args.get("crc_token"))
	return text_response("missing crc_token", 400)


def handle_delivery(raw_body, signature):
	"""Check the signature on the raw bytes (before any JSON parsing), store
	the new events, queue their processing. Returns (http status, text)."""
	courier = courier_for_signature(raw_body, signature)
	if not courier:
		return 400, "invalid signature"
	try:
		payload = json.loads(raw_body)
	except ValueError:
		return 400, "invalid json"

	names = store_events(courier, payload)
	if names:
		frappe.enqueue(
			"dz_cod.couriers.yalidine_webhook.process_events",
			queue="short",
			enqueue_after_commit=True,
			event_names=names,
		)
	return 200, "ok"


def courier_for_signature(raw_body, signature):
	"""The Yalidine courier whose webhook secret signed this body, or None."""
	signature = (signature or "").strip().lower()
	if not signature:
		return None
	for courier in frappe.get_all("Supplier", filters={"dz_courier_adapter": "Yalidine"}, pluck="name"):
		secret = get_decrypted_password("Supplier", courier, "dz_webhook_secret", raise_exception=False)
		if secret and hmac.compare_digest(sign(raw_body, secret), signature):
			return courier
	return None


def sign(raw_body, secret):
	return hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


def store_events(courier, payload):
	"""Store the events not seen before. Returns their names."""
	names = []
	for event in payload.get("events") or []:
		event_id = event.get("event_id")
		if not event_id or frappe.db.exists("Courier Webhook Event", event_id):
			continue
		try:
			frappe.get_doc(
				{
					"doctype": "Courier Webhook Event",
					"event_id": event_id,
					"event_type": payload.get("type"),
					"courier": courier,
					"tracking_number": (event.get("data") or {}).get("tracking"),
					"occurred_at": event.get("occurred_at"),
					"payload": json.dumps(event, ensure_ascii=False, indent=1),
				}
			).insert(ignore_permissions=True)
		except frappe.DuplicateEntryError:
			continue  # the same event arriving twice at the same moment
		names.append(event_id)
	return names


def process_events(event_names):
	"""Background job: apply each stored event to its order."""
	# The job was queued by a Guest request; the workflow buttons need a real user
	if not is_enabled("courier_api"):
		return
	frappe.set_user("Administrator")
	for name in event_names:
		event = frappe.get_doc("Courier Webhook Event", name)
		if event.status != PENDING:
			continue
		frappe.db.savepoint("dz_cod_webhook_event")
		try:
			status, order, message = handle_event(event)
		except Exception:
			frappe.db.rollback(save_point="dz_cod_webhook_event")
			frappe.log_error(title=f"Webhook Yalidine : {name}")
			status, order, message = ERROR, None, frappe.get_traceback()[-1000:]
		event.db_set({"status": status, "sales_order": order, "error": message})
		frappe.db.commit()


def handle_event(event):
	"""Returns (status of the event, order name, message)."""
	data = (json.loads(event.payload or "{}")).get("data") or {}
	tracking = data.get("tracking")

	if event.event_type == "parcel_status_updated":
		status = with_reason(data.get("status"), data.get("reason"))
		order = update_order(tracking, status=status, status_on=event.occurred_at)
		if not order:
			return (
				IGNORED,
				None,
				"Aucune commande avec ce n° de suivi, ou statut plus ancien que celui connu.",
			)
		move(order, map_status(data.get("status")))
		return DONE, order, None

	if event.event_type == "parcel_payment_updated":
		order = update_order(tracking, payment_status=data.get("status"), payment_id=data.get("payment_id"))
		return (DONE, order, None) if order else (IGNORED, None, "Aucune commande avec ce n° de suivi.")

	if event.event_type in ("parcel_created", "parcel_edited") and data.get("label"):
		order = frappe.db.get_value("Sales Order", {"dz_tracking_number": tracking, "docstatus": 1})
		if order:
			frappe.db.set_value("Sales Order", order, "dz_label_url", data["label"], update_modified=False)
			return DONE, order, None

	return IGNORED, None, None


def move(order, status):
	"""Livré / Retourné au vendeur -> press the workflow button, if the order
	is still Expédiée and automatic status updates are switched on."""
	action = ACTIONS.get(status)
	if not action or not frappe.db.get_single_value("COD Settings", "auto_sync_courier_status"):
		return
	doc = frappe.get_doc("Sales Order", order)
	if doc.workflow_state == S.SHIPPED:
		apply_workflow(doc, action)
