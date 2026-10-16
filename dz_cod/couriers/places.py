"""Communes and stop desks imported from the courier (doctypes DZ Commune and
DZ Stop Desk), and the pick lists of the order form.

A 2026 wilaya (59-69) the courier does not know yet has no communes of its
own in the list: its parent wilaya's communes and offices are offered instead.
"""

import unicodedata

import frappe

from dz_cod.features import is_enabled


def with_parent(wilaya):
	"""[wilaya, its parent wilaya] (just [wilaya] for the 58 older ones)."""
	parent = frappe.db.get_value("DZ Wilaya", wilaya, "parent_wilaya")
	return [wilaya, parent] if parent else [wilaya]


def communes_of(wilaya):
	"""Imported communes of a wilaya, or of its parent if it has none."""
	if not wilaya:
		return []
	for name in with_parent(wilaya):
		communes = frappe.get_all(
			"DZ Commune",
			filters={"wilaya": name},
			fields=["commune_name", "is_deliverable"],
			order_by="commune_name asc",
		)
		if communes:
			return communes
	return []


def simplify(text):
	"""'Bordj El-Kiffan ' and 'bordj el kiffan' compare equal, so do 'Béjaïa' and 'Bejaia'."""
	text = unicodedata.normalize("NFKD", text or "")
	text = "".join(c for c in text if not unicodedata.combining(c)).lower()
	for sign in "-'’":
		text = text.replace(sign, " ")
	return " ".join(text.split())


def match_commune(communes, name):
	wanted = simplify(name)
	return next((c for c in communes if simplify(c.commune_name) == wanted), None)


@frappe.whitelist()
def commune_names(wilaya=None, **kwargs):
	"""Pick list of the order's Commune field (sales_order.js). Returns all the
	wilaya's communes, so that a name typed outside the list is refused by the
	form; an empty list (nothing imported) leaves the field free."""
	if not wilaya or not is_enabled("courier_api") or not frappe.has_permission("DZ Commune", "read"):
		return []
	return [c.commune_name for c in communes_of(wilaya)]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def stopdesk_query(doctype, txt, searchfield, start, page_len, filters):
	"""Pick list of the order's "Bureau stop desk": offices of the order's wilaya
	(and of its parent wilaya)."""
	if not is_enabled("courier_api"):
		return []
	conditions = {}
	if filters and filters.get("wilaya"):
		conditions["wilaya"] = ["in", with_parent(filters["wilaya"])]
	return frappe.get_list(
		"DZ Stop Desk",
		filters=conditions,
		or_filters={"center_name": ["like", f"%{txt}%"], "commune_name": ["like", f"%{txt}%"]} if txt else None,
		fields=["name", "center_name", "commune_name"],
		order_by="center_name asc",
		offset=start,
		limit=page_len,
		as_list=True,
	)
