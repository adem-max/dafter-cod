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

Only you, from the hub (dz_hub: tick the options on the client, then
*Appliquer au site*) or with the command below. The list is in the client
site's `site_config.json`, key `dz_features` (sites made before 19 October
2026 had `dz_cod_features`; migrate moves it). Clients cannot edit it from
the screen (they are not System Manager and have no server access).

- Key missing: **everything is on** (demo, test, and sites made before the
  switches).
- A list, even empty: exactly that list.

## The command

```bash
bench --site client1.localhost dz-features --list                 # show
bench --site client1.localhost dz-features --enable phone_checks  # add one (repeatable)
bench --site client1.localhost dz-features --disable labels_reports
bench --site client1.localhost dz-features --set courier_api,phone_checks   # exact list
bench --site client1.localhost dz-features --set ""               # base only
bench --site client1.localhost dz-features --all                  # everything (removes the key)
bench --site client1.localhost dz-features --json                 # for scripts and the hub
```

`dz-cod-features` is the old name and still works.

A new client gets their list when the site is prepared:
`new_client.prepare(..., features=['courier_api', 'labels_reports'])`
(no list = base only).

Users see the change after reloading the page (running servers pick up a new
`site_config.json` within about a minute).

## How it works (for developers)

- The mechanism is dz_core's (`dz_core/features.py`, dafter-core): the
  site's list, `is_enabled()`, `check()`, `@requires_feature(...)` for
  whitelisted methods, `apply_features()`, the `dz-features` command and
  `frappe.boot.dz_features` (hook `extend_bootinfo`).
- This app declares its features in `dz_cod/features.py` (`FEATURES`) and
  points dz_core at them from hooks.py: `dz_features = ["dz_cod.features.FEATURES"]`.
  `dz_cod.features` re-exports `is_enabled` & co., so COD code imports from
  one place.
- `apply_features()` sets `disabled` on each feature's reports and print
  formats (Frappe then drops them from the sidebar, the workspace and the
  print menu, and refuses them by URL) and calls a feature's `on_change`
  (here: the n8n webhooks). It runs after every `bench migrate`, because
  migrate re-imports our standard reports and print formats and would
  switch them back on.
- Administrator still sees dead links to disabled reports in the sidebar
  (Frappe shows everything to Administrator); client users don't.
- Adding a feature: add it to `FEATURES` (label, description, reports, print
  formats, optional `on_change`), guard its server code with `is_enabled` /
  `@requires_feature`, hide its buttons with `frappe.boot.dz_features`, add
  tests in `dz_cod/tests/test_features.py`, and add a line to the table
  above. The hub picks it up as a new option on its next migrate.
