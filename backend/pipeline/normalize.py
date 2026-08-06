"""
pipeline/normalize.py — SAPA

⚠️ STATUS: BEST-EFFORT / BELUM DIVERIFIKASI KE inference.py ASLI TIM.
Tim belum memberikan file inference.py, jadi modul ini ditulis berdasarkan
deskripsi di dokumen konteks (bukan disalin dari kode training). Sebelum dipakai
untuk demo/submission final, WAJIB di-diff terhadap normalize_pose/resample_fps/
make_windows yang benar-benar dipakai saat training kepala BiLSTM. Kalau beda
sedikit saja, model akan akurat saat evaluasi offline tapi salah saat inferensi
di web (silent failure, tidak akan error, cuma hasilnya ngawur).

Asumsi yang levelnya "cukup yakin" (berdasarkan konvensi COCO-17 + fall_joints
yang sudah dikonfirmasi di config JSON):
- Format keypoint COCO-17 standar:
    0 nose, 1 l_eye, 2 r_eye, 3 l_ear, 4 r_ear,
    5 l_shoulder, 6 r_shoulder, 7 l_elbow, 8 r_elbow,
    9 l_wrist, 10 r_wrist, 11 l_hip, 12 r_hip,
    13 l_knee, 14 r_knee, 15 l_ankle, 16 r_ankle
- fall_joints = [5..16] (index 5 sampai 16, 12 sendi badan tanpa wajah) → sudah
  dikonfirmasi cocok di fall_head.json.
- hip_center  = rata-rata l_hip(11) & r_hip(12)
- shoulder_center = rata-rata l_shoulder(5) & r_shoulder(6)
- torso_length = jarak Euclidean(shoulder_center, hip_center)

Asumsi yang levelnya "tebakan wajar, PALING PERLU DICEK ke tim":
- Interpolasi resample: linear per-koordinat terhadap waktu (bukan cubic/spline).
- Kalau confidence keypoint rendah/hilang, tidak ada interpolasi spasial khusus —
  hanya interpolasi temporal apa adanya (asumsi datanya sudah cukup bersih dari
  tracker YOLOv8-pose).
- Padding jendela < 45 frame: pakai edge-padding (ulang frame terakhir), bukan
  zero-padding, supaya tidak menciptakan gerakan palsu mendadak ke titik nol.
- torso_length yang dipakai untuk skala dihitung PER FRAME lalu dirata-rata
  sepanjang sequence (bukan cuma dari 1 frame), supaya lebih stabil.
"""

import numpy as np

# --- Indeks keypoint COCO-17 ---
NOSE = 0
L_EYE, R_EYE = 1, 2
L_EAR, R_EAR = 3, 4
L_SHOULDER, R_SHOULDER = 5, 6
L_ELBOW, R_ELBOW = 7, 8
L_WRIST, R_WRIST = 9, 10
L_HIP, R_HIP = 11, 12
L_KNEE, R_KNEE = 13, 14
L_ANKLE, R_ANKLE = 15, 16

FALL_JOINTS = list(range(5, 17))  # 12 sendi badan (dikonfirmasi cocok fall_head.json)

MIN_TORSO_LEN = 1e-3  # guard pembagian nol


def _hip_center(frame_xy: np.ndarray) -> np.ndarray:
    """frame_xy: [17,2] -> [2]"""
    return (frame_xy[L_HIP] + frame_xy[R_HIP]) / 2.0


def _shoulder_center(frame_xy: np.ndarray) -> np.ndarray:
    return (frame_xy[L_SHOULDER] + frame_xy[R_SHOULDER]) / 2.0


def normalize_pose(seq: np.ndarray) -> np.ndarray:
    """
    seq: [T, 17, 3]  (x, y, confidence) dalam koordinat piksel mentah.
    return: [T, 17, 3] dengan (x, y) sudah dinormalisasi; confidence tidak diubah.

    Normalisasi:
      origin = titik tengah pinggul per frame
      skala  = rata-rata panjang torso (bahu-tengah <-> pinggul-tengah) sepanjang sequence
    """
    seq = seq.copy().astype(np.float32)
    T = seq.shape[0]

    xy = seq[:, :, :2]           # [T,17,2]
    conf = seq[:, :, 2:3]        # [T,17,1]

    hip_centers = np.stack([_hip_center(xy[t]) for t in range(T)], axis=0)       # [T,2]
    shoulder_centers = np.stack([_shoulder_center(xy[t]) for t in range(T)], axis=0)  # [T,2]

    torso_lengths = np.linalg.norm(shoulder_centers - hip_centers, axis=1)  # [T]
    torso_lengths = torso_lengths[torso_lengths > MIN_TORSO_LEN]
    scale = float(np.mean(torso_lengths)) if len(torso_lengths) > 0 else 1.0
    scale = max(scale, MIN_TORSO_LEN)

    xy_norm = (xy - hip_centers[:, None, :]) / scale  # broadcast origin per-frame, skala global

    return np.concatenate([xy_norm, conf], axis=-1)


