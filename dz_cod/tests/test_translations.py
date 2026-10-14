"""Every text a user can see must have an English version in translations/en.csv.

Fails when someone adds a French label, message or button and forgets en.csv.
Run: bench --site <site> run-tests --module dz_cod.tests.test_translations
"""

import re

from frappe.tests import UnitTestCase

from dz_cod.tests.i18n_strings import collect, read_en_csv

PLACEHOLDER = re.compile(r"\{\d+\}")


class TestEnglishTranslations(UnitTestCase):
	def test_every_text_has_an_english_version(self):
		known = read_en_csv()
		missing = {text: where for text, where in collect().items() if text not in known}
		self.assertFalse(
			missing,
			"Add these texts to dz_cod/translations/en.csv:\n"
			+ "\n".join(f"  {where}: {text}" for text, where in missing.items()),
		)

	def test_no_leftover_lines(self):
		# A line whose French text no longer exists in the app (renamed or removed)
		used = collect()
		leftovers = [text for text in read_en_csv() if text not in used]
		self.assertFalse(leftovers, f"Remove these lines from en.csv: {leftovers}")

	def test_placeholders_are_kept(self):
		# "{0}" is replaced by a value (an order number...): it must stay in English too
		for french, english in read_en_csv().items():
			self.assertEqual(
				sorted(PLACEHOLDER.findall(french)), sorted(PLACEHOLDER.findall(english)), french
			)
