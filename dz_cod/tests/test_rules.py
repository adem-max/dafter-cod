"""Unit tests for the pure rules (no database needed). Phone and wilaya-list
rules moved to dz_core with their tests (dz_core/tests/test_places_and_phones.py).

Run: bench --site <site> run-tests --module dz_cod.tests.test_rules
"""

from frappe.tests import UnitTestCase

from dz_cod.cod import settlement as rules
from dz_cod.cod import states as S
from dz_cod.demo.loader import combinations
from dz_cod.setup.wilayas import ZONE_RATES, ZONES
from dz_cod.setup.workflow import STATES, TRANSITIONS

COURIER = "Rapide"


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
		self.assertEqual(names, set(S.ALL_STATES + S.DIRECT_STATES))
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
	def test_every_wilaya_has_a_rate_zone(self):
		# The list itself is dz_core's (tested there); the zones are ours
		from dz_core.setup.wilayas import WILAYAS

		self.assertEqual(set(ZONES), {code for code, *_ in WILAYAS})
		self.assertTrue(set(ZONES.values()) <= set(ZONE_RATES))

	def test_variant_combinations(self):
		combos = combinations([("Taille", ["S", "M"]), ("Couleur", ["Noir", "Blanc"])])
		self.assertEqual(len(combos), 4)
		self.assertIn({"Taille": "M", "Couleur": "Blanc"}, combos)
