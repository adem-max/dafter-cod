"""Courier connectors. See base.py for the interface."""

import frappe
from frappe import _

from dz_cod.couriers.base import ManualAdapter
from dz_cod.couriers.mock import MockAdapter
from dz_cod.couriers.yalidine import YalidineAdapter
from dz_cod.couriers.zrexpress import ZRExpressAdapter

# Value of the Supplier field "Connecteur" -> adapter class
ADAPTERS = {
	"Manuel": ManualAdapter,
	"Mock": MockAdapter,
	"Yalidine": YalidineAdapter,
	"ZR Express": ZRExpressAdapter,  # coming soon: works like Manuel for now
}


def get_adapter(courier_name):
	"""Return the connector object for a courier (Supplier name)."""
	courier = frappe.get_cached_doc("Supplier", courier_name)
	adapter_class = ADAPTERS.get(courier.get("dz_courier_adapter") or "Manuel")
	if not adapter_class:
		frappe.throw(_("Connecteur inconnu pour le transporteur {0}.").format(courier_name))
	return adapter_class(courier)
