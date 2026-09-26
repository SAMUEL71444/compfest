import importlib.util
from pathlib import Path
import unittest

import numpy as np


SCRIPT = Path(__file__).resolve().parents[2] / "analisis_baseline.py"
SPEC = importlib.util.spec_from_file_location("analisis_baseline", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AggregateBaselineTests(unittest.TestCase):
    def test_rejects_invalid_confusion_matrix(self):
        with self.assertRaisesRegex(ValueError, "3x3"):
            MODULE.validasi_confusion_matrix(
                np.array([[1, 0], [0, 1]]), MODULE.FALL_CLASSES, Path("bad.json")
            )

    def test_pairwise_f1_keeps_predictions_outside_pair_as_errors(self):
        matrix = np.array([
            [4, 1, 2],
            [2, 5, 3],
            [0, 0, 7],
        ])
        rows = MODULE.f1_per_pasangan_kelas(matrix, ["a", "b", "c"])
        pair = next(row for row in rows if row["kelas_a"] == "a" and row["kelas_b"] == "b")
        self.assertEqual(pair["prediksi_di_luar_pasangan"], 5)
        self.assertEqual(pair["a_ke_b"], 1)
        self.assertEqual(pair["b_ke_a"], 2)

    def test_committed_fall_matrix_reproduces_expected_metrics(self):
        matrix = np.array([
            [14285, 582, 469],
            [790, 3913, 113],
            [367, 143, 3302],
        ])
        metrics = MODULE.metrik_per_kelas(matrix, MODULE.FALL_CLASSES)
        self.assertEqual(metrics["macro_f1"], 0.8714)
        self.assertEqual(metrics["per_kelas"]["jatuh"]["recall"], 0.8662)


if __name__ == "__main__":
    unittest.main()
