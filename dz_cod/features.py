"""The optional features of the COD app, and the checks that guard them.

The mechanism (the site's list, `is_enabled`, `@requires_feature`, the
`dz-features` command, hiding reports and print formats) is dz_core's:
dz_core/features.py. This app only declares its four features, through
`dz_features = ["dz_cod.features.FEATURES"]` in hooks.py, and keeps the
guards that are about couriers and webhooks.

    bench --site <site> dz-features --list          # dz-cod-features still works
    bench --site <site> dz-features --enable phone_checks

Rules for clients: docs/FEATURES.md.
"""

import frappe

# The mechanism, imported here so COD modules keep one place to import from
from dz_core.features import (
	CONFIG_KEY,
	MESSAGE,
	FeatureNotEnabled,
	apply_features,
	check,
	configured,
	enabled,
	is_enabled,
	requires_feature,
	set_features,
)
from frappe import _

FEATURES = {
	"courier_api": {
		"label": "Connecteurs transporteurs (API)",
		"description": "Yalidine (ZR Express bientôt) : colis, étiquettes, tarifs, communes, "
		"webhooks et synchronisation automatique des statuts.",
		"reports": [],
		"print_formats": [],
	},
	"phone_checks": {
		"label": "Contrôles téléphone",
		"description": "Avertit des colis déjà refusés pour un numéro et des clients en double.",
		"reports": [],
		"print_formats": [],
	},
	"n8n_webhooks": {
		"label": "Webhooks n8n",
		"description": "Envoie les commandes à n8n à chaque étape (Confirmée, Expédiée, Livrée, Retournée).",
		"reports": [],
		"print_formats": [],
		# Switch the four COD webhooks off and back on (apply_webhooks below)
		"on_change": "dz_cod.features.apply_webhooks",
	},
	"labels_reports": {
		"label": "Bordereau et rapports",
		"description": "Bordereau COD avec code-barres, rapports Commandes par jour et Taux de retour.",
		"reports": ["COD Daily Orders", "COD Return Rate"],
		"print_formats": ["Bordereau COD"],
	},
}

# Courier connectors that need "courier_api" (Manuel and Mock are in the base)
API_ADAPTERS = {"Yalidine", "ZR Express"}


# ------------------------------------------------------------ the n8n webhooks


def remembered_key(webhook):
	return f"dz_cod_webhook_enabled::{webhook}"


def apply_webhooks(feature_on):
	"""Off: remember whether each COD webhook was enabled, then disable it.
	On: put back what was remembered (the client's n8n URLs are never touched)."""
	from dz_cod.setup.webhooks import WEBHOOKS, webhook_name

	for state, _event in WEBHOOKS:
		name = webhook_name(state)
		if not frappe.db.exists("Webhook", name):
			continue
		key = remembered_key(name)
		if feature_on:
			remembered = frappe.db.get_default(key)
			if remembered is not None:
				frappe.db.set_value("Webhook", name, "enabled", int(remembered), update_modified=False)
				frappe.defaults.clear_default(key, parent="__default")
		else:
			if frappe.db.get_default(key) is None:
				frappe.db.set_default(key, str(frappe.db.get_value("Webhook", name, "enabled") or 0))
			frappe.db.set_value("Webhook", name, "enabled", 0, update_modified=False)


# ------------------------------------------------------------ hooks


def check_courier_connector(supplier, method=None):
	"""Supplier "validate" hook: API connectors need "courier_api"."""
	if supplier.get("dz_courier_adapter") in API_ADAPTERS and not is_enabled("courier_api"):
		frappe.throw(
			_("Le connecteur {0} n'est pas inclus dans votre offre : choisissez Manuel.").format(
				supplier.dz_courier_adapter
			),
			FeatureNotEnabled,
		)


def check_webhook(webhook, method=None):
	"""Webhook "validate" hook: the COD webhooks can only be enabled with "n8n_webhooks"."""
	from dz_cod.setup.webhooks import WEBHOOKS, webhook_name

	ours = {webhook_name(state) for state, _event in WEBHOOKS}
	switched_on = webhook.enabled and (webhook.is_new() or webhook.has_value_changed("enabled"))
	if webhook.name in ours and switched_on and not is_enabled("n8n_webhooks"):
		frappe.throw(_("Fonction non incluse dans votre offre"), FeatureNotEnabled)
