# Decisions

Every choice made while building this kit, with one line of reasoning.
Newest decisions are added at the bottom of each section.

## Platform

- **ERPNext v16 (16.50.0) on Frappe v16 (16.51.0)**: v16 is the latest stable major (branch `version-16`, October 2026). `develop` is the future v17 and is not stable.
- **Python 3.14, Node 24, MariaDB 10.11, Redis 7**: Frappe v16 requires Python 3.14 and Node ≥ 24 and supports MariaDB 10.6 to 11.8. Ubuntu 24.04 ships MariaDB 10.11.
- **Ubuntu 24.04 LTS for the server guide**: that is what everything was tested on. Ubuntu 26.04 LTS should work but was not tested.
- **The GitHub repo is the Frappe app itself** (the `dz_cod` package sits at the root): `bench get-app https://github.com/adem-max/dz-cod` works directly.
- **No core changes, everything in `dz_cod`**: project rule. We use hooks, custom fields, a Workflow, Webhooks and three small doctypes.

## Reference data

- **69 wilayas, not 58**: law 26-06 of 4 April 2026 (JO n° 25) created 11 wilayas, and decree 26-206 (JO n° 40) set their numbers 59 to 69. I could not open the Journal officiel itself; numbers and names come from several Algerian press articles quoting the decree. **Double-check them.**
- **Each new wilaya remembers its parent wilaya**: couriers may keep the 58-wilaya codes for a while (the transfer runs until 31 December 2026).
- **Parent wilayas of 59–69 come from press reports**, not from the law text. **Double-check them.**
- **Communes are free text**, not a master list: the 1,541 communes would need a verified source; listed in LATER.md.
- **…until the courier's own list is imported**: for Yalidine clients, *Importer communes et bureaux Yalidine* fills **DZ Commune** with Yalidine's spellings, and the order's *Commune* becomes a pick list (field type Autocomplete: free text while the list is empty). Yalidine refuses names it does not know, so its list is the source that matters for shipping. The field type was switched from Data directly in the database (`switch_commune_to_autocomplete`): Frappe's Custom Field refuses Data → Autocomplete although both are the same varchar column.
- **Example shipping rates in 6 zones (400 DA Alger home delivery … 1,400 DA far south)**: placeholders. Replace them with each client's courier rate card.
- **Default courier cost = customer rate**: most small sellers pass the courier price straight to the customer; edit per wilaya if not.
- **Phone rule**: mobile = 05/06/07 + 8 digits, landline = 9 digits; `+213` and `00213` are converted to `0`. Unknown formats are kept as typed, never destroyed.

## New doctypes (rule 3: only when a standard one does not fit)

- **DZ Wilaya** (label "Wilaya"): ERPNext has no list of Algerian provinces with rates. `Territory` was considered but it is ERPNext's sales-hierarchy tree; mixing addresses and courier rates into it would confuse sales targets and pricing rules.
- **COD Settings** (label "Paramètres COD", single record): rule 4 — per-client differences must live in settings, not code.
- **Courier Settlement + Courier Settlement Item** (label "Versement"): nothing standard matches "a third party's statement matched line by line against our orders". Payment Entry is per party (one customer) and full accounting is out of scope; Bank Reconciliation works on bank lines, not parcels.
- **DZ Commune and DZ Stop Desk**: the courier's communes and offices, imported from Yalidine. No standard doctype lists Algerian communes or courier offices; Address and Territory were rejected for the same reasons as for DZ Wilaya. The record name is Yalidine's id (commune id, center id), so a new import updates instead of duplicating, and the order stores the office id Yalidine needs.
- **Courier Webhook Event**: one line per event pushed by Yalidine, named by its event id, so a duplicate delivery is refused by the database itself. Frappe's Webhook Request Log only records webhooks we send, and Integration Request has no unique key on the event id. Cleared after 30 days (Log Settings).

## Order life cycle

