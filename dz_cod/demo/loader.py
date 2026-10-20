"""Demo shop loader: a fictional Algerian clothing seller with 60 days of history.

USE A DEDICATED DEMO SITE, NEVER A CLIENT SITE.

    bench new-site demo.localhost --install-app erpnext
    bench --site demo.localhost install-app dz_cod
    bench --site demo.localhost execute dz_cod.demo.loader.load

Change the return rate (default 20 %):

    bench --site demo.localhost execute dz_cod.demo.loader.load --kwargs "{'return_rate': 0.3}"

Safe to run twice: everything it creates is looked up first and skipped if
it already exists. To start from scratch, see dz_cod/demo/wipe.py.

What it does, in order:
 1. company (DZD, Algeria), warehouses, shipping income account, COD Settings
 2. brands, item groups, sizes/colours, ~30 products with variants, prices
 3. 80 customers across the wilayas, 2 couriers (offline "Mock" connector)
 4. opening stock, 65 days ago
 5. 200 orders over the last 60 days, each with a small story (confirmed or
    not, shipped, delivered or returned...), replayed day by day through the
    real workflow, so the data is exactly what the app would produce
 6. one courier settlement (Versement) per courier per week, with a few
    disputes and forgotten parcels
"""

import random

import frappe
from dz_core.setup.tax import unset_default_templates
from dz_core.setup.wilayas import WILAYAS, wilaya_docname
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, getdate, today
from frappe.utils.nestedset import get_root_of

from dz_cod.cod import states as S
from dz_cod.cod.stock import get_returned_items, inspect_return
from dz_cod.demo import data as D
from dz_cod.features import ALL, configured, set_features
from dz_cod.setup.new_client import make_cod_the_home_page

DAYS_OF_HISTORY = 60
NB_CUSTOMERS = 80
NB_ORDERS = 200
SEED = 2026  # same seed = same demo every time

# Event names used in the order stories (most are workflow actions)
INSPECT = "Inspecter"

# The newest orders arrived today. Their outcome is fixed so the demo always
# shows every state: 3 not called yet, 2 unreachable, 1 confirmed.
TODAY_ORDERS = [
	[],
	[],
	[],
	[S.ACTION_NO_ANSWER],
	[S.ACTION_NO_ANSWER, S.ACTION_NO_ANSWER],
	[S.ACTION_CONFIRM],
]


def load(return_rate=0.2, seed=SEED):
	return_rate = float(return_rate)
	check_site_is_for_demo()
	rng = random.Random(seed)

	print("1/6 Société et paramètres...")
	setup_company()
	setup_settings()
	# A demo shows every option; a site without a list would have the base only
	if configured() is None:
		set_features(ALL)
	print("2/6 Articles...")
	setup_items()
	print("3/6 Clients et transporteurs...")
	customers = setup_customers(rng)
	setup_couriers()
	print("4/6 Stock d'ouverture...")
	setup_opening_stock()
	frappe.db.commit()

	print("5/6 Commandes (cela prend quelques minutes)...")
	stories = plan_orders(rng, customers, return_rate)
	replay_stories(stories)
	print("6/6 Versements des transporteurs...")
	create_settlements(rng)
	frappe.db.commit()
	print_summary()


def check_site_is_for_demo():
	"""Refuse to run on a site that has real orders from another company."""
	real_orders = frappe.db.count("Sales Order", {"company": ["!=", D.COMPANY]})
	if real_orders:
		frappe.throw(
			f"Ce site contient {real_orders} commandes d'une autre société. "
			"Le chargeur de démo doit tourner sur un site dédié à la démo."
		)


# --------------------------------------------------------------- 1. company


