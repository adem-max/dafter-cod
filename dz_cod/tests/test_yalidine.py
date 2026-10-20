"""Yalidine connector, with a fake HTTP layer: the real API is never called.

The fake answers are the JSON examples of Yalidine's own docs (verbatim copy,
September 2026), with our order names and tracking numbers put in.

Run: bench --site <site> run-tests --module dz_cod.tests.test_yalidine
"""

import hashlib
import hmac
import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import frappe
import requests
from frappe import _
from frappe.tests import IntegrationTestCase, UnitTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from dz_cod.cod import states as S
from dz_cod.couriers import get_adapter, places, yalidine_import, yalidine_webhook
from dz_cod.couriers.base import DELIVERED, IN_TRANSIT, RETURNED, UNKNOWN
from dz_cod.couriers.sync import sync_shipped_orders
from dz_cod.couriers.yalidine import BASE_URL, map_status, split_name
from dz_cod.demo import data as D
from dz_cod.demo import loader
from dz_cod.tests import helpers as h

YALIDINE = "Transporteur Test (Yalidine)"
SECRET = "test-webhook-secret"
NEW_WILAYA = "59 - Aflou"  # 2026 wilaya, parent 03 - Laghouat
LAGHOUAT = "03 - Laghouat"


def setup_yalidine_courier():
	loader.ensure(
		"Supplier",
		YALIDINE,
		{
			"supplier_name": YALIDINE,
			"supplier_group": D.SUPPLIER_GROUP,
			"is_transporter": 1,
			"dz_courier_adapter": "Yalidine",
			"dz_api_id": "94986571734304520846",  # the example values of Yalidine's docs
			"dz_api_token": "5MKfvcyQtO3eouL6tDv0VDFhUT8Sc7w5",
			"dz_from_wilaya": h.ALGER,
			"dz_webhook_secret": SECRET,
		},
	)


def adapter():
	courier = get_adapter(YALIDINE)
	courier.clear_quota()
	return courier


# ------------------------------------------------------------ fake HTTP layer


def response(body, status=200, headers=None):
	answer = requests.Response()
	answer.status_code = status
	answer._content = json.dumps(body).encode()
	answer.encoding = "utf-8"
	answer.headers.update(headers or {})
	return answer


class FakeYalidine:
	"""Stands in for requests.request. `routes` maps (method, path) to an answer:
	a dict (JSON body), a requests.Response, or a function(params, json) giving one."""

	def __init__(self, routes):
		self.routes = routes
		self.calls = []

	def __call__(self, method, url, headers=None, params=None, json=None, timeout=None):
		path = url.removeprefix(BASE_URL)
		self.calls.append(
			SimpleNamespace(method=method, path=path, params=params or {}, json=json, headers=headers)
		)
		answer = self.routes[(method, path)]
		if callable(answer):
			answer = answer(params or {}, json)
		return answer if isinstance(answer, requests.Response) else response(answer)

	def paths(self, method):
		return [call.path for call in self.calls if call.method == method]


@contextmanager
def fake_api(routes):
	api = FakeYalidine(routes)
	with patch("dz_cod.couriers.yalidine.requests.request", api), patch("time.sleep") as sleep:
		api.sleep = sleep
		yield api


def created(params, parcels):
	"""Docs example answer of POST parcels/, for the parcel we sent."""
	order_id = parcels[0]["order_id"]
	tracking = "yal-" + order_id[-5:]
	return {
		order_id: {
			"success": True,
			"order_id": order_id,
			"tracking": tracking,
			"import_id": 234,
			"label": f"https://yalidine.app/app/bordereau.php?tracking={tracking}&token=eVIzd0lCdFRGdXlmbkcwK1JBOWlHUT09",
			"labels": "https://yalidine.app/app/bordereau.php?import_id=352&si=5455878&token=SFUxek1qQVdhbXV2QjZDUXZM6548",
			"message": "",
		}
	}


NO_PARCEL = {"has_more": False, "total_data": 0, "data": [], "links": {}}
SHIP_ROUTES = {("GET", "parcels/"): NO_PARCEL, ("POST", "parcels/"): created}


def shipped_yalidine_order(**values):
	order = h.act(h.make_order(courier=YALIDINE, **values), S.ACTION_CONFIRM, S.ACTION_PREPARE)
	with fake_api(SHIP_ROUTES):
		return h.act(order, S.ACTION_SHIP)


