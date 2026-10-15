"""Collect every text of the app that a user can see on screen.

The app is written in French (labels, workflow states, messages). Each other
language has a file in dz_cod/translations/ (en.csv, ar.csv) that pairs each
French text with its translation. test_translations.py uses this list to make
sure no text is forgotten in any of them.

Run by hand to list the texts still missing from a language file:
    bench --site <site> execute dz_cod.tests.i18n_strings.print_missing --kwargs "{'lang': 'ar'}"
"""

import csv
import glob
import json
import os
import re

APP = os.path.dirname(os.path.dirname(__file__))  # .../dz_cod/dz_cod (the Python package)

# The languages we translate into (French is the language of the code)
LANGUAGES = ("en", "ar")

# _("...") in Python and __("...") in JavaScript, single or double quotes
PY_CALL = re.compile(r"""(?<![\w.])_\(\s*(["'])((?:\\.|(?!\1).)+)\1""")
JS_CALL = re.compile(r"""__\(\s*(["'`])((?:\\.|(?!\1).)+)\1""")
# Choices of a Select filter in a report: options: "Produit\nArticle\nWilaya"
JS_SELECT = re.compile(r'options:\s*"([^"]*\\n[^"]*)"')

# Never in our language files, whatever the language
NOT_TRANSLATED = {
	# Names, brands, codes
	"COD",
	"Instagram",
	"Facebook",
	"WhatsApp",
	"TikTok",
	"Mock",
	"Yalidine",
	"API ID",
	"API Token",
	"Webhooks (n8n)",
	# English words that Frappe itself already translates into every language.
	# Our files apply to the whole site: a line here would also rename Frappe's own.
	"Amended From",
	"OK",
	"Total",
	"Date",
	"Note",
	"Client",  # Frappe's "Client" (OAuth Client)
	"Code",
}

# Words that are the same in English, but need translating into Arabic
SAME_IN_ENGLISH = {
	"Wilaya",
	"Stop desk",
	"Commune",
}


def skipped(lang):
	return NOT_TRANSLATED | (SAME_IN_ENGLISH if lang == "en" else set())

DOCTYPE_TEXT_KEYS = ("label", "description")
STEP_TEXT_KEYS = ("title", "description", "action_label", "report_description")


def read_json(path):
	with open(path, encoding="utf-8") as f:
		return json.load(f)


def add(found, text, where):
	text = (text or "").strip()
	if text:
		found.setdefault(text, where)


def add_select_options(found, options, where):
	for option in (options or "").split("\n"):
		add(found, option, where)


def from_field(found, field, where):
	"""A custom field or a doctype field: label, description, Select choices."""
	for key in DOCTYPE_TEXT_KEYS:
		add(found, field.get(key), where)
	if field.get("fieldtype") == "Select":
		add_select_options(found, field.get("options"), where)


def collect(lang="en"):
	"""Return {text: where it was found} for every text `lang` must translate."""
	from dz_cod.cod import states
	from dz_cod.setup import custom_fields, workflow

	found = {}

	# Custom fields on ERPNext doctypes
	for name in dir(custom_fields):
		value = getattr(custom_fields, name)
		if name.endswith("_FIELDS") and isinstance(value, list):
			for field in value:
				from_field(found, field, f"setup/custom_fields.py {name}")

	# Our own doctypes
	for path in glob.glob(os.path.join(APP, "dz_cod", "doctype", "*", "*.json")):
		for field in read_json(path).get("fields", []):
			from_field(found, field, os.path.relpath(path, APP))

	# Workflow: state names and button names
	for state in states.ALL_STATES:
		add(found, state, "cod/states.py")
	for name in dir(states):
		if name.startswith("ACTION_"):
			add(found, getattr(states, name), "cod/states.py")
	add(found, workflow.WORKFLOW_NAME, "setup/workflow.py")

	# Menu, home page, checklist, counters, charts
	for path in glob.glob(os.path.join(APP, "dz_cod", "sidebar", "*", "*.json")):
		for item in read_json(path).get("items", []):
			add(found, item.get("label"), os.path.relpath(path, APP))
	for path in glob.glob(os.path.join(APP, "dz_cod", "workspace", "*", "*.json")):
		doc = read_json(path)
		for table in ("links", "number_cards", "charts", "shortcuts"):
			for row in doc.get(table, []):
				add(found, row.get("label"), os.path.relpath(path, APP))
	for path in glob.glob(os.path.join(APP, "dz_cod", "module_onboarding", "*", "*.json")):
		add(found, read_json(path).get("title"), os.path.relpath(path, APP))
	for path in glob.glob(os.path.join(APP, "dz_cod", "onboarding_step", "*", "*.json")):
		doc = read_json(path)
		for key in STEP_TEXT_KEYS:
			add(found, doc.get(key), os.path.relpath(path, APP))
	for path in glob.glob(os.path.join(APP, "dz_cod", "number_card", "*", "*.json")):
		add(found, read_json(path).get("label"), os.path.relpath(path, APP))
	for path in glob.glob(os.path.join(APP, "dz_cod", "dashboard_chart", "*", "*.json")):
		add(found, read_json(path).get("empty_state_message"), os.path.relpath(path, APP))

	# Messages and labels in code: _("...") and __("...")
	for path in glob.glob(os.path.join(APP, "**", "*.py"), recursive=True):
		if f"{os.sep}tests{os.sep}" in path or f"{os.sep}demo{os.sep}" in path:
			continue
		with open(path, encoding="utf-8") as f:
			for match in PY_CALL.finditer(f.read()):
				add(found, unescape(match.group(2)), os.path.relpath(path, APP))
	for path in glob.glob(os.path.join(APP, "**", "*.js"), recursive=True):
		with open(path, encoding="utf-8") as f:
			source = f.read()
		for match in JS_CALL.finditer(source):
			add(found, unescape(match.group(2)), os.path.relpath(path, APP))
		for match in JS_SELECT.finditer(source):
			add_select_options(found, unescape(match.group(1)), os.path.relpath(path, APP))

	# Names of our own doctypes, reports and charts are English. French gets them
	# from fr.csv; every other non-English language needs them in its file too.
	if lang != "en":
		for folder in ("doctype", "report", "dashboard_chart"):
			for path in glob.glob(os.path.join(APP, "dz_cod", folder, "*", "*.json")):
				add(found, read_json(path).get("name"), os.path.relpath(path, APP))

	skip = skipped(lang)
	return {text: where for text, where in found.items() if text not in skip}


def unescape(text):
	return text.replace("\\'", "'").replace('\\"', '"').replace("\\n", "\n")


def csv_path(lang):
	return os.path.join(APP, "translations", f"{lang}.csv")


def read_csv(lang):
	"""Return {French text: translation} from translations/<lang>.csv."""
	path = csv_path(lang)
	if not os.path.exists(path):
		return {}
	with open(path, encoding="utf-8", newline="") as f:
		return {row[0]: row[1] for row in csv.reader(f) if len(row) >= 2}


def missing(lang):
	known = read_csv(lang)
	return {text: where for text, where in collect(lang).items() if text not in known}


def print_missing(lang="en"):
	for text, where in sorted(missing(lang).items(), key=lambda item: item[1]):
		print(f"{where}\t{text}")
