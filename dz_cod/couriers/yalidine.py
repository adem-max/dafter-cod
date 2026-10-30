# Built from a verbatim copy of Yalidine's official API docs (September 2026)
# and tested with a fake HTTP layer only. Nothing here has been called against
# a real Yalidine account yet: every "UNVERIFIED" comment below is a point to
# check with the client's keys (list in docs/COURIER_INTEGRATION.md, section 4).
"""Yalidine connector.

    base URL   https://api.yalidine.app/v1/
    headers    X-API-ID, X-API-TOKEN (from the client's Developer Dashboard)
    create     POST parcels/                 status   GET parcels/?tracking=a,b,c
    history    GET histories/<tracking>      prices   GET fees/ (yalidine_import.py)
    webhooks   yalidine_webhook.py

Rate limits (defaults): 5 calls/second, 50/minute, 1,000/hour, 10,000/day.
Each answer says how many calls are left in headers x-<window>-quota-left;
over the limit Yalidine answers 429 with Retry-After, and repeated abuse
disables the keys. So `call` remembers an exhausted window in the Redis cache
(shared by web server and workers) and refuses, or waits, until it resets.
"""

import time

import frappe
import requests
from frappe import _
from frappe.utils import cint, flt, get_datetime

from dz_cod.couriers import places
from dz_cod.couriers.base import DELIVERED, IN_TRANSIT, RETURNED, UNKNOWN, CourierAdapter

CONNECTOR = "Yalidine"  # its communes and offices: DZ Commune / DZ Stop Desk named Yalidine-<id>
BASE_URL = "https://api.yalidine.app/v1/"
TIMEOUT = 20  # seconds
MAX_PRICE = 150000  # Yalidine refuses an amount to collect above this
BATCH_SIZE = 50  # tracking numbers per status call
STOP_DESK = "Stop desk"
PARCEL_FIELDS = "tracking,order_id,label,last_status,date_last_status,payment_status,payment_id"

# Yalidine's last status (French text) -> our word. Anything else = still
# travelling. "Echèc livraison", "Retour vers vendeur", "Retour à retirer"...
# mean the parcel is coming back: they are shown on the order
# (dz_courier_status), but the order only becomes Retournée once the parcel is
# physically back ("Retourné au vendeur"), because that moves the stock.
STATUS_MAP = {"Livré": DELIVERED, "Retourné au vendeur": RETURNED}

# Quota header -> length of its window in seconds
QUOTA_WINDOWS = {
	"x-second-quota-left": 1,
	"x-minute-quota-left": 60,
	"x-hour-quota-left": 3600,
	"x-day-quota-left": 86400,
}
RETRY_AFTER = "retry-after"
QUOTA_CACHE_KEY = "dz_cod_yalidine_quota"