def setup_company():
	if frappe.db.exists("Company", D.COMPANY):
		return

	year = getdate(add_days(today(), -DAYS_OF_HISTORY - 10)).year
	args = {
		"language": "Français",
		"lang": "Français",
		"country": "Algeria",
		"timezone": "Africa/Algiers",
		"currency": "DZD",
		"company_name": D.COMPANY,
		"company_abbr": D.ABBR,
		"chart_of_accounts": "Algerie - Plan Comptable General 2 avec code",
		"fy_start_date": f"{year}-01-01",
		"fy_end_date": f"{year}-12-31",
		"setup_demo": 0,
	}
	if not frappe.is_setup_complete():
		# Fresh site: run ERPNext's setup wizard from code
		from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

		setup_complete(args)
	else:
		company = frappe.new_doc("Company")
		company.update(
			{
				"company_name": D.COMPANY,
				"abbr": D.ABBR,
				"default_currency": "DZD",
				"country": "Algeria",
				"chart_of_accounts": args["chart_of_accounts"],
			}
		)
		company.insert()
		system = frappe.get_doc("System Settings")
		system.update(
			{"country": "Algeria", "currency": "DZD", "time_zone": "Africa/Algiers", "language": "fr"}
		)
		system.save()

	# Saving the document (not just the value) also sets every user's default company
	defaults = frappe.get_doc("Global Defaults")
	defaults.update({"default_company": D.COMPANY, "default_currency": "DZD", "country": "Algeria"})
	defaults.save()
	ensure_fiscal_years()


def ensure_fiscal_years():
	"""The history may cross a year end: make sure every year exists."""
	first_year = getdate(add_days(today(), -DAYS_OF_HISTORY - 10)).year
	for year in range(first_year, getdate(today()).year + 1):
		if not frappe.db.exists("Fiscal Year", {"year_start_date": f"{year}-01-01"}):
			fy = frappe.new_doc("Fiscal Year")
			fy.update(
				{"year": str(year), "year_start_date": f"{year}-01-01", "year_end_date": f"{year}-12-31"}
			)
			fy.insert()


def warehouse_name(name):
	return f"{name} - {D.ABBR}"


def setup_settings():
	root_warehouse = frappe.db.get_value(
		"Warehouse", {"company": D.COMPANY, "is_group": 1, "parent_warehouse": ["is", "not set"]}
	)
	for name in (D.MAIN_WAREHOUSE, D.WORKSHOP_WAREHOUSE, D.RETURNS_WAREHOUSE):
		if not frappe.db.exists("Warehouse", warehouse_name(name)):
			wh = frappe.new_doc("Warehouse")
			wh.update({"warehouse_name": name, "company": D.COMPANY, "parent_warehouse": root_warehouse})
			wh.insert()

	# Income account for the delivery fees we charge customers
	shipping_account = f"{D.SHIPPING_ACCOUNT} - {D.ABBR}"
	if not frappe.db.exists("Account", shipping_account):
		income_root = frappe.db.get_value(
			"Account",
			{"company": D.COMPANY, "root_type": "Income", "is_group": 1, "parent_account": ["is", "not set"]},
		)
		account = frappe.new_doc("Account")
		account.update(
			{
				"account_name": D.SHIPPING_ACCOUNT,
				"company": D.COMPANY,
				"parent_account": income_root,
				"account_type": "Income Account",
			}
		)
		account.insert()

	settings = frappe.get_doc("COD Settings")
	settings.update(
		{
			"company": D.COMPANY,
			"main_warehouse": warehouse_name(D.MAIN_WAREHOUSE),
			"returns_warehouse": warehouse_name(D.RETURNS_WAREHOUSE),
			"shipping_income_account": shipping_account,
			"max_call_attempts": settings.max_call_attempts or 3,
		}
	)
	settings.save()

	# Default warehouse for stock movements. ERPNext 16.51+ keeps it on the
	# Company ("Warehouse Defaults"); up to 16.50 it is in Stock Settings
	if frappe.get_meta("Company").has_field("default_warehouse"):
		frappe.db.set_value("Company", D.COMPANY, "default_warehouse", warehouse_name(D.MAIN_WAREHOUSE))
	else:
		frappe.db.set_single_value("Stock Settings", "default_warehouse", warehouse_name(D.MAIN_WAREHOUSE))

	# The setup wizard makes "Algeria TVA 19%" the default: the order form would add
	# 19 % VAT to every order typed by hand. The shop is not VAT-registered: IFU.
	unset_default_templates(D.COMPANY)

	make_cod_the_home_page()
	complete_onboarding()


