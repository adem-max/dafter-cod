"""Fixed data for the demo shop "Encre & Fil" (a FICTIONAL Algerian seller).

Nothing here is a real brand or a real person. Phone numbers are generated
at random by the loader.
"""

COMPANY = "Encre & Fil SARL"
ABBR = "EF"

# Warehouse names (the " - EF" suffix is added by ERPNext)
MAIN_WAREHOUSE = "Stock principal"
WORKSHOP_WAREHOUSE = "Atelier"
RETURNS_WAREHOUSE = "Retours"


CUSTOMER_GROUP = "Particuliers (démo)"
SUPPLIER_GROUP = "Transporteurs"

# Two fictional couriers, both using the offline Mock connector.
# Share of orders each one gets.
COURIERS = {"Rapide Express (démo)": 0.65, "Colis Sahara (démo)": 0.35}
DEFAULT_COURIER = "Rapide Express (démo)"

BRANDS = ["Encre Urbaine", "Fil Doux"]

SIZES = ["S", "M", "L", "XL", "XXL"]
COLOURS = ["Noir", "Blanc", "Gris chiné", "Bleu marine", "Beige", "Bordeaux", "Vert kaki"]

# Item groups (created under the root item group)
TSHIRTS = "T-shirts"
SWEATS = "Sweats et hoodies"
ACCESSORIES = "Accessoires"
RAW = "Textile vierge"

