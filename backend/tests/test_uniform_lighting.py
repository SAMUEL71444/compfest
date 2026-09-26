"""Regresi pencocokan seragam pada perubahan saturation kamera."""

import cv2
import numpy as np

from pipeline import uniform


def _solid_hsv(hue: int, saturation: int, value: int = 220) -> np.ndarray:
    hsv = np.full((90, 60, 3), (hue, saturation, value), dtype=np.uint8)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def test_seragam_tetap_cocok_saat_saturation_berubah():
    registered = _solid_hsv(35, 220)
    live_camera = _solid_hsv(28, 50)
    signature = uniform.buat_signature([registered])

    assert signature is not None
    assert uniform.cocokkan_seragam(live_camera, signature) is True


def test_warna_lain_tidak_dianggap_pegawai():
    registered = _solid_hsv(35, 220)
    blue_customer = _solid_hsv(115, 50)
    signature = uniform.buat_signature([registered])

    assert signature is not None
    assert uniform.cocokkan_seragam(blue_customer, signature) is False