class YalidineAdapter(CourierAdapter):
	label = "Yalidine"

	# ------------------------------------------------------------ HTTP

	def call(self, method, path, params=None, json=None, max_wait=0, retry=True):
		"""One call to the API; returns the decoded JSON answer.

		max_wait: how many seconds we may sleep when Yalidine says "wait"
		(429 or a quota at 0). 0 when a person is clicking (they get a clear
		message instead), up to 60 in background jobs."""
		self.wait_for_quota(max_wait)
		try:
			response = requests.request(
				method, BASE_URL + path, headers=self.headers(), params=params, json=json, timeout=TIMEOUT
			)
		except requests.RequestException as e:
			frappe.throw(_("Yalidine ne répond pas ({0}). Réessayez plus tard.").format(e.__class__.__name__))

		self.remember_quota(response)
		if response.status_code == 429:
			retry_after = cint(response.headers.get("Retry-After")) or 60
			if retry and retry_after <= max_wait:
				# wait_for_quota sleeps the Retry-After time, then one more try
				return self.call(method, path, params=params, json=json, max_wait=max_wait, retry=False)
			frappe.throw(_("Yalidine : quota d'appels dépassé, réessayez dans {0} s.").format(retry_after))
		if response.status_code in (401, 403):
			frappe.throw(
				_("Yalidine refuse les clés API du transporteur {0} (API ID / API Token).").format(
					self.courier.name
				)
			)
		if response.status_code >= 400:
			frappe.throw(
				_("Yalidine a répondu par une erreur {0} : {1}").format(
					response.status_code, response.text[:300]
				)
			)
		return response.json()

	def headers(self):
		token = self.courier.get_password("dz_api_token", raise_exception=False)
		if not (self.courier.get("dz_api_id") and token):
			frappe.throw(
				_("Renseignez l'API ID et l'API Token du transporteur {0}.").format(self.courier.name)
			)
		return {"X-API-ID": self.courier.dz_api_id, "X-API-TOKEN": token}

	def quota_key(self, header):
		return f"{QUOTA_CACHE_KEY}|{self.courier.name}|{header}"

	def remember_quota(self, response):
		"""After a 429, wait Retry-After seconds. A window whose quota reached 0
		stays closed until it resets (at the latest one window from now)."""
		if response.status_code == 429:
			self.close_window(RETRY_AFTER, cint(response.headers.get("Retry-After")) or 60)
			return
		for header, window in QUOTA_WINDOWS.items():
			left = response.headers.get(header)
			if left is not None and cint(left) <= 0:
				self.close_window(header, window)

	def close_window(self, name, seconds):
		frappe.cache.set_value(self.quota_key(name), time.time() + seconds, expires_in_sec=seconds)

	def wait_for_quota(self, max_wait=0):
		for header in (*QUOTA_WINDOWS, RETRY_AFTER):
			wait = flt(frappe.cache.get_value(self.quota_key(header))) - time.time()
			if wait <= 0:
				continue
			if wait <= max(max_wait, 1):  # the per-second window is always worth waiting for
				time.sleep(wait)
				continue
			frappe.throw(_("Yalidine : quota d'appels dépassé, réessayez dans {0} s.").format(cint(wait) + 1))

	def clear_quota(self):
		for header in (*QUOTA_WINDOWS, RETRY_AFTER):
			frappe.cache.delete_value(self.quota_key(header))

	def get_all(self, path, params=None, pause=0.5):
		"""Every page of a list endpoint (communes/, centers/...)."""
		rows, page = [], 1
		while True:
			answer = self.call("GET", path, params=dict(params or {}, page=page, page_size=1000), max_wait=60)
			rows += answer.get("data") or []
			if not answer.get("has_more"):
				return rows
			page += 1
			time.sleep(pause)

	# ------------------------------------------------------------ places

	def yalidine_wilaya(self, wilaya):
		"""(id, name) of one of our wilayas as Yalidine knows it.

		Yalidine's ids are the official wilaya codes, and its docs list 58
		wilayas. A 2026 wilaya (59-69) is sent as its parent wilaya, unless
		the communes imported from Yalidine show that Yalidine knows it.
		UNVERIFIED: whether Yalidine has added wilayas 59-69 (GET wilayas/)."""
		doc = frappe.get_cached_doc("DZ Wilaya", wilaya)
		if (
			cint(doc.code) > 58
			and doc.parent_wilaya
			and not frappe.db.exists("DZ Commune", {"wilaya": wilaya, "connector": CONNECTOR})
		):
			return self.yalidine_wilaya(doc.parent_wilaya)
		name = frappe.db.get_value(
			"DZ Commune", {"wilaya": wilaya, "connector": CONNECTOR}, "courier_wilaya_name"
		)
		return cint(doc.code), name or doc.wilaya_name

	def commune_name(self, wilaya, name):
		"""Yalidine's spelling of a commune. Refuses a commune Yalidine does not
		know, once the communes are imported; before that, sends it as typed."""
		communes = places.communes_of(wilaya, CONNECTOR)
		if not communes:
			return name
		commune = places.match_commune(communes, name)
		if not commune:
			frappe.throw(
				_(
					"Commune « {0} » inconnue de Yalidine dans la wilaya {1}. Choisissez-la dans la liste."
				).format(name, wilaya)
			)
		if not commune.is_deliverable:
			frappe.throw(_("Yalidine ne livre pas la commune {0}.").format(commune.commune_name))
		return commune.commune_name

	def check_order(self, order):
		"""At confirmation: the commune must be one Yalidine knows (and is
		stored with Yalidine's spelling), while the order can still be edited."""
		if order.dz_delivery_type != STOP_DESK and order.dz_commune and order.dz_wilaya:
			order.dz_commune = self.commune_name(order.dz_wilaya, order.dz_commune)

	# ------------------------------------------------------------ create

	def create_shipment(self, order):
		"""Declare the parcel. Returns the tracking number and stores the label link.

		The call runs inside the "Expédier" database transaction: if something
		fails after it, the parcel exists at Yalidine but the order stays
		Préparée. So first look for a parcel already made for this order and
		reuse it, instead of creating a second one on the next click."""
		result = self.find_parcel(order.name)
		if not result:
			answer = self.call("POST", "parcels/", json=[self.build_parcel(order)])
			result = (answer or {}).get(order.name) or {}
			if not result.get("success") or not result.get("tracking"):
				frappe.throw(
					_("Yalidine a refusé le colis : {0}").format(
						result.get("message") or _("réponse inattendue")
					),
					title=_("Expédition impossible"),
				)
		order.dz_label_url = result.get("label")
		return result.get("tracking")

	def find_parcel(self, order_name):
		"""The parcel already created for this order, if any (not cancelled).
		UNVERIFIED: that the order_id filter is an exact match."""
		answer = self.call("GET", "parcels/", params={"order_id": order_name, "fields": PARCEL_FIELDS})
		for parcel in answer.get("data") or []:
			if parcel.get("order_id") == order_name and parcel.get("last_status") != "Annulé":
				return parcel

	def build_parcel(self, order):
		"""The parcel as Yalidine's POST parcels/ expects it (all fields required by the docs)."""
		if not self.courier.get("dz_from_wilaya"):
			frappe.throw(_("Renseignez la wilaya de départ du transporteur {0}.").format(self.courier.name))
		_from_id, from_wilaya_name = self.yalidine_wilaya(self.courier.dz_from_wilaya)

		stop_desk = order.dz_delivery_type == STOP_DESK
		wilaya, commune, address = order.dz_wilaya, order.dz_commune, order.dz_address
		if stop_desk:
			if not order.dz_stopdesk_id:
				frappe.throw(_("Choisissez le bureau stop desk de la commande avant d'expédier."))
			desk = frappe.db.get_value(
				"DZ Stop Desk",
				order.dz_stopdesk_id,
				["connector", "center_id", "center_name", "commune_name", "wilaya"],
				as_dict=True,
			)
			if not desk or desk.connector != CONNECTOR:
				frappe.throw(
					_("Le bureau {0} n'est pas un bureau Yalidine. Choisissez-le dans la liste.").format(
						order.dz_stopdesk_id
					)
				)
			# The desk's commune is the destination; the address is optional for us, not for Yalidine
			wilaya, commune = desk.wilaya or wilaya, desk.commune_name or commune
			address = address or desk.center_name
		else:
			commune = self.commune_name(wilaya, commune)
		_to_id, to_wilaya_name = self.yalidine_wilaya(wilaya)

		amount = cint(round(flt(order.dz_cod_amount)))
		if not 0 <= amount <= MAX_PRICE:
			frappe.throw(_("Yalidine accepte un montant à encaisser de 0 à {0} DA.").format(MAX_PRICE))

		firstname, familyname = split_name(order.customer_name or order.customer)
		parcel = {
			"order_id": order.name,
			"from_wilaya_name": from_wilaya_name,
			"firstname": firstname,
			"familyname": familyname,
			"contact_phone": ",".join(phone for phone in (order.dz_phone, order.dz_phone_2) if phone),
			"address": address or commune,
			"to_commune_name": commune,
			"to_wilaya_name": to_wilaya_name,
			"product_list": product_list(order),
			"price": amount,  # what the courier collects: items + delivery
			"do_insurance": False,
			"declared_value": amount,
			# Weight and size: 1 kg, 1 cm. Yalidine charges extra only above 5 kg.
			"length": 1,
			"width": 1,
			"height": 1,
			"weight": 1,
			# The delivery fee is already inside `price`, so Yalidine must not add
			# it again for the customer ("false = paid by the receiver"): it keeps
			# its fee from what it pays us. UNVERIFIED: check on the first real
			# parcel that the amount to collect shown by Yalidine equals `price`.
			"freeshipping": True,
			"is_stopdesk": stop_desk,
			"has_exchange": False,
		}
		if stop_desk:
			parcel["stopdesk_id"] = desk.center_id  # Yalidine's own id, not our record name
		return parcel

	# ------------------------------------------------------------ status

	def get_status(self, tracking_number):
		return self.get_statuses([tracking_number]).get(tracking_number, UNKNOWN)

	def get_statuses(self, tracking_numbers):
		"""One call per 50 parcels (GET parcels/?tracking=a,b,...), not one per
		order: the hourly sync stays far below the rate limits. Also writes
		Yalidine's own words and the payment status on each order."""
		statuses = {}
		tracking_numbers = [t for t in tracking_numbers if t]
		for start in range(0, len(tracking_numbers), BATCH_SIZE):
			chunk = tracking_numbers[start : start + BATCH_SIZE]
			answer = self.call(
				"GET",
				"parcels/",
				params={"tracking": ",".join(chunk), "fields": PARCEL_FIELDS, "page_size": BATCH_SIZE},
			)
			for parcel in answer.get("data") or []:
				statuses[parcel.get("tracking")] = map_status(parcel.get("last_status"))
				update_order(
					parcel.get("tracking"),
					self.courier.name,  # the adapter holds the Supplier document
					status=parcel.get("last_status"),
					status_on=parcel.get("date_last_status"),
					payment_status=parcel.get("payment_status"),
					payment_id=parcel.get("payment_id"),
				)
		return statuses

	def get_tracking(self, tracking_number):
		answer = self.call("GET", "histories/" + requests.utils.quote(tracking_number))
		history = sorted(answer.get("data") or [], key=lambda row: row.get("date_status") or "")
		return [
			{
				"date": row.get("date_status"),
				"status": with_reason(row.get("status"), row.get("reason")),
				"location": row.get("center_name")
				or ", ".join(filter(None, (row.get("commune_name"), row.get("wilaya_name")))),
			}
			for row in history
		]


