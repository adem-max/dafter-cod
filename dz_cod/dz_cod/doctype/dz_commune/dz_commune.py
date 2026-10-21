"""DZ Commune: the communes as a courier spells them, imported from the
courier (button on a Yalidine courier). Yalidine refuses a parcel whose
commune name it does not know, so the order form offers the list of the
order's courier as a pick list.

One list per connector, named <connector>-<courier's id> (Yalidine-1630).
Filled and refreshed by dz_cod.couriers.yalidine_import.import_places.
"""

from frappe.model.document import Document


class DZCommune(Document):
	pass
