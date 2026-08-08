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


def extract_poses(video_path: str, cfg: dict, camera_type: str = "lorong") -> dict:
    """
    Ekstraksi pose dari klip video menggunakan YOLOv8-pose + tracking.

    video_path: path ke file .mp4
    cfg: dict konfigurasi
    camera_type: 'rak' = top-down (person lebih kecil), 'lorong' = samping

    Returns: dict {
        track_id (int): {
            "frames": list of (frame_idx, keypoints[17, 3]),
            "fps": float,
            "total_frames": int,
        }
    }
    """
    video_path = str(video_path)
    model = _get_yolo()

    # Baca metadata video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Tidak bisa membuka video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    frame_area = frame_w * frame_h

    # ── Filter untuk menghindari false positive (kamera/bayangan di sudut) ──────
    # Confidence minimum deteksi YOLO (naik dari default 0.25 untuk eliminasi noise)
    det_conf = float(cfg.get("det_conf", 0.45))

    # Minimum area bounding box (sebagai fraksi frame) — benda kecil di sudut diabaikan
    # Kamera rak: orang terlihat lebih kecil dari atas → pakai threshold lebih kecil
    if camera_type == "rak":
        min_bbox_ratio = float(cfg.get("min_bbox_ratio", 0.005))   # 0.5% frame
    else:
        min_bbox_ratio = float(cfg.get("min_bbox_ratio", 0.01))    # 1% frame
    min_bbox_area = frame_area * min_bbox_ratio

    # Minimum rata-rata confidence keypoint visible
    # (deteksi palsu biasanya punya keypoint confidence sangat rendah)
    min_kp_conf = float(cfg.get("min_kp_conf", 0.25))

    logger.info(
        f"Mengekstrak pose dari {Path(video_path).name} "
        f"({total_frames} frame, {fps:.1f} fps, {frame_w}×{frame_h}) "
        f"[conf≥{det_conf}, bbox≥{min_bbox_ratio*100:.1f}%frame, kp≥{min_kp_conf}]"
    )

    # Frame skip untuk video panjang
    frame_skip = max(1, int(round(fps / 15.0)))
    if frame_skip > 1:
        logger.info(f"Frame skip={frame_skip} (video {fps:.0f}fps → efektif {fps/frame_skip:.1f}fps)")

    # Jalankan YOLOv8 tracking
    tracks_raw: dict = {}

    results_gen = model.track(
        video_path,
        stream=True,
        persist=True,
        verbose=False,
        tracker="bytetrack.yaml",
        conf=det_conf,             # ← naikkan dari default 0.25
        vid_stride=frame_skip,
    )

    skipped_conf = 0
    skipped_bbox = 0
    skipped_kp   = 0

    for frame_idx, result in enumerate(results_gen):
        if result.keypoints is None:
            continue

        kps_data = result.keypoints.data   # tensor [N, 17, 3]
        boxes    = result.boxes

        if kps_data is None or len(kps_data) == 0:
            continue

        for i in range(len(kps_data)):
            # ── Filter 1: confidence bounding box ─────────────────────────
            if boxes is not None and boxes.conf is not None and i < len(boxes.conf):
                box_conf = float(boxes.conf[i].item())
                if box_conf < det_conf:
                    skipped_conf += 1
                    continue

            # ── Filter 2: ukuran bounding box (buang deteksi di sudut kecil) ─
            if boxes is not None and boxes.xywh is not None and i < len(boxes.xywh):
                bw = float(boxes.xywh[i][2].item())
                bh = float(boxes.xywh[i][3].item())
                bbox_area = bw * bh
                if bbox_area < min_bbox_area:
                    skipped_bbox += 1
                    logger.debug(
                        f"  frame={frame_idx} bbox terlalu kecil: {bbox_area:.0f}px² "
                        f"(min={min_bbox_area:.0f})"
                    )
                    continue

            # Dapatkan track ID
            track_id = None
            if boxes is not None and boxes.id is not None and i < len(boxes.id):
                track_id = int(boxes.id[i].item())
            else:
                track_id = -(i + 1)

            kps = kps_data[i].cpu().numpy().astype(np.float32)  # [17, 3]

            if kps.shape != (17, 3):
                continue

            # ── Filter 3: kualitas keypoint (buang deteksi ghost/noise) ───
            visible_confs = kps[:, 2][kps[:, 2] > 0.1]
            if len(visible_confs) == 0 or float(visible_confs.mean()) < min_kp_conf:
                skipped_kp += 1
                continue

            # ── Filter 4: minimum jumlah joint visible ─────────────────────
            # Stickman anomali hanya punya sedikit joint visible
            # Orang asli dari kamera rak minimal punya bahu + siku + pinggul = 6+ joint
            min_visible_kp = int(cfg.get("min_visible_kp", 6))
            n_visible = int(np.sum(kps[:, 2] > 0.20))
            if n_visible < min_visible_kp:
                skipped_kp += 1
                logger.debug(
                    f"  frame={frame_idx} terlalu sedikit joint: {n_visible} "
                    f"(min={min_visible_kp})"
                )
                continue

            if track_id not in tracks_raw:
                tracks_raw[track_id] = []
            tracks_raw[track_id].append((frame_idx, kps))

    logger.info(
        f"Filter: {skipped_conf} dibuang (conf), "
        f"{skipped_bbox} dibuang (bbox kecil), "
        f"{skipped_kp} dibuang (kp rendah)"
    )

    # Filter track terlalu pendek (< min_track_frames frame)
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
        frames_sorted = sorted(frames, key=lambda x: x[0])
        result_dict[track_id] = {
            "frames": frames_sorted,
            "fps": fps,
            "total_frames": total_frames,
        }

    return result_dict




# CATATAN: extract_keypoints_per_frame() dihapus.
#
# Fungsi itu memakai model.predict() sehingga "track_id" yang dikembalikannya
# sebenarnya hanya INDEKS DETEKSI dalam frame — angka yang berubah setiap kali
# urutan deteksi bergeser, bukan identitas yang melekat pada orang. Semua
# pemakainya membangun sekuens gerak per-orang di atas angka itu, sehingga satu
# buffer bisa berisi campuran beberapa manusia.
#
# Penggantinya menjalankan model.track(persist=True) dengan state tracker
# terpisah per sumber video:
#   - production/worker.py  CameraWorker._pose_dan_track()   (kamera CCTV)
#   - live_server.py        _pose_track()                    (webcam browser)
