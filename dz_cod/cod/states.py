"""Names of the order states (Workflow states on Sales Order).

Always use these constants in code instead of typing the French text again,
so a typo cannot silently break a check.
"""

NEW = "Nouvelle"
UNREACHABLE = "Injoignable"
CONFIRMED = "Confirmée"
PREPARED = "Préparée"
SHIPPED = "Expédiée"
DELIVERED = "Livrée"
SETTLED = "Réglée"
RETURNED = "Retournée"
# Two cancel states are needed because Frappe cannot "cancel" a draft:
# - CANCELLED: the customer said no on the phone (order still a draft)
# - CANCELLED_AFTER_CONFIRMATION: the order was confirmed (submitted), then cancelled
CANCELLED = "Annulée"
CANCELLED_AFTER_CONFIRMATION = "Annulée après confirmation"

# Order of the normal path, used to sort reports and to check progress
MAIN_PATH = [NEW, CONFIRMED, PREPARED, SHIPPED, DELIVERED, SETTLED]

ALL_STATES = [
	NEW,
	UNREACHABLE,
	CONFIRMED,
	PREPARED,
	SHIPPED,
	DELIVERED,
	SETTLED,
	RETURNED,
	CANCELLED,
	CANCELLED_AFTER_CONFIRMATION,
]

# States where the parcel has left our warehouse (used for the return rate)
SHIPPED_OR_LATER = [SHIPPED, DELIVERED, SETTLED, RETURNED]

# A direct sale (cod/channel.py) is validated, then follows ERPNext's usual
# delivery note and invoice; its draft and cancel states are the ones above
VALIDATED = "Validée"
DIRECT_STATES = [VALIDATED]

# Workflow action (button) names
ACTION_CONFIRM = "Confirmer"
ACTION_NO_ANSWER = "Pas de réponse"
ACTION_CANCEL = "Annuler"
ACTION_PREPARE = "Préparer"
ACTION_SHIP = "Expédier"
ACTION_DELIVER = "Marquer livrée"
ACTION_RETURN = "Marquer retournée"
ACTION_SETTLE = "Marquer réglée"
ACTION_VALIDATE = "Valider"
