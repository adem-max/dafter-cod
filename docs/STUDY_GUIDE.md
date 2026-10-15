# Study guide

Written for you, Adem: a planning engineer who knows Oracle EBS and some
Python, and who must be able to read, deploy, debug and rebuild this kit
alone.

Each chapter follows the same pattern:

1. **Mental model**: what the thing is, with an EBS / manufacturing analogy.
2. **The lines that matter**: the one or two lines of code to really understand.
3. **Break it on purpose**: a safe experiment on your *demo* site, to see the error you will one day meet for real.
4. **Rebuild it yourself**: a small exercise that proves you understood.
5. **Failure modes**: what goes wrong in real life, and how to find out why.

Do the exercises on your laptop (docs/LOCAL_TEST.md), **never on a client
site**. After each "break it", undo your change (`git checkout -- <file>` and
`bench --site demo.localhost migrate`).

**Read first:** chapter 0 (the big picture), chapter 3 (the order life cycle)
and chapter 4 (stock). Everything else hangs off those three.

---

## Contents

0. [The big picture: bench, site, app, doctype](#0-the-big-picture)
1. [Custom fields](#1-custom-fields)
2. [Settings](#2-settings-paramètres-cod)
3. [The order life cycle: Workflow + hooks](#3-the-order-life-cycle)
4. [Stock: reservation, shipment, return, inspection](#4-stock-movements)
5. [Shipping rates](#5-shipping-rates)
6. [Courier connectors (adapters)](#6-courier-connectors)
7. [Courier settlement (Versement)](#7-courier-settlement-versement)
8. [Webhooks](#8-webhooks)
9. [Reports](#9-reports)
10. [The demo loader](#10-the-demo-loader)
11. [Tests](#11-tests)
12. [Production: processes, backups, updates](#12-production)
13. [How to read an error](#13-how-to-read-an-error)
14. [A four-week learning plan](#14-a-four-week-learning-plan)
15. [Languages: French, English, Arabic](#15-languages-french-english-arabic)

---

## 0. The big picture

### Mental model

| Frappe / ERPNext | Oracle EBS equivalent |
|------------------|-----------------------|
| **bench** (the `~/frappe-bench` folder + the `bench` command) | the application tier: `APPL_TOP`, `adadmin`, `adcmctl` |
| **app** (frappe, erpnext, dz_cod) | a product top: `FND_TOP`, `INV_TOP`... and **dz_cod is your `XX_TOP`** (custom top) |
| **site** (one per client, one database each) | one EBS instance (but here they share the same code) |
| **DocType** | a table + its form + its API + its permissions, all described in one JSON file |
| **document** (one Sales Order) | one row (plus its child rows) |
| **hooks.py** | the registration of your custom code: like registering a concurrent program or a business event subscription |
| **`bench migrate`** | `adpatch` + `autoconfig`: applies new table definitions, custom fields, patches |
| **background workers + scheduler** | the concurrent managers |

The golden rule is the same as in EBS: **never modify seeded code**.
In EBS you never edit standard packages; you put your code in `XX_TOP` and
hook it in. Here you never edit `apps/frappe` or `apps/erpnext`; everything
lives in `apps/dz_cod`, and `hooks.py` plugs it in. That is why `bench update`
can upgrade ERPNext without destroying your work.

The folder that matters:

```
dz_cod/
  hooks.py                 <- how the app plugs into ERPNext (read it first, it is short)
  cod/                     <- the business rules: order life cycle, stock, shipping, settlement
  couriers/                <- courier connectors (adapter pattern)
  setup/                   <- what install/migrate creates: custom fields, workflow, wilayas, webhooks
  dz_cod/doctype/          <- our 4 doctypes (JSON = definition, .py = rules, .js = form behaviour)
  dz_cod/report/           <- our 3 reports
  demo/                    <- the demo shop loader and wipe
  tests/                   <- automated tests
  public/js/sales_order.js <- extra buttons on the order form
  translations/fr.csv      <- French names for our doctypes
  translations/en.csv      <- English version of every French text of the app
  translations/ar.csv      <- Arabic version (Frappe switches the screen to right-to-left)
```

### The lines that matter

`dz_cod/hooks.py`:

```python
after_migrate = "dz_cod.setup.install.after_migrate"
doc_events = {"Sales Order": {"on_update_after_submit": "dz_cod.cod.order.on_update_after_submit", ...}}
```

The first line means "every `bench migrate`, run our setup" (custom fields,
workflow, wilayas, webhooks). The second means "every time a submitted
Sales Order is saved, also call our function". Almost everything in this kit
starts from one of these two lines.

### Break it on purpose

In `hooks.py`, rename `"dz_cod.cod.order.on_update_after_submit"` to
`"dz_cod.cod.order.on_update_after_submitX"`. Restart `bench start`, open a
"Préparée" order and click **Actions → Expédier**. You get an error saying
the module has no attribute `on_update_after_submitX`. Lesson: a typo in
hooks.py breaks every save of that doctype. Read the *last* line of the
traceback first.

### Rebuild it yourself

Add a hook that prints a line in the terminal running `bench start` each time
a Customer is saved: in `hooks.py` add `"Customer": {"on_update":
"dz_cod.cod.order.say_hello"}` and in `cod/order.py` a function
`def say_hello(doc, method=None): print("Saved customer", doc.name)`.
Restart `bench start`, save a customer, watch the terminal. Then remove it.

### Failure modes

- *"No module named dz_cod"* → the app is not installed in the bench's Python: `bench pip install -e apps/dz_cod` or `bench setup requirements`.
- *Changes in a doctype JSON do nothing* → you forgot `bench --site <site> migrate`.
- *Works on demo, not on the client site* → the app is installed in the bench but not on that site: `bench --site <site> list-apps`, then `install-app dz_cod`.

---

## 1. Custom fields

### Mental model

Custom fields are ERPNext's **descriptive flexfields (DFF)**: extra columns
added to a standard table without touching its seeded definition. They are
stored as records of the doctype "Custom Field" and survive upgrades. All of
ours start with `dz_` so you can tell them apart instantly (like `ATTRIBUTE1..15`
being "yours" in EBS).

### The lines that matter

`dz_cod/setup/custom_fields.py`:

```python
create_custom_fields({"Sales Order": SALES_ORDER_FIELDS, ...}, update=True)
```

and, in many field definitions:

```python
"allow_on_submit": 1,
```

`create_custom_fields(..., update=True)` creates missing fields and updates
existing ones, so it is safe to run on every migrate. `allow_on_submit`
decides whether a field may still change **after** the order is confirmed
(submitted). A submitted document is frozen except for those fields; the
tracking number, dates and links filled during shipping need it.

### Break it on purpose

In `custom_fields.py`, in the `dz_tracking_number` field, change
`"allow_on_submit": 1` to `0`. Run `bench --site demo.localhost migrate`.
Open a "Préparée" order, **Expédier** with a tracking number. Error:
*"Not allowed to change N° de suivi after submission"*. Put it back and
migrate again.

### Rebuild it yourself

Add a field "Instructions de livraison" (`dz_delivery_note_text`, Small Text)
to Sales Order after `dz_address`, migrate, check it appears in the form.
Then add it to the webhook payload (chapter 8).

### Failure modes

- *Field not visible* → check `insert_after` points to an existing field name; check `depends_on`.
- *Field visible but empty on new orders* → `fetch_from` only fills it when the source (customer) has a value, and `fetch_if_empty` means it never overwrites what was typed.
- *Changed the definition in Python but nothing changed* → migrate.

---

## 2. Settings (Paramètres COD)

### Mental model

**COD Settings** is the kit's **profile options** screen. In EBS, behaviour
that differs between sites is controlled by profile options, not by
customising code. Here, rule 4 of the project: *per-client differences go in
settings and custom fields, never in code branches*. If you ever write
`if company == "Client X":`, stop and add a setting instead.

It is a *single* doctype (`issingle: 1`): one record per site, like a
site-level profile option.

### The lines that matter

`dz_cod/dz_cod/doctype/cod_settings/cod_settings.py`:

```python
settings = frappe.get_cached_doc("COD Settings")
```

Reads the settings from the Redis cache (fast). Frappe clears that cache
automatically when someone saves the settings.

### Break it on purpose

In the database console (`bench --site demo.localhost mariadb`) run
`update tabSingles set value='Stock principal - XX' where doctype='COD Settings' and field='main_warehouse';`
then create a new order. The error mentions a warehouse that does not exist.
Lesson: writing in the database behind Frappe's back skips validation *and*
leaves a stale cache. Fix it by opening **Paramètres COD** and saving the
right warehouse (or `bench --site demo.localhost clear-cache`).

### Rebuild it yourself

Add a setting "Source par défaut" (Select, same options as `dz_source`) to
COD Settings (edit the JSON or use the form builder in developer mode), and
in `order.before_validate` fill `order.dz_source` from it when empty.

### Failure modes

- *"Veuillez d'abord remplir les Paramètres COD"* → a new site where nobody filled the settings. Fill them.
- *A setting change has no effect* → it was written directly in SQL; save it through the form or clear the cache.

---

## 3. The order life cycle

The heart of the kit. Read `dz_cod/cod/order.py` from top to bottom; it is
about 150 lines.

### Mental model

The order goes through a **routing**. Each **workflow state** is an
**operation** where the order sits (Nouvelle, Confirmée, Préparée,
Expédiée, Livrée, Réglée), and each **transition** is a **move** from one
operation to the next, with a name (the button), a role allowed to do it,
and sometimes a condition. Side exits (Annulée, Injoignable, Retournée) are
like scrap or rework branches of the routing.

```
Nouvelle ──Confirmer──> Confirmée ──Préparer──> Préparée ──Expédier──> Expédiée ──Marquer livrée──> Livrée ──Marquer réglée──> Réglée
   │ ▲                     │                       │                     │
   │ └─Pas de réponse─> Injoignable                │                     └──Marquer retournée──> Retournée
   └─Annuler─> Annulée     └──────Annuler──────────┴──> Annulée après confirmation
```

There are two layers, and keeping them apart is the key idea:

- **The Workflow** (`setup/workflow.py`) is pure *description*: states,
  buttons, roles, conditions. Like the routing definition in BOM/Routing.
- **The hooks** (`cod/order.py`) are the *execution*: what happens when the
  order arrives at an operation (create a delivery note, return stock...).
  Like the move-transaction logic that issues components at an operation.

Under the hood, ERPNext also has `docstatus`, the life of any transaction
document, like the status of a work order:

| docstatus | meaning | our states | EBS analogy |
|-----------|---------|------------|-------------|
| 0 Draft | editable, no impact | Nouvelle, Injoignable, Annulée | Unreleased |
| 1 Submitted | frozen, has effects (stock reserved) | Confirmée … Réglée, Retournée | Released |
| 2 Cancelled | effects reversed | Annulée après confirmation | Cancelled |

"Confirmer" is the **release**: it submits the Sales Order, which reserves
the stock. That is why the order is editable before confirmation (the phone
call may change size or address) and frozen after it.

### The lines that matter

`dz_cod/cod/order.py`, in `on_update_after_submit`:

```python
if not order.has_value_changed("workflow_state"):
    return
```

A submitted order can be saved for many reasons (someone fixes the tracking
number...). We only act when the **state** changed in this save.
`has_value_changed` compares with the version loaded before the save. Without
this line, every save of a shipped order would create another delivery note.

`dz_cod/setup/workflow.py`, the transitions table:

```python
(S.PREPARED, S.ACTION_SHIP, S.SHIPPED, STOCK, None),
```

Read it as: "from *Préparée*, the button *Expédier* goes to *Expédiée*,
allowed to *Stock User*, no extra condition". To change the routing, change
this table and migrate; no other code changes.

The call counter is a nice example of using the platform instead of code:
the "Injoignable" state has `update_field = dz_call_attempts` and
`update_value = (doc.dz_call_attempts or 0) + 1`, so Frappe adds 1 each time
the order enters that state. The "Pas de réponse" transition has a condition
that hides the button once the maximum from COD Settings is reached.

### Break it on purpose

1. In `order.py`, comment out the two `has_value_changed` lines in
   `on_update_after_submit`. Ship an order, then edit and save its
   tracking number (it is editable after submit): a second delivery note is
   created and the stock goes down twice. Undo.
2. In `workflow.py`, give the "Expédier" transition the role `"Accounts User"`
   instead of `STOCK`, migrate, log in as a user who only has Stock User:
   the button disappears. Lesson: when a user says "I don't have the button",
   check the transition's role and condition first.

### Rebuild it yourself

Add a state **"En attente de stock"** between Confirmée and Préparée:
- in `states.py` add `WAITING_STOCK = "En attente de stock"` and the action names,
- in `workflow.py` add it to `STATES` (docstatus 1, style "Warning", role STOCK)
  and two transitions: Confirmée → En attente de stock ("Mettre en attente"),
  En attente de stock → Préparée ("Préparer"),
- add it to `ALL_STATES`, migrate, try it,
- run the tests: `TestWorkflowDefinition` must still pass.

### Failure modes

- *"Workflow State transition not allowed from X to Y"* → someone (or code) set `workflow_state` directly to a state that is not reachable from the current one. Use the buttons, or `apply_workflow(doc, action)` in code.
- *"Not a valid Workflow Action"* → the action name is wrong, or the user lacks the role, or the transition condition is false (e.g. max calls reached).
- *"Self approval is not allowed"* → `allow_self_approval` is 0 on that transition.
- *The order is stuck in a state* → check **Error Log** for an exception during the save; the whole move is rolled back, so the order stays where it was (that is a good thing: no half-done shipment).
- *Debug technique*: `bench --site demo.localhost console`, then
  `from frappe.model.workflow import get_transitions; doc = frappe.get_doc("Sales Order", "SAL-ORD-2026-00012"); get_transitions(doc)` lists what is possible right now for that order.

---

## 4. Stock movements

Read `dz_cod/cod/stock.py`.

### Mental model

| COD step | ERPNext document | Planning analogy |
|----------|------------------|------------------|
| Confirmer | Sales Order submitted → `reserved_qty` goes up in the Bin | **material allocation** (soft reservation) against a work order: the stock is still on the shelf, but promised |
| Expédier | **Delivery Note** submitted → `actual_qty` goes down, reservation released | **material issue** to the order |
| Marquer retournée | **return Delivery Note** into **Retours** warehouse | **receipt into a quarantine / MRB sub-inventory**: nobody may use it before inspection |
| Inspecter le retour | **Stock Entry** Material Transfer (good) and Material Issue (damaged) | **MRB disposition**: return to stock or scrap |

The **Bin** is ERPNext's on-hand table per item and warehouse
(`MTL_ONHAND_QUANTITIES` + reservations in one row). *Projected qty* =
actual − reserved + ordered...: the available-to-promise idea.

### The lines that matter

`create_delivery_note`:

```python
dn = make_delivery_note(order.name)
```

This is ERPNext's own "Create → Delivery Note" button, called from Python. We
reuse it instead of building the delivery note ourselves, so every ERPNext
rule (batches, taxes, links to the order) is respected.

`create_return`:

```python
for row in ret.items:
    row.warehouse = returns_warehouse
```

The return note is a copy of the delivery note with negative quantities;
changing the warehouse on each line sends the parcel to quarantine instead of
back to the shelf.

### Break it on purpose

1. Set the stock of one variant to 0 (Stock Reconciliation), confirm an order
   for it (just a warning, unless you tick *Bloquer la confirmation*), prepare
   and **Expédier**: error *"…needed in Stock principal…"* (negative stock is
   not allowed). Lesson: the warning at confirmation is a planning signal; the
   real stop happens at shipment.
2. Remove the loop `for row in ret.items: row.warehouse = returns_warehouse`,
   return an order: the stock goes straight back to the main warehouse,
   uninspected. Undo.

### Rebuild it yourself

Write, in the console, the stock situation of one item:

```python
frappe.get_all("Bin", filters={"item_code": "EU-TS-CASBAH-M-NOI"},
               fields=["warehouse", "actual_qty", "reserved_qty", "projected_qty"])
```

Then confirm an order for that item and run it again: `reserved_qty` +1.
Ship it: `actual_qty` −1 and `reserved_qty` −1. Write down the numbers;
that is the whole stock model of the kit.

### Failure modes

- *"Closed order cannot be cancelled" / "status is Closed"* → returned orders are closed on purpose (so they never reserve stock again). To undo a return by mistake: reopen the order (button **Statut → Ré-ouvrir**), cancel the return delivery note, then fix.
- *Reserved quantity looks wrong* → `bench --site <site> execute erpnext.stock.stock_balance.repost_stock` recalculates bins (run at night, it can be slow).
- *Inspection refused* → quantities good + damaged must equal exactly what came back.

---

## 5. Shipping rates

Read `dz_cod/cod/shipping.py` and `dz_cod/dz_cod/doctype/dz_wilaya/`.

### Mental model

The **wilaya list is the rate table** (one row per wilaya, two prices: home
and stop desk, plus what the courier keeps). When an order is saved as a
draft, we look up its wilaya and delivery type and add the fee to the order
as a **freight charge line** in "Taxes and Charges", type *Actual* — exactly
like a freight modifier in Advanced Pricing, and exactly how ERPNext's own
Shipping Rule works. Because it is a normal charge line, the total, the
delivery note and the accounts all include it automatically.

### The lines that matter

```python
row = order.append("taxes", {"charge_type": "Actual", "account_head": account, "description": SHIPPING_DESCRIPTION})
row.tax_amount = amount
```

and in `before_validate` the guard `if order.docstatus != 0: return`: the fee
is only recalculated while the order is a draft. After confirmation the
amount the courier collects must never change silently.

### Break it on purpose

Set the *Tarif domicile* of "16 - Alger" to 0 and untick *Livrable* for
"11 - Tamanrasset". Create an order to Tamanrasset: error *"La wilaya … n'est
pas livrable"*. Create one to Alger: no delivery line at all. Restore.

### Rebuild it yourself

Add a "free delivery above X DA" rule: a setting `free_shipping_above`
(Currency) in COD Settings, and in `apply_shipping_charge`, if
`order.total >= settings.free_shipping_above > 0`, use 0. Write a test for it
in `tests/test_order_flow.py` (copy `test_stop_desk_rate`).

### Failure modes

- *Fee not updated after changing the wilaya rate* → existing draft orders recalculate on their next save; confirmed orders keep their fee (on purpose).
- *"Choisissez le compte des frais de livraison…"* → fill the account in COD Settings.
- *Fee counted twice* → someone added a Sales Taxes template containing the same account; remove it from the template.

---

## 6. Courier connectors

Read `dz_cod/couriers/base.py`, `mock.py`, `__init__.py`, `yalidine.py`.

### Mental model

An **adapter** is a translation layer, like an **open interface** in EBS: the
core never talks to the outside world directly; it talks to one fixed
interface (here 3 methods: `create_shipment`, `get_status`, `get_tracking`),
and each courier has its own small class that translates. Adding a courier
= adding one class. The **Mock** courier is the **test harness**: a fake
outside world that answers instantly and offline.

Status words are translated into our 4-word vocabulary (`in_transit`,
`delivered`, `returned`, `unknown`), like mapping a supplier's status codes to
your own lookup codes.

**Important:** Yalidine is only a documented stub. The official API docs
could not be reached when this was written, and the project rule is "never
invent endpoints". Before writing it, read the official documentation from
the client's courier account.

### The lines that matter

`dz_cod/couriers/__init__.py`:

```python
adapter_class = ADAPTERS.get(courier.get("dz_courier_adapter") or "Manuel")
return adapter_class(courier)
```

The choice of connector is **data** (a field on the Supplier), not code:
per-client difference in settings, rule 4 again.

### Break it on purpose

Set the courier "Rapide Express (démo)" connector to **Yalidine** and ship an
order without tracking number: *"Le connecteur Yalidine n'est pas encore
implémenté"*. Lesson: this is how an unfinished connector must fail — loudly,
before any stock moves. Set it back to Mock.

### Rebuild it yourself

Write a `CsvAdapter` whose `get_status` reads a CSV file
`/tmp/statuses.csv` (`tracking_number,status`) — a cheap way to import a
courier's daily export. Register it in `ADAPTERS`, add "Csv" to the
connector options in `custom_fields.py`, migrate, test with the hourly sync:
`bench --site demo.localhost execute dz_cod.couriers.sync.sync_shipped_orders`
(tick *Synchroniser les statuts* in COD Settings first).

### Failure modes

- *Sync does nothing* → the setting is off, or the scheduler is disabled (`bench --site <site> enable-scheduler`), or no worker runs.
- *One order fails during sync* → it is logged in **Error Log** ("Synchronisation transporteur : …") and the others continue.
- *Real API: works in the shell, not in production* → the firewall or the courier's IP allow-list; tokens must be in the Supplier's *API Token* field (encrypted), never in code.

---

## 7. Courier settlement (Versement)

Read `dz_cod/cod/settlement.py` (pure rules) and
`dz_cod/dz_cod/doctype/courier_settlement/courier_settlement.py`.

### Mental model

A **three-way match**, like AP invoice matching: *what the courier says it
collected and kept* vs *what the order says it should collect and what the
rate table says the courier should keep*. The **tolerance** is your match
tolerance. Each line gets a status:

| Status | Meaning | On submit |
|--------|---------|-----------|
| OK | amounts match (within tolerance) | order → Réglée |
| Écart | amounts differ | stays Livrée, unless you tick *Accepter* |
| Inconnue | tracking number unknown | nothing |
| Déjà réglée | order paid in an earlier Versement | nothing (double payment!) |
| Invalide | other courier, or order not Livrée | nothing |

And the summary answers the three questions: **paid**, **disputed**,
**missing** (delivered by this courier but absent from the statement).

### The lines that matter

`dz_cod/cod/settlement.py`:

```python
if abs(net_paid - expected_net) <= tolerance:
    return OK
```

We compare **net** amounts: (collected − courier fee) against (expected
amount − expected fee). A courier who collects correctly but over-charges
its fee is caught too.

The rules are in a separate file with **no database access**, so they are
easy to test (17 fast tests in `tests/test_rules.py`). Keep that separation
when you add rules.

### Break it on purpose

Create a Versement, load the delivered orders, change one *Encaissé* to
−500 DA, save: Écart. Tick *Accepter* on it, submit: the order is Réglée.
Now cancel the Versement: the orders go back to Livrée (look at the order's
timeline comment). Then create a Versement with the same order twice:
*"…apparaît deux fois"*.

### Rebuild it yourself

Add a status **"Frais anormaux"** for lines where the amount collected is
right but the courier fee is above the expected fee: add the constant in
`settlement.py`, the check in `line_status` (before the `abs(...)` line), the
option in the line doctype JSON, and a unit test in `TestSettlementRules`.

### Failure modes

- *Many "Invalide" lines* → orders still "Expédiée": the courier delivered them but nobody clicked *Marquer livrée*. Select them in the list → **Actions → Marquer livrée** (bulk), then save the Versement again.
- *"Écart reçu / relevé" not 0* → the bank transfer does not equal the statement total: the courier's own arithmetic, or a parcel paid outside the statement.
- *Courier pays the rest of a dispute later* → *Charger les commandes livrées* in the new Versement pre-fills only what is still due (column *Déjà versé* shows what the earlier Versement paid). If the courier writes the whole amount again, the line shows Écart: it was already paid once.

---

## 8. Webhooks

Read `dz_cod/setup/webhooks.py` and `docs/WEBHOOKS.md`.

### Mental model

**Business Event subscriptions** (Oracle Workflow Business Event System):
"when the order becomes Expédiée, call this URL with this message". The
subscription is data (a Webhook record), the message is a template. The call
happens in the background **after** the database commit, so a slow or broken
n8n never blocks the warehouse.

### The lines that matter

```python
condition = f'doc.workflow_state == "{state}" and doc.has_value_changed("workflow_state")'
```

Same idea as chapter 3: fire only when the state changed in this save.

And in the template: `{% for row in doc["items"] %}` — **not** `doc.items`
(in the template `doc` is a dictionary; `doc.items` is the dictionary's
`items` method). That bug was caught by the tests.

### Break it on purpose

Follow "Testing without n8n" in docs/WEBHOOKS.md. Then stop the listener and
move another order: the order still moves; open **Webhook Request Log** and
see the failed call with its error. Lesson: webhooks never block the
business, so you must *watch* the log.

### Rebuild it yourself

Create a fifth webhook "COD - Annulée" (state Annulée is a **draft** state:
docevent `on_update`, condition with `has_value_changed`), point it to the
local listener, cancel a Nouvelle order, check the JSON.

### Failure modes

- *Nothing arrives* → webhook not Enabled; no worker running (`sudo supervisorctl status`); wrong URL → Webhook Request Log.
- *"Too many queued background jobs"* → workers stopped for a long time; restart them and wait.
- *n8n receives the same order twice* → someone moved the order back and forth (cancel/amend); in n8n, de-duplicate on `order` + `event`.

---

## 9. Reports

Read `dz_cod/dz_cod/report/*/` (each report = `.json` definition, `.py`
data, `.js` filters).

### Mental model

**Script reports** are like your SQL reports in EBS: a query, some Python to
shape rows, columns with types. They are written in plain SQL on purpose:
you already read SQL fluently.

- **Commandes par jour**: orders per day (rows) and state (columns). Read a row as "of the orders taken that day, how many are now in each state".
- **Taux de retour**: returned / (delivered + returned), by product, variant or wilaya. Orders still on the road are shown apart (not yet a success or a failure).
- **Encours transporteurs**: cash each courier owes (orders Livrée, not Réglée), disputes, and cash still on the road.

### The lines that matter

In `cod_daily_orders.py`:

```sql
SELECT transaction_date AS date, workflow_state AS state, COUNT(*) AS count, SUM(dz_cod_amount) AS amount
FROM `tabSales Order` ... GROUP BY transaction_date, workflow_state
```

Every doctype is a table called `` `tab<DocType name>` ``; every custom
field is a real column. You can test any query first in
`bench --site demo.localhost mariadb`.

### Break it on purpose

Remove `AND workflow_state IN %(states)s` from the daily report query and
create an order on a site where an old order has no workflow state
(`update \`tabSales Order\` set workflow_state=NULL where name='...'`): the
report crashes on an unknown column. Lesson: always filter on the values you
know how to display.

### Rebuild it yourself

Add a "Source" grouping (Instagram, Facebook...) to *Taux de retour*: a new
option in the `.js` filter and a branch in `get_rows` grouping by
`so.dz_source`. Which channel brings the most refusals?

### Failure modes

- *Report empty* → the company filter: the report uses COD Settings' company when the filter is empty.
- *"Unknown column"* → the field is not on that site (app not migrated).

---

## 10. The demo loader

Read `dz_cod/demo/loader.py` (start with the docstring and `load()`).

### Mental model

A **re-runnable data conversion script**: like a conversion that loads open
items through the standard interfaces rather than inserting into base
tables. The loader does not write fake rows into tables; it **replays
history through the real workflow**, day by day, so the stock ledger,
delivery notes, returns and settlements are exactly what the app produces.
It is **idempotent**: each step first checks whether its result already
exists (keys: item codes, customer names, "Customer's PO" `DEMO-0001`,
settlement references).

### The lines that matter

```python
if order.workflow_state not in EXPECTED_STATE[action]:
    return  # already played (second run of the loader)
```

and

```python
order.flags.dz_event_date = date
apply_workflow(order, action)
```

The first makes re-runs safe. The second presses the real button, but tells
our hooks "pretend it is that day" so delivery notes get past dates.

### Break it on purpose

Comment out the `EXPECTED_STATE` check and run the loader a second time:
errors "Not a valid Workflow Action" (it tries to confirm orders already
confirmed). Undo. Then run the loader on your *test* site after creating any
order for another company: it refuses ("…doit tourner sur un site dédié…").
That guard protects client sites.

### Rebuild it yourself

Add a third brand with two products in `demo/data.py`, wipe and reload
(docs/DEMO.md). Then change `SEED` and reload: a different but equally
realistic shop.

### Failure modes

- *"Too many queued background jobs"* → see chapter 12; run a worker.
- *Stock errors during the load* → `opening_qty` too small for the planned orders; raise it.
- *Different results on another day* → normal: dates are relative to today.

---

## 11. Tests

Read `dz_cod/tests/test_rules.py` then `test_order_flow.py`.

### Mental model

Tests are **CRP/conference-room-pilot scripts that run themselves**: each
test sets up a situation, presses the buttons and checks the outcome. Two
kinds:

- **Unit tests** (`test_rules.py`): pure rules, no database, run in milliseconds.
- **Integration tests** (the others): a real site, real documents. Each test class is rolled back at the end, so the site is left as it was.

### The lines that matter

```python
order = h.act(h.make_order(qty=3), S.ACTION_CONFIRM)
self.assertEqual(h.bin_qty(h.main_warehouse(), "reserved_qty"), reserved_before + 3)
```

That is the whole pattern: build, act, assert. `tests/helpers.py` hides the
boring setup.

### Break it on purpose

In `dz_cod/dz_cod/doctype/dz_wilaya/dz_wilaya.py`, in `get_rates`, change
`return self.stopdesk_rate, self.stopdesk_courier_cost` to
`return self.home_rate, self.home_courier_cost`. Run
`bench --site test.localhost run-tests --module dz_cod.tests.test_order_flow`:
`test_stop_desk_rate` fails and tells you expected 250, got 400. Undo.

### Rebuild it yourself

Write `test_cancel_releases_stock_from_unreachable` : an order that was
"Injoignable" twice and then "Annulée" never touched the reserved quantity.

### Failure modes

- *"Testing is disabled for this site"* → `bench --site test.localhost set-config allow_tests 1` (laptop only).
- *Tests pass alone but fail together* → a test depends on data left by another; make each test create what it needs.
- *A test made data permanent* → code that calls `frappe.db.commit()` inside the tested path; patch it like `TestCourierSync` does.

---

## 12. Production

Read `docs/DEPLOY.md`.

### Mental model

| Process (supervisor) | Role | EBS analogy |
|----------------------|------|-------------|
| `web` (gunicorn) | answers browser requests | the forms/OAF server |
| `worker` (short/default/long) | background jobs: webhooks, emails, reposts | concurrent managers |
| `schedule` | starts periodic jobs (our hourly courier sync) | the scheduler of concurrent requests |
| `redis` | cache + job queue | — |
| nginx | front door, HTTPS, chooses the site by domain name | the HTTP server / load balancer |

**Backup = database + files + site config (encryption key).** A backup is
only proven by a restore; DEPLOY.md section 10 is the procedure that was run.

### The lines that matter

```bash
bench --site all backup --with-files --compress
bench --site restore-test.localhost restore "$B-database.sql.gz" --with-public-files ... --with-private-files ...
bench --site restore-test.localhost set-config encryption_key "<key from the site_config backup>"
```

The second restore line is the one people forget: without the site's
`encryption_key`, every stored password (courier API tokens, email accounts)
is unreadable after a restore on a new server.

### Break it on purpose (laptop)

Stop the workers (just run `bench serve` instead of `bench start`), move 600
orders with a script or load the demo twice: *"Too many queued background
jobs"*. Then run `bench worker --queue default,short,long --burst` and watch
the queue drain. That is exactly what happened while building this kit.

### Rebuild it yourself

On your laptop: back up the demo site, drop it, restore it into a new site
name, and compare the number of orders. Time it. That number is your
"recovery time" to promise clients.

### Failure modes

- *Site shows "Internal Server Error"* → `tail -f logs/web.error.log`.
- *Emails/webhooks not sent* → workers down: `sudo supervisorctl status`, `bench doctor`.
- *After update: "column … doesn't exist"* → a site was not migrated: `bench --site <site> migrate`.
- *Disk full* → old backups: the backup script keeps 7 days locally; check `du -sh sites/*/private/backups`.

---

## 13. How to read an error

1. **Read the last line first.** `frappe.exceptions.ValidationError: Impossible de confirmer, il manque : la wilaya` tells you everything.
2. **Then find the first line that is in `apps/dz_cod/`** going up the traceback: that is where *our* code was when it happened. Lines in `apps/frappe` and `apps/erpnext` are the platform doing its job.
3. **Reproduce in the console**: `bench --site demo.localhost console`, load the document, call the same function.
4. **Look in the browser logs**: *Error Log* (server errors with full traceback), *Webhook Request Log*, *Scheduled Job Log*.
5. **Search the code**: `grep -rn "the French message" apps/dz_cod` finds where a message comes from in seconds.

---

## 14. A four-week learning plan

| Week | Goal |
|------|------|
| 1 | Install on your laptop (LOCAL_TEST.md). Load the demo. Do the 10-minute demo script in DEMO.md until you can do it without notes. Read chapters 0, 3, 4. |
| 2 | Chapters 1, 2, 5, 7: do every "break it" and "rebuild it". Run the tests after each change. |
| 3 | Chapters 6, 8, 9, 10, 11. Build one small n8n workflow that receives "Expédiée" and sends you a Telegram/WhatsApp message. |
| 4 | DEPLOY.md on a cheap test VPS from zero, including a real restore. Time the "new client in under 2 hours" checklist. Then you are ready for your friend's shop. |

---

## 15. Languages: French, English, Arabic

Read `dz_cod/translations/en.csv` and `ar.csv`, then `dz_cod/tests/test_translations.py`.

### Mental model

The app is **written in French**: field labels, workflow states, buttons,
messages. Each other language is a **lookup table** laid on top, like a
translated item description: `en.csv` pairs each French text with its English
text, `ar.csv` with its Arabic text. When a user's language is English or
Arabic, Frappe swaps every text it finds in that table. For Arabic, Frappe
also mirrors the whole screen (right-to-left); we have nothing to do for that. The data does not change: an order is still stored as "Livrée", it is
only *shown* as "Delivered".

Each user picks their language (**User → Language**). On the same site, one
person can work in French and another in English.

### The lines that matter

```python
frappe.throw(_("La wilaya {0} n'est pas livrable.").format(self.name))   # Python: _()
```
```javascript
frm.add_custom_button(__("Inspecter le retour"), ...)                     // JavaScript: __()
```
```
La wilaya {0} n'est pas livrable.,Wilaya {0} is not deliverable.          # en.csv
La wilaya {0} n'est pas livrable.,الولاية {0} غير قابلة للتوصيل.          # ar.csv
```

A text that is not wrapped in `_()` / `__()` is never translated. Labels in
JSON files (fields, menu, home page) and in `setup/custom_fields.py` are
translated automatically.

The welcome guide on the home page is plain HTML, which Frappe does not
translate: `setup/home_block/home.html` holds the three versions, and `home.js`
shows the one matching the user's language.

The names of our own doctypes and reports are English ("Courier Settlement",
"COD Daily Orders"): `fr.csv` gives their French names and `ar.csv` their
Arabic names. English users simply see them as they are.

### Break it on purpose

Add a new button label in `public/js/sales_order.js`, e.g. `__("Rappeler")`,
and run `bench --site test.localhost run-tests --module dz_cod.tests.test_translations`.
The test fails and names the text and the file, once for English and once
for Arabic: add `Rappeler,Call back` to `en.csv` and `Rappeler,إعادة الاتصال`
to `ar.csv`, and run it again. Undo.

### Rebuild it yourself

List what is missing at any time:
`bench --site test.localhost execute dz_cod.tests.i18n_strings.print_missing --kwargs "{'lang': 'ar'}"`.

Adding a fourth language (Tamazight, for example) is the same work: a new
`<code>.csv` file, the code added to `LANGUAGES` in `tests/i18n_strings.py`,
and a fourth copy of the welcome guide.

### Failure modes

- **A text stays French for an English or Arabic user**: it is not wrapped in `_()` / `__()`, or its line in the language file does not match exactly (accents, punctuation, final full stop).
- **A text from ERPNext changes too**: a language file applies to the whole site. Never translate a French word that is also an English word used by Frappe or ERPNext (that is why "Client" and "Code" are left alone: Frappe already translates them).
- **Some English left on an Arabic screen** ("Optional", "Terms", "4 of 6 steps done"): that is Frappe's own text, not translated into Arabic by Frappe. Not ours to fix.
- **Change not visible**: `bench --site <site> clear-cache`, then Ctrl+Shift+R in the browser.
