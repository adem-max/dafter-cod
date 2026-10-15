"""ZR Express connector: COMING SOON.

ZR Express is moving its merchants from the old "Procolis" API
(procolis.com/api_v1) to a new platform (api.zrexpress.app). Building the old
API now would be thrown away, and the new one has no official docs yet, so the
real connector waits (docs/COURIER_INTEGRATION.md, section 5).

Until then a ZR Express courier works like "Manuel": the operator types the
tracking number and moves orders to Livrée / Retournée by hand. Choosing
"ZR Express" now means the courier is already set up when the connector
arrives: only this class changes.
"""

from dz_cod.couriers.base import ManualAdapter


class ZRExpressAdapter(ManualAdapter):
	label = "ZR Express"
	coming_soon = True
