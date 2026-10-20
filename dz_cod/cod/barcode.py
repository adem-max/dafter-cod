"""Code 128 barcodes as SVG, for the shipping label (print format "Bordereau COD").

Pure Python, no extra package to install on the server. Code set B covers
every printable ASCII character, which is all a tracking number uses.
Usage in a print format (Jinja): {{ code128_svg(doc.dz_tracking_number) }}

The bar patterns below come from python-barcode
(https://github.com/WhyNotHugo/python-barcode, MIT licence), values 0 to 105.
Each pattern is 11 modules: 1 = bar, 0 = space.
"""

from html import escape

# The table stays 6 patterns a line (ruff would put one per line)
# fmt: off
PATTERNS = (
	"11011001100", "11001101100", "11001100110", "10010011000", "10010001100", "10001001100",
	"10011001000", "10011000100", "10001100100", "11001001000", "11001000100", "11000100100",
	"10110011100", "10011011100", "10011001110", "10111001100", "10011101100", "10011100110",
	"11001110010", "11001011100", "11001001110", "11011100100", "11001110100", "11101101110",
	"11101001100", "11100101100", "11100100110", "11101100100", "11100110100", "11100110010",
	"11011011000", "11011000110", "11000110110", "10100011000", "10001011000", "10001000110",
	"10110001000", "10001101000", "10001100010", "11010001000", "11000101000", "11000100010",
	"10110111000", "10110001110", "10001101110", "10111011000", "10111000110", "10001110110",
	"11101110110", "11010001110", "11000101110", "11011101000", "11011100010", "11011101110",
	"11101011000", "11101000110", "11100010110", "11101101000", "11101100010", "11100011010",
	"11101111010", "11001000010", "11110001010", "10100110000", "10100001100", "10010110000",
	"10010000110", "10000101100", "10000100110", "10110010000", "10110000100", "10011010000",
	"10011000010", "10000110100", "10000110010", "11000010010", "11001010000", "11110111010",
	"11000010100", "10001111010", "10100111100", "10010111100", "10010011110", "10111100100",
	"10011110100", "10011110010", "11110100100", "11110010100", "11110010010", "11011011110",
	"11011110110", "11110110110", "10101111000", "10100011110", "10001011110", "10111101000",
	"10111100010", "11110101000", "11110100010", "10111011110", "10111101110", "11101011110",
	"11110101110", "11010000100", "11010010000", "11010011100",
)
# fmt: on
START_B = 104
STOP = "1100011101011"  # stop pattern (11 modules) + final 2-module bar


def code128_modules(text):
	"""The 1/0 module string of `text` in code set B, with its checksum."""
	values = []
	for char in text:
		value = ord(char) - 32
		if not 0 <= value <= 95:
			raise ValueError(f"Code 128 B cannot encode {char!r}")
		values.append(value)
	checksum = (START_B + sum(position * value for position, value in enumerate(values, 1))) % 103
	return PATTERNS[START_B] + "".join(PATTERNS[v] for v in values) + PATTERNS[checksum] + STOP


def code128_svg(text, height=60, module=2, show_text=True):
	"""An inline SVG barcode of `text` (empty string if there is no text).

	`module` is the width of the thinnest bar in pixels; 10 modules of quiet
	zone are kept on each side so scanners find the start.
	"""
	if not text:
		return ""
	text = str(text).strip()
	modules = code128_modules(text)
	quiet = 10
	width = (len(modules) + 2 * quiet) * module
	text_height = 16 if show_text else 0
	bars = []
	x = quiet
	position = 0
	while position < len(modules):
		if modules[position] == "1":
			start = position
			while position < len(modules) and modules[position] == "1":
				position += 1
			left, bar_width = (x + start) * module, (position - start) * module
			bars.append(f'<rect x="{left}" y="0" width="{bar_width}" height="{height}"/>')
		else:
			position += 1
	label = (
		f'<text x="{width / 2}" y="{height + 13}" font-family="monospace" font-size="13" '
		f'text-anchor="middle">{escape(text)}</text>'
		if show_text
		else ""
	)
	return (
		f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height + text_height}" '
		f'viewBox="0 0 {width} {height + text_height}"><rect width="100%" height="100%" fill="#fff"/>'
		f'<g fill="#000">{"".join(bars)}</g>{label}</svg>'
	)
