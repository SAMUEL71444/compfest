import json
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "reproducibility/source/backend"
sys.path.insert(0, str(RUNTIME))

from pipeline.analyze import window_fall_geometry
from pipeline.models import load_head


class NewModelTests(unittest.TestCase):
    def test_weight_matches_declared_architecture(self):
        model, cfg = load_head(ROOT / "models/fall_head.pt", ROOT / "models/fall_head.json")
        self.assertEqual(model.in_dim, cfg["in_dim"])
        self.assertEqual(model.n_classes, len(cfg["class_names"]))
        self.assertEqual(cfg["class_names"], ["normal", "oleng", "jatuh"])

    def test_recommended_threshold_is_supplied_candidate(self):
        cfg = json.loads((ROOT / "models/fall_head.json").read_text())
        candidates = json.loads((ROOT / "training_artifacts/threshold_best_models.json").read_text())
        expected = cfg["threshold_recommended"]
        best = candidates[0]
        self.assertEqual((expected["T_prob"], expected["T_angle"], expected["T_speed"]),
                         (best["T_prob"], best["T_angle"], best["T_speed"]))

    def test_geometry_matches_training_definition(self):
        # Local joints 0/1 are shoulders and 6/7 hips after slicing COCO 5..16.
        window = np.zeros((3, 24), dtype=np.float32).reshape(3, 12, 2)
        window[:, 6:8, :] = 0.0
        window[0, 0:2, :] = [0.0, -1.0]
        window[1, 0:2, :] = [1.0, 0.0]
        window[2, 0:2, :] = [0.0, 1.0]
        angle, speed = window_fall_geometry(window.reshape(3, 24), 15.0)
        self.assertAlmostEqual(angle, 90.0, places=3)
        self.assertAlmostEqual(speed, np.sqrt(2) * 15.0, places=4)


if __name__ == "__main__":
    unittest.main()
