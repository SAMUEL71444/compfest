"""
pipeline/analyze.py — SAPA

Orkestrasi inferensi end-to-end:
  extract → normalize → resample → window → infer → detect_events → timeline

Urutan pipeline wajib (sesuai spesifikasi):
  1. extract_poses()           → raw keypoints [T,17,3] per track
  2. build_windows_for_heads() → normalize → resample → window dalam satu panggilan
       ├── fall_input      [W,45,24]  (12 sendi × x,y — untuk Kepala Jatuh)
       ├── interaction_input [W,45,51] (17 sendi × x,y,conf — untuk Kepala Interaksi)
       └── raw_windows     [W,45,17,3] (koordinat MENTAH — untuk lapisan geometri)
  3. predict_proba()           → probabilitas per jendela
  4. Lapisan geometri          → konfirmasi jatuh (torso_angle) + dwell (is_dwell)
  5. detect_events             → timeline

PENTING: Geometri (torso_angle, is_dwell) SELALU menggunakan raw_windows,
         bukan yang sudah dinormalisasi.
"""

import numpy as np
import torch
import logging
from typing import Optional

from .extract import extract_poses
from .normalize import build_windows_for_heads
from .geometry import is_dwell, window_torso_angle, INTERACTION_CLASS_NAMES
from .models import predict_proba, BiLSTMHead

logger = logging.getLogger(__name__)

# Indeks kelas jatuh di output Kepala Jatuh (0=normal, 1=oleng, 2=jatuh)
_FALL_CLASS_IDX = 2


def _compute_window_times(frame_indices: np.ndarray, src_fps: float,
                           W: int, window: int, stride: int, dst_fps: float) -> list:
    """
    Hitung pasangan (t0, t1) dalam detik untuk setiap jendela.

    Strategi: petakan posisi jendela di ruang resampled kembali ke detik nyata.
    """
    t_start = float(frame_indices[0]) / src_fps
    t_end = float(frame_indices[-1]) / src_fps

    times = []
    for w in range(W):
        wt0 = t_start + (w * stride) / dst_fps
        wt1 = t_start + (w * stride + window) / dst_fps
        # Klem ke rentang track yang sebenarnya ada
        wt1 = min(wt1, t_end + (window / dst_fps))
        times.append((float(wt0), float(wt1)))
    return times