def parcel(tracking, last_status, **values):
	"""One parcel as GET parcels/ returns it (fields we ask for)."""
	row = {
		"tracking": tracking,
		"order_id": None,
		"label": f"https://yalidine.app/app/bordereau.php?tracking={tracking}",
		"last_status": last_status,
		"date_last_status": "2026-10-15 10:00:00",
		"payment_status": "not-ready",
		"payment_id": None,
	}
	row.update(values)
	return row


def parcel_list(*parcels):
	return {"has_more": False, "total_data": len(parcels), "data": list(parcels), "links": {}}


# ------------------------------------------------------------------ tests


class TestYalidineRules(UnitTestCase):
	def test_status_mapping(self):
		self.assertEqual(map_status("Livré"), DELIVERED)
		self.assertEqual(map_status("Retourné au vendeur"), RETURNED)
		# Coming back, but not arrived yet: stays in transit (stock not moved yet)
		for status in ("Retour vers vendeur", "Echèc livraison", "Retour à retirer", "Sorti en livraison"):
			self.assertEqual(map_status(status), IN_TRANSIT)
		self.assertEqual(map_status(None), UNKNOWN)

	def test_name_split(self):
		self.assertEqual(split_name("Amine Ben Ali"), ("Amine", "Ben Ali"))
		self.assertEqual(split_name("Amine"), ("Amine", "Amine"))

	def test_commune_names_compare_without_accents_or_dashes(self):
		self.assertEqual(places.simplify("Bordj El-Kiffan "), places.simplify("bordj el kiffan"))
		self.assertEqual(places.simplify("Béjaïa"), "bejaia")


