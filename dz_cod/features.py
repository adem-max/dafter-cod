"""What each client gets: optional features, switched on per site.

Each client buys the base (orders, stock, Versements, couriers by hand...) and
a hand-picked list of the optional features below. The list lives in the
site's site_config.json, key "dz_cod_features", so only the vendor (who has
the server) can change it, with:

    bench --site <site> dz-cod-features --list
    bench --site <site> dz-cod-features --enable phone_checks
    bench --site <site> dz-cod-features --set courier_api,labels_reports

Rules (docs/FEATURES.md):
- key missing: EVERY feature is on (demo, test and sites made before the
  switches keep working); a list, even empty, is followed exactly.
- a feature that is off is hidden: buttons (JS reads frappe.boot.dz_cod_features),
  reports and print formats (disabled records drop out of menus), and the
  server refuses its actions with "Fonction non incluse dans votre offre".
- apply_features() makes the site's records match the list. It runs after
  every migrate, because migrate re-imports our standard reports and print
  formats and would switch them back on.
"""

import functools

import frappe
from frappe import _

CONFIG_KEY = "dz_cod_features"
MESSAGE = "Fonction non incluse dans votre offre"

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
		"webhooks": True,
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


class FeatureNotEnabled(frappe.PermissionError):
	pass


def configured():
	"""The list in site_config, or None when the key is missing."""
	value = frappe.conf.get(CONFIG_KEY)
	if value is None:
		return None
	if isinstance(value, str):  # tolerate "a,b" typed by hand
		value = [part.strip() for part in value.split(",") if part.strip()]
	return list(value)


def enabled():
	"""Set of the features this site has."""
	value = configured()
	if value is None:
		return set(FEATURES)
	return {name for name in value if name in FEATURES}


def is_enabled(feature):
	return feature in enabled()


def check(feature):
	if not is_enabled(feature):
		raise FeatureNotEnabled(_("Fonction non incluse dans votre offre"))


def requires_feature(feature):
	"""Decorator for whitelisted methods: refuse when the feature is off.
	Put it UNDER @frappe.whitelist()."""

	def decorator(function):
		@functools.wraps(function)
		def wrapper(*args, **kwargs):
			check(feature)
			return function(*args, **kwargs)

		return wrapper

	return decorator


def boot(bootinfo):
	"""extend_bootinfo hook: the browser hides what the site doesn't have."""
	bootinfo.dz_cod_features = sorted(enabled())


# ------------------------------------------------------------ apply to records


def apply_features():
	"""Make reports, print formats and webhooks match the site's features."""
	on = enabled()
	for name, feature in FEATURES.items():
		disabled = 0 if name in on else 1
		for report in feature.get("reports", []):
			if frappe.db.exists("Report", report):
				frappe.db.set_value("Report", report, "disabled", disabled, update_modified=False)
		for print_format in feature.get("print_formats", []):
			if frappe.db.exists("Print Format", print_format):
				frappe.db.set_value("Print Format", print_format, "disabled", disabled, update_modified=False)
		if feature.get("webhooks"):
			apply_webhooks(name in on)
	frappe.clear_cache()


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


def set_features(features):
	"""Write the site's list (None = remove the key = everything) and apply it."""
	from frappe.installer import update_site_config

	if features is None:
		update_site_config(CONFIG_KEY, "None")
	else:
		unknown = [name for name in features if name not in FEATURES]
		if unknown:
			frappe.throw(_("Fonctions inconnues : {0}").format(", ".join(unknown)))
		update_site_config(CONFIG_KEY, sorted(set(features)))
	frappe.local.conf = frappe._dict(frappe.get_site_config())
	apply_features()


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