- **The life cycle is a standard Frappe Workflow on Sales Order** ("Commande COD"): it gives buttons, roles, history comments and list colours for free.
- **Confirmer = submit the Sales Order**: before confirmation the operator must be able to edit everything (size, address) during the phone call; after it, stock is reserved and the order is locked.
- **Two cancel states**: "Annulée" (draft, customer said no on the phone) and "Annulée après confirmation" (submitted then cancelled). Frappe cannot cancel a draft, so one state cannot cover both.
- **Stock reservation = ERPNext's standard "reserved qty"** (soft reservation, automatic on submit), not Stock Reservation Entries (hard reservation): simpler and enough for a small shop. Hard reservation is in LATER.md.
- **Stock check at confirmation warns by default and can block** (setting): a print-on-demand seller confirms before printing.
- **Expédier creates and submits the Delivery Note immediately**: stock leaves the main warehouse when the parcel leaves. Courier and tracking number are copied to the standard "Transporter" and "Transport Receipt No" fields.
- **Retournée creates a return Delivery Note into the "Retours" warehouse** and then closes the Sales Order, so ERPNext never reserves that stock again.
- **Inspection uses standard Stock Entries**: Material Transfer (Retours → main) for good pieces, Material Issue for damaged ones, linked back to the order with a custom field.
- **No Sales Invoice and no Payment Entry**: full accounting is out of scope. Consequence: sales revenue is not in the general ledger and delivered orders show ERPNext status "To Bill". Listed first in LATER.md.
- **Delivery details are stored on the order** (phone, wilaya, commune, address), copied from the customer when empty: the courier needs a snapshot per order, and COD order entry must be fast. ERPNext's Address and Contact doctypes are not used for COD.
- **Unanswered calls are counted by the Workflow itself** (the "update field" option of the "Injoignable" state), with no code. The "Pas de réponse" button disappears at the maximum set in COD Settings (default 3).
- **Standard roles only**: Sales User confirms, Stock User prepares/ships/delivers/returns, Accounts User settles, Sales Manager may edit cancelled orders. "Allow self approval" is on because the shops are tiny teams.
- **The "Expédier" button opens a small dialog** (courier + tracking number) before the workflow action, because the tracking number must be saved before the move.
- **Event dates can be forced through `order.flags.dz_event_date`**: only the demo loader uses it, to replay 60 days of history with correct past dates.

## Courier connectors

- **Adapter pattern with three methods** (create shipment, get status, get tracking): the rest of the app never knows which courier is used.
- **"Manuel" is the default connector**: tracking typed by hand, status moved by hand.
- **"Mock" connector works offline**: tracking `MOCK-<order>`, statuses simulated in the Redis cache.
- **Yalidine connector built from a verbatim copy of its docs, without an account** (October 2026): the official docs sit behind the merchant login; a verbatim copy (API + webhooks, September 2026) in an open-source project was used, every endpoint and field comes from it, and points it leaves open are marked `UNVERIFIED` in the code. Tested only with a fake HTTP layer (`unittest.mock.patch` on `requests.request`) answering the docs' JSON examples. A real-parcel check with a client's keys is required before going live (checklist in docs/COURIER_INTEGRATION.md §4). ZR Express waits for ZR's official docs. Y8 (Versement from Yalidine payments) is not built.
- **`freeshipping: true` on Yalidine parcels**: our amount to collect already includes the delivery fee. Yalidine's docs define `false` as "paid by the receiver", so `false` risks the customer paying the fee twice; with `true` Yalidine deducts its fee from the payout, as our settlement expects. The plan said `false`; the first real parcel decides.
- **Only "Livré" and "Retourné au vendeur" move a Yalidine order**: "Retour vers vendeur", "Echèc livraison"... mean the parcel is coming back but not here, and Retournée moves stock into the Retours warehouse. Yalidine's exact words go into *Statut chez le transporteur* so the team sees them.
- **Statuses read from `parcels/?tracking=…` (50 per call)**, not `histories/`: one line per parcel with `last_status`, so no paging; the hourly sync asks each courier for all its parcels at once (`get_statuses`).
- **A parcel already created for the order is reused** (`GET parcels/?order_id=`): the API call happens inside the "Expédier" transaction, so a failure after it would otherwise create a second parcel on the next click.
- **Quota memory in Redis, shared by web and workers**: a quota window at 0 or a Retry-After is remembered per courier; a click gets a clear message, a background job waits (up to 60 s) and retries once. Repeated 429s can get the keys disabled, so we never hammer.
- **Yalidine prices import into the courier costs only**, one call per wilaya 1.5 s apart (40/min under the 50/min limit), price of the chef-lieu commune; customer prices stay the seller's decision. A 2026 wilaya Yalidine does not know gets its parent's cost.
- **Webhooks: store fast, apply in a job**: Yalidine wants a 2xx within 10 s and disables the webhook after 7 failed deliveries. The signature (HMAC-SHA256 of the raw body) is checked against the secret of every Yalidine courier; unsigned or wrongly signed bodies get a 400 and are not stored. An event older than the status already stored is ignored (Yalidine does not guarantee order). Webhooks move orders only when automatic sync is on, and the hourly sync stays as the safety net.
- **Wilayas 59–69 sent as their parent** to Yalidine, unless imported communes show Yalidine knows them: its docs list 58 wilayas.
- **ZR Express: "coming soon", new platform only** (15 October 2026): ZR is moving its merchants from the old Procolis API to api.zrexpress.app, so a Procolis connector would be thrown away soon. The connector option "ZR Express" exists now and behaves like Manuel (with a notice on the courier form); the real connector will target the new platform once its official docs are available. What was learned about Procolis is kept in docs/COURIER_INTEGRATION.md §5.
- **Courier prices are per account, not public**: Yalidine prices depend on the departure wilaya and the destination commune and can be imported from its fees API; ZR Express rates are negotiated. The wilaya table stays the single place for rates, filled by import (Yalidine) or by hand (ZR).
- **ERPNext manufacturing is left installed and untouched**: out of scope for this phase, nothing in dz_cod depends on it or disables it, so it can be used later for the print workshop.
- **Courier settings live on the Supplier** (custom fields shown when "Is Transporter" is ticked): a courier is a supplier in ERPNext, no new doctype needed.
- **Hourly status sync is off by default** (setting) and uses the normal workflow actions, so webhooks and stock movements behave as if a person clicked.

