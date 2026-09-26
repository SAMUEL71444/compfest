"""Uji runner tanpa mengunduh model atau memakai video palsu sebagai baseline."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from evaluate import metrics


class EvaluationTests(unittest.TestCase):
    def test_confusion_and_errors(self):
        result = metrics([
            dict(status="ok", expected=["jatuh"], predicted=["jatuh"]),
            dict(status="ok", expected=[], predicted=["jatuh"]),
            dict(status="ok", expected=["jatuh"], predicted=[]),
            dict(status="error", expected=["jatuh"]),
        ])
        self.assertEqual(result["per_label"]["jatuh"]["f1"], 0.5)
        self.assertEqual(result["coverage"], 0.75)
        self.assertEqual(result["exact_match"], 1 / 3)
        self.assertIsNone(result["per_label"]["butuh_bantuan"]["f1"])

    def test_no_ground_truth_has_no_score(self):
        result = metrics([dict(status="ok", expected=None, predicted=[])])
        self.assertIsNone(result["exact_match"])
        self.assertIsNone(result["macro_f1_defined_labels"])


if __name__ == "__main__":
    unittest.main()
