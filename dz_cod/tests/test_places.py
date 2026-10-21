"""Communes and stop desks of several connectors side by side
(dz_cod/couriers/places.py), and the patches that moved the Yalidine-only
records to that shape.

Run: bench --site <site> run-tests --module dz_cod.tests.test_places
"""

import frappe
from frappe.tests import IntegrationTestCase

from dz_cod.couriers import get_adapter, places
from dz_cod.demo import data as D
from dz_cod.demo import loader
from dz_cod.patches import name_places_by_connector, rename_place_fields
from dz_cod.tests import helpers as h
from dz_cod.tests.test_yalidine import YALIDINE, setup_yalidine_courier

ZR = "Transporteur Test (ZR Express)"


def add_commune(connector, courier_id, name, wilaya=h.ALGER):
	frappe.get_doc(
		{
			"doctype": "DZ Commune",
			"connector": connector,
			"courier_id": courier_id,
			"commune_name": name,
			"wilaya": wilaya,
			"is_deliverable": 1,
		}
	).insert()


def add_desk(connector, center_id, name, wilaya=h.ALGER):
	frappe.get_doc(
		{
			"doctype": "DZ Stop Desk",
			"connector": connector,
			"center_id": center_id,
			"center_name": name,
			"wilaya": wilaya,
		}
	).insert()


def desks_of(courier):
	rows = places.stopdesk_query("DZ Stop Desk", "", "name", 0, 20, {"wilaya": h.ALGER, "courier": courier})
	return [row[0] for row in rows]


class TestPlaces(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.setup_fixtures()
		setup_yalidine_courier()
		loader.ensure(
			"Supplier",
			ZR,
			{
				"supplier_name": ZR,
				"supplier_group": D.SUPPLIER_GROUP,
				"is_transporter": 1,
				"dz_courier_adapter": "ZR Express",
			},
		)

	def test_two_connectors_do_not_mix(self):
		# Same ids at both couriers, each with its own spelling and offices
		add_commune("Yalidine", "1630", "Bordj El Kiffan")
		add_commune("ZR Express", "1630", "Bordj El-Kiffan (ZR)")
		add_desk("Yalidine", "163001", "Centre de Bordj El Kiffan")
		add_desk("ZR Express", "163001", "Agence ZR Bordj El Kiffan")

		# (the other test of the class may have left Yalidine records too)
		self.assertIn("Bordj El Kiffan", places.commune_names(h.ALGER, YALIDINE))
		self.assertNotIn("Bordj El-Kiffan (ZR)", places.commune_names(h.ALGER, YALIDINE))
		self.assertEqual(places.commune_names(h.ALGER, ZR), ["Bordj El-Kiffan (ZR)"])
		self.assertIn("Yalidine-163001", desks_of(YALIDINE))
		self.assertNotIn("ZR Express-163001", desks_of(YALIDINE))
		self.assertEqual(desks_of(ZR), ["ZR Express-163001"])

		# Yalidine checks the commune against its own list only
		yalidine = get_adapter(YALIDINE)
		self.assertEqual(yalidine.commune_name(h.ALGER, "bordj el kiffan"), "Bordj El Kiffan")
		with self.assertRaises(frappe.ValidationError):
			yalidine.commune_name(h.ALGER, "Bordj El-Kiffan (ZR)")

	def test_patch_names_old_records_and_orders_follow(self):
		# The shape before October 2026: named by Yalidine's id, no connector
		for doctype, values in (
			("DZ Commune", {"name": "1615", "courier_id": "1615", "commune_name": "Kouba"}),
			("DZ Stop Desk", {"name": "161501", "center_id": "161501", "center_name": "Centre de Kouba"}),
		):
			frappe.get_doc({"doctype": doctype, "wilaya": h.ALGER, **values}).db_insert()
		order = h.make_order(dz_delivery_type="Stop desk", dz_stopdesk_id="161501")

		rename_place_fields.execute()  # already migrated: does nothing
		name_places_by_connector.execute()

		self.assertTrue(frappe.db.has_column("DZ Commune", "courier_id"))
		self.assertEqual(frappe.db.get_value("DZ Commune", "Yalidine-1615", "connector"), "Yalidine")
		self.assertFalse(frappe.db.exists("DZ Commune", "1615"))
		self.assertEqual(frappe.db.get_value("DZ Stop Desk", "Yalidine-161501", "connector"), "Yalidine")
		self.assertFalse(frappe.db.exists("DZ Stop Desk", "161501"))
		self.assertEqual(frappe.db.get_value("Sales Order", order.name, "dz_stopdesk_id"), "Yalidine-161501")

		# A second run changes nothing
		name_places_by_connector.execute()
		self.assertTrue(frappe.db.exists("DZ Stop Desk", "Yalidine-161501"))
