"""Collect every text of the app that a user can see on screen.

The app is written in French (labels, workflow states, messages). English
comes from dz_cod/translations/en.csv, which pairs each French text with its
English version. test_translations.py uses this list to make sure no text is
forgotten in en.csv.

Run by hand to list the texts still missing from en.csv:
    bench --site <site> execute dz_cod.tests.i18n_strings.print_missing
"""

import csv
import glob
import json
import os
import re

APP = os.path.dirname(os.path.dirname(__file__))  # .../dz_cod/dz_cod (the Python package)

# _("...") in Python and __("...") in JavaScript, single or double quotes
PY_CALL = re.compile(r"""(?<![\w.])_\(\s*(["'])((?:\\.|(?!\1).)+)\1""")
JS_CALL = re.compile(r"""__\(\s*(["'`])((?:\\.|(?!\1).)+)\1""")
# Choices of a Select filter in a report: options: "Produit\nArticle\nWilaya"
JS_SELECT = re.compile(r'options:\s*"([^"]*\\n[^"]*)"')

# Texts that are the same in both languages (names, brands, codes)
SAME_IN_ENGLISH = {
	"COD",
	"Wilaya",
	"Wilayas",
	"Stop desk",
	"Instagram",
	"Facebook",
	"WhatsApp",
	"TikTok",
	"Mock",
	"Yalidine",
	"Zone",
	"Code",
	"Commune",
	"API ID",
	"Webhooks (n8n)",
	# Already English (or the same word in English)
	"Amended From",
	"API Token",
	"OK",
	"Total",
	"Date",
	"Note",
	"Client",  # also an English word in Frappe (OAuth Client): must not be renamed
}

DOCTYPE_TEXT_KEYS = ("label", "description")
STEP_TEXT_KEYS = ("title", "description", "action_label", "report_description")


def read_json(path):
	with open(path, encoding="utf-8") as f:
		return json.load(f)


def add(found, text, where):
	text = (text or "").strip()
	if text and text not in SAME_IN_ENGLISH:
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


def collect():
	"""Return {text: where it was found} for every user-facing text of the app."""
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

	return found


def unescape(text):
	return text.replace("\\'", "'").replace('\\"', '"').replace("\\n", "\n")


def en_csv_path():
	return os.path.join(APP, "translations", "en.csv")


def read_en_csv():
	"""Return {French text: English text} from translations/en.csv."""
	path = en_csv_path()
	if not os.path.exists(path):
		return {}
	with open(path, encoding="utf-8", newline="") as f:
		return {row[0]: row[1] for row in csv.reader(f) if len(row) >= 2}


def missing():
	known = read_en_csv()
	return {text: where for text, where in collect().items() if text not in known}


def print_missing():
	for text, where in sorted(missing().items(), key=lambda item: item[1]):
		print(f"{where}\t{text}")
