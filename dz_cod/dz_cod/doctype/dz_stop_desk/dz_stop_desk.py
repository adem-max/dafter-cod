"""DZ Stop Desk: a courier's offices where customers collect parcels
("stop desk"), imported from the courier (button on a Yalidine courier).
The order links to its office in dz_stopdesk_id; the parcel sends the
office's own id at the courier (center_id).

One list per connector, named <connector>-<courier's id> (Yalidine-163001).
"""

from frappe.model.document import Document


class DZStopDesk(Document):
	pass