def complete_onboarding():
	"""The demo shop is fully set up: hide "Lancez votre boutique COD" so a
	prospect does not see an unfinished checklist."""
	onboarding = frappe.get_doc("Module Onboarding", "COD Onboarding")
	for row in onboarding.steps:
		frappe.db.set_value("Onboarding Step", row.step, "is_complete", 1)
	frappe.db.set_value("Module Onboarding", onboarding.name, "is_complete", 1)


# ----------------------------------------------------------------- 2. items


def setup_items():
	ensure("UOM", "Pièce", {"uom_name": "Pièce", "must_be_whole_number": 1})
	for brand in D.BRANDS:
		ensure("Brand", brand, {"brand": brand})

	root_group = get_root_of("Item Group")
	for group in (D.TSHIRTS, D.SWEATS, D.ACCESSORIES, D.RAW):
		ensure("Item Group", group, {"item_group_name": group, "parent_item_group": root_group})

	ensure_attribute("Taille", D.SIZES)
	ensure_attribute("Couleur", D.COLOURS)

	price_list = selling_price_list()
	for code, name, brand, group, price, cost, sizes, colours in D.PRODUCTS:
		for item_code in create_product(code, name, brand, group, cost, sizes, colours):
			ensure_price(item_code, price_list, price)

	for code, name, group, cost, sizes, colours in D.BLANKS:
		create_product(code, name, None, group, cost, sizes, colours, is_sales_item=0)


def ensure(doctype, name, values):
	if not frappe.db.exists(doctype, name):
		doc = frappe.new_doc(doctype)
		doc.update(values)
		doc.insert()


def ensure_attribute(name, values):
	if frappe.db.exists("Item Attribute", name):
		return
	attribute = frappe.new_doc("Item Attribute")
	attribute.attribute_name = name
	for value in values:
		# Short code used in the variant item code, e.g. "EU-TS-CASBAH-M-NOI"
		abbr = value if name == "Taille" else value.upper().replace("É", "E")[:3]
		attribute.append("item_attribute_values", {"attribute_value": value, "abbr": abbr})
	attribute.insert()


def selling_price_list():
	return frappe.db.get_single_value("Selling Settings", "selling_price_list") or frappe.db.get_value(
		"Price List", {"selling": 1, "enabled": 1}
	)


def create_product(code, name, brand, group, cost, sizes, colours, is_sales_item=1):
	"""Create one product. Returns the item codes that can be sold
	(the variants, or the item itself when it has no variants)."""
	attributes = []
	if sizes:
		attributes.append(("Taille", sizes))
	if colours:
		attributes.append(("Couleur", colours))

	if not frappe.db.exists("Item", code):
		item = frappe.new_doc("Item")
		item.update(
			{
				"item_code": code,
				"item_name": name,
				"item_group": group,
				"brand": brand,
				"stock_uom": "Pièce",
				"is_stock_item": 1,
				"is_sales_item": is_sales_item,
				"include_item_in_manufacturing": 0,
				"valuation_rate": cost,
				"has_variants": 1 if attributes else 0,
			}
		)
		for attribute, _values in attributes:
			item.append("attributes", {"attribute": attribute})
		item.insert()

	if not attributes:
		return [code]

	from erpnext.controllers.item_variant import create_variant

	variant_codes = []
	for combination in combinations(attributes):
		existing = find_variant(code, combination)
		if existing:
			variant_codes.append(existing)
			continue
		variant = create_variant(code, combination)
		# Readable name: "T-shirt Casbah Noir M"
		variant.item_name = " ".join(
			[name, combination.get("Couleur", ""), combination.get("Taille", "")]
		).strip()
		variant.valuation_rate = cost
		variant.insert()
		variant_codes.append(variant.name)
	return variant_codes


