# The demo shop

A fictional Algerian clothing seller, **Encre & Fil SARL**, with 60 days of
cash-on-delivery history. Use it to practise, to test changes and to show
prospects what they get.

**Always on a dedicated demo site, never on a client site.** The loader
refuses to run on a site that contains another company's orders.

## What is in it

| What | How much |
|------|----------|
| Company | Encre & Fil SARL (abbreviation EF), DZD, Algeria, Algerian chart of accounts, French interface |
| Warehouses | Stock principal - EF, Atelier - EF (blank t-shirts), Retours - EF |
| Brands | Encre Urbaine (printed designs), Fil Doux (plain basics) |
| Products | 30 (t-shirts, hoodies, sweats, joggings, accessories), about 260 size/colour variants, priced 900 to 6,500 DA |
| Customers | 80, spread over 27 wilayas (more in Alger, Oran, Constantine...), with commune, address and phone |
| Couriers | Rapide Express (démo) and Colis Sahara (démo), both on the offline **Mock** connector |
| Orders | 200 over the last 60 days, in every state: Nouvelle, Injoignable, Confirmée, Préparée, Expédiée, Livrée, Réglée, Retournée, Annulée, Annulée après confirmation |
| Returns | about 20 % of shipped parcels (configurable), inspected: most pieces back in stock, some written off |
| Settlements | one Versement per courier per week, with a few short payments (disputes) and forgotten parcels |

Orders come mostly from Instagram and Facebook, are usually one piece, and
about 1 in 20 is a bulk order (3 sizes × 5–10 pieces).

## Create the demo site (first time)

```bash
cd ~/frappe-bench
bench new-site demo.localhost --install-app erpnext      # asks for the MariaDB root password, then an admin password
bench --site demo.localhost install-app dz_cod
bench --site demo.localhost execute dz_cod.demo.loader.load
bench use demo.localhost                                  # the development server will show this site
bench start
```

The loader takes 2 to 5 minutes and ends with a count of orders per state.
Then open `http://demo.localhost:8000` and log in as `Administrator`.
On a laptop, `bench start` shows only the site chosen with `bench use`
(see docs/LOCAL_TEST.md, section 5).

## Change the return rate

```bash
bench --site demo.localhost execute dz_cod.demo.loader.load --kwargs "{'return_rate': 0.35}"
```

The rate only applies to orders created by that run. To apply a new rate to
all orders, wipe first (below).

## Run it twice?

Safe. Everything already there is skipped. Run it again a few days later and
it continues the story: recent orders move forward (confirmed, shipped,
delivered...) as their planned dates are reached.

## Wipe and reload

Option 1 — keep the site, delete the demo data (about 1 minute):

```bash
bench --site demo.localhost execute dz_cod.demo.wipe.run
bench --site demo.localhost execute dz_cod.demo.loader.load
```

Keep `bench start` running in another terminal while you do this: the wipe
and the loader queue about 1,000 background clean-up jobs, and the workers
started by `bench start` process them. Without workers the queue fills up
and Frappe refuses new jobs ("Too many queued background jobs"); fix it with
`bench worker --queue default,short,long --burst`.

It cancels and deletes settlements, stock entries, delivery notes and orders,
then the demo customers, couriers and items. The company, warehouses,
accounts and COD Settings stay (the loader reuses them).

Option 2 — total reset (cleanest, 5 minutes):

```bash
bench drop-site demo.localhost --force          # deletes the database and the site folder
bench new-site demo.localhost --install-app erpnext
bench --site demo.localhost install-app dz_cod
bench --site demo.localhost execute dz_cod.demo.loader.load
```

## A 10-minute demo script for a prospect

1. **Commandes** list: colours per state, filter "Wilaya = 16 - Alger".
2. Open a **Nouvelle** order: show phone, wilaya, delivery type, delivery fee
   added automatically. Change *Domicile* to *Stop desk*, save: the fee drops.
3. **Actions → Pas de réponse** twice: the call counter goes up. Then
   **Actions → Confirmer**: stock is reserved.
4. **Préparer**, then **Expédier**: the dialog asks for the courier; the Mock
   courier gives a tracking number and a delivery note is created.
5. **Rapports → Encours transporteurs**: how much cash each courier owes.
6. **Versements → new**: courier "Rapide Express (démo)", button *Charger les
   commandes livrées*, change one amount (−500), save: OK / Écart lines and
   the paid / disputed / missing summary. Submit.
7. **Rapports → Taux de retour**, group by *Wilaya* then by *Produit*.
8. Open a **Retournée** order: *Inspecter le retour*.

## Where the code is

- `dz_cod/demo/data.py`: the catalogue, names, communes (edit to change the shop)
- `dz_cod/demo/loader.py`: the loader, step by step
- `dz_cod/demo/wipe.py`: the wipe