def resample_fps(seq: np.ndarray, src_fps: float, dst_fps: float = 15.0) -> np.ndarray:
    """
    seq: [T, 17, C]  (C = 2 atau 3, tergantung sudah dinormalisasi atau belum)
    Interpolasi LINEAR temporal dari src_fps ke dst_fps.

    ⚠️ ASUMSI: linear interpolation. Cek ke tim apakah training pakai metode lain.
    """
    T = seq.shape[0]
    if T < 2 or src_fps == dst_fps:
        return seq.astype(np.float32)

    duration = (T - 1) / src_fps
    n_dst = max(2, int(round(duration * dst_fps)) + 1)

    t_src = np.linspace(0, duration, T)
    t_dst = np.linspace(0, duration, n_dst)

    flat = seq.reshape(T, -1)
    flat_out = np.empty((n_dst, flat.shape[1]), dtype=np.float32)
    for c in range(flat.shape[1]):
        flat_out[:, c] = np.interp(t_dst, t_src, flat[:, c])
    out = flat_out.reshape((n_dst,) + seq.shape[1:])
    return out


def make_windows(seq: np.ndarray, window: int = 45, stride: int = 15) -> np.ndarray:
    """
    seq: [T, 17, C]
    return: [W, window, 17, C]

    Kalau T < window: pad dengan mengulang frame terakhir (edge padding) sampai
    panjang window, hasilkan 1 jendela.
    ⚠️ ASUMSI: edge padding, bukan zero padding. Cek ke tim.
    """
    T = seq.shape[0]

    if T < window:
        pad_len = window - T
        pad = np.repeat(seq[-1:], pad_len, axis=0)
        seq_padded = np.concatenate([seq, pad], axis=0)
        return seq_padded[None, ...]  # [1, window, 17, C]

    starts = list(range(0, T - window + 1, stride))
    if not starts or starts[-1] + window < T:
        starts.append(T - window)  # pastikan sisa akhir sequence ikut terjendela

    windows = np.stack([seq[s:s + window] for s in starts], axis=0)
    return windows.astype(np.float32)


def build_windows_for_heads(raw_seq_xyc: np.ndarray, src_fps: float,
                             window: int = 45, stride: int = 15, dst_fps: float = 15.0):
    """
    Pipeline lengkap satu track orang: normalize -> resample -> window,
    lalu siapkan dua versi input sesuai kontrak tiap kepala.

    raw_seq_xyc: [T, 17, 3] koordinat piksel MENTAH dari YOLOv8-pose (belum dinormalisasi).

    return dict:
      "fall_input"        : [W, window, 24]  (12 sendi x [x,y])
      "interaction_input" : [W, window, 51]  (17 sendi x [x,y,conf])
      "raw_windows"       : [W, window, 17, 3]  koordinat piksel MENTAH (untuk lapisan geometri,
                             lihat catatan Bagian 4.4 — geometri pakai raw, bukan yang dinormalisasi)
    """
    norm_seq = normalize_pose(raw_seq_xyc)                       # [T,17,3] dinormalisasi
    norm_resampled = resample_fps(norm_seq, src_fps, dst_fps)    # [T',17,3]
    raw_resampled = resample_fps(raw_seq_xyc, src_fps, dst_fps)  # [T',17,3] tetap mentah, buat geometri

    norm_windows = make_windows(norm_resampled, window, stride)  # [W,window,17,3]
    raw_windows = make_windows(raw_resampled, window, stride)    # [W,window,17,3]

    W = norm_windows.shape[0]
    fall_input = norm_windows[:, :, FALL_JOINTS, :2].reshape(W, window, -1)  # [W,window,24]
    interaction_input = norm_windows.reshape(W, window, -1)                   # [W,window,51]

    return {
        "fall_input": fall_input.astype(np.float32),
        "interaction_input": interaction_input.astype(np.float32),
        "raw_windows": raw_windows.astype(np.float32),
    }


if __name__ == "__main__":
    # Sanity check cepat
    dummy = np.random.rand(90, 17, 3).astype(np.float32) * 100  # 90 frame @ 30fps ~ 3 detik
    out = build_windows_for_heads(dummy, src_fps=30.0)
    print("fall_input:", out["fall_input"].shape)               # expect [W,45,24]
    print("interaction_input:", out["interaction_input"].shape) # expect [W,45,51]
    print("raw_windows:", out["raw_windows"].shape)             # expect [W,45,17,3]
