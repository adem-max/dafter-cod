"""The base interface every courier connector ("adapter") must follow.

Why an adapter? Each delivery company has its own API. The rest of the app
should not care which one is used: it only calls the three methods below.
To add a new courier, write one new class with these three methods and add it
to ADAPTERS in dz_cod/couriers/__init__.py. Nothing else changes.

Statuses returned by get_status() always use OUR small vocabulary below, not
the courier's own words. Translating the courier's words into ours is the
adapter's job.
"""

# Our parcel status vocabulary
IN_TRANSIT = "in_transit"
DELIVERED = "delivered"
RETURNED = "returned"
UNKNOWN = "unknown"


class CourierAdapter:
	"""Base class. `courier` is the Supplier document of the delivery company."""

	# Shown in error messages
	label = "Base"

	def __init__(self, courier):
		self.courier = courier

	def check_order(self, order):
		"""Optional: refuse an order the courier would refuse (unknown commune...).
		Called at confirmation, before the order is locked. No network call here."""

	def create_shipment(self, order):
		"""Declare the parcel to the courier.

		Receives the Sales Order. Returns the tracking number (text), or None
		if the tracking number must be typed by hand.
		"""
		raise NotImplementedError

	def get_status(self, tracking_number):
		"""Return one of IN_TRANSIT, DELIVERED, RETURNED or UNKNOWN."""
		raise NotImplementedError

	def get_statuses(self, tracking_numbers):
		"""Several parcels at once: {tracking_number: status}. Connectors whose
		API answers for many parcels in one call override this (fewer calls)."""
		return {tracking: self.get_status(tracking) for tracking in tracking_numbers}

	def get_tracking(self, tracking_number):
		"""Return the parcel history as a list of dicts:
		[{"date": "2026-10-01 10:00:00", "status": "...", "location": "..."}]
		"""
		raise NotImplementedError


class ManualAdapter(CourierAdapter):
	"""No connection: the operator types the tracking number and moves the
	order to Livrée / Retournée by hand. This is the default."""

	label = "Manuel"

	def create_shipment(self, order):
		return None

	def get_status(self, tracking_number):
		return UNKNOWN

	def get_tracking(self, tracking_number):
		return []
