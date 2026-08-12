import unittest

import process


class PricingRulesTest(unittest.TestCase):
    def test_unknown_cpo_does_not_create_false_comparison(self):
        pricing = process.build_pricing(None, "unknown", "TotalEnergies", 22)
        self.assertEqual(set(pricing), {"shell_basic"})
        self.assertEqual(pricing["shell_basic"]["confidence"], "low")

    def test_anwb_free_uses_cpo_plus_session_fee(self):
        quote = process.build_pricing(0.40, "ndw", "50five", 22)["anwb_free"]
        self.assertEqual(quote["kwh"], 0.40)
        self.assertEqual(quote["session"], 0.89)
        self.assertEqual(quote["confidence"], "high")

    def test_anwb_discount_network_is_not_invented(self):
        quote = process.build_pricing(0.40, "ndw", "TotalEnergies", 22)["anwb_free"]
        self.assertEqual(quote["kwh"], 0.40)
        self.assertEqual(quote["confidence"], "medium")
        self.assertIn("korting", quote["note"].lower())

    def test_vattenfall_own_network_has_no_session_fee(self):
        quote = process.build_pricing(0.42, "ndw", "Vattenfall InCharge", 22)["vattenfall"]
        self.assertEqual(quote["session"], 0.0)
        self.assertEqual(quote["confidence"], "high")

    def test_vattenfall_roaming_has_session_fee_and_lower_confidence(self):
        quote = process.build_pricing(0.42, "ndw", "Ubitricity", 22)["vattenfall"]
        self.assertEqual(quote["session"], 0.35)
        self.assertEqual(quote["confidence"], "medium")

    def test_eflux_flex_own_network_has_no_kwh_markup(self):
        quote = process.build_pricing(0.45, "ndw", "E-Flux by Road", 22)["eflux_flex"]
        self.assertEqual(quote["kwh"], 0.45)
        self.assertEqual(quote["session"], 0.31)

    def test_eflux_flex_roaming_adds_kwh_markup(self):
        quote = process.build_pricing(0.45, "ndw", "Ubitricity", 22)["eflux_flex"]
        self.assertEqual(quote["kwh"], 0.474)
        self.assertEqual(quote["session"], 0.31)
        self.assertIn("0,48", quote["note"])

    def test_shell_ac_price_band_is_explicit_estimate(self):
        quote = process.build_pricing(0.40, "ndw", "Ubitricity", 22)["shell_basic"]
        self.assertEqual(quote["kwh"], 0.55)
        self.assertEqual(quote["session"], 0.35)
        self.assertEqual(quote["range"], [0.5, 0.6])
        self.assertEqual(quote["confidence"], "low")

    def test_shell_dc_uses_dc_band(self):
        quote = process.build_pricing(0.55, "ndw", "Fastcharge", 150)["shell_basic"]
        self.assertEqual(quote["kwh"], 0.82)
        self.assertEqual(quote["range"], [0.79, 0.85])

    def test_laadkompas_free_uses_cpo_plus_session_fee(self):
        quote = process.build_pricing(0.40, "ndw", "50five", 22)["laadkompas_free"]
        self.assertEqual(quote["kwh"], 0.40)
        self.assertEqual(quote["session"], 0.47)


if __name__ == "__main__":
    unittest.main()
