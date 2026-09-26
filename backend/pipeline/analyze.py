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

import cv2
import numpy as np
import torch
import logging
from typing import Optional

from .extract import extract_poses
from .normalize import build_windows_for_heads
from .geometry import is_dwell, window_torso_angle, INTERACTION_CLASS_NAMES
from .models import predict_proba, BiLSTMHead
from .gestures import deteksi_angkat_tangan, DURASI_MIN_DEFAULT, TOLERANSI_JEDA_DETIK
from . import uniform as _uniform

logger = logging.getLogger(__name__)

# Indeks kelas jatuh di output Kepala Jatuh (0=normal, 1=oleng, 2=jatuh)
_FALL_CLASS_IDX = 2

# Berapa frame awal tiap track yang dicoba untuk cek seragam — cukup
# beberapa saja (bukan seluruh track) karena pakaian tidak berubah
# sepanjang track hidup, dan membuka lebih banyak frame cuma menambah
# biaya seek video tanpa menambah keyakinan.
_MAX_FRAME_CEK_SERAGAM = 5


def _deteksi_pegawai_per_track(video_path: str, tracks: dict, path_seragam) -> dict:
    """
    Cek status pegawai untuk tiap track, dari beberapa frame awal saja.
    Status bertahan sepanjang track_id hidup — sama seperti pola Mode Live
    (lihat MASTER_PROMPT §5): sidik diambil di beberapa frame awal, lalu
    dipakai terus tanpa mengecek ulang tiap frame.

    Returns: {track_id: bool} — True bila cocok salah satu seragam terdaftar.
             Track yang tidak bisa dinilai sama sekali (torso selalu < ambang
             ukuran) TIDAK masuk dict ini (diperlakukan sebagai bukan pegawai
             oleh pemanggil, arah aman: tetap dicek butuh-bantuan).
    """
    daftar_pegawai = _uniform.muat_daftar_signature(path_seragam)
    if not daftar_pegawai:
        return {}
    signatures = _uniform.daftar_signature_objects(daftar_pegawai)
    if not signatures:
        return {}

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.warning("Tidak bisa membuka video untuk cek seragam — dilewati.")
        return {}

    status: dict = {}
    try:
        for track_id, tdata in tracks.items():
            frames = tdata["frames"][:_MAX_FRAME_CEK_SERAGAM]
            for fidx, kps in frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, fidx)
                ok, frame = cap.read()
                if not ok:
                    continue
                patch = _uniform.crop_torso(frame, kps)
                hasil = _uniform.cocokkan_seragam_terdaftar(patch, signatures)
                if hasil is True:
                    status[track_id] = True
                    break   # cukup satu kecocokan, tidak perlu cek frame lain
                # hasil False atau None (torso kecil) — coba frame berikutnya
    finally:
        cap.release()

    return status


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
    camera_type: str = "both",
) -> dict:
    """
    Analisis penuh satu klip video.

    camera_type: 'lorong' | 'rak' | 'both'
      - 'rak'    → kamera top-down (atas rak) — fall detection DIMATIKAN karena
                    sudut torso selalu ≈90° dari atas, pasti false positive.
      - 'lorong' → kamera samping lorong — fall detection AKTIF, interaction OFF.
      - 'both'   → kedua kepala aktif.
    """
    # 1. Ekstraksi pose per track (filter false positive berdasarkan camera_type)
    tracks = extract_poses(video_path, cfg, camera_type=camera_type)

    if not tracks:
        logger.warning("Tidak ada track valid ditemukan di video.")
        return {"timeline": [], "frame_annotations": {}, "src_fps": 30.0, "total_frames": 0}

    first = next(iter(tracks.values()))
    src_fps = first["fps"]
    total_frames = first["total_frames"]

    # Status pegawai per track (opsional — hanya aktif bila cfg menyediakan
    # path_seragam dan ada pegawai terdaftar). CAKUPAN PENTING: status ini
    # HANYA dipakai untuk exclude dari butuh_bantuan/angkat_tangan di bawah,
    # TIDAK PERNAH dipakai untuk menyaring deteksi jatuh (pegawai yang jatuh
    # tetap darurat) — lihat pipeline/uniform.py.
    path_seragam = cfg.get("path_seragam")
    status_pegawai: dict = {}
    if path_seragam:
        status_pegawai = _deteksi_pegawai_per_track(video_path, tracks, path_seragam)
        if status_pegawai:
            logger.info(f"Pegawai terdeteksi pada track: {sorted(status_pegawai.keys())}")

    # Parameter dari cfg
    dst_fps     = float(cfg.get("target_fps", 15))
    window_size = int(cfg.get("window", 45))
    stride      = int(cfg.get("stride", 15))
    # camera_type menentukan kepala mana yang aktif
    # Jangan batasi berdasar camera_type — selalu jalankan semua model yang ada.
    # camera_type hanya mematikan FALL untuk kamera rak (false positive kamera atas).
    run_fall    = bool(cfg.get("run_fall", True))
    run_inter   = bool(cfg.get("run_interaction", True))
    # Untuk kamera rak (top-down), jatuh hampir selalu false positive — nonaktifkan
    if camera_type == "rak":
        run_fall = False
        logger.info("camera_type='rak' → deteksi jatuh DIMATIKAN (kamera top-down).")
    # Default mengikuti preset "prob_sudut" di pipeline/thresholds.py bila
    # pemanggil tidak menyediakan cfg — lihat docstring modul itu utk kalibrasi.
    fall_thr    = float(cfg.get("fall_thr", 0.57))
    fall_ang    = float(cfg.get("fall_angle", 5.0))
    fall_confirm= bool(cfg.get("fall_confirm", True))
    # Label (dari geometry.py INTERACTION_CLASS_NAMES): 0=other, 1=inspecting.
    # Model 2-kelas (BILSTMandOther_2Class.ipynb) — default [1].
    inspect_idx = list(cfg.get("inspect_idx", [1]))
    help_min_win= int(cfg.get("help_min_win", 2))
    # dwell_ratio berbeda untuk top-down vs samping:
    # top-down: torso_length sangat kecil karena kompresi perspektif → pakai nilai besar
    # samping: gunakan default kecil
    if camera_type == "rak":
        dwell_ratio = float(cfg.get("dwell_ratio", 3.0))   # besar = toleran — top-down
    else:
        dwell_ratio = float(cfg.get("dwell_ratio", 0.4))
    # Untuk kamera rak, is_dwell tidak diandalkan (YOLO top-down tidak akurat di pinggul)
    # → skip dwell check sepenuhnya untuk kamera rak
    skip_dwell = (camera_type == "rak")

    # Gestur angkat tangan (aturan geometri, lihat pipeline/gestures.py)
    run_gestures         = bool(cfg.get("run_gestures", True))
    gesture_durasi_min   = float(cfg.get("gesture_durasi_min", DURASI_MIN_DEFAULT))
    gesture_toleransi_jeda = float(cfg.get("gesture_toleransi_jeda", TOLERANSI_JEDA_DETIK))

    timeline: list = []
    frame_annotations: dict = {}

    for track_id, tdata in tracks.items():
        frames = tdata["frames"]   # [(frame_idx, kps[17,3])]
        if len(frames) < 2:
            continue

        # Pegawai terdaftar: kecualikan dari butuh_bantuan/angkat_tangan di
        # bawah (lihat status_pegawai di atas) — TIDAK mempengaruhi deteksi
        # jatuh, yang tetap berjalan penuh untuk track ini seperti biasa.
        is_pegawai = bool(status_pegawai.get(track_id, False))

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

        action_per_fidx: dict = {}   # {frame_idx: label} — untuk syarat 3 gestur angkat tangan
        for orig_i, (fidx, kps) in enumerate(frames):
            t_rel = (float(fidx) / src_fps) - t_start
            ri = min(int(round(t_rel * dst_fps)), max(window_action_for_resamp.keys(), default=0))
            action = window_action_for_resamp.get(ri, "background")
            action_per_fidx[fidx] = action

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

        # 5c. Deteksi kejadian ANGKAT TANGAN (aturan geometri, bukan model)
        # Aktif untuk camera_type "lorong"/"both" — kamera top-down (rak)
        # tidak relevan karena bahu/pinggul terkompresi perspektif.
        # Dilewati untuk pegawai terdaftar (sinyal minta-bantuan, bukan darurat).
        if run_gestures and camera_type != "rak" and not is_pegawai:
            angkat_events = deteksi_angkat_tangan(
                frames, src_fps,
                action_labels=action_per_fidx,
                durasi_min=gesture_durasi_min,
                toleransi_jeda=gesture_toleransi_jeda,
            )
            for ev in angkat_events:
                timeline.append({
                    "tipe": "angkat_tangan",
                    "t0": ev["t0"],
                    "t1": ev["t1"],
                    "durasi": ev["durasi"],
                    "track_id": int(track_id),
                })

        # 5b. Deteksi kejadian BUTUH BANTUAN
        # Dilewati untuk pegawai terdaftar (mereka bertugas menimbang/mengamati
        # rak, itu bukan indikasi butuh bantuan) — lihat pipeline/uniform.py.
        if inter_probs is not None and not is_pegawai:
            run_count, run_t0, run_t1 = 0, None, None
            best_prob = 0.0

            # Debug: log distribusi probabilitas semua kelas per jendela
            logger.info(f"Track {track_id} — {W} jendela, inspect_idx={inspect_idx}, dwell_ratio={dwell_ratio}")
            for w in range(min(W, 5)):  # log 5 jendela pertama saja
                probs_str = " ".join(f"{v:.2f}" for v in inter_probs[w])
                logger.info(f"  w={w}: probs=[{probs_str}], "
                            f"inspect_sum={sum(inter_probs[w,i] for i in inspect_idx):.3f}, "
                            f"is_dwell={is_dwell(raw_windows[w], dwell_ratio)}")

            for w, (wt0, wt1) in enumerate(window_times):
                inspect_prob = float(sum(inter_probs[w, i] for i in inspect_idx))
                stationary   = skip_dwell or is_dwell(raw_windows[w], dwell_ratio)

                # Kelas prediksi harus BENAR-BENAR "inspecting" (argmax == 1),
                # bukan ambang jumlah probabilitas — argmax langsung memakai
                # keputusan model 2-kelas, tanpa angka ambang tambahan yang
                # belum divalidasi.
                inspect_aktif = int(np.argmax(inter_probs[w])) in inspect_idx

                if skip_dwell:
                    # Kamera rak (top-down): is_dwell tidak dapat diandalkan
                    # karena torso terkompresi perspektif, jadi dilewati.
                    active = inspect_aktif
                else:
                    active = inspect_aktif and stationary

                if active:
                    if run_count == 0:
                        run_t0 = wt0
                    run_count += 1
                    run_t1 = wt1
                    best_prob = max(best_prob, inspect_prob)
                else:
                    if run_count >= help_min_win:
                        timeline.append({
                            "tipe": "butuh_bantuan",
                            "t0": float(run_t0),
                            "t1": float(run_t1),
                            "durasi_window": run_count,
                            "skor": round(best_prob, 3),
                            "track_id": int(track_id),
                        })
                    run_count, run_t0, run_t1, best_prob = 0, None, None, 0.0

            # Flush run yang masih jalan di akhir sekuens
            if run_count >= help_min_win:
                timeline.append({
                    "tipe": "butuh_bantuan",
                    "t0": float(run_t0),
                    "t1": float(run_t1),
                    "durasi_window": run_count,
                    "skor": round(best_prob, 3),
                    "track_id": int(track_id),
                })

        logger.debug(f"Track {track_id}: {T_orig} frame → {W} jendela diproses.")


    timeline.sort(key=lambda x: x["t0"])

    n_jatuh  = sum(1 for e in timeline if e["tipe"] == "jatuh")
    n_bantu  = sum(1 for e in timeline if e["tipe"] == "butuh_bantuan")
    n_angkat = sum(1 for e in timeline if e["tipe"] == "angkat_tangan")
    logger.info(f"Analisis selesai: {n_jatuh} jatuh, {n_bantu} butuh_bantuan, "
                f"{n_angkat} angkat_tangan dari {len(tracks)} track.")

    return {
        "timeline": timeline,
        "frame_annotations": frame_annotations,
        "src_fps": src_fps,
        "total_frames": total_frames,
        "status_pegawai": status_pegawai,   # {track_id: True} — untuk render() (label abu-abu)
    }
