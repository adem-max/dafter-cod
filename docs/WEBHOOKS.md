# Webhooks for n8n

When an order reaches one of four key states, ERPNext can send its details
to a URL (your n8n workflow) as JSON. This uses ERPNext's built-in
**Webhook** feature; dz_cod only creates four ready-made webhooks.

| Webhook name        | Sent when the order becomes | Typical n8n use                                  |
|---------------------|-----------------------------|--------------------------------------------------|
| `COD - Confirmée`   | Confirmée                   | WhatsApp/SMS "your order is confirmed"           |
| `COD - Expédiée`    | Expédiée                    | send the tracking number to the customer         |
| `COD - Livrée`      | Livrée                      | thank-you message, ask for a review              |
| `COD - Retournée`   | Retournée                   | alert the seller, flag the customer              |

Each webhook fires **once per move** (not every time someone edits the order),
**after** the change is saved in the database, in a **background job**. If
n8n is down, the order still moves; the failed call is visible in
**Webhook Request Log**.

## Turning them on

They are created **disabled**, pointing to `https://n8n.example.com/webhook/dz-cod`.

1. In n8n, create a workflow starting with a **Webhook** node, method `POST`.
   Copy its *Production URL*.
2. In ERPNext, open **Webhook** (search bar → "Webhook"), open `COD - Confirmée`.
3. Paste the n8n URL into **Request URL**, tick **Enabled**, save.
4. Repeat for the other three (they can all use the same URL: the `event`
   field tells n8n which state it is).
5. Optional but recommended: tick **Enable Security** and set a **Webhook
   Secret**. ERPNext then signs each call (header `X-Frappe-Webhook-Signature`,
   HMAC-SHA256 of the body, base64) so n8n can check the call really comes
   from your ERPNext.

`bench migrate` never touches your URL, the Enabled tick or the headers.
When a new version of dz_cod changes the JSON template or the condition, it
refreshes them on each site, but only if nobody edited them there (it keeps a
fingerprint of what it last wrote). A template edited by hand is left alone,
with a note in the Error Log saying the new version was not applied.

> **Background workers must be running** (they are in production, through
> supervisor). Webhooks are sent by a worker. If no worker runs, jobs pile up
> and after ~500 queued jobs Frappe refuses to queue new ones (error "Too many
> queued background jobs").

## Payload

Real example captured during testing (demo data; phone replaced):

```json
{
  "event": "Expédiée",
  "order": "SAL-ORD-2026-00148",
  "order_date": "2026-10-09",
  "customer": "Amine Mebarki",
  "customer_name": "Amine Mebarki",
  "phone": "0555000000",
  "phone_2": "",
  "wilaya": "31 - Oran",
  "commune": "Arzew",
  "address": "Cité AADL, bloc 66, Arzew",
  "delivery_type": "Stop desk",
  "source": "Instagram",
  "shipping_charge": 400.0,
  "cod_amount": 6900.0,
  "courier": "Rapide Express (démo)",
  "tracking_number": "MOCK-SAL-ORD-2026-00148",
  "call_attempts": 0,
  "items": [
    {
      "item_code": "EU-HD-ATLAS-M-BLE",
      "item_name": "Hoodie Atlas Bleu marine M",
      "qty": 1.0,
      "rate": 6500.0
    }
  ]
}
```

The four events send the same fields. Differences you will see:

- `Confirmée`: `tracking_number` is usually empty (not shipped yet).
- `Expédiée`, `Livrée`, `Retournée`: `tracking_number` is filled.
- `event` holds the state name in French, with accents (`"Confirmée"`,
  `"Expédiée"`, `"Livrée"`, `"Retournée"`). In n8n, use a **Switch** node on
  `{{$json.body.event}}`.
- Amounts are numbers in DZD. `cod_amount` = articles + delivery fee = what the
  courier collects.

## Changing the payload

Open the webhook, section **Webhook Data**, field **JSON Request Body**. It is
a Jinja template where `doc` is the Sales Order. Add a field like this:

```
  "customer_group": "{{ doc.customer_group }}",
```

Two traps:

- Text that may contain quotes or accents: use `{{ doc.field | tojson }}`
  (it adds the quotes and escapes everything), not `"{{ doc.field }}"`.
- The order lines: write `doc["items"]`, **not** `doc.items`. In the template
  `doc` is a dictionary and `doc.items` is the dictionary's own `items`
  method: the webhook fails with "'builtin_function_or_method' object is not
  iterable".

The original template is in `dz_cod/setup/webhooks.py` (`PAYLOAD`). To go
back to it, delete the webhook and run `bench --site <site> migrate`: it is
re-created (disabled).

## Testing without n8n

On the server:

```bash
# 1. a tiny listener on port 9999 that prints what it receives
python3 -c "
import http.server
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        print(self.rfile.read(int(self.headers['Content-Length'])).decode()); self.send_response(200); self.end_headers()
http.server.HTTPServer(('127.0.0.1', 9999), H).serve_forever()"
```

2. Point one webhook to `http://127.0.0.1:9999/`, enable it.
3. Move an order to that state. Within a few seconds the JSON is printed.
4. Put the real URL back.