def analyze(
    video_path: str,
    cfg: dict,
    fall_model: Optional[BiLSTMHead] = None,
    inter_model: Optional[BiLSTMHead] = None,
) -> dict:
    """
    Analisis penuh satu klip video.

    video_path: path ke .mp4
    cfg: konfigurasi — field yang relevan:
        run_fall / run_interaction : bool — aktifkan tiap kepala
        fall_thr      : float 0–1  — ambang probabilitas jatuh (default 0.80)
        fall_angle    : float °    — ambang sudut torso konfirmasi jatuh (default 55°)
        fall_confirm  : bool       — wajibkan gate geometri sudut torso (default True)
        fall_joints   : list[int]  — 12 indeks sendi untuk Kepala Jatuh
        inspect_idx   : list[int]  — indeks kelas inspect (default [4,5])
        help_min_win  : int        — jendela berturut-turut untuk butuh_bantuan (default 3)
        dwell_ratio   : float      — ambang gerak hip sebagai fraksi torso (default 0.3)
        target_fps    : float      — fps target setelah resample (default 15)
        window        : int        — panjang jendela frame (default 45)
        stride        : int        — langkah jendela (default 15)
        min_track_frames : int     — filter track terlalu pendek (default 10)

    Returns: {
        "timeline"          : [event_dict, ...]  — diurutkan by t0
        "frame_annotations" : {frame_idx: [{track_id, keypoints, action_label}]}
        "src_fps"           : float
        "total_frames"      : int
    }
    """
    # 1. Ekstraksi pose per track
    tracks = extract_poses(video_path, cfg)
    if not tracks:
        logger.warning("Tidak ada track valid ditemukan di video.")
        return {"timeline": [], "frame_annotations": {}, "src_fps": 30.0, "total_frames": 0}

    first = next(iter(tracks.values()))
    src_fps = first["fps"]
    total_frames = first["total_frames"]

    # Parameter dari cfg
    dst_fps     = float(cfg.get("target_fps", 15))
    window_size = int(cfg.get("window", 45))
    stride      = int(cfg.get("stride", 15))
    run_fall    = bool(cfg.get("run_fall", True))
    run_inter   = bool(cfg.get("run_interaction", True))
    fall_thr    = float(cfg.get("fall_thr", 0.80))
    fall_ang    = float(cfg.get("fall_angle", 55.0))
    fall_confirm= bool(cfg.get("fall_confirm", True))
    inspect_idx = list(cfg.get("inspect_idx", [4, 5]))
    help_min_win= int(cfg.get("help_min_win", 3))
    dwell_ratio = float(cfg.get("dwell_ratio", 0.3))

    timeline: list = []
    frame_annotations: dict = {}

    for track_id, tdata in tracks.items():
        frames = tdata["frames"]   # [(frame_idx, kps[17,3])]
        if len(frames) < 2:
            continue

        frame_indices = np.array([f[0] for f in frames])
        raw_seq = np.array([f[1] for f in frames], dtype=np.float32)  # [T,17,3]

        # 2. Pipeline normalisasi → jendela (satu panggilan)
        head_inputs = build_windows_for_heads(
            raw_seq, src_fps,
            window=window_size, stride=stride, dst_fps=dst_fps,
        )
        fall_input   = head_inputs["fall_input"]        # [W,45,24]
        inter_input  = head_inputs["interaction_input"] # [W,45,51]
        raw_windows  = head_inputs["raw_windows"]       # [W,45,17,3]
        W = raw_windows.shape[0]

        # Timestamp per jendela
        window_times = _compute_window_times(frame_indices, src_fps, W, window_size, stride, dst_fps)

        # 3a. Inferensi Kepala Jatuh
        fall_probs = None
        if run_fall and fall_model is not None:
            t = torch.from_numpy(fall_input)            # [W,45,24]
            fall_probs = predict_proba(fall_model, t).cpu().numpy()  # [W,3]

        # 3b. Inferensi Kepala Interaksi
        inter_probs = None
        if run_inter and inter_model is not None:
            t = torch.from_numpy(inter_input)           # [W,45,51]
            inter_probs = predict_proba(inter_model, t).cpu().numpy()  # [W,6]

        # 4. Peta label aksi ke frame asli (untuk rendering)
        # Setiap jendela w mencakup resampled frame [w*stride, w*stride+window)
        # Petakan balik ke frame indeks asli via timestamp
        T_orig = len(frames)
        t_start = float(frame_indices[0]) / src_fps

        window_action_for_resamp: dict = {}   # {resamp_idx: label}
        if inter_probs is not None:
            for w in range(W):
                act_idx = int(np.argmax(inter_probs[w]))
                label = INTERACTION_CLASS_NAMES[act_idx]
                for ri in range(w * stride, min(w * stride + window_size,
                                                 int((float(frame_indices[-1]) / src_fps - t_start) * dst_fps) + 1)):
                    window_action_for_resamp[ri] = label

        for orig_i, (fidx, kps) in enumerate(frames):
            t_rel = (float(fidx) / src_fps) - t_start
            ri = min(int(round(t_rel * dst_fps)), max(window_action_for_resamp.keys(), default=0))
            action = window_action_for_resamp.get(ri, "background")

            frame_annotations.setdefault(fidx, []).append({
                "track_id": int(track_id),
                "keypoints": kps,
                "action_label": action,
            })

        # 5a. Deteksi kejadian JATUH
        if fall_probs is not None:
            for w, (wt0, wt1) in enumerate(window_times):
                prob = float(fall_probs[w, _FALL_CLASS_IDX])
                if prob >= fall_thr:
                    angle = window_torso_angle(raw_windows[w])
                    if not fall_confirm or angle >= fall_ang:
                        timeline.append({
                            "tipe": "jatuh",
                            "t0": wt0,
                            "t1": wt1,
                            "skor": prob,
                            "sudut_torso": angle,
                            "track_id": int(track_id),
                        })

        # 5b. Deteksi kejadian BUTUH BANTUAN
        if inter_probs is not None:
            run_count, run_t0, run_t1 = 0, None, None
            for w, (wt0, wt1) in enumerate(window_times):
                inspect_prob = float(sum(inter_probs[w, i] for i in inspect_idx))
                stationary = is_dwell(raw_windows[w], dwell_ratio)

                if inspect_prob > 0.5 and stationary:
                    if run_count == 0:
                        run_t0 = wt0
                    run_count += 1
                    run_t1 = wt1
                else:
                    if run_count >= help_min_win:
                        timeline.append({
                            "tipe": "butuh_bantuan",
                            "t0": float(run_t0),
                            "t1": float(run_t1),
                            "durasi_window": run_count,
                            "track_id": int(track_id),
                        })
                    run_count, run_t0, run_t1 = 0, None, None

            # Flush run yang masih jalan di akhir sekuens
            if run_count >= help_min_win:
                timeline.append({
                    "tipe": "butuh_bantuan",
                    "t0": float(run_t0),
                    "t1": float(run_t1),
                    "durasi_window": run_count,
                    "track_id": int(track_id),
                })

        logger.debug(f"Track {track_id}: {T_orig} frame → {W} jendela diproses.")

    timeline.sort(key=lambda x: x["t0"])

    n_jatuh  = sum(1 for e in timeline if e["tipe"] == "jatuh")
    n_bantu  = sum(1 for e in timeline if e["tipe"] == "butuh_bantuan")
    logger.info(f"Analisis selesai: {n_jatuh} jatuh, {n_bantu} butuh_bantuan dari {len(tracks)} track.")

    return {
        "timeline": timeline,
        "frame_annotations": frame_annotations,
        "src_fps": src_fps,
        "total_frames": total_frames,
    }
