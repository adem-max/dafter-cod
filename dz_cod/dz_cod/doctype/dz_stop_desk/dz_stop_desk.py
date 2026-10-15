"""DZ Stop Desk: the courier's offices where customers collect parcels
("stop desk"), imported from Yalidine (button on the courier). The order
stores the office id in dz_stopdesk_id; Yalidine needs it for every
stop-desk parcel.
"""

from frappe.model.document import Document


class DZStopDesk(Document):
	pass