def combinations(attributes):
	"""All attribute combinations: [("Taille", ["S","M"]), ("Couleur", ["Noir"])]
	-> [{"Taille": "S", "Couleur": "Noir"}, {"Taille": "M", "Couleur": "Noir"}]"""
	result = [{}]
	for attribute, values in attributes:
		result = [dict(combo, **{attribute: value}) for combo in result for value in values]
	return result


def find_variant(template, combination):
	from erpnext.controllers.item_variant import get_variant

	return get_variant(template, args=combination)


def ensure_price(item_code, price_list, rate):
	if not frappe.db.exists("Item Price", {"item_code": item_code, "price_list": price_list}):
		price = frappe.new_doc("Item Price")
		price.update({"item_code": item_code, "price_list": price_list, "price_list_rate": rate})
		price.insert()


# ------------------------------------------------- 3. customers and couriers


def setup_customers(rng):
	"""Create 80 customers. Returns a list of dicts used to build orders."""
	ensure(
		"Customer Group",
		D.CUSTOMER_GROUP,
		{"customer_group_name": D.CUSTOMER_GROUP, "parent_customer_group": get_root_of("Customer Group")},
	)
	wilaya_names = {code: wilaya_docname(code, name) for code, name, _parent in WILAYAS}
	wilaya_codes = list(D.WILAYA_COMMUNES)
	weights = [D.WILAYA_COMMUNES[code][0] for code in wilaya_codes]

	# First build all the customer data (same random draws every run)...
	customers, used_names = [], set()
	while len(customers) < NB_CUSTOMERS:
		full_name = f"{rng.choice(D.FIRST_NAMES)} {rng.choice(D.LAST_NAMES)}"
		code = rng.choices(wilaya_codes, weights)[0]
		commune = rng.choice(D.WILAYA_COMMUNES[code][1])
		street = rng.choice(D.STREETS).format(n=rng.randint(1, 120), name=rng.choice(D.LAST_NAMES))
		phone = rng.choice(["05", "06", "07"]) + "".join(str(rng.randint(0, 9)) for _ in range(8))
		if full_name in used_names:
			continue
		used_names.add(full_name)
		customers.append(
			{
				"customer_name": full_name,
				"dz_phone": phone,
				"dz_wilaya": wilaya_names[code],
				"dz_commune": commune,
				"dz_address": f"{street}, {commune}",
				"zone": frappe.db.get_value("DZ Wilaya", wilaya_names[code], "zone"),
			}
		)

	# ...then create the ones that do not exist yet
	territory = get_root_of("Territory")
	for customer in customers:
		name = frappe.db.get_value("Customer", {"customer_name": customer["customer_name"]})
		if not name:
			doc = frappe.new_doc("Customer")
			doc.update({k: v for k, v in customer.items() if k != "zone"})
			doc.update(
				{"customer_type": "Individual", "customer_group": D.CUSTOMER_GROUP, "territory": territory}
			)
			doc.insert()
			name = doc.name
		customer["name"] = name
	return customers


def setup_couriers():
	ensure(
		"Supplier Group",
		D.SUPPLIER_GROUP,
		{"supplier_group_name": D.SUPPLIER_GROUP, "parent_supplier_group": get_root_of("Supplier Group")},
	)
	for courier in D.COURIERS:
		ensure(
			"Supplier",
			courier,
			{
				"supplier_name": courier,
				"supplier_group": D.SUPPLIER_GROUP,
				"is_transporter": 1,
				"dz_courier_adapter": "Mock",
			},
		)
	frappe.db.set_single_value("COD Settings", "default_courier", D.DEFAULT_COURIER)


# ----------------------------------------------------------- 4. opening stock


def opening_qty(item_code):
	"""How many pieces of each item we start with."""
	if item_code.startswith("FD-TS-BASIC"):
		return 60  # bulk orders use the basic t-shirt
	if item_code.startswith("BLANK"):
		return 80
	if "-HD-" in item_code or "-SW-" in item_code or "JOGGING" in item_code:
		return 12
	size = item_code.split("-")[-2] if item_code.count("-") >= 3 else ""
	return {"S": 10, "M": 18, "L": 18, "XL": 12, "XXL": 6}.get(size, 30)


