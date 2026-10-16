# What each client gets: optional features

Every client has the **base**: orders and their life cycle (Nouvelle →
Réglée), stock and returns, Versements, the *Encours transporteurs* report,
wilaya rates, couriers typed by hand (*Manuel*), the COD home page, counters
and charts.

On top of it, each client gets a hand-picked list of **optional features**
(à la carte, decided October 2026):

| Feature | What the client gets | When it is off |
|---|---|---|
| `courier_api` | Courier connectors (Yalidine; ZR Express when built): parcel created on *Expédier*, courier label, price / commune / stop-desk imports, Yalidine webhooks, hourly status sync | Only *Manuel* in *Connecteur*; a courier already set to Yalidine works as Manuel; imports refused; webhook URL answers 403; no sync |
| `phone_checks` | Warnings for phones with refused parcels and for customers in double | No warnings (phones are still cleaned up) |
| `n8n_webhooks` | The 4 webhooks to n8n (Confirmée, Expédiée, Livrée, Retournée); later the order intake and SMS | The 4 webhooks are switched off and cannot be switched on; their URL is kept and they come back as they were when the feature returns |
| `labels_reports` | *Bordereau COD* label (button *Bordereau*), reports *Commandes par jour* and *Taux de retour* | Button, label and both reports are gone from menus and refused if opened by URL |

A feature that is off is **hidden**, and the server refuses its actions with
"Fonction non incluse dans votre offre".

## Who decides, and where it is stored

Only you. The list is in the client site's `site_config.json`, key
`dz_cod_features`. Clients cannot edit it from the screen (they are not
System Manager and have no server access).

- Key missing: **everything is on** (demo, test, and sites made before the
  switches).
- A list, even empty: exactly that list.

## The command

```bash
bench --site client1.localhost dz-cod-features --list                 # show
bench --site client1.localhost dz-cod-features --enable phone_checks  # add one (repeatable)
bench --site client1.localhost dz-cod-features --disable labels_reports
bench --site client1.localhost dz-cod-features --set courier_api,phone_checks   # exact list
bench --site client1.localhost dz-cod-features --set ""               # base only
bench --site client1.localhost dz-cod-features --all                  # everything (removes the key)
bench --site client1.localhost dz-cod-features --json                 # for scripts and the hub
```

A new client gets their list when the site is prepared:
`new_client.prepare(..., features=['courier_api', 'labels_reports'])`
(no list = base only).

Users see the change after reloading the page (running servers pick up a new
`site_config.json` within about a minute).

## How it works (for developers)

- `dz_cod/features.py`: the list of features, `is_enabled()`, `check()`,
  `@requires_feature(...)` for whitelisted methods, and `apply_features()`.
- `apply_features()` sets `disabled` on the feature's reports and print
  formats (Frappe then drops them from the sidebar, the workspace and the
  print menu, and refuses them by URL) and switches the COD webhooks. It runs
  after every `bench migrate`, because migrate re-imports our standard reports
  and print formats and would switch them back on.
- The browser reads `frappe.boot.dz_cod_features` (hook `extend_bootinfo`) to
  hide buttons and settings.
- Administrator still sees dead links to disabled reports in the sidebar
  (Frappe shows everything to Administrator); client users don't.
- Adding a feature: add it to `FEATURES`, guard its server code with
  `is_enabled` / `@requires_feature`, hide its buttons with
  `frappe.boot.dz_cod_features`, list its reports and print formats in
  `FEATURES`, add tests in `dz_cod/tests/test_features.py`, and add a line to
  the table above.
