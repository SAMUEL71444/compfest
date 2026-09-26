"""Regressions for strided video poses and original-frame timestamps."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reproducibility/source/backend"))
from pipeline.normalize import resample_fps, build_windows_for_heads
from pipeline.analyze import _compute_window_times
from pipeline.extract import extract_poses


class TimingTests(unittest.TestCase):
    def test_stride_preserves_six_seconds_and_four_windows(self):
        raw = np.ones((90, 17, 3), dtype=np.float32)
        indices = np.arange(1, 180, 2)
        raw[:, :, 0] = indices[:, None]
        sampled = resample_fps(raw, 30, 15, indices)
        self.assertEqual(len(sampled), 90)
        np.testing.assert_allclose(sampled[:, 0, 0], indices)
        result = build_windows_for_heads(raw, 30, frame_indices=indices)
        self.assertEqual(result['fall_input'].shape, (4, 45, 24))
        self.assertEqual(result['interaction_input'].shape, (4, 45, 51))

    def test_missing_detection_keeps_time_gap(self):
        raw = np.array([0, 2, 6], dtype=np.float32).reshape(3, 1, 1)
        sampled = resample_fps(raw, 30, 15, np.array([0, 2, 6]))
        np.testing.assert_allclose(sampled.ravel(), [0, 2, 4, 6])

    def test_short_track_padding_does_not_extend_event_past_track(self):
        times = _compute_window_times(np.array([31, 59]), 30, 1, 45, 15, 15)
        np.testing.assert_allclose(times, [[31 / 30, 2]])

    def test_extraction_returns_original_indices(self):
        result = SimpleNamespace(keypoints=SimpleNamespace(data=torch.ones(1, 17, 3)),
            boxes=SimpleNamespace(conf=torch.ones(1), xywh=torch.tensor([[10,10,100,100]]), id=torch.ones(1)))
        model = SimpleNamespace(track=lambda *a, **kw: iter([result, result, result]))
        import cv2
        cap = SimpleNamespace(isOpened=lambda: True, release=lambda: None,
            get=lambda prop: {cv2.CAP_PROP_FPS: 30, cv2.CAP_PROP_FRAME_COUNT: 6,
                cv2.CAP_PROP_FRAME_WIDTH: 200, cv2.CAP_PROP_FRAME_HEIGHT: 200}[prop])
        with patch('pipeline.extract._get_yolo', return_value=model), patch('pipeline.extract.cv2.VideoCapture', return_value=cap):
            tracks = extract_poses('test.mp4', {'min_track_frames': 2})
        self.assertEqual([f[0] for f in tracks[1]['frames']], [1,3,5])
        self.assertEqual(tracks[1]['fps'], 30)


if __name__ == '__main__':
    unittest.main()