## Settlement (Versement)

- **One line per parcel, matched by order name or tracking number.**
- **Net amount is what matters**: difference = (collected − courier fee) − (expected amount − expected fee).
- **Line statuses**: OK, Écart, Inconnue, Déjà réglée, Invalide. Only OK lines (and Écart lines ticked "Accepter") move the order to Réglée on submit.
- **Only "Livrée" orders can be settled**: an order still "Expédiée" is shown as Invalide; mark it delivered first (the list view allows bulk workflow actions).
- **"Missing" = delivered by this courier up to the settlement date, not in this statement and not paid yet.**
- **Cancelling a Versement puts its orders back to "Livrée" by writing the field directly**: a Workflow cannot move backwards.
- **A dispute stays on the order until a later Versement pays the rest**: an order can be paid over several Versements. "Déjà versé" on a line = the net of the order's lines in earlier submitted Versements of the same courier; the line then expects only the rest, "Charger les commandes livrées" pre-fills only the rest (no fee again), and "Encours transporteurs" shows the rest as owed and as "Montant en litige". Found in the 15 Oct 2026 demo walk: before this, the next Versement pre-filled the whole order again and it was booked as paid twice.
- **A Versement cannot be cancelled while a later Versement settled one of its disputed orders on the rest**: cancel the later one first, or the order would stay Réglée while paid short.
- **Tolerance** (COD Settings, default 0 DA) for rounding differences.

## Webhooks

- **Classic document-event Webhooks with a condition** `doc.workflow_state == "…" and doc.has_value_changed("workflow_state")`: they fire once per move, respect the "Enabled" box and run in the background after the database commit. Frappe v16's "workflow transition" webhooks were rejected because they run synchronously (a down n8n would block the button) and ignore "Enabled".
- **Created disabled with a placeholder URL, never overwritten afterwards**: the client's real n8n URL survives `bench migrate`. Side effect: a fix to the template needs a manual update or a patch on existing sites.
- **In the template write `doc["items"]`**: `doc.items` is the Python dictionary method in Jinja (bug found by the tests).

## Interface

