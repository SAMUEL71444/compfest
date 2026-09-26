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
# Model 2-kelas (interaction2_head, dilatih via BILSTMandOther_2Class.ipynb):
# index 0=other, 1=inspecting. Menggantikan skema 6-kelas MERL lama.
INTERACTION_CLASS_NAMES = ["other", "inspecting"]


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
    Hitung sudut torso terhadap sumbu vertikal (°), via atan2(|dx|, |dy|).

    Konvensi: 0° = berdiri tegak, 90° = horizontal (rebah/jatuh).
    Dipakai di koordinat piksel (y meningkat ke bawah).

    Rentang [0°, 90°] — BUKAN arccos [0°, 180°]. atan2(|dx|,|dy|) melipat
    torso terbalik (bahu di bawah pinggul) ke rentang yang sama dengan
    rebah biasa, karena bagi ambang deteksi jatuh keduanya sama-sama
    "horizontal", bukan dua kondisi berbeda. Ambang fall_angle hasil sweep
    dikalibrasi pada rumus ini — memakai arccos akan membuat sudut yang
    sama secara visual terbaca hingga 2× lebih besar.

    keypoints: [17, 3]
    Returns: float sudut dalam derajat [0°, 90°]
    """
    shoulder_c = (keypoints[_LEFT_SHOULDER, :2] + keypoints[_RIGHT_SHOULDER, :2]) / 2.0
    hip_c = hip_center(keypoints)

    # Vektor dari pinggul ke bahu
    dx, dy = shoulder_c - hip_c  # (dx, dy), di image: y ke bawah

    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return 0.0

    angle_deg = float(np.degrees(np.arctan2(abs(dx), abs(dy))))
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
    Sudut torso MAKSIMUM sepanjang jendela (bukan rata-rata beberapa frame
    terakhir). Kejatuhan adalah puncak singkat — dirata-rata bersama frame
    tegak di sekitarnya, nilainya jatuh di bawah ambang.

    raw_window: [T, 17, 3]
    Returns: float sudut dalam derajat [0°, 90°]
    """
    T = raw_window.shape[0]
    angles = [torso_angle(raw_window[t]) for t in range(T)]
    return float(np.max(angles))


def window_torso_speed(raw_window: np.ndarray, fps: float = 15.0) -> float:
    """
    Kecepatan perubahan vektor torso MAKSIMUM sepanjang jendela (torso
    length/detik) — dari vektor torso (bahu-pinggul), bukan pergerakan
    pinggul: pinggul menuju ~0 setelah normalisasi, torso tidak.

    Dimatikan secara default di lapisan ambang (lihat thresholds.py):
    kecepatan gerak jatuh vs normal nyaris sama, jadi menurunkan recall
    bila dipaksa jadi syarat wajib. Tetap disediakan sebagai opsi.

    raw_window: [T, 17, 3]
    fps: laju jendela ini (dst_fps, biasanya 15)
    Returns: float — piksel torso per detik (skala relatif thd panjang torso)
    """
    T = raw_window.shape[0]
    if T < 2:
        return 0.0

    vectors = []
    for t in range(T):
        shoulder_c = (raw_window[t, _LEFT_SHOULDER, :2] + raw_window[t, _RIGHT_SHOULDER, :2]) / 2.0
        hip_c = hip_center(raw_window[t])
        vectors.append(shoulder_c - hip_c)
    vectors = np.array(vectors)  # [T, 2]

    diffs = np.linalg.norm(np.diff(vectors, axis=0), axis=1)  # [T-1]
    avg_torso = float(np.mean([torso_length(raw_window[t]) for t in range(T)]))
    avg_torso = max(avg_torso, 1.0)

    max_diff = float(np.max(diffs)) if len(diffs) else 0.0
    return (max_diff / avg_torso) * fps