class TestYalidineShipping(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()
		setup_yalidine_courier()
		frappe.db.set_single_value("COD Settings", "auto_sync_courier_status", 1)

	def setUp(self):
		adapter()  # clears the quota memory of earlier tests

	def test_create_shipment_sends_the_parcel(self):
		order = h.act(
			h.make_order(courier=YALIDINE, dz_phone_2="0661234567"), S.ACTION_CONFIRM, S.ACTION_PREPARE
		)
		with fake_api(SHIP_ROUTES) as api:
			order = h.act(order, S.ACTION_SHIP)

		self.assertEqual(order.workflow_state, S.SHIPPED)
		self.assertEqual(order.dz_tracking_number, "yal-" + order.name[-5:])
		self.assertIn("bordereau.php", order.dz_label_url)

		post = next(call for call in api.calls if call.method == "POST")
		self.assertEqual(post.headers["X-API-ID"], "94986571734304520846")
		sent = post.json[0]
		self.assertEqual(sent["order_id"], order.name)
		self.assertEqual(sent["price"], order.dz_cod_amount)
		self.assertEqual(sent["declared_value"], order.dz_cod_amount)
		self.assertEqual((sent["firstname"], sent["familyname"]), ("Client", "Test COD"))
		self.assertEqual(sent["contact_phone"], "0555123456,0661234567")
		self.assertEqual((sent["from_wilaya_name"], sent["to_wilaya_name"]), ("Alger", "Alger"))
		self.assertEqual(sent["to_commune_name"], "Kouba")
		self.assertEqual(sent["product_list"], "1 x T-shirt de test")
		self.assertFalse(sent["is_stopdesk"])
		self.assertNotIn("stopdesk_id", sent)
		self.assertTrue(sent["freeshipping"])  # the delivery fee is already in the price
		for field in ("do_insurance", "length", "width", "height", "weight", "has_exchange", "address"):
			self.assertIn(field, sent)

	def test_refused_parcel_keeps_the_order_prepared(self):
		order = h.act(h.make_order(courier=YALIDINE), S.ACTION_CONFIRM, S.ACTION_PREPARE)
		refused = lambda params, parcels: {  # noqa: E731 - docs example of a failed parcel
			parcels[0]["order_id"]: {
				"success": False,
				"order_id": parcels[0]["order_id"],
				"tracking": None,
				"import_id": None,
				"label": None,
				"labels": None,
				"message": "The do_insurance parameter must be of type boolean",
			}
		}
		with fake_api({("GET", "parcels/"): NO_PARCEL, ("POST", "parcels/"): refused}):
			with self.assertRaisesRegex(frappe.ValidationError, "do_insurance parameter"):
				h.act(order, S.ACTION_SHIP)
		self.assertEqual(frappe.db.get_value("Sales Order", order.name, "workflow_state"), S.PREPARED)

	def test_second_click_reuses_the_parcel_already_created(self):
		order = h.act(h.make_order(courier=YALIDINE), S.ACTION_CONFIRM, S.ACTION_PREPARE)
		existing = parcel_list(parcel("yal-EXISTS", "En préparation", order_id=order.name))
		with fake_api({("GET", "parcels/"): existing}) as api:
			order = h.act(order, S.ACTION_SHIP)
		self.assertEqual(order.dz_tracking_number, "yal-EXISTS")
		self.assertEqual(api.paths("POST"), [])  # no second parcel
		self.assertEqual(api.calls[0].params["order_id"], order.name)

	def test_stop_desk_parcel(self):
		frappe.get_doc(
			{
				"doctype": "DZ Stop Desk",
				"center_id": "163001",
				"center_name": "Centre de Bordj El Kiffan",
				"commune_name": "Bordj El Kiffan",
				"wilaya": h.ALGER,
			}
		).insert()
		order = h.make_order(courier=YALIDINE, dz_delivery_type="Stop desk")
		with self.assertRaises(frappe.ValidationError) as error:
			adapter().build_parcel(order)
		# Compared in the active language: another test may have switched it
		self.assertEqual(
			str(error.exception), _("Choisissez le bureau stop desk de la commande avant d'expédier.")
		)

		order.dz_stopdesk_id = "163001"
		sent = adapter().build_parcel(order)
		self.assertTrue(sent["is_stopdesk"])
		self.assertEqual(sent["stopdesk_id"], "163001")
		self.assertEqual(sent["to_commune_name"], "Bordj El Kiffan")

	def test_new_wilaya_is_sent_as_its_parent(self):
		# Yalidine's docs list 58 wilayas: Aflou (59) goes as Laghouat (03)
		order = h.make_order(courier=YALIDINE, dz_wilaya=NEW_WILAYA, dz_commune="Aflou")
		self.assertEqual(adapter().build_parcel(order)["to_wilaya_name"], "Laghouat")

	def test_amount_above_yalidine_limit_is_refused(self):
		order = h.make_order(courier=YALIDINE)
		order.dz_cod_amount = 150001
		with self.assertRaisesRegex(frappe.ValidationError, "150000"):
			adapter().build_parcel(order)

	def test_sync_asks_for_50_parcels_per_call_and_moves_orders(self):
		delivered = shipped_yalidine_order()
		coming_back = shipped_yalidine_order()
		answer = parcel_list(
			parcel(delivered.dz_tracking_number, "Livré", payment_status="ready"),
			parcel(coming_back.dz_tracking_number, "Retour vers vendeur"),
		)
		with fake_api({("GET", "parcels/"): answer}) as api, patch("frappe.db.commit"):
			sync_shipped_orders()

		self.assertEqual(len(api.calls), 1)
		tracking_asked = api.calls[0].params["tracking"].split(",")
		self.assertIn(delivered.dz_tracking_number, tracking_asked)
		self.assertIn(coming_back.dz_tracking_number, tracking_asked)

		delivered.reload()
		coming_back.reload()
		self.assertEqual(delivered.workflow_state, S.DELIVERED)
		self.assertEqual(delivered.dz_courier_payment_status, "ready")
		self.assertEqual(coming_back.workflow_state, S.SHIPPED)  # not back yet
		self.assertEqual(coming_back.dz_courier_status, "Retour vers vendeur")

	def test_statuses_are_asked_in_batches_of_50(self):
		trackings = [f"yal-{n:04d}" for n in range(120)]
		with fake_api({("GET", "parcels/"): NO_PARCEL}) as api:
			adapter().get_statuses(trackings)
		self.assertEqual([len(call.params["tracking"].split(",")) for call in api.calls], [50, 50, 20])

	def test_tracking_history(self):
		history = {  # docs example
			"has_more": False,
			"total_data": 2,
			"data": [
				{
					"date_status": "2022-12-17 01:48:09",
					"tracking": "yal-337AAS",
					"status": "Sorti en livraison",
					"reason": "",
					"center_id": 120201,
					"center_name": "Centre de Bir el Ater",
					"wilaya_id": 12,
					"wilaya_name": "Tébessa",
					"commune_id": 1202,
					"commune_name": "Bir el Ater",
				},
				{
					"date_status": "2022-12-17 16:10:00",
					"tracking": "yal-337AAS",
					"status": "Tentative échouée",
					"reason": "Client ne répond pas",
					"center_id": None,
					"center_name": None,
					"wilaya_id": 12,
					"wilaya_name": "Tébessa",
					"commune_id": 1202,
					"commune_name": "Bir el Ater",
				},
			],
		}
		with fake_api({("GET", "histories/yal-337AAS"): history}):
			rows = adapter().get_tracking("yal-337AAS")
		self.assertEqual(rows[0]["status"], "Sorti en livraison")
		self.assertEqual(rows[0]["location"], "Centre de Bir el Ater")
		self.assertEqual(rows[1]["status"], "Tentative échouée (Client ne répond pas)")
		self.assertEqual(rows[1]["location"], "Bir el Ater, Tébessa")

	def test_429_gives_a_clear_message_and_stops_the_next_calls(self):
		too_many = response({"error": "Too Many Requests"}, status=429, headers={"Retry-After": "30"})
		with fake_api({("GET", "wilayas/"): too_many}) as api:
			with self.assertRaisesRegex(frappe.ValidationError, "30 s"):
				adapter().call("GET", "wilayas/")
			# Remembered: the next call does not even reach Yalidine
			with self.assertRaises(frappe.ValidationError):
				get_adapter(YALIDINE).call("GET", "wilayas/")
		self.assertEqual(len(api.calls), 1)

	def test_429_in_a_background_job_waits_and_retries(self):
		answers = iter(
			[response({}, status=429, headers={"Retry-After": "2"}), response({"data": [{"id": 16}]})]
		)
		with fake_api({("GET", "wilayas/"): lambda params, body: next(answers)}) as api:
			result = adapter().call("GET", "wilayas/", max_wait=60)
		self.assertEqual(result["data"][0]["id"], 16)
		self.assertEqual(len(api.calls), 2)
		self.assertTrue(api.sleep.called)

	def test_exhausted_quota_blocks_until_reset(self):
		last_call = response({"data": []}, headers={"x-minute-quota-left": "0", "x-day-quota-left": "9000"})
		with fake_api({("GET", "wilayas/"): last_call}) as api:
			adapter().call("GET", "wilayas/")
			with self.assertRaisesRegex(frappe.ValidationError, "quota"):
				get_adapter(YALIDINE).call("GET", "wilayas/")
		self.assertEqual(len(api.calls), 1)


class TestYalidineImports(IntegrationTestCase):
	"""Prices, communes and stop desks imported from Yalidine."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()
		setup_yalidine_courier()

	def setUp(self):
		adapter()

	def test_fee_import_writes_courier_costs_only(self):
		wilayas = {
			"has_more": False,
			"total_data": 2,
			"data": [
				{"id": 3, "name": "Laghouat", "zone": 3, "is_deliverable": 1},
				{"id": 16, "name": "Alger", "zone": 1, "is_deliverable": 1},
			],
		}
		prices = {  # chef-lieu first: (express_home, express_desk)
			3: [(301, "Laghouat", 800, 500), (302, "Ksar El Hirane", 850, None)],
			16: [(1630, "Bordj El Kiffan", 450, 300), (1601, "Alger Centre", 400, 250)],
		}

		def fees(params, body):  # docs example shape
			self.assertEqual(params["from_wilaya_id"], 16)  # the courier's departure wilaya
			communes = prices[params["to_wilaya_id"]]
			return {
				"from_wilaya_name": "Alger",
				"to_wilaya_name": "x",
				"zone": 1,
				"retour_fee": 250,
				"cod_percentage": 0.75,
				"insurance_percentage": 0.75,
				"oversize_fee": 100,
				"per_commune": {
					str(cid): {
						"commune_id": cid,
						"commune_name": name,
						"express_home": home,
						"express_desk": desk,
						"economic_home": None,
						"economic_desk": None,
					}
					for cid, name, home, desk in communes
				},
			}

		with fake_api({("GET", "wilayas/"): wilayas, ("GET", "fees/"): fees}) as api:
			yalidine_import.update_courier_costs(adapter())

		alger = frappe.get_doc("DZ Wilaya", h.ALGER)
		self.assertEqual((alger.home_courier_cost, alger.stopdesk_courier_cost), (400, 250))  # Alger Centre
		self.assertEqual((alger.home_rate, alger.stopdesk_rate), (400, 250))  # customer prices untouched
		laghouat = frappe.get_doc("DZ Wilaya", LAGHOUAT)
		self.assertEqual((laghouat.home_courier_cost, laghouat.stopdesk_courier_cost), (800, 500))
		# Aflou (59) is unknown to Yalidine: delivered as Laghouat, same cost
		self.assertEqual(frappe.db.get_value("DZ Wilaya", NEW_WILAYA, "home_courier_cost"), 800)
		# Calls are spaced out (50 calls per minute at most)
		self.assertEqual(api.paths("GET").count("fees/"), 2)
		api.sleep.assert_any_call(yalidine_import.PAUSE)

	def test_communes_and_stop_desks_import(self):
		pages = iter(
			[
				{
					"has_more": True,
					"data": [
						{
							"id": 1601,
							"name": "Alger Centre",
							"wilaya_id": 16,
							"wilaya_name": "Alger",
							"has_stop_desk": 1,
							"is_deliverable": 1,
						},
						{
							"id": 1630,
							"name": "Bordj El Kiffan",
							"wilaya_id": 16,
							"wilaya_name": "Alger",
							"has_stop_desk": 1,
							"is_deliverable": 1,
						},
					],
				},
				{
					"has_more": False,
					"data": [
						{
							"id": 1615,
							"name": "Kouba",
							"wilaya_id": 16,
							"wilaya_name": "Alger",
							"has_stop_desk": 0,
							"is_deliverable": 1,
						},
						{
							"id": 1699,
							"name": "Ile Fermée",
							"wilaya_id": 16,
							"wilaya_name": "Alger",
							"has_stop_desk": 0,
							"is_deliverable": 0,
						},
						{
							"id": 301,
							"name": "Aflou",
							"wilaya_id": 3,
							"wilaya_name": "Laghouat",
							"has_stop_desk": 1,
							"is_deliverable": 1,
						},
					],
				},
			]
		)
		centers = {
			"has_more": False,
			"total_data": 1,
			"data": [
				{
					"center_id": 163001,
					"name": "Centre de Bordj El Kiffan",
					"address": "Cité 1",
					"gps": "36.7,3.2",
					"commune_id": 1630,
					"commune_name": "Bordj El Kiffan",
					"wilaya_id": 16,
					"wilaya_name": "Alger",
				}
			],
		}
		routes = {("GET", "communes/"): lambda params, body: next(pages), ("GET", "centers/"): centers}
		with fake_api(routes):
			self.assertEqual(yalidine_import.update_places(adapter()), (5, 1))

		self.assertEqual(frappe.db.get_value("DZ Commune", "1630", "wilaya"), h.ALGER)
		self.assertIn("Kouba", places.commune_names(h.ALGER))
		# Aflou (59) has no commune of its own at Yalidine: its parent's list is offered
		self.assertEqual(places.commune_names(NEW_WILAYA), ["Aflou"])
		desks = places.stopdesk_query("DZ Stop Desk", "", "name", 0, 20, {"wilaya": h.ALGER})
		self.assertEqual(desks[0][0], "163001")

		# Confirming an order: Yalidine's spelling is stored, an unknown commune is refused
		order = h.act(h.make_order(courier=YALIDINE, dz_commune="kouba"), S.ACTION_CONFIRM)
		self.assertEqual(order.dz_commune, "Kouba")
		with self.assertRaisesRegex(frappe.ValidationError, "Koubba"):
			h.act(h.make_order(courier=YALIDINE, dz_commune="Koubba"), S.ACTION_CONFIRM)
		with self.assertRaisesRegex(frappe.ValidationError, "Ile Fermée"):  # not deliverable
			h.act(h.make_order(courier=YALIDINE, dz_commune="Ile Fermée"), S.ACTION_CONFIRM)


# ------------------------------------------------------------------ webhook


@contextmanager
def incoming(method, body=b"", query=None, headers=None):
	"""Pretend Yalidine is calling our endpoint."""
	environ = EnvironBuilder(
		method=method, query_string=query, data=body, headers=headers or {}, content_type="application/json"
	).get_environ()
	previous = getattr(frappe.local, "request", None)
	frappe.local.request = Request(environ)
	try:
		yield
	finally:
		frappe.local.request = previous


def signed(payload, secret=SECRET):
	body = json.dumps(payload).encode()
	return body, {"X-YALIDINE-SIGNATURE": hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}


def status_event(event_id, tracking, status, occurred_at="2026-10-15 12:00:00", reason=None):
	return {
		"event_id": event_id,
		"occurred_at": occurred_at,
		"data": {"tracking": tracking, "status": status, "reason": reason},
	}


class TestYalidineWebhook(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()
		setup_yalidine_courier()
		frappe.db.set_single_value("COD Settings", "auto_sync_courier_status", 1)

	def setUp(self):
		adapter()

	def deliver(self, body, headers):
		"""POST to the endpoint; returns (response, names of the events queued)."""
		with incoming("POST", body, headers=headers), patch("frappe.enqueue") as enqueue:
			answer = yalidine_webhook.receive()
		queued = enqueue.call_args.kwargs["event_names"] if enqueue.called else []
		if queued:
			with patch("frappe.db.commit"):
				yalidine_webhook.process_events(queued)
		return answer, queued

	def test_crc_token_is_echoed(self):
		with incoming("GET", query={"subscribe": "", "crc_token": "a1B2c3"}):
			answer = yalidine_webhook.receive()
		self.assertEqual(answer.status_code, 200)
		self.assertEqual(answer.get_data(as_text=True), "a1B2c3")

	def test_signed_status_event_moves_the_order(self):
		order = shipped_yalidine_order()
		payload = {
			"type": "parcel_status_updated",
			"events": [status_event("evt-ok-1", order.dz_tracking_number, "Livré")],
		}
		answer, queued = self.deliver(*signed(payload))

		self.assertEqual(answer.status_code, 200)
		self.assertEqual(queued, ["evt-ok-1"])
		order.reload()
		self.assertEqual(order.workflow_state, S.DELIVERED)
		self.assertEqual(order.dz_courier_status, "Livré")
		self.assertEqual(frappe.db.get_value("Courier Webhook Event", "evt-ok-1", "status"), "Traité")

	def test_bad_or_missing_signature_is_rejected(self):
		order = shipped_yalidine_order()
		payload = {
			"type": "parcel_status_updated",
			"events": [status_event("evt-bad-1", order.dz_tracking_number, "Livré")],
		}
		for headers in (signed(payload, secret="not-the-secret")[1], {}):
			answer, queued = self.deliver(json.dumps(payload).encode(), headers)
			self.assertEqual(answer.status_code, 400)
			self.assertEqual(queued, [])
		self.assertFalse(frappe.db.exists("Courier Webhook Event", "evt-bad-1"))
		self.assertEqual(frappe.db.get_value("Sales Order", order.name, "workflow_state"), S.SHIPPED)

	def test_duplicate_event_is_handled_once(self):
		order = shipped_yalidine_order()
		payload = {
			"type": "parcel_status_updated",
			"events": [status_event("evt-dup-1", order.dz_tracking_number, "Centre")],
		}
		first, queued_first = self.deliver(*signed(payload))
		again, queued_again = self.deliver(*signed(payload))
		self.assertEqual((first.status_code, again.status_code), (200, 200))
		self.assertEqual((queued_first, queued_again), (["evt-dup-1"], []))

	def test_older_event_does_not_overwrite_a_newer_status(self):
		order = shipped_yalidine_order()
		events = [
			status_event(
				"evt-new",
				order.dz_tracking_number,
				"Tentative échouée",
				"2026-10-15 16:00:00",
				"Client absent (reporté)",
			),
			status_event("evt-old", order.dz_tracking_number, "Sorti en livraison", "2026-10-15 09:00:00"),
		]
		self.deliver(*signed({"type": "parcel_status_updated", "events": events}))
		self.assertEqual(
			frappe.db.get_value("Sales Order", order.name, "dz_courier_status"),
			"Tentative échouée (Client absent (reporté))",
		)
		self.assertEqual(frappe.db.get_value("Courier Webhook Event", "evt-old", "status"), "Ignoré")

	def test_payment_event_is_stored_on_the_order(self):
		order = shipped_yalidine_order()
		payload = {  # docs example
			"type": "parcel_payment_updated",
			"events": [
				{
					"event_id": "evt-pay-1",
					"occurred_at": "2026-10-15 12:01:26",
					"data": {
						"tracking": order.dz_tracking_number,
						"status": "receivable",
						"payment_id": "pmt-123456",
					},
				}
			],
		}
		self.deliver(*signed(payload))
		values = frappe.db.get_value(
			"Sales Order", order.name, ["dz_courier_payment_status", "dz_courier_payment_id"], as_dict=True
		)
		self.assertEqual(
			(values.dz_courier_payment_status, values.dz_courier_payment_id), ("receivable", "pmt-123456")
		)
