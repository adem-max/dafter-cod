# Later

Things that are useful but were out of scope, or not possible yet.
Roughly in order of value for a COD seller.

## Next phase candidates

1. **Accounting of COD sales.** Create and submit a Sales Invoice when an order becomes "Livrée", and record the courier payout ("Réglée") as a Journal Entry: debit bank, debit "courier fees" expense, credit each customer's receivable against its invoice. Today revenue is not in the general ledger and delivered orders stay "To Bill".
2. **Real courier connectors**: Yalidine first (API known, plan ready), then ZR Express (get its official docs first), then Maystro / Ecotrack-based couriers. Step-by-step plan: `docs/COURIER_INTEGRATION.md`. Includes importing Yalidine's own prices into the wilaya list and its return fee / COD percentage in the settlement.
3. **Order intake endpoint for n8n**: one whitelisted method that receives an order from Instagram, Facebook or the website, finds or creates the customer by phone, looks up prices, and creates the Sales Order. (ERPNext does not apply the price list on server-side inserts, so this method must do it.)
4. **Commune master list** (1,541 communes, law 26-06) with the courier's own commune codes and stop desk offices per commune.
5. **Customer phone checks**: warn when a new order's phone belongs to a customer with several refused parcels (blacklist), and detect duplicate customers by phone.
6. **Rates per courier**, plus return fees (couriers usually charge for a returned parcel) in the settlement expected amount.
7. **Exchanges and returns after delivery** ("échange", customer sends back a delivered item): today Retournée is only reachable from Expédiée.
8. **Shipping label / bordereau print format** with barcode of the tracking number.
9. **Dashboard with number cards** (orders today, to confirm, to ship, cash outstanding).
10. **Hard stock reservation** (ERPNext Stock Reservation Entries) if overselling the last pieces becomes a problem.
11. **Arabic names of wilayas and an Arabic interface option.**
12. **A patch to update the webhook templates** on existing client sites when the template changes (today setup never overwrites a webhook).
13. **SMS confirmation** of the order to the customer (through n8n).

## Out of scope by request (do not build here)

- Manufacturing for the print workshop (BOM: blank t-shirt + ink → printed t-shirt, work orders). ERPNext's Manufacturing module is installed and untouched; when needed, start with a BOM per printed design and "Manufacture" stock entries from the Atelier warehouse to Stock principal, before considering work orders.
- Full accounting beyond ERPNext defaults, payroll, POS.
- A customer-facing website.
- The n8n workflows themselves (the webhooks and their payloads are ready: `docs/WEBHOOKS.md`).
