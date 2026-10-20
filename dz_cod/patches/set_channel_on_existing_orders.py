"""Orders made before the sales channel (October 2026) were all COD orders:
give them the COD channel, so the COD counters and reports keep them.

The channel is a custom field, which a migrate makes after the patches
(setup/install.py): this patch makes the custom fields first."""

import frappe

from dz_cod.cod.channel import COD
from dz_cod.setup.custom_fields import setup_custom_fields


def execute():
	setup_custom_fields()
	frappe.db.sql("UPDATE `tabSales Order` SET dz_channel = %s WHERE IFNULL(dz_channel, '') = ''", COD)