def setup_opening_stock():
	if frappe.db.exists("Stock Entry", {"remarks": "Stock d'ouverture (démo)", "docstatus": 1}):
		return

	posting_date = add_days(today(), -DAYS_OF_HISTORY - 5)
	entry = frappe.new_doc("Stock Entry")
	entry.update(
		{
			"stock_entry_type": "Material Receipt",
			"company": D.COMPANY,
			"set_posting_time": 1,
			"posting_date": posting_date,
			"remarks": "Stock d'ouverture (démo)",
		}
	)
	items = frappe.get_all(
		"Item",
		filters={"has_variants": 0, "is_stock_item": 1, "brand": ["in", D.BRANDS]},
		fields=["name", "valuation_rate"],
	)
	blanks = frappe.get_all("Item", filters={"variant_of": "BLANK-TS"}, fields=["name", "valuation_rate"])
	for item in items + blanks:
		warehouse = D.WORKSHOP_WAREHOUSE if item.name.startswith("BLANK") else D.MAIN_WAREHOUSE
		entry.append(
			"items",
			{
				"item_code": item.name,
				"qty": opening_qty(item.name),
				"basic_rate": item.valuation_rate,
				"t_warehouse": warehouse_name(warehouse),
			},
		)
	entry.insert()
	entry.submit()


# --------------------------------------------------------------- 5. orders


def sellable_items():
	"""{template or item code: [sellable item codes]} for the demo brands."""
	result = {}
	for item in frappe.get_all(
		"Item",
		filters={"has_variants": 0, "is_sales_item": 1, "brand": ["in", D.BRANDS]},
		fields=["name", "variant_of"],
		order_by="name",
	):
		result.setdefault(item.variant_of or item.name, []).append(item.name)
	return result


def pick_lines(rng, catalogue, stock_left):
	"""Choose what a customer buys. Mostly one piece, sometimes two,
	rarely a bulk order (a team or an event)."""
	roll = rng.random()
	if roll < 0.05:
		# Bulk: one design, several sizes, 5 to 10 pieces each
		template = rng.choice(["FD-TS-BASIC", "EU-TS-CASBAH", "EU-TS-FENNEC"])
		colour_variants = catalogue[template]
		lines = [(code, rng.randint(5, 10)) for code in rng.sample(colour_variants, 3)]
	elif roll < 0.17:
		lines = [(rng.choice(catalogue[t]), 1) for t in rng.sample(sorted(catalogue), 2)]
	else:
		lines = [(rng.choice(catalogue[rng.choice(sorted(catalogue))]), 1)]

	# Never plan more than we have on the shelf (shipping would fail)
	lines = [(code, qty) for code, qty in lines if stock_left.get(code, 0) >= qty]
	for code, qty in lines:
		stock_left[code] -= qty
	return lines


