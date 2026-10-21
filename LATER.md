# Later

Things that are useful but were out of scope, or not possible yet.
Roughly in order of value for a COD seller.

## Next phase candidates

1. ~~Accounting of COD sales~~: **done** (20 October 2026): a Sales Invoice when an order becomes Livrée, one Journal Entry per Versement (DECISIONS.md, "COD accounting"). Still to do: the accountant's answers (accounts, TVA on the delivery fee, stamp duty on cash).
2. **Real courier connectors**: Yalidine is built (October 2026) but **must be checked with a client's real account before use** (checklist in `docs/COURIER_INTEGRATION.md` §4). Still to do for Yalidine: step Y8 (fill a Versement from Yalidine's payments, `payment_status=receivable` / `payment_id`), its return fee and COD percentage in the settlement's expected fee, and a weight from the items when parcels can exceed 5 kg. Then ZR Express, for its new platform only (api.zrexpress.app; ZR is migrating merchants off the old Procolis API): the connector option already exists as "coming soon" and works like Manuel, then Maystro / Ecotrack-based couriers.
3. **Order intake endpoint for n8n**: one whitelisted method that receives an order from Instagram, Facebook or the website, finds or creates the customer by phone, looks up prices, and creates the Sales Order. (ERPNext does not apply the price list on server-side inserts, so this method must do it.)
4. **Commune master list** (1,541 communes, law 26-06) with the courier's own commune codes and stop desk offices per commune. Partly done: Yalidine clients import Yalidine's communes and stop desks (DZ Commune, DZ Stop Desk), kept per connector since October 2026 so a second courier's list can sit next to it. Missing: the master list itself (one commune, each courier's spelling), ZR Express's import, communes on the Customer form, and the 2026 wilayas' own communes when couriers adopt them.
5. ~~Customer phone checks~~: **done** (October 2026): warning on the order when its phone already has refused parcels (threshold in COD Settings), warning with links when a customer is saved with another customer's phone. Never blocking. Possible next step: a red badge on the order form instead of a message.
6. **Rates per courier**, plus return fees (couriers usually charge for a returned parcel) in the settlement expected amount.
7. **Exchanges and returns after delivery** ("échange", customer sends back a delivered item): today Retournée is only reachable from Expédiée.
8. ~~Shipping label~~: **done** (October 2026): print format "Bordereau COD" (100 x 150 mm, Code 128 barcode of the tracking number), button *Bordereau* on confirmed orders. Not yet printed on a real thermal printer: check the size and the barcode scan with the client's printer and the courier's scanner.
9. ~~Dashboard with number cards~~: **done** (October 2026): the COD home page (Accueil) has counters for to confirm, to ship, in transit and money held by couriers, plus two charts. Possible next step: orders today.
10. **Hard stock reservation** (ERPNext Stock Reservation Entries) if overselling the last pieces becomes a problem.
11. ~~Arabic names of wilayas~~: **moved** (20 October 2026) to dafter-core's ROADMAP ("French and Arabic labels"), since the wilaya list is dz_core's. The Arabic interface itself is done (October 2026: `translations/ar.csv`, per user).
12. ~~Webhook template updates~~: **done** (October 2026): `bench migrate` refreshes the template and condition of webhooks nobody edited; URL, Enabled and headers are never touched.
13. **SMS confirmation** of the order to the customer (through n8n).

## Out of scope by request (do not build here)

- Full accounting beyond ERPNext defaults, payroll, POS.
- Manufacturing (BOMs, work orders), sector templates, legal invoices and the
  Excel import: these live in dz_core (repo dafter-core), the base this app
  runs on. Build them there, not here.
- A customer-facing website.
- The n8n workflows themselves (the webhooks and their payloads are ready: `docs/WEBHOOKS.md`).
