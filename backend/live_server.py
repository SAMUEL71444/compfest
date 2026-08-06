"""
live_server.py — SAPA
Router FastAPI untuk mode Live (WebSocket /ws/live).

Protokol (sesuai addendum B.2):
  Browser → Server (tiap ~200ms):
    { "type": "frame", "image": "data:image/jpeg;base64,...", "t": 12.34,
      "camera_type": "lorong" | "rak" }

  Server → Browser:
    { "type": "pose",  "t": 12.34, "tracks": { "3": [[x,y,conf], ...×17] } }
    { "type": "event", "tipe": "jatuh"|"butuh_bantuan",
      "t0": .., "t1": .., "track_id": .. }

Arsitektur:
- Satu WebSocket per sesi klien (satu browser tab).
- State tracker per-koneksi disimpan di TrackBuffer (dalam memori WS handler,
  tidak ada shared state global → aman untuk concurrent connections).
- Reuse pipeline yang sama dengan mode upload:
  extract_keypoints_per_frame → normalize → models → geometry
- Threshold klasifikasi sama dengan analyze.py.

run_local_capture():
- Untuk edge deployment / demo CCTV asli.
- source=0 (webcam) atau source="rtsp://..." (kamera IP).
- Jalankan terpisah: python live_server.py
"""

import asyncio
import base64
import json
import logging
import os
from collections import defaultdict, deque

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# ── Router FastAPI ─────────────────────────────────────────────────────────────
router = APIRouter()

# ── Konfigurasi (sama dengan analyze.py) ──────────────────────────────────────
WINDOW_SIZE   = int(os.getenv("WINDOW_SIZE",   45))   # frame per jendela BiLSTM
STRIDE        = int(os.getenv("STRIDE",        15))   # langkah geser jendela
FALL_THRESH   = float(os.getenv("FALL_THRESH",   0.55))
DWELL_THRESH  = float(os.getenv("DWELL_THRESH",  0.60))
TORSO_THRESH  = float(os.getenv("TORSO_THRESH",  45.0))  # derajat
DWELL_SECONDS = float(os.getenv("DWELL_SECONDS", 3.0))
FPS_LIVE      = 5.0   # frame rate efektif yang diterima server (1000ms / 200ms)


class TrackBuffer:
    """
    Buffer keypoint per track untuk satu sesi WebSocket.
    Menyimpan deque keypoints mentah [17,3] per track_id.
    """

    def __init__(self, window_size: int = WINDOW_SIZE):
        self.window_size = window_size
        # {track_id: deque([[17,3], ...])}
        self.buffers: dict[int, deque] = defaultdict(
            lambda: deque(maxlen=window_size * 4)  # simpan 4× jendela untuk stride
        )
        # Sudah diproses pada pointer terakhir
        self.last_processed: dict[int, int] = defaultdict(int)

    def push(self, track_id: int, keypoints: np.ndarray):
        """Tambahkan satu frame keypoints [17,3] ke buffer track."""
        self.buffers[track_id].append(keypoints.copy())

    def ready_tracks(self) -> list[int]:
        """Kembalikan track yang punya cukup frame baru untuk jendela berikutnya."""
        ready = []
        for tid, buf in self.buffers.items():
            n = len(buf)
            last = self.last_processed[tid]
            if n >= self.window_size and n - last >= STRIDE:
                ready.append(tid)
        return ready

    def get_window(self, track_id: int) -> np.ndarray:
        """
        Ambil jendela 45-frame terakhir dari buffer.
        Returns: np.ndarray [WINDOW_SIZE, 17, 3]
        """
        buf = list(self.buffers[track_id])
        # Pakai 45 frame terakhir
        window = buf[-self.window_size:] if len(buf) >= self.window_size else buf
        # Edge-pad jika kurang
        while len(window) < self.window_size:
            window.insert(0, window[0])
        arr = np.stack(window, axis=0).astype(np.float32)  # [45, 17, 3]
        self.last_processed[track_id] = len(self.buffers[track_id])
        return arr


