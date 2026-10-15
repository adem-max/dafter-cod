"""DZ Commune: the communes as the courier spells them, imported from
Yalidine (button on the courier). Yalidine refuses a parcel whose commune
name it does not know, so the order form offers this list as a pick list.

Filled and refreshed by dz_cod.couriers.yalidine_import.import_places.
"""

from frappe.model.document import Document


class DZCommune(Document):
	pass
