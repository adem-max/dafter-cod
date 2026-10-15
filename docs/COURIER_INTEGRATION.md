# Courier integration: Yalidine and ZR Express

What is known about the couriers' APIs and prices (October 2026), how sure
we are, and the step-by-step plan for real connectors.

**Status (15 October 2026):** the Yalidine connector is **built** (steps Y1
to Y7 and Y9 below; Y8 is not), tested with a fake HTTP layer that answers
with the JSON examples of Yalidine's docs. **It has never been called
against a real Yalidine account.** Before the first client uses it, go
through the checklist in section 4 ("Before going live").

**ZR Express: coming soon.** ZR is moving its merchants from the old Procolis
API to its new platform, so building the old API now would be wasted, and
the new one has no official docs yet. Meanwhile the *Connecteur* "ZR Express"
can already be chosen on a courier: it works like *Manuel* (tracking typed
by hand) and the courier form says the connector is coming
(`dz_cod/couriers/zrexpress.py`). When the connector is built, only that
class changes.

---

## 1. What was found, and how much to trust it

| Source | What it gives | Trust |
|--------|---------------|-------|
| **Yalidine official docs** (in the merchant dashboard, login required; not reachable from the build machine) | everything | the authority: always check against it |
| **Copy of Yalidine's official API + webhook docs** saved in the open-source project [TaharBn12/Ecommerce-sys](https://github.com/TaharBn12/Ecommerce-sys) (`.agents/skills/yalidine-integration-skill-main/offcial-docs.md` and `webook.md`, updated September 2026) | endpoints, fields, statuses, fees, rate limits, webhooks | **high**: a verbatim copy of Yalidine's documentation |
| [ZaouiAmine/dzcouriers](https://github.com/ZaouiAmine/dzcouriers) (Go client, Sept 2026) and [PiteurStudio/CourierDZ](https://github.com/PiteurStudio/CourierDZ) (PHP) | working client code for Yalidine, ZR Express (new and legacy), Ecotrack, Maystro, NOEST | medium: unofficial, but they agree with each other and with the Yalidine docs copy |
| ZR Express official docs ("API Docs" in the ZR merchant app, per [zrexpress.net](https://www.zrexpress.net/en)) | ZR endpoints | not reachable from here: **ask ZR for them** |
| Price comparison sites ([dz-ecom.com](https://dz-ecom.com/en/blog/yalidine-vs-zr-express-vs-noest-comparatif-2026), [dropdz.space](https://dropdz.space/livraison-algerie), [codrocket.com](https://codrocket.com/fr/blog/best-delivery-companies-algeria-2026)) | indicative 2026 price ranges | low: they contradict each other |

## 2. Prices: why there is no public price list

**Neither Yalidine nor ZR Express publishes an official national price
list.** Prices depend on the merchant account:

- **Yalidine**: the price depends on the **departure wilaya** (where the shop
  hands the parcels over), the **destination commune** (not only the wilaya),
  the delivery type, and the **weight** (above 5 kg). Yalidine exposes the
  account's own prices through its API (`GET /v1/fees/`), so **we can import
  them automatically** (step Y5 below).
- **ZR Express**: the price list is negotiated per merchant (ZR advertises
  "preferential rates from 50 parcels/month"). No price endpoint was found
  in the open-source clients. **Type the client's ZR rate card into the
  wilaya list** (*Wilayas et tarifs*).

Indicative 2026 ranges from comparison sites (≤ 5 kg, not official):

| | Home delivery | Stop desk |
|---|---|---|
| Yalidine, north | ~400–600 DA | ~250–450 DA |
| Yalidine, south / far south | ~900–1,400 DA | ~600–1,100 DA |
| ZR Express, north | ~350–700 DA | ~200–450 DA |

Our example rates (400 → 1,400 DA by zone) sit in that range, but only the
client's account gives the real numbers.

**Other costs from the Yalidine fees API** (per account): `retour_fee`
(charged when a parcel comes back, e.g. 250 DA), `cod_percentage` (e.g. 0.75 %
of the collected amount), `insurance_percentage`, and `oversize_fee` per kg
above 5 kg. Today the kit only models one courier cost per wilaya; the return
fee and COD percentage are a planned improvement (step Y5, last point).

---

## 3. Yalidine: what the API looks like

Facts from the docs copy. Check each against the client's dashboard docs.

- **Base URL**: `https://api.yalidine.app/v1/`
- **Authentication**: two HTTP headers on every call, `X-API-ID` and
  `X-API-TOKEN`, from the Yalidine *Developer Dashboard* of the client's account.
- **Rate limits** (defaults): 5 calls/second, 50/minute, 1,000/hour,
  10,000/day. Remaining quota comes back in headers `x-second-quota-left`,
  `x-minute-quota-left`, `x-hour-quota-left`, `x-day-quota-left`. Over the
  limit: HTTP 429 with a `Retry-After` header. Repeated abuse temporarily
  disables the API key, so stay well under the limits.
- **Endpoints**:

| Need | Call |
|------|------|
| create parcels | `POST /v1/parcels/` with a JSON **list** of parcels |
| read parcel(s) | `GET /v1/parcels/<tracking>` or `GET /v1/parcels/?tracking=a,b,c` |
| edit / delete | `PATCH` / `DELETE /v1/parcels/<tracking>` (only while status is "En préparation") |
| status history | `GET /v1/histories/<tracking>` or `GET /v1/histories/?tracking=a,b,c` |
| stop desks | `GET /v1/centers/?wilaya_id=16` (gives `center_id`) |
| communes | `GET /v1/communes/?wilaya_id=16` (with `has_stop_desk`, `is_deliverable`) |
| wilayas | `GET /v1/wilayas/` |
| prices | `GET /v1/fees/?from_wilaya_id=<departure>&to_wilaya_id=<destination>` |

- **Create parcel, required fields**: `order_id` (we send the Sales Order
  name), `from_wilaya_name`, `firstname`, `familyname`, `contact_phone`
  (starts with 0; several numbers separated by commas), `address`,
  `to_commune_name`, `to_wilaya_name`, `product_list` (text), `price` (amount
  to collect, 0–150,000), `do_insurance`, `declared_value`, `length`, `width`,
  `height`, `weight`, `freeshipping`, `is_stopdesk`, `stopdesk_id` (required
  when `is_stopdesk` is true), `has_exchange` (+ `product_to_collect` if true).
- **Create parcel, answer**: one entry per `order_id`:
  `{"SAL-ORD-2026-00012": {"success": true, "tracking": "yal-12345A", "label": "https://…", "message": ""}}`.
  Valid parcels are created even if others in the same call fail.
- **Statuses** (French text): Pas encore expédié, A vérifier, En préparation,
  Pas encore ramassé, Prêt à expédier, En passation, Ramassé, Bloqué,
  Débloqué, Transfert, Expédié, Centre, En localisation, Vers Wilaya, En
  transit, Reçu à Wilaya, En attente du client, Prêt pour livreur, Sorti en
  livraison, En attente, Annulé, En alerte, Alerte résolue, Tentative échouée,
  **Livré**, Echèc livraison, Retour vers centre, Retourné au centre, Retour
  transfert, Retour groupé, Retour à retirer, Retour non retiré, Colis
  abandonné, Retour vers vendeur, **Retourné au vendeur**, Echange échoué.
- **Payment status of each parcel**: `not-ready`, `ready`, `receivable`,
  `payed`, with a `payment_id` (the payout manifest) — useful to pre-fill
  our Versement.
- **Webhooks** (push instead of polling): events `parcel_created`,
  `parcel_edited`, `parcel_deleted`, `parcel_status_updated`,
  `parcel_payment_updated`. Each delivery groups several events, each with an
  `event_id` (to ignore duplicates) and `occurred_at` (order is not
  guaranteed). Yalidine first sends a **GET** with `subscribe` and
  `crc_token`: the endpoint must answer the `crc_token` value as plain text
  within 10 s, and Yalidine re-checks this from time to time (fail = webhook
  disabled). Each delivery carries an `X-YALIDINE-SIGNATURE` header =
  HMAC-SHA256 of the raw body with the webhook's secret key. Failed
  deliveries are retried 7 times with growing delays, then the webhook is
  disabled.
- **Wilaya codes**: Yalidine works with wilaya **names** in parcels and
  numeric ids in filters. Check in `GET /v1/wilayas/` whether the 2026
  wilayas (59–69) exist in Yalidine; if not, send the **parent wilaya**
  (field *Wilaya d'origine* on our wilaya records, already filled).

## 4. Yalidine: implementation steps

**Built** in October 2026, without a Yalidine account. Where the code is:

| Step | Code |
|------|------|
| Y1 fields | `setup/custom_fields.py` (Supplier: *Wilaya de départ*, *Clé secrète webhook*; Sales Order: *Bureau stop desk*, *Étiquette du transporteur*, *Statut chez le transporteur* + date, *Paiement chez le transporteur* + n°) |
| Y2–Y4 | `couriers/yalidine.py` (`call`, `create_shipment`, `get_statuses`, `get_tracking`) |
| Y5, Y6 | `couriers/yalidine_import.py` (two buttons on the courier, `public/js/supplier.js`), `couriers/places.py`, doctypes DZ Commune and DZ Stop Desk |
| Y7 | `couriers/yalidine_webhook.py`, doctype Courier Webhook Event |
| Y9 | `tests/test_yalidine.py` (23 tests) |

Differences from the plan below, and why (also in DECISIONS.md):
- **`freeshipping` is sent as `true`, not `false`.** Yalidine's docs say
  `false` = "paid by the receiver", which reads as "Yalidine adds its fee to
  what the customer pays". Our `price` already contains the delivery fee, so
  `false` could make the customer pay it twice. With `true` Yalidine keeps
  its fee from what it pays us, which is what our settlement expects.
  **Check 2 below decides.**
- **Status sync reads `GET parcels/?tracking=…` (field `last_status`)**
  instead of `histories/`: one line per parcel, so 50 parcels fit in one
  call without paging. `get_tracking` still reads `histories/<tracking>`.
- **Duplicate guard**: before creating, `GET parcels/?order_id=<order>`
  (the filter is in the docs); an existing parcel that is not "Annulé" is
  reused instead of creating a second one.
- **Commune check at confirmation**: once communes are imported, an order
  for a Yalidine courier cannot be confirmed with a commune Yalidine does
  not know (the spelling is corrected automatically: "kouba" → "Kouba").
  Before the import, the commune is sent as typed.
- **Webhooks only move orders when *Synchroniser les statuts
  automatiquement* is ticked** in COD Settings, like the hourly sync.
  Yalidine's own words are always written on the order.
- **Wilayas 59–69** are sent as their parent wilaya unless the communes
  import shows Yalidine knows them (communes with that wilaya id).

### Before going live: checks with the client's real Yalidine account

Do them in this order, on your laptop, with **one or two test parcels** that
you delete right after in the Yalidine dashboard (allowed while the status is
"En préparation"). Fill in the courier first: *Connecteur* = Yalidine,
*API ID*, *API Token*, *Wilaya de départ*.

1. **Keys and quotas**: in `bench --site <site> console`,
   `from dz_cod.couriers import get_adapter; get_adapter("<courier>").call("GET", "wilayas/")`
   returns the wilayas. Note the account's real rate limits in the Developer
   Dashboard (the code assumes the defaults 5/s, 50/min).
2. **Amount collected** (the most important): ship one test order. In the
   Yalidine dashboard the amount to collect must equal the order's *Montant
   à encaisser*, **not** that amount plus the delivery fee. If Yalidine adds
   its fee, `freeshipping` must change (`build_parcel` in `yalidine.py`).
3. **The parcel**: names, phones, commune, address, product list look right;
   the label link (*Étiquette du transporteur* button on the order) opens and
   prints.
4. **Retry guard**: call `get_adapter(...).find_parcel("<order name>")` and
   check it finds the test parcel, and only it (the `order_id` filter must
   be an exact match).
5. **Wilayas 59–69**: does `GET wilayas/` list them? If yes, run *Importer
   communes et bureaux Yalidine* and check a 2026 wilaya gets its own
   communes; if no, check a parcel to a 2026 wilaya goes to the parent.
6. **Communes and stop desks**: run the import; ship one stop-desk test
   parcel (Yalidine wants `stopdesk_id`; we send the id as text).
7. **Statuses**: `get_adapter(...).get_statuses(["<tracking>"])` returns
   `in_transit`; check the exact spelling of the statuses the account
   returns ("Livré", "Retourné au vendeur" move the order). Agree the
   mapping with the client.
8. **Prices**: run *Importer les tarifs Yalidine*, compare 3 wilayas with the
   dashboard (express home / stop desk of the chef-lieu). If the account
   uses the "economic" prices, `chef_lieu_prices` must read those.
9. **Webhook**: in the Yalidine Webhooks dashboard add
   `https://<client site>/api/method/dz_cod.couriers.yalidine_webhook.receive`,
   copy its secret key into *Clé secrète webhook*, run Yalidine's test page:
   the URL check (crc) must pass and a test event must appear in **Courier
   Webhook Event** as "Traité" or "Ignoré", not be refused. Then set the
   webhook active. A background worker must run (the events are applied by
   a job).
10. Delete the test parcels, then tick *Synchroniser les statuts
    automatiquement* in COD Settings.

The original plan follows (kept for the reasoning).

**Y1. Configuration fields** (`setup/custom_fields.py`, then migrate)
- On **Supplier** (the courier): `dz_from_wilaya` (Link DZ Wilaya, the
  shop's departure wilaya) and `dz_webhook_secret` (Password). `dz_api_id`
  and `dz_api_token` already exist.
- On **Sales Order**: `dz_stopdesk_id` (Data, "Bureau stop desk"), needed
  when the delivery type is Stop desk; `dz_label_url` (Data, read-only,
  allow on submit) to print the courier's label.

**Y2. A small HTTP helper** in `couriers/yalidine.py`

```python
BASE_URL = "https://api.yalidine.app/v1/"

def call(self, method, path, params=None, json=None):
    headers = {"X-API-ID": self.courier.dz_api_id,
               "X-API-TOKEN": self.courier.get_password("dz_api_token")}
    response = requests.request(method, BASE_URL + path, headers=headers,
                                params=params, json=json, timeout=20)
    if response.status_code == 429:
        frappe.throw(_("Yalidine : quota dépassé, réessayez dans {0} s.").format(response.headers.get("Retry-After")))
    response.raise_for_status()
    return response.json()
```

Check: `call("GET", "wilayas/", params={"page_size": 1})` in the console
returns data with the client's keys.

**Y3. `create_shipment(order)`**
- Build one parcel dict from the order: `order_id` = order name;
  `from_wilaya_name` = name of the courier's `dz_from_wilaya`;
  `to_wilaya_name` = wilaya name (or its parent wilaya for 59–69 if Yalidine
  does not know it); `to_commune_name` = `dz_commune` (must match Yalidine's
  spelling: see Y6); `firstname` / `familyname` = split customer name
  (repeat the first name if there is only one word); `contact_phone` =
  `dz_phone` (plus `,dz_phone_2`); `address`; `product_list` = "2 x T-shirt
  Casbah Noir M, …"; `price` = `dz_cod_amount`; `declared_value` = same;
  `do_insurance` = false; `weight` = 1 (or a weight from the items);
  `length/width/height` = 1; `freeshipping` = false (the customer pays,
  already inside `price`); `is_stopdesk` = delivery type is Stop desk;
  `stopdesk_id` = `dz_stopdesk_id`; `has_exchange` = false.
- `POST parcels/` with `[parcel]`; read the entry for our `order_id`; if
  `success` is false, `frappe.throw` the `message` (the order then stays
  Préparée and nothing moves in stock).
- Return the `tracking`; save `label` into `dz_label_url`.
- Check: ship one test order; the parcel appears in the Yalidine dashboard
  with the same amount; delete it there.

Note: the API call happens inside the database transaction of the
"Expédier" click. If something fails *after* the call (very rare), the
parcel exists at Yalidine but our order stays Préparée. Clicking again
would create a second parcel, so first look the parcel up with
`GET parcels/?order_id=…` (check that filter exists in the docs) or show a
clear message to delete the orphan parcel in the dashboard.

**Y4. `get_status(tracking)` and `get_tracking(tracking)`**
- `GET histories/<tracking>`, take the latest `date_status`.
- Translate to our four words. Proposal (decide with the client):

| Yalidine status | Ours |
|-----------------|------|
| Livré | `delivered` |
| Retourné au vendeur | `returned` (the parcel is physically back: the return note goes into the Retours warehouse) |
| everything else | `in_transit` |

  "Echèc livraison", "Retour vers vendeur", "Retour à retirer" mean the
  parcel is *coming back*; show them on the order (a new read-only field
  `dz_courier_status`) so the team knows, but only move to Retournée when it
  has arrived.
- For the hourly sync, ask for 50 tracking numbers per call
  (`histories/?tracking=a,b,…`) instead of one call per order, to stay far
  below the rate limits.
- Check: with the test parcel, `get_tracking` lists its history.

**Y5. Import prices into the wilaya list**
- A button on the courier (Supplier) form, "Importer les tarifs Yalidine":
  for each of the 58 Yalidine wilayas call
  `fees/?from_wilaya_id=<dz_from_wilaya>&to_wilaya_id=<n>`, wait 1.5 s
  between calls (50/minute limit), and write the price of the wilaya's
  chef-lieu commune into *Coût transporteur domicile / stop desk*
  (`express_home`, `express_desk`). Leave the customer prices (*Tarif
  domicile / stop desk*) to the seller: they decide whether to add a margin.
- Later, for exact prices per commune: a "commune" master list (LATER.md
  item 4) with Yalidine's per-commune prices, and add `retour_fee` and
  `cod_percentage` to the settlement's expected fee.
- Check: compare 3 wilayas with the prices shown in the client's dashboard.

**Y6. Communes and stop desks**
- Yalidine refuses commune names it does not know. Add a small "Communes
  Yalidine" import (`communes/?wilaya_id=…`) and use it in the order form
  as a dropdown filtered by wilaya, instead of free text, for clients who
  use Yalidine.
- Same for stop desks: import `centers/` and let the operator pick the
  office when the delivery type is Stop desk (fills `dz_stopdesk_id`).

**Y7. Webhook receiver (optional, replaces polling)**
- A guest endpoint `dz_cod.couriers.yalidine_webhook.receive`
  (`@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])`):
  - GET with `subscribe` and `crc_token`: return the token as plain text
    (`return werkzeug.wrappers.Response(crc_token)`; Frappe passes a returned
    Response straight through, checked in v16's `handler.py`).
  - POST: compute `hmac.new(secret, raw_body, hashlib.sha256).hexdigest()`,
    compare with `X-YALIDINE-SIGNATURE` using `hmac.compare_digest`; reject
    if different. Read `frappe.request.get_data()` **before** parsing JSON.
  - For each event: skip it if its `event_id` was already processed (store
    ids in a small log doctype), then for `parcel_status_updated` apply the
    same mapping as Y4 with `apply_workflow`; for `parcel_payment_updated`
    store `status`/`payment_id` on the order.
  - Answer 200 quickly; do the work in `frappe.enqueue` if it is slow.
- In the Yalidine Webhooks dashboard: URL
  `https://erp.client.com/api/method/dz_cod.couriers.yalidine_webhook.receive`,
  test it with Yalidine's test page, then set it to active.
- Keep the hourly sync as a safety net (webhooks can be disabled after 7
  failed deliveries).

**Y8. Versement from Yalidine payments (optional, NOT built)**
- A button "Charger depuis Yalidine": read parcels with
  `payment_status=receivable` or a given `payment_id`, and create one line per
  parcel (tracking, amount, fee). The matching rules stay the same.

**Y9. Tests**
- Unit tests with a fake HTTP layer (`unittest.mock.patch("requests.request")`)
  returning the JSON examples from the docs: create success, create failure
  message, history → status mapping, 429 handling, webhook signature
  accepted / rejected, `crc_token` echo.
- One manual end-to-end test with the client's account before going live.

## 5. ZR Express: what the API looks like

ZR Express has **two APIs**. Ask the client which one their account uses.

**New platform** (`https://api.zrexpress.app/api/v1/`, read from two
independent open-source clients; ask ZR for the official "API Docs"):
- **Authentication**: headers `X-Api-Key` (secret key) and `X-Tenant`
  (tenant id, a UUID), both from the ZR merchant portal (API / integrations).
- **Places are UUIDs, not names**: wilayas ("city") and communes
  ("district") are *territories* found with
  `POST territories/search` `{"keyword": "Alger", "pageSize": 50, "pageNumber": 1}`
  (add `"deliveryType": {"value": "pickup-point"}` to find stop desks).
- **Creating a parcel takes 4 calls**: create the customer
  (`POST customers/individual` → customer id), find the city and district
  UUIDs, `POST parcels` (→ parcel id), then `GET parcels/<id>` to read the
  `trackingNumber`. Phones are sent in international format (`+213…`).
- **Tracking**: `GET parcels/<tracking>/state-history`.
- **Labels**: `POST parcels/labels/individual/pdf`.
- **Cancel**: `POST parcels/bulk/by-tracking-number`.
- **Webhooks**: registered through the API (`webhooks/endpoints`), with a
  signing secret.
- **State names are free text configured per merchant account** (for
  example "Out for Delivery", "In Transit", "At Hub"): there is no fixed
  list. You must look at the real names in the client's account and map them.
- **Prices**: no price endpoint found; use the negotiated rate card.

**Old platform "Procolis"** (`https://procolis.com/api_v1/`): credentials
*Token* + *Key* (ZR portal → Paramètres → Info personnelles). Older accounts
may still use it. Do not build both: build the one the client has.

**Decision (15 October 2026): build only the new platform.** ZR is migrating
its merchants off Procolis. What was learned about Procolis, in case the
migration stalls (from the merchant portal's *Développement* page and the
CourierDZ PHP client, never called for real):
- headers `token` and `key` on every call; `GET /token` answers
  `{"Statut": "Accès activé"}` when the keys are valid
- `POST /add_colis` with `{"Colis": [{Tracking, TypeLivraison (0 home, 1 stop
  desk), TypeColis (1 exchange), Confrimee (sic; 1 = ready to ship), Client,
  MobileA, MobileB, Adresse, IDWilaya, Commune, Total, Note, TProduit,
  id_Externe, Source}]}`; **we choose the tracking number**; the answer's
  `Colis[0].MessageRetour` is `"Good"`, `"Double Tracking"` or an error text
- `POST /lire` and `POST /pret` with `{"Colis": [{"Tracking": …}, …]}` (read
  parcels incl. their `Situation`; mark ready to ship); `POST /tarification`
  (list per `IDWilaya`)
- no labels, no cancel, no webhooks (Telegram notifications only), no
  stop-desk list; the `Situation` values and rate limits are not documented

## 6. ZR Express (new platform): implementation steps

Estimated effort: 3–5 days, more uncertain than Yalidine because the
official docs must first be obtained.

**Z0. Get the official documentation** from ZR (merchant app → API Docs, or
the client's account manager). Compare it with section 5 and correct this
plan where it differs. Do not start coding before this.

**Z1. Configuration fields**: on Supplier, `dz_api_id` holds the tenant id
and `dz_api_token` the secret key (rename the labels for ZR, or add
`dz_tenant_id`); add a child table **"Correspondance des statuts"** (ZR state
name → our word: delivered / returned / in_transit). This mapping is per
client because ZR state names are per account (rule 4: settings, not code).

**Z2. Territory cache**: a doctype or a cached dict "ZR territory" (wilaya
code / commune name → UUID), filled once with `territories/search` and
refreshed monthly. Avoids 2 extra calls per parcel.

**Z3. `create_shipment(order)`**: customer → (cached) territories →
`POST parcels` with `externalId` = order name, `amount` = `dz_cod_amount`,
`deliveryType` = `home` or `pickup-point` (+ `hubId` for stop desk),
`orderedProducts` from the order lines → `GET parcels/<id>` for the tracking
number. If the tracking number is not ready yet, store the parcel id and let
the sync fill the tracking number later.

**Z4. `get_status` / `get_tracking`**: `state-history`, last entry, mapped
through the table from Z1; unknown state names → `in_transit` + an Error Log
entry "ZR state not mapped: …" so you add it to the table.

**Z5. Webhook receiver** (like Y7) once the official docs describe the
payload and signature; until then, hourly polling.

**Z6. Tests**: same approach as Y9, with JSON captured from the client's
real account.

## 7. Common work for any courier

1. Add the new class to `ADAPTERS` in `dz_cod/couriers/__init__.py` and the
   option name to the Supplier field *Connecteur* (`setup/custom_fields.py`).
2. Never put keys in code: they live in the Supplier record (*API Token* is
   encrypted). Back up the site's `encryption_key` (docs/DEPLOY.md §9).
3. Turn on *Synchroniser les statuts automatiquement* in COD Settings only
   after the status mapping has been checked on real parcels.
4. Add a print format with the courier label link / barcode (LATER.md).
5. Update DECISIONS.md and the study guide chapter 6 with what you built.