def _load_pipeline_models():
    """
    Lazy-import pipeline dan muat model saat pertama dibutuhkan.
    Model YOLO dan BiLSTM di-cache via singleton masing-masing.
    """
    from pipeline.models import load_head
    from pipeline.normalize import build_windows_for_heads
    from pipeline.geometry import torso_angle as _torso_angle, is_dwell
    return load_head, build_windows_for_heads, _torso_angle, is_dwell


async def process_track_window(
    ws: WebSocket,
    track_id: int,
    window: np.ndarray,   # [45, 17, 3] — koordinat MENTAH
    camera_type: str,
    t_now: float,
    fall_head,
    interaction_head,
) -> None:
    """
    Jalankan inferensi BiLSTM untuk satu jendela satu track.
    Kirim event ke browser jika threshold terlampaui.
    Ini sync (torch inference) tapi dipanggil dari thread executor agar tidak block WS loop.
    """
    from pipeline.normalize import build_windows_for_heads
    from pipeline.geometry import torso_angle as raw_torso_angle, is_dwell

    try:
        # Normalisasi + bangun tensor input per kepala
        fall_windows, interaction_windows = build_windows_for_heads(
            window,
            window_size=WINDOW_SIZE,
            stride=WINDOW_SIZE,   # single jendela
        )

        # ── Kepala Jatuh ────────────────────────────────────────────
        if camera_type != "rak" and fall_head is not None and len(fall_windows) > 0:
            from pipeline.models import predict_proba
            import torch
            fall_tensor = torch.tensor(fall_windows, dtype=torch.float32)
            proba = predict_proba(fall_head, fall_tensor)  # [N, 3]
            fall_score = float(proba[0, 2])  # kelas 2 = jatuh

            # Verifikasi geometri: sudut torso
            torso_deg = raw_torso_angle(window[-1])  # frame terakhir
            if torso_deg is not None:
                torso_ok = abs(torso_deg) > TORSO_THRESH
            else:
                torso_ok = True  # tidak bisa verifikasi → lewatkan saja

            if fall_score >= FALL_THRESH and torso_ok:
                await ws.send_json({
                    "type":     "event",
                    "tipe":     "jatuh",
                    "track_id": track_id,
                    "t0":       round(t_now - WINDOW_SIZE / FPS_LIVE, 2),
                    "t1":       round(t_now, 2),
                    "skor":     round(fall_score, 3),
                })
                logger.info(f"[live] Jatuh track={track_id} skor={fall_score:.2f} torso={torso_deg}°")

        # ── Kepala Interaksi ─────────────────────────────────────────
        if camera_type != "lorong" and interaction_head is not None and len(interaction_windows) > 0:
            from pipeline.models import predict_proba
            import torch
            inter_tensor = torch.tensor(interaction_windows, dtype=torch.float32)
            proba = predict_proba(interaction_head, inter_tensor)  # [N, 6]
            # Kelas 3..5 = hand_in_shelf, inspect_product, inspect_shelf → aktivitas di rak
            rak_score = float(proba[0, 3:].max())

            # Verifikasi dwell (diam lama)
            dwell_ok = is_dwell(window[:, 11:13, :2], fps=FPS_LIVE, seconds=DWELL_SECONDS)

            if rak_score >= DWELL_THRESH and dwell_ok:
                await ws.send_json({
                    "type":       "event",
                    "tipe":       "butuh_bantuan",
                    "track_id":   track_id,
                    "t0":         round(t_now - WINDOW_SIZE / FPS_LIVE, 2),
                    "t1":         round(t_now, 2),
                })
                logger.info(f"[live] Butuh bantuan track={track_id} rak_skor={rak_score:.2f}")

    except Exception as e:
        logger.warning(f"[live] process_track_window error track={track_id}: {e}")


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """
    Endpoint WebSocket utama mode live.
    Satu sesi per klien — state buffer tidak dibagi antar koneksi.
    """
    await websocket.accept()
    logger.info("[live] Klien terhubung.")

    # Muat model (singleton — tidak dimuat ulang kalau sudah ada)
    try:
        from pipeline.models import load_head, predict_proba  # noqa
        fall_head        = load_head("fall")
        interaction_head = load_head("interaction")
    except Exception as e:
        logger.warning(f"[live] Gagal muat BiLSTM heads: {e}. Mode stub (pose only).")
        fall_head        = None
        interaction_head = None

    from pipeline.extract import extract_keypoints_per_frame

    buf = TrackBuffer(window_size=WINDOW_SIZE)
    loop = asyncio.get_event_loop()

    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
            except asyncio.TimeoutError:
                # Klien tidak kirim frame selama 10 detik → anggap mati
                break

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") != "frame":
                continue

            image_b64  = msg.get("image", "")
            t_now      = float(msg.get("t", 0.0))
            camera_type = msg.get("camera_type", "both")

            # Decode gambar JPEG base64
            try:
                header, data = image_b64.split(",", 1) if "," in image_b64 else ("", image_b64)
                img_bytes = base64.b64decode(data)
                arr = np.frombuffer(img_bytes, np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is None:
                    continue
            except Exception as e:
                logger.debug(f"[live] Decode frame gagal: {e}")
                continue

            # Ekstraksi pose — di thread terpisah agar tidak block event loop
            try:
                track_kps = await loop.run_in_executor(
                    None, extract_keypoints_per_frame, frame
                )
            except Exception as e:
                logger.debug(f"[live] extract_keypoints_per_frame error: {e}")
                continue

            # Push ke buffer
            for tid, kps in track_kps.items():
                buf.push(tid, kps)

            # Kirim pose ke browser untuk overlay langsung
            tracks_json = {
                str(tid): kps.tolist()
                for tid, kps in track_kps.items()
            }
            await websocket.send_json({
                "type":   "pose",
                "t":      round(t_now, 3),
                "tracks": tracks_json,
            })

            # Jalankan inferensi untuk track yang siap (non-blocking)
            for tid in buf.ready_tracks():
                window = buf.get_window(tid)
                await loop.run_in_executor(
                    None,
                    lambda tid=tid, w=window: asyncio.run_coroutine_threadsafe(
                        process_track_window(
                            websocket, tid, w, camera_type, t_now,
                            fall_head, interaction_head,
                        ),
                        loop,
                    ).result()
                )

    except WebSocketDisconnect:
        logger.info("[live] Klien terputus.")
    except Exception as e:
        logger.warning(f"[live] Error sesi WS: {e}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("[live] Sesi WS ditutup.")


# ── run_local_capture() ────────────────────────────────────────────────────────
def run_local_capture(source=0, camera_type: str = "lorong"):
    """
    Mode edge deployment — jalankan analisis langsung dari webcam atau RTSP.

    source: 0 (webcam lokal) atau "rtsp://user:pass@ip:554/stream" (kamera IP)
    camera_type: "lorong" | "rak"

    Tekan 'q' untuk berhenti.
    Contoh jalankan: python live_server.py
    """
    from pipeline.extract import extract_keypoints_per_frame
    from pipeline.models import load_head

    try:
        fall_head        = load_head("fall")
        interaction_head = load_head("interaction")
    except Exception as e:
        print(f"[local] Gagal muat model: {e}. Lanjut mode pose-only.")
        fall_head        = None
        interaction_head = None

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"Tidak bisa membuka source: {source}")
        return

    print(f"[local] Memulai capture dari: {source} | kamera_type={camera_type}")
    print("[local] Tekan 'q' untuk berhenti.")

    local_buf = TrackBuffer()
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1

        # Ekstraksi pose
        track_kps = extract_keypoints_per_frame(frame)

        # Gambar overlay sederhana (untuk preview lokal)
        for tid, kps in track_kps.items():
            local_buf.push(tid, kps)
            for (x, y, c) in kps:
                if c > 0.3:
                    cv2.circle(frame, (int(x), int(y)), 4, (47, 107, 88), -1)

        # Overlay label
        cv2.putText(frame, f"frame={frame_count} tracks={len(track_kps)}",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (35, 38, 31), 1)

        cv2.imshow("SAPA — Local Capture", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[local] Capture selesai.")


if __name__ == "__main__":
    import sys
    source = sys.argv[1] if len(sys.argv) > 1 else 0
    cam    = sys.argv[2] if len(sys.argv) > 2 else "lorong"
    run_local_capture(source=source, camera_type=cam)
