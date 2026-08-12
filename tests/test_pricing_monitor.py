import json
import unittest
from pathlib import Path

from scripts import check_pricing_sources as monitor


ROOT = Path(__file__).resolve().parents[1]


class PricingMonitorTest(unittest.TestCase):
    def test_config_is_valid(self):
        config = monitor.load_config(ROOT / "pricing-sources.json")
        self.assertEqual(config["schema_version"], 1)
        self.assertEqual(len(config["sources"]), 7)
        self.assertIn("tap_light", {source["id"] for source in config["sources"]})

    def test_normalize_page_removes_markup_and_whitespace(self):
        text = monitor.normalize_page("<h1>Tap&nbsp;Electric</h1>\n<p>Light   +5% transactiekosten</p>")
        self.assertEqual(text, "tap electric light +5% transactiekosten")

    def test_current_reference_snippets_match_all_configured_checks(self):
        config = monitor.load_config(ROOT / "pricing-sources.json")
        snippets = {
            "anwb_free": "Gratis laadpas zonder abonnement. Wel betaal je per laadsessie een starttarief van € 0,89.",
            "tap_light": "Light De beste keuze. € 0.00 /maand Je betaalt het tarief van de laadpaal +5% transactiekosten per sessie.",
            "vattenfall": "Voor onze gratis laadpas betaal je geen abonnementskosten. Je betaalt een starttarief van €0,35 als je laadt bij laadpalen die niet van ons zijn.",
            "eflux_flex": "Flex Gratis. €0,31 per laadsessie. €0,024/kWh toeslag op sessies bij niet-E-Flux laadpunten.",
            "shell_basic": "Shell Recharge Basic Geen maandelijkse kosten. DC: € 0,79 / kWh - € 0,82 / kWh - € 0,85 / kWh. AC: € 0,50 / kWh - € 0,55 / kWh - € 0,60 / kWh. € 0,35 transactiekosten per laadsessie.",
            "laadkompas_free": "Laadpas zonder abonnement. Het tarief is € 0,47 per laadsessie.",
            "totalenergies_mrae": "Provincies Flevoland, Noord-Holland en Utrecht MRA-E 2 t/m 5 €0,40 €0,48. MRA-E 6 €0,30 €0,36. MRA-E 6 - Dynamische tarieven €0,34 €0,36. Snelladers DC Provincies Flevoland, Noord-Holland en Utrecht (MRA-E) €0,45 €0,54.",
        }
        for source in config["sources"]:
            with self.subTest(source=source["id"]):
                normalized = monitor.normalize_page(f"<p>{snippets[source['id']]}</p>")
                self.assertEqual(monitor.evaluate_source(source, normalized), [])

    def test_mismatch_is_reported(self):
        source = {
            "checks": [{"label": "expected fee", "patterns": [r"0[,.]89"]}],
        }
        self.assertEqual(monitor.evaluate_source(source, "starttarief 1,25"), ["expected fee"])


if __name__ == "__main__":
    unittest.main()