# ---------------------------------------------------------------- helpers


def map_status(yalidine_status):
	if not yalidine_status:
		return UNKNOWN
	return STATUS_MAP.get(yalidine_status.strip(), IN_TRANSIT)


def with_reason(status, reason):
	return f"{status} ({reason})" if reason else status


def split_name(full_name):
	"""Yalidine wants a first name and a family name: "Amine Benali" ->
	("Amine", "Benali"). One word only: repeat it."""
	words = (full_name or "").split()
	if not words:
		return "", ""
	return words[0], " ".join(words[1:]) or words[0]


def product_list(order):
	"""'2 x T-shirt Casbah Noir M, 1 x Mug Alger' (the delivery fee line left out)"""
	from dz_cod.cod.accounts import FEE_ITEM

	return ", ".join(
		f"{flt(row.qty):g} x {row.item_name or row.item_code}"
		for row in order.items
		if row.item_code != FEE_ITEM
	)


def order_of_parcel(tracking, courier, fields="name"):
	"""The submitted order of this courier's parcel. Two couriers can number
	their parcels the same way: a tracking number alone is not enough (review
	of 27 October 2026, 2.4)."""
	return frappe.db.get_value(
		"Sales Order",
		{"dz_tracking_number": tracking, "dz_courier": courier, "docstatus": 1},
		fields,
		as_dict=not isinstance(fields, str),
	)


def update_order(tracking, courier, status=None, status_on=None, payment_status=None, payment_id=None):
	"""Write what Yalidine says about a parcel of this courier on its order
	(sync or webhook).

	A status older than the one already stored is ignored: webhook events can
	arrive out of order. Returns the order name, or None if no order has this
	tracking number or the status is older than the stored one."""
	order = order_of_parcel(tracking, courier, ["name", "dz_courier_status_on"])
	if not order:
		return None

	values = {}
	if status:
		if status_on and order.dz_courier_status_on and get_datetime(status_on) < order.dz_courier_status_on:
			return None
		values.update({"dz_courier_status": status, "dz_courier_status_on": status_on})
	if payment_status:
		values.update({"dz_courier_payment_status": payment_status, "dz_courier_payment_id": payment_id})
	if values:
		frappe.db.set_value("Sales Order", order.name, values, update_modified=False)
	return order.name
