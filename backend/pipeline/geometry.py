"""
pipeline/geometry.py — SAPA

Fungsi geometri berbasis koordinat MENTAH (bukan yang dinormalisasi).
Dipakai untuk:
  - Konfirmasi jatuh (sudut torso)
  - Deteksi diam/dwell (pergerakan hip center)
  - Deteksi kejadian final (detect_events)
"""

import numpy as np

# Indeks sendi COCO-17
_LEFT_SHOULDER = 5
_RIGHT_SHOULDER = 6
_LEFT_HIP = 11
_RIGHT_HIP = 12


# Nama kelas interaksi (sesuai interaction_head.json)
INTERACTION_CLASS_NAMES = [
    "background",
    "reach",
    "retract",
    "hand_in_shelf",
    "inspect_product",
    "inspect_shelf",
]


def hip_center(keypoints: np.ndarray) -> np.ndarray:
    """
    Hitung titik tengah pinggul dari keypoints satu frame.

    keypoints: [17, 3] — (x, y, confidence)
    Returns: np.ndarray [2] — (x, y) koordinat mentah
    """
    return (keypoints[_LEFT_HIP, :2] + keypoints[_RIGHT_HIP, :2]) / 2.0


def torso_length(keypoints: np.ndarray) -> float:
    """
    Hitung panjang torso (piksel) dari keypoints satu frame.

    keypoints: [17, 3]
    Returns: float, minimal 1.0 (hindari division by zero)
    """
    shoulder_c = (keypoints[_LEFT_SHOULDER, :2] + keypoints[_RIGHT_SHOULDER, :2]) / 2.0
    hip_c = hip_center(keypoints)
    length = float(np.linalg.norm(shoulder_c - hip_c))
    return max(length, 1.0)


def torso_angle(keypoints: np.ndarray) -> float:
    """
    Hitung sudut torso terhadap sumbu vertikal (°).

    Konvensi: 0° = berdiri tegak, 90° = horizontal (rebah/jatuh).
    Dipakai di koordinat piksel (y meningkat ke bawah).

    keypoints: [17, 3]
    Returns: float sudut dalam derajat [0°, 180°]
    """
    shoulder_c = (keypoints[_LEFT_SHOULDER, :2] + keypoints[_RIGHT_SHOULDER, :2]) / 2.0
    hip_c = hip_center(keypoints)

    # Vektor dari pinggul ke bahu
    vec = shoulder_c - hip_c  # (dx, dy), di image: y ke bawah

    norm = float(np.linalg.norm(vec))
    if norm < 1e-6:
        return 0.0

    vec_norm = vec / norm

    # Vertikal "ke atas" dalam koordinat image = (0, -1)
    vertical_up = np.array([0.0, -1.0])
    cos_angle = float(np.clip(np.dot(vec_norm, vertical_up), -1.0, 1.0))
    angle_deg = float(np.degrees(np.arccos(cos_angle)))
    return angle_deg


def is_dwell(raw_window: np.ndarray, dwell_ratio: float = 0.3) -> bool:
    """
    Deteksi apakah orang "diam" dalam satu jendela (koordinat MENTAH).

    raw_window: [T, 17, 3] — koordinat piksel mentah untuk satu jendela
    dwell_ratio: ambang gerak hip center sebagai fraksi panjang torso
                 (default 0.3 untuk kamera samping; gunakan ~1.2 untuk top-down)
    Returns: True jika total gerak hip < dwell_ratio × panjang_torso rata-rata
    """
    T = raw_window.shape[0]
    if T < 2:
        return True

    # Hitung posisi hip center per frame
    hip_positions = np.array([hip_center(raw_window[t]) for t in range(T)])  # [T, 2]

    # Gerak maksimum dari posisi awal
    displacements = np.linalg.norm(hip_positions - hip_positions[0:1], axis=1)
    max_movement = float(np.max(displacements))

    # Panjang torso rata-rata sebagai referensi skala
    avg_torso = float(np.mean([torso_length(raw_window[t]) for t in range(T)]))

    return max_movement < dwell_ratio * avg_torso


def window_torso_angle(raw_window: np.ndarray) -> float:
    """
    Rata-rata sudut torso dari 5 frame terakhir jendela.
    Lebih stabil untuk konfirmasi jatuh daripada hanya 1 frame.

    raw_window: [T, 17, 3]
    Returns: float sudut dalam derajat
    """
    T = raw_window.shape[0]
    n_frames = min(5, T)
    angles = [torso_angle(raw_window[t]) for t in range(T - n_frames, T)]
    return float(np.mean(angles))