# Products: (code, name, brand, group, selling price DA, cost DA, sizes, colours)
# sizes/colours = None means no variant on that attribute.
PRODUCTS = [
	# Encre Urbaine: printed designs (screen printing in the workshop)
	(
		"EU-TS-CASBAH",
		"T-shirt Casbah",
		"Encre Urbaine",
		TSHIRTS,
		2800,
		1150,
		SIZES,
		["Blanc", "Noir", "Beige"],
	),
	(
		"EU-TS-DJURDJURA",
		"T-shirt Djurdjura",
		"Encre Urbaine",
		TSHIRTS,
		2800,
		1150,
		SIZES,
		["Blanc", "Vert kaki"],
	),
	("EU-TS-TASSILI", "T-shirt Tassili", "Encre Urbaine", TSHIRTS, 2900, 1200, SIZES, ["Beige", "Noir"]),
	(
		"EU-TS-FENNEC",
		"T-shirt Fennec",
		"Encre Urbaine",
		TSHIRTS,
		2600,
		1100,
		SIZES,
		["Blanc", "Gris chiné", "Noir"],
	),
	("EU-TS-HOGGAR", "T-shirt Hoggar", "Encre Urbaine", TSHIRTS, 2900, 1200, SIZES, ["Noir", "Bordeaux"]),
	(
		"EU-TS-BAHDJA",
		"T-shirt El Bahdja",
		"Encre Urbaine",
		TSHIRTS,
		3000,
		1250,
		SIZES,
		["Blanc", "Bleu marine"],
	),
	("EU-TS-MEDINA", "T-shirt Médina", "Encre Urbaine", TSHIRTS, 2700, 1150, SIZES, ["Blanc", "Beige"]),
	("EU-TS-CALLI", "T-shirt Calligraphie", "Encre Urbaine", TSHIRTS, 3200, 1300, SIZES, ["Noir", "Blanc"]),
	(
		"EU-TS-SAHARA",
		"T-shirt Coucher de soleil",
		"Encre Urbaine",
		TSHIRTS,
		2800,
		1150,
		SIZES,
		["Noir", "Beige"],
	),
	("EU-TS-RAI", "T-shirt Raï 90", "Encre Urbaine", TSHIRTS, 2900, 1200, SIZES, ["Blanc", "Noir"]),
	(
		"EU-OV-CASBAH",
		"T-shirt oversize Casbah",
		"Encre Urbaine",
		TSHIRTS,
		3400,
		1450,
		SIZES,
		["Noir", "Beige"],
	),
	(
		"EU-HD-CASBAH",
		"Hoodie Casbah",
		"Encre Urbaine",
		SWEATS,
		6200,
		2900,
		["S", "M", "L", "XL"],
		["Noir", "Gris chiné"],
	),
	(
		"EU-HD-FENNEC",
		"Hoodie Fennec",
		"Encre Urbaine",
		SWEATS,
		5900,
		2800,
		["S", "M", "L", "XL"],
		["Noir", "Bordeaux"],
	),
	(
		"EU-HD-TASSILI",
		"Hoodie Tassili",
		"Encre Urbaine",
		SWEATS,
		6200,
		2900,
		["S", "M", "L", "XL"],
		["Beige", "Vert kaki"],
	),
	(
		"EU-HD-ATLAS",
		"Hoodie Atlas",
		"Encre Urbaine",
		SWEATS,
		6500,
		3000,
		["S", "M", "L", "XL"],
		["Noir", "Bleu marine"],
	),
	(
		"EU-SW-MEDINA",
		"Sweat col rond Médina",
		"Encre Urbaine",
		SWEATS,
		4800,
		2300,
		["S", "M", "L", "XL"],
		["Gris chiné", "Beige"],
	),
	# Fil Doux: plain basics
	(
		"FD-TS-BASIC",
		"T-shirt basique coton",
		"Fil Doux",
		TSHIRTS,
		1600,
		700,
		SIZES,
		["Blanc", "Noir", "Gris chiné", "Bleu marine"],
	),
	(
		"FD-TS-OVERSIZE",
		"T-shirt oversize uni",
		"Fil Doux",
		TSHIRTS,
		2200,
		950,
		SIZES,
		["Noir", "Beige", "Blanc"],
	),
	("FD-TS-COLV", "T-shirt col V", "Fil Doux", TSHIRTS, 1700, 750, SIZES, ["Blanc", "Noir"]),
	(
		"FD-TS-ML",
		"T-shirt manches longues",
		"Fil Doux",
		TSHIRTS,
		2100,
		900,
		SIZES,
		["Noir", "Blanc", "Bordeaux"],
	),
	("FD-POLO", "Polo piqué", "Fil Doux", TSHIRTS, 2500, 1100, SIZES, ["Bleu marine", "Blanc", "Vert kaki"]),
	("FD-DEBARDEUR", "Débardeur", "Fil Doux", TSHIRTS, 1200, 500, ["S", "M", "L", "XL"], ["Blanc", "Noir"]),
	(
		"FD-HD-BASIC",
		"Hoodie basique",
		"Fil Doux",
		SWEATS,
		4300,
		2100,
		["S", "M", "L", "XL"],
		["Noir", "Gris chiné", "Bleu marine"],
	),
	(
		"FD-SW-BASIC",
		"Sweat basique",
		"Fil Doux",
		SWEATS,
		3800,
		1800,
		["S", "M", "L", "XL"],
		["Gris chiné", "Noir"],
	),
	(
		"FD-JOGGING",
		"Jogging molleton",
		"Fil Doux",
		SWEATS,
		3500,
		1700,
		["S", "M", "L", "XL"],
		["Noir", "Gris chiné"],
	),
	# Accessories (both brands)
	("EU-CASQ", "Casquette brodée Fennec", "Encre Urbaine", ACCESSORIES, 1800, 650, None, ["Noir", "Beige"]),
	("EU-BOB", "Bob imprimé Casbah", "Encre Urbaine", ACCESSORIES, 1600, 600, None, ["Noir", "Beige"]),
	("EU-TOTE", "Tote bag imprimé Médina", "Encre Urbaine", ACCESSORIES, 1200, 400, None, None),
	(
		"FD-BONNET",
		"Bonnet côtelé",
		"Fil Doux",
		ACCESSORIES,
		1300,
		450,
		None,
		["Noir", "Bordeaux", "Gris chiné"],
	),
	("FD-CHAUSSETTES", "Chaussettes (lot de 3)", "Fil Doux", ACCESSORIES, 900, 350, None, None),
]

# Blank t-shirts waiting in the workshop (not sold online, shows the workshop stock)
BLANKS = [("BLANK-TS", "T-shirt vierge 180 g", RAW, 550, SIZES, ["Blanc", "Noir"])]

