# Deployment: what COD adds

The server itself (Ubuntu, MariaDB, bench, nginx, SSL, backups, restore,
updates, security) is the same for every client and is in **dafter-core's
docs/DEPLOY.md**. Follow it first, up to and including section 12. This file
only adds what an online seller's site needs on top.

(Until October 2026 this file held the whole server guide; it moved to
dafter-core with the backup scripts.)

Status: install, `prepare`, the demo and the tests were run for real
(Ubuntu 24.04, Python 3.14, MariaDB 10.11). Production mode was not: see the
status note in dafter-core's guide.

## 1. Get the app

Next to dz_core on the bench (dafter-core DEPLOY.md, section 5):

```bash
cd ~/frappe-bench
bench get-app https://github.com/adem-max/dafter-cod    # folder apps/dz_cod
```

## 2. A site for an online seller

Same as dafter-core DEPLOY.md section 7, but install dz_cod instead of
dz_core: it declares `required_apps = ["erpnext", "dz_core"]`, so dz_core is
installed first.

```bash
bench --site erp.client1.com install-app dz_cod     # dz_core first (legal fields, 69 wilayas), then COD: fields, workflow, wilaya rates, webhooks
```

## 3. New client in under 2 hours

**Shortcut:** the wizard, sector, warehouses, tax regime, delivery-fee
account, COD Settings and courier are one command. It runs dz_core's
`prepare` first, then the COD part:

```bash
bench --site erp.client1.com execute dz_cod.setup.new_client.prepare \
  --kwargs "{'company': 'Client One', 'abbr': 'C1', 'courier': 'Yalidine', 'features': ['courier_api', 'labels_reports'], 'sector': 'Confection', 'tax_regime': 'IFU'}"
bench --site erp.client1.com dz-cod-features --list     # check what the client gets
```

`features` is the client's list of optional features (docs/FEATURES.md); leave
it out for the base only. Change it later with `dz-cod-features`.
`sector` is `Confection` or `Alimentaire et cosmétique`; `tax_regime` is `IFU`
(no TVA on orders, the usual case) or `Régime réel` (19 % by default).

| Time | Step |
|------|------|
| 0:00 | Client sends: company name, logo, domain, list of products with prices and stock, courier(s) and their rate card, users (names, emails, roles). |
| 0:10 | DNS, site, SSL (dafter-core DEPLOY.md section 7), with `install-app dz_cod` (section 2 above). |
| 0:25 | `prepare` (above). dz_core part: setup wizard, sector template, warehouses **Matières premières**, **Travaux en cours**, **Produits finis**, tax regime (IFU: no default TVA template, so orders carry no VAT). COD part: **Retours** warehouse, **Frais de livraison facturés** account, **Paramètres COD** (orders leave from Produits finis), the courier, the features, COD as the home page. |
| 0:35 | **Paramètres COD**: check max calls (3), stock blocking (on/off), tolerance. |
| 0:40 | Courier: Supplier → the courier made by `prepare`, *Connecteur* = Manuel (or Yalidine with the client's API keys, docs/COURIER_INTEGRATION.md §4). |
| 0:50 | **Wilayas et tarifs**: list view → edit *Tarif domicile*, *Tarif stop desk* and the courier costs from the client's rate card; untick *Livrable* where the courier does not go. (Report view allows editing many rows quickly.) |
| 1:05 | Products and opening stock: dz_core's import workbook (dafter-core README), into Produits finis. |
| 1:35 | Users: one per person, roles Sales User / Stock User / Accounts User; language Français (or English or Arabic: the whole COD app follows). |
| 1:45 | Webhooks: if the client uses n8n, paste the URLs and enable (docs/WEBHOOKS.md). |
| 1:50 | Smoke test with the client: one order Nouvelle → Confirmer → Préparer → Expédier → Marquer livrée, then cancel/delete it. Check the delivery note and stock. |
| 1:55 | Backups are automatic (every site); the restore drill also compares orders and Versements on a COD site. Note the admin password in your password manager. |

## 4. Updates

`bench update` pulls every app (dafter-core DEPLOY.md section 11). Only
dz_cod changed:

```bash
cd ~/frappe-bench/apps/dz_cod && git pull && cd ~/frappe-bench   # get the new code
bench --site all migrate                                         # update doctypes, fields, workflow on every site
bench build --app dz_cod                                         # rebuild JavaScript if it changed
sudo supervisorctl restart all                                   # restart web and workers
```

If a dz_cod change needs a newer dz_core, pull dz_core first.

## 5. Security, on top of dafter-core's checklist

- [ ] Courier API tokens are stored in the Supplier's *API Token* field (encrypted), never in code.
- [ ] Webhook secrets set when the n8n webhooks are enabled.
- [ ] Client users have Sales User / Stock User / Accounts User only: never System Manager (they could change their features).

## 6. When something goes wrong (COD)

In the browser: **Webhook Request Log** lists every webhook call to n8n and
its answer, **Courier Webhook Event** the events Yalidine pushed, **Scheduled
Job Log** the hourly courier sync. The general commands are in dafter-core
DEPLOY.md section 14.
