# dz_cod — COD e-commerce starter kit on ERPNext (Algeria)

A Frappe app, installed next to ERPNext, that turns ERPNext into a
cash-on-delivery order desk for Algerian online sellers (Instagram, Facebook,
website): phone confirmation, stock reservation, shipping fees by wilaya,
courier hand-over, returns, and courier cash settlement ("Versement").

## Status

| | |
|---|---|
| **Target version** | **ERPNext v16.50.0 on Frappe v16.51.0** (branch `version-16`, latest stable major in October 2026) |
| **Tested on a real site?** | **Yes.** Installed and run in an Ubuntu 24.04 container: Python 3.14, Node 24, MariaDB 10.11, Redis. |
| **Automated tests** | 60 tests (22 unit + 38 integration on a real ERPNext site), all passing, on the development site and on a brand-new site. |
| **Checked in a real browser** | order list and form, "Expédier" dialog, return inspection dialog, reports, COD sidebar (headless Chromium). |
| **Demo** | loaded on a fresh site in 2 min 20 s; second run changes nothing; wipe + reload checked. |
| **Backup / restore** | backup of the demo site restored into a new site, data and encrypted secrets verified. |
| **Not run** | production mode (nginx, supervisor, Let's Encrypt, firewall), off-site copy to a real cloud storage (the backup script was run with a local rclone remote), the Fedora/distrobox commands — they need a public server or a Fedora machine. Marked *(not run here)* in the docs. |
| **Not implemented** | real courier API connector: `couriers/yalidine.py` is a documented stub (`# UNTESTED`, raises "not implemented"). The Yalidine and ZR Express APIs have since been researched; the implementation plan is in docs/COURIER_INTEGRATION.md. |

## What you get

**Order life cycle** — a standard ERPNext Workflow on Sales Order ("Commande"):

```
Nouvelle ──Confirmer──> Confirmée ──Préparer──> Préparée ──Expédier──> Expédiée ──Marquer livrée──> Livrée ──Marquer réglée──> Réglée
   │ ▲                     │                       │                     │
   │ └─Pas de réponse─> Injoignable (call counter) │                     └──Marquer retournée──> Retournée
   └─Annuler─> Annulée     └────────Annuler────────┴──> Annulée après confirmation
```

- **Confirmée**: phone, wilaya and address checked; stock reserved (ERPNext reserved qty); optional block if stock is short.
- **Injoignable**: each "Pas de réponse" adds 1 to the call counter; the button disappears at the maximum (default 3).
- **Expédiée**: courier + tracking number (typed, or given by the courier connector); a Delivery Note takes the stock out.
- **Retournée**: a return Delivery Note brings the parcel into the **Retours** warehouse; then **Inspecter le retour** puts good pieces back in stock and writes damaged ones off.
- **Réglée**: set by a courier settlement (Versement).

**Shipping fees** — the list of the **69 wilayas** (2026 division) holds a
home-delivery and a stop-desk rate plus the courier's cost; the fee is added
to each order automatically (editable "manual rate" for free delivery).

**Versement (courier settlement)** — record a courier's statement, match each
parcel to its order (by tracking number), see what is **paid**, **disputed**
and **missing**; submitting marks paid orders "Réglée".

**Courier connectors** — one interface (create shipment, get status, get
tracking); **Manuel** (default), **Mock** (offline, for tests and demos),
**Yalidine** (stub). Optional hourly status sync.

**Webhooks for n8n** — on Confirmée, Expédiée, Livrée, Retournée, with a
documented JSON payload (docs/WEBHOOKS.md). Created disabled.

**Reports** — *Commandes par jour (COD)*, *Taux de retour (COD)* (by
product, variant or wilaya), *Encours transporteurs (COD)*.

**Demo shop** — "Encre & Fil SARL", a fictional seller: 30 products / ~260
variants, 80 customers, 200 orders over 60 days in every state, weekly
settlements (docs/DEMO.md).

## Install

On a bench with Frappe v16 and ERPNext v16 (full server guide: docs/DEPLOY.md):

```bash
cd ~/frappe-bench
bench get-app https://github.com/adem-max/dz-cod        # downloads the app (folder apps/dz_cod)
bench --site erp.client1.com install-app dz_cod          # custom fields, workflow, 69 wilayas, webhooks
```

Then, in the site (interface in French):

1. **Paramètres COD**: company, main warehouse, returns warehouse, account for delivery fees.
2. **Fournisseur** for each courier with *Est un transporteur* ticked (connector "Manuel").
3. **Wilayas et tarifs**: replace the example rates with the courier's rate card.
4. Optionally enable the **Webhooks** (docs/WEBHOOKS.md).

Updates: `bench update`, or for this app only `git pull` in `apps/dz_cod`
then `bench --site all migrate` (docs/DEPLOY.md §11).

## Try it on your laptop

docs/LOCAL_TEST.md (Fedora, using an Ubuntu 24.04 distrobox), then docs/DEMO.md.

## Run the tests

```bash
bench --site test.localhost set-config allow_tests 1      # on a test site, never in production
bench --site test.localhost run-tests --app dz_cod
```

## Documentation

| File | For |
|------|-----|
| [docs/STUDY_GUIDE.md](docs/STUDY_GUIDE.md) | **Start here.** How every part works, with exercises and failure modes |
| [docs/DEMO.md](docs/DEMO.md) | The demo shop: load, reload, wipe, a 10-minute demo script |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Ubuntu server, one site per client, SSL, backups, restore, updates, security, new client in 2 hours |
| [docs/WEBHOOKS.md](docs/WEBHOOKS.md) | n8n webhooks and payloads |
| [docs/COURIER_INTEGRATION.md](docs/COURIER_INTEGRATION.md) | Yalidine / ZR Express APIs and prices: what is known, and the step-by-step plan for real connectors |
| [docs/LOCAL_TEST.md](docs/LOCAL_TEST.md) | Run everything on your Fedora machine |
| [DECISIONS.md](DECISIONS.md) | Every design choice, one line of reasoning each |
| [LATER.md](LATER.md) | Ideas and out-of-scope items for later phases |

## Code map

```
dz_cod/
  hooks.py                  how the app plugs into ERPNext
  cod/                      business rules
    states.py                 state and button names
    order.py                  what happens at each step of the order
    stock.py                  delivery note, return, inspection
    shipping.py               shipping fee from the wilaya rate table
    settlement.py             settlement matching rules (pure functions)
    phone.py                  Algerian phone numbers
  couriers/                 courier connectors: base, mock, yalidine (stub), hourly sync
  setup/                    created on install/migrate: custom fields, workflow, wilayas, webhooks
  dz_cod/doctype/           DZ Wilaya, COD Settings, Courier Settlement (+ Item)
  dz_cod/report/            the 3 reports
  dz_cod/sidebar/           the "COD" menu
  demo/                     demo shop loader and wipe
  tests/                    automated tests
  public/js/sales_order.js  "Expédier" dialog and return inspection on the order form
  translations/fr.csv       French names for our doctypes and reports
  translations/en.csv       English version of every French text (per-user language)
  translations/ar.csv       Arabic version (right-to-left)
scripts/backup_offsite.sh   nightly backup of all sites, copied off the server
```

## Rules this code follows

1. ERPNext / Frappe core is never modified: everything is in this app.
2. Standard doctypes first (Sales Order, Delivery Note, Stock Entry, Customer, Supplier, Item); new doctypes only where nothing fits (justified in DECISIONS.md).
3. Per-client differences live in settings and data, never in code branches.
4. Short, plainly commented code, English in code, French for users (English and Arabic available per user: User → Language).
5. Currency DZD, no VAT logic.

License: MIT.
