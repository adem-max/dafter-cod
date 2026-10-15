"""Courier Webhook Event: one line per event pushed by a courier (Yalidine
webhooks). The event id is the record name, so an event delivered twice is
stored once and handled once. Old lines are deleted after 30 days (hooks.py,
default_log_clearing_doctypes).
"""

import frappe
from frappe.model.document import Document


class CourierWebhookEvent(Document):
	@staticmethod
	def clear_old_logs(days=30):
		from frappe.query_builder import Interval
		from frappe.query_builder.functions import Now

		table = frappe.qb.DocType("Courier Webhook Event")
		frappe.db.delete(table, filters=(table.creation < (Now() - Interval(days=days))))
