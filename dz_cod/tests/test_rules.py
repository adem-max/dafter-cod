"""Unit tests for the pure rules (no database needed).

Run: bench --site <site> run-tests --module dz_cod.tests.test_rules
"""

from frappe.tests import UnitTestCase

from dz_cod.cod import settlement as rules
from dz_cod.cod import states as S
from dz_cod.cod.phone import is_valid_phone, normalize_phone
from dz_cod.demo.loader import combinations
from dz_cod.setup.wilayas import WILAYAS
from dz_cod.setup.workflow import STATES, TRANSITIONS

COURIER = "Rapide"


class TestPhone(UnitTestCase):
	def test_normalize_international_formats(self):
		self.assertEqual(normalize_phone("+213 555 12 34 56"), "0555123456")
		self.assertEqual(normalize_phone("00213-661-12-34-56"), "0661123456")
		self.assertEqual(normalize_phone("0770 12 34 56"), "0770123456")

	def test_unknown_format_is_kept(self):
		# We never destroy what the operator typed
		self.assertEqual(normalize_phone(" 12345 "), "12345")
		self.assertIsNone(normalize_phone(None))

	def test_validity(self):
		self.assertTrue(is_valid_phone("0555123456"))  # mobile
		self.assertTrue(is_valid_phone("021234567"))  # landline (9 digits)
		self.assertFalse(is_valid_phone("0855123456"))  # 08 is not a mobile prefix
		self.assertFalse(is_valid_phone("055512345"))  # too short for a mobile
		self.assertFalse(is_valid_phone(""))


class TestSettlementRules(UnitTestCase):
	def status(self, state=S.DELIVERED, courier=COURIER, net=3000, expected=3000, tolerance=0):
		return rules.line_status(state, courier, COURIER, net, expected, tolerance)

	def test_exact_amount_is_ok(self):
		self.assertEqual(self.status(), rules.OK)

	def test_difference_within_tolerance_is_ok(self):
		self.assertEqual(self.status(net=2995, tolerance=10), rules.OK)

	def test_difference_is_a_gap(self):
		self.assertEqual(self.status(net=2500), rules.GAP)

	def test_unknown_order(self):
		self.assertEqual(self.status(state=None), rules.UNKNOWN)

	def test_already_settled(self):
		self.assertEqual(self.status(state=S.SETTLED), rules.ALREADY_SETTLED)

	def test_not_delivered_or_other_courier_is_invalid(self):
		self.assertEqual(self.status(state=S.SHIPPED), rules.INVALID)
		self.assertEqual(self.status(state=S.RETURNED), rules.INVALID)
		self.assertEqual(self.status(courier="Autre"), rules.INVALID)

	def test_is_paid(self):
		self.assertTrue(rules.is_paid(rules.OK, 0))
		self.assertFalse(rules.is_paid(rules.GAP, 0))
		self.assertTrue(rules.is_paid(rules.GAP, 1))  # gap accepted by the user
		self.assertFalse(rules.is_paid(rules.UNKNOWN, 1))  # cannot accept an unknown parcel

	def test_disputed_amount(self):
		self.assertEqual(rules.disputed_amount(rules.GAP, 2500, -500), 500)
		self.assertEqual(rules.disputed_amount(rules.UNKNOWN, 1200, 0), 1200)

	def test_remaining_due(self):
		self.assertEqual(rules.remaining_due(2500, 0), 2500)
		self.assertEqual(rules.remaining_due(2500, 2000), 500)  # 500 short the first time
		self.assertEqual(rules.remaining_due(2500, 3000), -500)  # paid too much

	def test_prefill_amounts(self):
		# First Versement: the whole order and its fee
		self.assertEqual(rules.prefill_amounts(3000, 500, 0), (3000, 500))
		# After a line 500 short: only the 500 left, no fee again
		self.assertEqual(rules.prefill_amounts(3000, 500, 2000), (500, 0))
		# Paid too much: nothing to pre-fill (the line shows the gap to accept)
		self.assertEqual(rules.prefill_amounts(3000, 500, 3000), (0, 0))


class TestWorkflowDefinition(UnitTestCase):
	"""The workflow table must respect Frappe's rules, or setup fails."""

	def test_every_transition_uses_known_states(self):
		names = {state for state, *_ in STATES}
		self.assertEqual(names, set(S.ALL_STATES))
		for from_state, _action, to_state, _role, _condition in TRANSITIONS:
			self.assertIn(from_state, names)
			self.assertIn(to_state, names)

	def test_docstatus_moves_are_allowed_by_frappe(self):
		docstatus = {state: status for state, status, *_ in STATES}
		for from_state, _action, to_state, *_ in TRANSITIONS:
			# Frappe forbids: leaving a cancelled doc, submitted -> draft, draft -> cancelled
			self.assertNotEqual(docstatus[from_state], 2)
			self.assertFalse(docstatus[from_state] == 1 and docstatus[to_state] == 0)
			self.assertFalse(docstatus[from_state] == 0 and docstatus[to_state] == 2)

	def test_confirmation_submits_the_order(self):
		docstatus = {state: status for state, status, *_ in STATES}
		self.assertEqual(docstatus[S.NEW], 0)
		self.assertEqual(docstatus[S.CONFIRMED], 1)


class TestReferenceData(UnitTestCase):
	def test_69_wilayas_with_unique_codes(self):
		codes = [code for code, *_ in WILAYAS]
		self.assertEqual(len(codes), 69)
		self.assertEqual(codes, [f"{n:02d}" for n in range(1, 70)])

	def test_new_wilayas_have_an_existing_parent(self):
		codes = {code for code, *_ in WILAYAS}
		for code, _name, _zone, parent in WILAYAS:
			if int(code) > 58:
				self.assertIn(parent, codes)
				self.assertLessEqual(int(parent), 58)

	def test_variant_combinations(self):
		combos = combinations([("Taille", ["S", "M"]), ("Couleur", ["Noir", "Blanc"])])
		self.assertEqual(len(combos), 4)
		self.assertIn({"Taille": "M", "Couleur": "Blanc"}, combos)
