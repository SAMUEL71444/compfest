"""
pipeline/extract.py — SAPA

Ekstraksi pose dari video menggunakan YOLOv8-pose + ByteTrack tracking.
YOLOv8-pose pretrained — tidak dilatih tim, otomatis diunduh oleh ultralytics.

Output: dict per track_id berisi sekuens keypoints mentah per orang.
"""

import cv2
import numpy as np
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Singleton YOLO — dimuat sekali saat pertama dipanggil
_yolo_model = None


def _get_yolo():
    """Lazy-load YOLOv8n-pose. Model di-cache sebagai singleton."""
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO
        logger.info("Memuat YOLOv8n-pose (pertama kali, mungkin butuh unduh)...")
        _yolo_model = YOLO("yolov8n-pose.pt")
        logger.info("YOLOv8n-pose siap.")
    return _yolo_model


def extract_poses(video_path: str, cfg: dict) -> dict:
    """
    Ekstraksi pose dari klip video menggunakan YOLOv8-pose + tracking.

    video_path: path ke file .mp4
    cfg: dict konfigurasi (dipakai untuk future params, saat ini tidak ada parameter extract)

    Returns: dict {
        track_id (int): {
            "frames": list of (frame_idx, keypoints[17, 3]),
            "fps": float,
            "total_frames": int,
        }
    }
    Catatan:
    - keypoints[j] = (x_piksel, y_piksel, confidence) — koordinat MENTAH
    - Hanya track dengan >= 10 frame yang dimasukkan (menghindari deteksi sementara)
    """
    video_path = str(video_path)
    model = _get_yolo()

    # Baca metadata video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Tidak bisa membuka video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    logger.info(f"Mengekstrak pose dari {Path(video_path).name} ({total_frames} frame, {fps:.1f} fps)...")

    # Jalankan YOLOv8 tracking
    tracks_raw: dict = {}  # {track_id: [(frame_idx, kps[17,3])]}

    results_gen = model.track(
        video_path,
        stream=True,
        persist=True,
        verbose=False,
        tracker="bytetrack.yaml",
    )

    for frame_idx, result in enumerate(results_gen):
        if result.keypoints is None:
            continue

        kps_data = result.keypoints.data  # tensor [N, 17, 3]
        boxes = result.boxes

        if kps_data is None or len(kps_data) == 0:
            continue

        for i in range(len(kps_data)):
            # Dapatkan track ID
            track_id = None
            if boxes is not None and boxes.id is not None and i < len(boxes.id):
                track_id = int(boxes.id[i].item())
            else:
                # Fallback: gunakan indeks deteksi sebagai pseudo-ID
                track_id = i * 1000 + frame_idx  # unik tapi tidak stabil antar frame

            kps = kps_data[i].cpu().numpy().astype(np.float32)  # [17, 3]

            if track_id not in tracks_raw:
                tracks_raw[track_id] = []
            tracks_raw[track_id].append((frame_idx, kps))

    # Filter track terlalu pendek (< 10 frame)
    min_frames = max(2, cfg.get("min_track_frames", 10))
    tracks_filtered = {
        tid: frames
        for tid, frames in tracks_raw.items()
        if len(frames) >= min_frames
    }

    logger.info(f"Ditemukan {len(tracks_filtered)} track valid (dari {len(tracks_raw)} total).")

    # Bangun output
    result_dict = {}
    for track_id, frames in tracks_filtered.items():
        # Urutkan berdasarkan frame_idx (seharusnya sudah urut, tapi pastikan)
        frames_sorted = sorted(frames, key=lambda x: x[0])
        result_dict[track_id] = {
            "frames": frames_sorted,
            "fps": fps,
            "total_frames": total_frames,
        }

    return result_dict


def extract_keypoints_per_frame(frame: np.ndarray) -> dict:
    """
    Ekstraksi keypoint dari satu frame BGR (OpenCV) — dipakai oleh live_server.py.

    Signature:
        frame: np.ndarray shape [H, W, 3] BGR (hasil cv2.imdecode atau VideoCapture.read)

    Returns:
        dict { track_id (int): np.ndarray shape [17, 3] }
        Keypoints dalam koordinat piksel mentah: (x, y, confidence)

    Catatan:
    - Menggunakan model singleton yang sama dengan extract_poses() — tidak dimuat ulang.
    - mode predict (bukan track) karena satu frame tidak punya konteks temporal.
      Track ID di sini adalah indeks deteksi (0-based). State tracker per-WS-session
      dikelola di TrackBuffer live_server.py.
    - Frame dengan confidence < 0.25 diabaikan.
    """
    model  = _get_yolo()
    result = model.predict(frame, verbose=False, conf=0.25)[0]

    out: dict[int, np.ndarray] = {}

    if result.keypoints is None or result.keypoints.data is None:
        return out

    kps_data = result.keypoints.data  # tensor [N, 17, 3]
    boxes    = result.boxes

    for i in range(len(kps_data)):
        # Untuk mode live, pakai box ID kalau ada (dari tracker terus-menerus),
        # fallback ke indeks deteksi
        track_id = i
        if boxes is not None and boxes.id is not None and i < len(boxes.id):
            track_id = int(boxes.id[i].item())

        kps = kps_data[i].cpu().numpy().astype(np.float32)  # [17, 3]
        out[track_id] = kps

    return out
