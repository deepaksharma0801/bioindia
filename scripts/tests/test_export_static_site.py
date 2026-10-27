import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from export_static_site import WITHHELD, scrub, scrub_report, snapshot_key


ROOT = Path(__file__).resolve().parents[2]


class SnapshotKeyTests(unittest.TestCase):
    CASES = [
        ("/model-info", None),
        ("/prediction/ranking?limit=6&unlabelled_only=true", None),
        ("/simulation/extinction-cascade", {"species_id": "tiger", "threshold": 0.5}),
        ("/reports/regional", {"region": "Andaman & Nicobar"}),
    ]

    def test_python_keys_are_safe_file_names(self) -> None:
        for path, body in self.CASES:
            self.assertRegex(snapshot_key(path, body), r"^[A-Za-z0-9/._-]+\.json$")
        self.assertEqual(snapshot_key("/simulation/extinction-cascade", {"threshold": 0.25, "species_id": "croc"}),
                         "simulation/extinction-cascade__species_id-croc_threshold-0.25.json")

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_javascript_keys_match(self) -> None:
        source = (ROOT / "bioindia-phase5.js").read_text(encoding="utf-8")
        function = re.search(r"function snapshotKey\(path, body\) \{.*?\n  \}", source, re.S).group(0)
        script = function + "\nconsole.log(JSON.stringify(" + json.dumps(self.CASES) + ".map(c => snapshotKey(c[0], c[1]))));"
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [snapshot_key(path, body) for path, body in self.CASES])


class ScrubTests(unittest.TestCase):
    def test_export_categories_are_blanked_except_flagships(self) -> None:
        payload = {"species": [{"species_id": "ardeola_grayii", "official_iucn_category": "LC", "predicted_probability": 0.1},
                               {"species_id": "tiger", "reported_category": "EN"}]}
        cleaned = scrub(payload)

        self.assertIsNone(cleaned["species"][0]["official_iucn_category"])
        self.assertEqual(cleaned["species"][0]["predicted_probability"], 0.1)
        self.assertEqual(cleaned["species"][1]["reported_category"], "EN")

    def test_owner_applies_to_nested_profiles(self) -> None:
        profile = {"conservation_assessment": {"category": "VU"}}
        self.assertEqual(scrub(profile, "rhino")["conservation_assessment"]["category"], "VU")
        self.assertIsNone(scrub(profile, "pavo_cristatus")["conservation_assessment"]["category"])

    def test_report_keeps_only_the_threatened_count(self) -> None:
        report = {"sections": {"threatened_species": [{"text": "2 species ...: A (EN), B (VU).",
                                                       "evidence": {"species": [{"species_id": "a", "category": "EN"}, {"species_id": "b", "category": "VU"}]}}]},
                  "markdown": "A (EN)"}
        cleaned = scrub_report(report)
        statement = cleaned["sections"]["threatened_species"][0]

        self.assertTrue(statement["text"].startswith("2 species"))
        self.assertNotIn("(EN)", statement["text"])
        self.assertEqual(statement["evidence"], {"officially_threatened_species": 2})
        self.assertNotIn("markdown", cleaned)
        self.assertEqual(WITHHELD, "-")


if __name__ == "__main__":
    unittest.main()
