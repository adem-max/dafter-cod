# Tested with a fake HTTP layer only: compare the result with the client's
# Yalidine dashboard the first time (docs/COURIER_INTEGRATION.md, Y5 and Y6).
"""Buttons on a Yalidine courier (supplier.js):

- "Importer les tarifs Yalidine": Yalidine's prices for this account, from the
  courier's departure wilaya to each wilaya, written into the wilaya list as
  *Coût transporteur domicile / stop desk*. The customer prices (*Tarif
  domicile / stop desk*) are not touched: the seller decides on a margin.
- "Importer communes et bureaux Yalidine": Yalidine's communes (exact
  spellings, deliverable or not) and its stop-desk offices, used as pick lists
  on the order.

Both run as background jobs: the prices need one call per wilaya, spaced out
to stay under Yalidine's 50 calls per minute.
"""

import time

import frappe
from frappe import _
from frappe.utils import cint

from dz_cod.couriers import get_adapter, places
from dz_cod.couriers.yalidine import YalidineAdapter
from dz_cod.features import requires_feature

PAUSE = 1.5  # seconds between two price calls: 40 calls per minute at most
JOBS = {"fees": "import_fees", "places": "import_places"}


@frappe.whitelist()
@requires_feature("courier_api")
def start_import(courier, what):
	if what not in JOBS:
		frappe.throw(_("Import inconnu."))
	frappe.get_doc("Supplier", courier).check_permission("write")
	frappe.has_permission("DZ Wilaya", "write", throw=True)
	yalidine(courier)  # fails now, in the user's face, if the courier is not Yalidine

	job = frappe.enqueue(
		f"dz_cod.couriers.yalidine_import.{JOBS[what]}",
		queue="long",
		timeout=1800,
		job_id=f"dz_cod_yalidine_{what}_{courier}",
		deduplicate=True,
		courier=courier,
		user=frappe.session.user,
	)
	if not job:
		return _("Un import est déjà en cours pour ce transporteur.")
	return _("Import lancé en arrière-plan. Un message s'affichera à la fin (1 à 2 minutes).")


def yalidine(courier):
	adapter = get_adapter(courier)
	if not isinstance(adapter, YalidineAdapter):
		frappe.throw(_("Le connecteur du transporteur {0} n'est pas Yalidine.").format(courier))
	return adapter


def wilaya_by_code(code):
	return frappe.db.get_value("DZ Wilaya", {"code": str(code).zfill(2)})


def notify(user, message, failed=False):
	if user:
		frappe.publish_realtime(
			"msgprint",
			{"message": message, "title": "Yalidine", "indicator": "red" if failed else "green"},
			user=user,
		)


# ---------------------------------------------------------------- prices (Y5)


def import_fees(courier, user=None):
	try:
		count = update_courier_costs(yalidine(courier))
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"Import des tarifs Yalidine : {courier}")
		notify(user, _("L'import des tarifs Yalidine a échoué : voir le journal des erreurs."), failed=True)
		return
	frappe.db.commit()
	notify(user, _("Tarifs Yalidine importés pour {0} wilayas (coûts transporteur seulement).").format(count))


def update_courier_costs(adapter):
	"""For each Yalidine wilaya: the price to its chef-lieu commune (express
	home / express desk) becomes our courier cost. Returns the number of
	wilayas updated."""
	if not adapter.courier.get("dz_from_wilaya"):
		frappe.throw(_("Renseignez la wilaya de départ du transporteur {0}.").format(adapter.courier.name))
	from_id, _from_name = adapter.yalidine_wilaya(adapter.courier.dz_from_wilaya)

	yalidine_wilayas = adapter.get_all("wilayas/")
	known_codes = {cint(w.get("id")) for w in yalidine_wilayas}
	count = 0
	for i, yalidine_wilaya in enumerate(yalidine_wilayas):
		wilaya = wilaya_by_code(yalidine_wilaya.get("id"))
		if not wilaya:
			continue
		if i:
			time.sleep(PAUSE)
		fees = adapter.call(
			"GET",
			"fees/",
			params={"from_wilaya_id": from_id, "to_wilaya_id": yalidine_wilaya["id"]},
			max_wait=60,
		)
		home, desk = chef_lieu_prices(fees, yalidine_wilaya.get("name"))
		# A 2026 wilaya Yalidine does not know is delivered as its parent: same price
		children = [
			child.name
			for child in frappe.get_all(
				"DZ Wilaya", filters={"parent_wilaya": wilaya}, fields=["name", "code"]
			)
			if cint(child.code) not in known_codes
		]
		for name in [wilaya, *children]:
			count += set_courier_costs(name, home, desk)
	return count