def plan_orders(rng, customers, return_rate):
	"""Write the story of each order: a list of (date, action) events.

	Events after today are dropped, so recent orders naturally stop in an
	early state (Nouvelle, Confirmée, Expédiée...)."""
	catalogue = sellable_items()
	stock_left = {code: opening_qty(code) for codes in catalogue.values() for code in codes}
	couriers, courier_weights = list(D.COURIERS), list(D.COURIERS.values())
	sources, source_weights = list(D.SOURCES), list(D.SOURCES.values())
	last_day = getdate(today())
	stories = []

	for number in range(1, NB_ORDERS + 1):
		# More orders recently (the shop is growing)
		age = int(rng.triangular(0, DAYS_OF_HISTORY, 0))
		# The last few orders arrived today, with a fixed outcome (see TODAY_ORDERS)
		today_outcome = (
			TODAY_ORDERS[number - NB_ORDERS - 1] if number > NB_ORDERS - len(TODAY_ORDERS) else None
		)
		if today_outcome is not None:
			age = 0
		order_date = add_days(last_day, -age)
		customer = rng.choice(customers)
		lines = pick_lines(rng, catalogue, stock_left)
		story = {
			"key": f"DEMO-{number:04d}",
			"date": order_date,
			"customer": customer,
			"lines": lines,
			"delivery_type": "Stop desk" if rng.random() < 0.3 else "Domicile",
			"source": rng.choices(sources, source_weights)[0],
			"courier": rng.choices(couriers, courier_weights)[0],
			"events": [],
		}
		day = order_date
		events = story["events"]

		# Phone confirmation
		roll = rng.random()
		if roll < 0.07:
			events.append((day, S.ACTION_CANCEL))
		elif roll < 0.20:
			attempts = rng.randint(1, 3)
			for _ in range(attempts):
				events.append((day, S.ACTION_NO_ANSWER))
				day = add_days(day, 1)
			events.append((day, S.ACTION_CANCEL if rng.random() < 0.4 else S.ACTION_CONFIRM))
		else:
			# Most orders are confirmed by phone the next day
			day = add_days(day, rng.choice([0, 1, 1]))
			events.append((day, S.ACTION_CONFIRM))

		if events[-1][1] == S.ACTION_CONFIRM:
			if rng.random() < 0.03:
				events.append((add_days(day, 1), S.ACTION_CANCEL))  # cancelled after confirmation
			else:
				day = add_days(day, rng.randint(0, 1))
				events.append((day, S.ACTION_PREPARE))
				day = add_days(day, rng.randint(0, 1))
				events.append((day, S.ACTION_SHIP))
				# Transit time grows with distance (zone 1 = Alger ... 6 = far south)
				zone = customer["zone"] or 3
				day = add_days(day, rng.randint(1, 2) + zone // 2)
				# Bulk buyers (a team, an event) have agreed the order: they do not
				# refuse the parcel. One returned bulk parcel would also make its
				# product's return rate jump to 50 % in the report.
				is_bulk = any(qty >= 5 for _code, qty in lines)
				if rng.random() < return_rate and not is_bulk:
					# Customer refused or never came: parcel comes back a few days later
					day = add_days(day, rng.randint(3, 7))
					events.append((day, S.ACTION_RETURN))
					events.append((add_days(day, rng.randint(1, 4)), INSPECT))
				else:
					events.append((day, S.ACTION_DELIVER))

		if today_outcome is not None:
			story["events"] = events = [(last_day, action) for action in today_outcome]
		story["events"] = [(date, action) for date, action in events if getdate(date) <= last_day]
		if story["lines"]:
			stories.append(story)
	return stories


def replay_stories(stories):
	"""Create the orders and play all events in date order, like real life."""
	timeline = []
	for story in stories:
		order_name = create_order(story)
		for position, (date, action) in enumerate(story["events"]):
			timeline.append((getdate(date), story["date"], position, order_name, action))

	timeline.sort(key=lambda event: (event[0], event[1], event[3], event[2]))
	for count, (date, _order_date, _position, order_name, action) in enumerate(timeline, start=1):
		play_event(order_name, action, date)
		if count % 100 == 0:
			frappe.db.commit()
			print(f"   {count}/{len(timeline)} événements")


def create_order(story):
	existing = frappe.db.get_value("Sales Order", {"po_no": story["key"]})
	if existing:
		return existing

	customer = story["customer"]
	order = frappe.new_doc("Sales Order")
	order.update(
		{
			"company": D.COMPANY,
			"customer": customer["name"],
			"transaction_date": story["date"],
			"delivery_date": add_days(story["date"], 7),
			"po_no": story["key"],
			"dz_source": story["source"],
			"dz_delivery_type": story["delivery_type"],
			"dz_courier": story["courier"],
			"dz_phone": customer["dz_phone"],
			"dz_wilaya": customer["dz_wilaya"],
			"dz_commune": customer["dz_commune"],
			"dz_address": customer["dz_address"],
		}
	)
	price_list = selling_price_list()
	for item_code, qty in story["lines"]:
		# Server-side inserts do not fetch prices (the browser form does): set it
		rate = frappe.db.get_value(
			"Item Price", {"item_code": item_code, "price_list": price_list}, "price_list_rate"
		)
		order.append(
			"items",
			{
				"item_code": item_code,
				"qty": qty,
				"rate": rate,
				"price_list_rate": rate,
				"delivery_date": order.delivery_date,
			},
		)
	order.insert()
	return order.name


# For each event, the state the order must be in before it (else: already done)
EXPECTED_STATE = {
	S.ACTION_CONFIRM: [S.NEW, S.UNREACHABLE],
	S.ACTION_NO_ANSWER: [S.NEW, S.UNREACHABLE],
	S.ACTION_CANCEL: [S.NEW, S.UNREACHABLE, S.CONFIRMED, S.PREPARED],
	S.ACTION_PREPARE: [S.CONFIRMED],
	S.ACTION_SHIP: [S.PREPARED],
	S.ACTION_DELIVER: [S.SHIPPED],
	S.ACTION_RETURN: [S.SHIPPED],
}


def play_event(order_name, action, date):
	order = frappe.get_doc("Sales Order", order_name)

	if action == INSPECT:
		if order.workflow_state == S.RETURNED and not order.dz_return_inspected:
			inspect(order, date)
		return

	if order.workflow_state not in EXPECTED_STATE[action]:
		return  # already played (second run of the loader)
	if action == S.ACTION_NO_ANSWER and order.dz_call_attempts >= 3:
		return

	order.flags.dz_event_date = date
	apply_workflow(order, action)


def inspect(order, date):
	"""Most returns are fine; about one in six has a damaged piece."""
	items = []
	for index, row in enumerate(get_returned_items(order.name)):
		# sum of the letters: a stable "random" choice (same result every run)
		damaged = 1 if index == 0 and sum(map(ord, order.name)) % 6 == 0 else 0
		items.append(
			{"item_code": row["item_code"], "good_qty": row["qty"] - damaged, "damaged_qty": damaged}
		)
	inspect_return(order.name, items, posting_date=date)


# ---------------------------------------------------------- 6. settlements


def create_settlements(rng):
	"""Each courier pays once a week for parcels delivered at least 2 days
	before. Now and then a parcel is paid short (dispute) or forgotten."""
	last_day = getdate(today())
	for courier in D.COURIERS:
		for weeks_ago in range(DAYS_OF_HISTORY // 7, -1, -1):
			pay_day = add_days(last_day, -3 - 7 * weeks_ago)
			reference = f"DEMO-{courier[:5].upper()}-{pay_day}"
			if frappe.db.exists("Courier Settlement", {"reference": reference}):
				continue
			orders = frappe.get_all(
				"Sales Order",
				filters={
					"workflow_state": S.DELIVERED,
					"dz_courier": courier,
					"dz_delivered_on": ["<=", add_days(pay_day, -2)],
				},
				fields=["name", "dz_tracking_number", "dz_cod_amount", "dz_courier_fee"],
				order_by="name",
			)
			# Orders already disputed in an earlier Versement stay disputed
			already_listed = set(frappe.get_all("Courier Settlement Item", pluck="sales_order"))
			orders = [order for order in orders if order.name not in already_listed]
			if not orders:
				continue

			settlement = frappe.new_doc("Courier Settlement")
			settlement.update(
				{"courier": courier, "company": D.COMPANY, "posting_date": pay_day, "reference": reference}
			)
			for order in orders:
				roll = rng.random()
				if roll < 0.04:
					continue  # the courier "forgot" this parcel: it shows as missing
				collected = order.dz_cod_amount
				if roll < 0.08:
					collected -= 500  # paid short: a dispute to follow up
				settlement.append(
					"items",
					{
						"tracking_number": order.dz_tracking_number,
						"collected_amount": collected,
						"courier_fee": order.dz_courier_fee,
					},
				)
			settlement.insert()
			settlement.amount_received = settlement.total_net
			settlement.save()
			settlement.submit()


def print_summary():
	states = frappe.get_all("Sales Order", filters={"company": D.COMPANY}, pluck="workflow_state")
	print("\nDémo chargée. Commandes par état :")
	for state in S.ALL_STATES:
		print(f"   {state:<30} {states.count(state)}")
	print(f"   {'Total':<30} {len(states)}")
