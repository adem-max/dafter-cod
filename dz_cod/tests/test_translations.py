"""Every text a user can see must be translated in every language file
(translations/en.csv, translations/ar.csv).

Fails when someone adds a French label, message or button and forgets a file.
Run: bench --site <site> run-tests --module dz_cod.tests.test_translations
"""

import re

from frappe.tests import UnitTestCase

from dz_cod.tests.i18n_strings import LANGUAGES, collect, read_csv

PLACEHOLDER = re.compile(r"\{\d+\}")


class TestTranslations(UnitTestCase):
	def test_every_text_is_translated(self):
		for lang in LANGUAGES:
			with self.subTest(lang=lang):
				known = read_csv(lang)
				missing = {text: where for text, where in collect(lang).items() if text not in known}
				self.assertFalse(
					missing,
					f"Add these texts to dz_cod/translations/{lang}.csv:\n"
					+ "\n".join(f"  {where}: {text}" for text, where in missing.items()),
				)

	def test_no_leftover_lines(self):
		# A line whose French text no longer exists in the app (renamed or removed)
		for lang in LANGUAGES:
			with self.subTest(lang=lang):
				used = collect(lang)
				leftovers = [text for text in read_csv(lang) if text not in used]
				self.assertFalse(leftovers, f"Remove these lines from {lang}.csv: {leftovers}")

	def test_placeholders_are_kept(self):
		# "{0}" is replaced by a value (an order number...): it must stay in every language
		for lang in LANGUAGES:
			for french, translated in read_csv(lang).items():
				with self.subTest(lang=lang, text=french):
					self.assertEqual(
						sorted(PLACEHOLDER.findall(french)), sorted(PLACEHOLDER.findall(translated))
					)