def chef_lieu_prices(fees, wilaya_name):
	"""(express_home, express_desk) of the commune named like the wilaya, else
	of the commune with the smallest id (Yalidine numbers the chef-lieu first,
	e.g. 1601 for Alger). UNVERIFIED on a real account."""
	communes = list((fees.get("per_commune") or {}).values())
	if not communes:
		return None, None
	wanted = places.simplify(wilaya_name)
	commune = next((c for c in communes if places.simplify(c.get("commune_name")) == wanted), None)
	commune = commune or min(communes, key=lambda c: cint(c.get("commune_id")))
	return commune.get("express_home"), commune.get("express_desk")


def set_courier_costs(wilaya, home, desk):
	values = {}
	if home is not None:
		values["home_courier_cost"] = home
	if desk is not None:
		values["stopdesk_courier_cost"] = desk
	if not values:
		return 0
	frappe.db.set_value("DZ Wilaya", wilaya, values)
	frappe.clear_document_cache("DZ Wilaya", wilaya)
	return 1


# ------------------------------------------------- communes and stop desks (Y6)


def import_places(courier, user=None):
	try:
		communes, desks = update_places(yalidine(courier))
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"Import des communes Yalidine : {courier}")
		notify(user, _("L'import des communes Yalidine a échoué : voir le journal des erreurs."), failed=True)
		return
	frappe.db.commit()
	notify(user, _("{0} communes et {1} bureaux stop desk importés de Yalidine.").format(communes, desks))


def update_places(adapter):
	"""Create or refresh DZ Commune and DZ Stop Desk. Returns (communes, desks)."""
	wilayas = {}  # Yalidine wilaya id -> our wilaya, looked up once

	def our_wilaya(yalidine_id):
		if yalidine_id not in wilayas:
			wilayas[yalidine_id] = wilaya_by_code(yalidine_id)
		return wilayas[yalidine_id]

	communes = 0
	for row in adapter.get_all("communes/"):
		wilaya = our_wilaya(cint(row.get("wilaya_id")))
		if wilaya and row.get("id"):
			upsert(
				"DZ Commune",
				str(row["id"]),
				{
					"yalidine_id": str(row["id"]),
					"commune_name": row.get("name"),
					"wilaya": wilaya,
					"yalidine_wilaya_name": row.get("wilaya_name"),
					"has_stop_desk": cint(row.get("has_stop_desk")),
					"is_deliverable": cint(row.get("is_deliverable")),
				},
			)
			communes += 1

	desks = 0
	for row in adapter.get_all("centers/"):
		if row.get("center_id"):
			upsert(
				"DZ Stop Desk",
				str(row["center_id"]),
				{
					"center_id": str(row["center_id"]),
					"center_name": row.get("name"),
					"address": row.get("address"),
					"commune_name": row.get("commune_name"),
					"wilaya": our_wilaya(cint(row.get("wilaya_id"))),
					"gps": row.get("gps"),
					"courier": adapter.courier.name,
				},
			)
			desks += 1
	return communes, desks


def upsert(doctype, name, values):
	if frappe.db.exists(doctype, name):
		frappe.db.set_value(doctype, name, values)
	else:
		frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True)
