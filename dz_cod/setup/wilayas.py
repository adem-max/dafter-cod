"""Example delivery rates per wilaya, by zone.

The list of wilayas itself lives in dz_core (dz_core/setup/wilayas.py, doctype
DZ Wilaya); this app adds the rate fields to it (setup/custom_fields.py) and
fills them once per wilaya with the example rates of its zone.

The rates below are EXAMPLES grouped by zone. Replace them with the real rate
card of each client's courier (Wilaya list -> edit the 4 rate columns).
"""

import frappe
from dz_core.setup.wilayas import WILAYAS, wilaya_docname

# Example rates in DZD per zone: (home delivery, stop desk)
ZONE_RATES = {
	1: (400, 250),  # Alger
	2: (550, 350),  # Around Alger
	3: (650, 400),  # Rest of the north
	4: (750, 450),  # High plateaus
	5: (950, 600),  # South
	6: (1400, 900),  # Far south
}

# Rate zone of each wilaya, by code
ZONES = {
	"01": 5,  # Adrar
	"02": 3,  # Chlef
	"03": 4,  # Laghouat
	"04": 3,  # Oum El Bouaghi
	"05": 4,  # Batna
	"06": 3,  # Béjaïa
	"07": 4,  # Biskra
	"08": 5,  # Béchar
	"09": 2,  # Blida
	"10": 3,  # Bouira
	"11": 6,  # Tamanrasset
	"12": 4,  # Tébessa
	"13": 3,  # Tlemcen
	"14": 4,  # Tiaret
	"15": 3,  # Tizi Ouzou
	"16": 1,  # Alger
	"17": 4,  # Djelfa
	"18": 3,  # Jijel
	"19": 3,  # Sétif
	"20": 4,  # Saïda
	"21": 3,  # Skikda
	"22": 3,  # Sidi Bel Abbès
	"23": 3,  # Annaba
	"24": 3,  # Guelma
	"25": 3,  # Constantine
	"26": 3,  # Médéa
	"27": 3,  # Mostaganem
	"28": 4,  # M'Sila
	"29": 3,  # Mascara
	"30": 5,  # Ouargla
	"31": 3,  # Oran
	"32": 4,  # El Bayadh
	"33": 6,  # Illizi
	"34": 3,  # Bordj Bou Arréridj
	"35": 2,  # Boumerdès
	"36": 3,  # El Tarf
	"37": 6,  # Tindouf
	"38": 3,  # Tissemsilt
	"39": 5,  # El Oued
	"40": 4,  # Khenchela
	"41": 3,  # Souk Ahras
	"42": 2,  # Tipaza
	"43": 3,  # Mila
	"44": 3,  # Aïn Defla
	"45": 4,  # Naâma
	"46": 3,  # Aïn Témouchent
	"47": 5,  # Ghardaïa
	"48": 3,  # Relizane
	"49": 5,  # Timimoun
	"50": 6,  # Bordj Badji Mokhtar
	"51": 4,  # Ouled Djellal
	"52": 5,  # Béni Abbès
	"53": 6,  # In Salah
	"54": 6,  # In Guezzam
	"55": 5,  # Touggourt
	"56": 6,  # Djanet
	"57": 5,  # El M'Ghair
	"58": 5,  # El Meniaa
	"59": 4,  # Aflou
	"60": 4,  # Barika
	"61": 4,  # El Kantara
	"62": 4,  # Bir El Ater
	"63": 4,  # El Aricha
	"64": 4,  # Ksar Chellala
	"65": 4,  # Aïn Ouessara
	"66": 4,  # Messaad
	"67": 3,  # Ksar El Boukhari
	"68": 4,  # Bou Saâda
	"69": 4,  # El Abiodh Sidi Cheikh
}


def setup_wilaya_rates():
	"""Give each wilaya its zone and the example rates of that zone, once: a
	wilaya that already has a zone is left alone (its rates are the client's)."""
	for code, name, _parent in WILAYAS:
		docname = wilaya_docname(code, name)
		if not frappe.db.exists("DZ Wilaya", docname) or frappe.db.get_value("DZ Wilaya", docname, "zone"):
			continue
		zone = ZONES[code]
		home, stopdesk = ZONE_RATES[zone]
		frappe.db.set_value(
			"DZ Wilaya",
			docname,
			{
				"zone": zone,
				"enabled": 1,
				"stopdesk_available": 1,
				"home_rate": home,
				"stopdesk_rate": stopdesk,
				# By default we charge the customer what the courier charges us
				"home_courier_cost": home,
				"stopdesk_courier_cost": stopdesk,
			},
		)