- **Doctype names in English, user-facing labels in French**: code stays English (rule 6), and `translations/fr.csv` shows "Versement", "Paramètres COD", "Commande", etc.
- **Sales Order is relabelled "Commande"** and Delivery Note "Bon de livraison" in French through the same CSV.
- **English and Arabic, by translation, not by rewriting**: the app stays written in French and `translations/en.csv` gives the English version of each text (about 250). Frappe's usual way is the opposite (English source, French translation), but switching would mean renaming every label and changing the workflow state values already stored in clients' orders. With a translation file nothing stored changes: an order stays "Livrée" in the database and is shown as "Delivered" to English users. Each user picks their language (User → Language). `tests/test_translations.py` fails when a new French text has no English line. The welcome guide (plain HTML) holds both versions. "Client" is deliberately not translated: Frappe uses "Client" as an English word too (OAuth Client), and the CSV applies to the whole site. Account names, item names and other data stay as entered. **Arabic** works the same way with `translations/ar.csv` (Modern Standard Arabic; standard ERPNext terms reused where they exist: إشعار التسليم, العميل, الأصناف; "courier" is شركة التوصيل as Algerian shops say it); Frappe mirrors the screen right-to-left by itself. The Arabic file also names our own doctypes and reports, which are English in the code. "Code" is left out of it: Frappe already translates it.
- **Reports use plain SQL**: easier to read for someone who knows Oracle SQL than Frappe's query builder.
- **Reports default to the COD Settings company** when the company filter is empty.
- **A "COD" module sidebar** groups orders, settlements, reports and settings. No desktop icon: the icon grid is being retired in v16.
- **The COD sidebar is mounted on ERPNext's left rail** (`dz_cod/dock/dz_cod/dz_cod.json`, a v16 "Dock" with `mount_on: erpnext`): a truck icon next to Vente/Stock. Without it a normal user had no way to reach the COD menu (it only opened from a direct link). Mounting rather than adding a separate "COD" app tile keeps one app and one rail for the client.
- **A COD home page ("Accueil", the first item of the COD menu)**, built like ERPNext's own module home pages: a standard Workspace (`dz_cod/dz_cod/workspace/cod/`) holding a "life of an order" overview, an onboarding checklist (`module_onboarding/`, `onboarding_step/`), four live counters (`number_card/`: to confirm, to ship, in transit, money held by couriers), two charts (`dashboard_chart/`) and link cards. All standard Frappe records, shipped as files and loaded by `bench migrate`. The overview is a Custom HTML Block, which Frappe cannot ship as a file, so `setup/install.py` creates it from `setup/home_block/` on install and migrate. Onboarding steps tick themselves when the matching record exists (a courier, an item, an order...), so an already-running shop sees most steps done. Each user can fold the overview (**Réduire**) or close it (**✕**); the choice is a per-user default saved on the server (`cod/home.py`), so it follows them on every device, and **Paramètres COD → Réafficher le guide d'accueil** brings it back. An administrator can also remove the block for everyone with the page's standard *Edit* mode.
- **No VAT by default**: ERPNext's setup wizard makes "Algeria TVA 19%" the default sales tax template, which the order form adds to every order typed by hand. The demo loader unticks it; for a client site it is a step of the new-client checklist (docs/DEPLOY.md, section 13), not code, so a VAT-registered client can keep it.

## Demo data

- **Invented seller "Encre & Fil SARL"**, brands "Encre Urbaine" (printed designs) and "Fil Doux" (basics), couriers "Rapide Express (démo)" and "Colis Sahara (démo)" on the Mock connector. None resembles a real brand.
- **ERPNext's Algerian chart of accounts** ("Algerie - Plan Comptable General 2 avec code") for the demo company, DZD, Africa/Algiers, French interface.
- **30 products, ~260 variants** (size × colour), unit "Pièce", realistic DZD prices and costs.
- **History is replayed day by day through the real workflow**, so the demo data is exactly what the app produces (stock ledger, delivery notes, returns, settlements).
- **Idempotent keys**: orders by "Customer's PO" = `DEMO-0001`…; settlements by reference; everything else by name. A fixed random seed gives the same demo every time.
- **The loader refuses to run on a site holding another company's orders**: protection against loading fake data into a client site.
- **Prices are set by the loader**: ERPNext only applies the price list in the browser form, not on server-side inserts.
- **Disputed parcels stay disputed in the demo** (the next weekly statement does not re-pay them), so the outstanding report has something to show.
- **Wipe = cancel and delete in reverse order, keep the company**; a total reset is simply dropping and re-creating the demo site.

## Tests

- **Tests live in `dz_cod/tests/`, outside doctype folders**: this way Frappe does not try to build ERPNext's own test records (slow and fragile); our fixtures reuse the demo setup functions and everything is rolled back after each test class.
- **The courier sync test patches `frappe.db.commit`**: the real job commits after each order, which would otherwise make test data permanent.