# Wilayas used for demo customers, with some real communes and a weight
# (bigger cities get more orders).
WILAYA_COMMUNES = {
	"16": (
		20,
		[
			"Bab Ezzouar",
			"Kouba",
			"Hussein Dey",
			"Bir Mourad Raïs",
			"Chéraga",
			"Bab El Oued",
			"Dar El Beïda",
			"Rouïba",
		],
	),
	"31": (10, ["Oran", "Bir El Djir", "Es Senia", "Arzew", "Aïn El Turck"]),
	"25": (8, ["Constantine", "El Khroub", "Aïn Smara", "Hamma Bouziane"]),
	"19": (7, ["Sétif", "El Eulma", "Aïn Oulmene", "Aïn Arnat"]),
	"09": (7, ["Blida", "Boufarik", "Ouled Yaïch", "Larbaâ"]),
	"15": (5, ["Tizi Ouzou", "Azazga", "Draâ Ben Khedda", "Tigzirt"]),
	"06": (5, ["Béjaïa", "Akbou", "El Kseur", "Amizour"]),
	"23": (5, ["Annaba", "El Bouni", "El Hadjar", "Sidi Amar"]),
	"05": (4, ["Batna", "Arris", "Merouana", "Aïn Touta"]),
	"35": (4, ["Boumerdès", "Boudouaou", "Bordj Menaïel", "Dellys"]),
	"42": (3, ["Tipaza", "Koléa", "Cherchell", "Fouka"]),
	"13": (3, ["Tlemcen", "Maghnia", "Remchi", "Mansourah"]),
	"02": (3, ["Chlef", "Ténès", "Oued Fodda"]),
	"17": (2, ["Djelfa", "Hassi Bahbah", "Charef"]),
	"07": (2, ["Biskra", "Tolga", "Sidi Okba"]),
	"34": (2, ["Bordj Bou Arréridj", "Ras El Oued", "Medjana"]),
	"18": (2, ["Jijel", "Taher", "El Milia"]),
	"21": (2, ["Skikda", "Azzaba", "Collo"]),
	"27": (2, ["Mostaganem", "Hassi Mamèche", "Aïn Tédelès"]),
	"10": (2, ["Bouira", "Lakhdaria", "Sour El Ghozlane"]),
	"22": (2, ["Sidi Bel Abbès", "Telagh", "Sfisef"]),
	"30": (2, ["Ouargla", "Hassi Messaoud", "N'Goussa"]),
	"47": (1, ["Ghardaïa", "Métlili", "Berriane"]),
	"39": (1, ["El Oued", "Guemar", "Debila"]),
	"68": (1, ["Bou Saâda"]),
	"60": (1, ["Barika"]),
	"11": (1, ["Tamanrasset"]),
}

FIRST_NAMES = [
	"Mohamed",
	"Amine",
	"Yacine",
	"Karim",
	"Sofiane",
	"Walid",
	"Bilal",
	"Rayan",
	"Nassim",
	"Islam",
	"Abdelkader",
	"Mehdi",
	"Riad",
	"Hichem",
	"Anis",
	"Oussama",
	"Ayoub",
	"Zakaria",
	"Fares",
	"Lyes",
	"Amina",
	"Sarah",
	"Meriem",
	"Yasmine",
	"Lina",
	"Imane",
	"Nour",
	"Khadidja",
	"Rania",
	"Asma",
	"Lydia",
	"Kenza",
	"Selma",
	"Nesrine",
	"Chaïma",
	"Wissam",
	"Mélissa",
	"Ikram",
	"Houda",
	"Feriel",
]

LAST_NAMES = [
	"Benali",
	"Bouzid",
	"Belkacem",
	"Haddad",
	"Mansouri",
	"Cherif",
	"Saïdi",
	"Kaci",
	"Aït Ahmed",
	"Hamidi",
	"Meziane",
	"Brahimi",
	"Zerrouki",
	"Khelifi",
	"Bensalem",
	"Djebbar",
	"Lounis",
	"Ouali",
	"Messaoudi",
	"Rahmani",
	"Taleb",
	"Bouchama",
	"Ferhat",
	"Amrani",
	"Boukhalfa",
	"Chikhi",
	"Hadj Ali",
	"Benyahia",
	"Slimani",
	"Mebarki",
	"Guerfi",
	"Larbi",
	"Touati",
	"Belhadj",
	"Hamdi",
]

STREETS = [
	"Cité 500 logements, bât. {n}",
	"Rue des frères {name}, n° {n}",
	"Cité AADL, bloc {n}",
	"Lotissement El Nour, villa {n}",
	"Boulevard du 1er Novembre, n° {n}",
	"Cité 20 Août, immeuble {n}",
	"Rue Didouche Mourad, n° {n}",
	"Quartier El Amel, n° {n}",
]

# Where orders come from, with weights
SOURCES = {"Instagram": 45, "Facebook": 30, "Site web": 12, "WhatsApp": 8, "TikTok": 5}
