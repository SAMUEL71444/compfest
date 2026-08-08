"""
app.py — SAPA Backend (FastAPI)

Endpoint:
  POST /analyze      → analisis klip video (sinkron), return timeline + URL video beranotasi
  GET  /outputs/{fn} → sajikan video beranotasi
  WS   /ws/live      → mode live: terima frame webcam, kirim pose + event real-time

Model dimuat SEKALI saat startup (bukan per request).
"""

import os
import uuid
import shutil
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pipeline.models import load_head
from pipeline.analyze import analyze
from pipeline.render import render
from live_server import router as live_router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sapa.app")

# ── Path ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
MODELS_DIR = BASE_DIR / "models"
OUTPUTS_DIR = BASE_DIR / "outputs"
UPLOADS_DIR = BASE_DIR / "uploads"

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ── State global (model dimuat sekali) ────────────────────────────────────────
_state: dict = {
    "fall_model": None,
    "inter_model": None,
    "fall_cfg": {},
    "inter_cfg": {},
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model saat startup, bersihkan saat shutdown."""
    fall_pt = MODELS_DIR / "fall_head.pt"
    fall_json = MODELS_DIR / "fall_head.json"
    inter_pt = MODELS_DIR / "interaction_head.pt"
    inter_json = MODELS_DIR / "interaction_head.json"

    if fall_pt.exists() and fall_json.exists():
        try:
            _state["fall_model"], _state["fall_cfg"] = load_head(str(fall_pt), str(fall_json))
            logger.info("✅ Fall model berhasil dimuat.")
        except Exception as e:
            logger.error(f"❌ Gagal muat fall model: {e}")
    else:
        logger.warning("⚠️  fall_head.pt atau fall_head.json tidak ditemukan — deteksi jatuh dinonaktifkan.")

    if inter_pt.exists() and inter_json.exists():
        try:
            _state["inter_model"], _state["inter_cfg"] = load_head(str(inter_pt), str(inter_json))
            logger.info("✅ Interaction model berhasil dimuat.")
        except Exception as e:
            logger.error(f"❌ Gagal muat interaction model: {e}")
    else:
        logger.warning("⚠️  interaction_head.pt atau interaction_head.json tidak ditemukan — deteksi pelayanan dinonaktifkan.")

    yield  # aplikasi berjalan

    logger.info("SAPA backend shutdown.")


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="SAPA API",
    description="Safety and Assistance through Pose Analytics — analitik toko berbasis pose (privacy-by-design).",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mode Live — WebSocket /ws/live
app.include_router(live_router)

# Sajikan folder outputs sebagai file statis
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")


# ── Endpoint ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Cek status server dan model."""
    return {
        "status": "ok",
        "fall_model_loaded": _state["fall_model"] is not None,
        "inter_model_loaded": _state["inter_model"] is not None,
    }


@app.get("/api/status")
def api_status():
    """
    Status ketersediaan model untuk ditampilkan di frontend.
    Return:
      fall_model    : bool — Kepala Jatuh (fall_head.pt) siap
      inter_model   : bool — Kepala Interaksi (interaction_head.pt) siap
      pipeline_ready: bool — minimal YOLO tersedia (YOLOv8 selalu ready jika terinstal)
    """
    return {
        "fall_model":     _state["fall_model"] is not None,
        "inter_model":    _state["inter_model"] is not None,
        "pipeline_ready": True,  # YOLOv8-pose selalu di-load lazy saat pertama infer
    }


@app.post("/analyze")
async def analyze_video(
    file: UploadFile = File(..., description="File video .mp4"),
    camera_type: str = Form(
        "both",
        description=(
            "Jenis kamera: "
            "'lorong' (deteksi jatuh, kamera samping), "
            "'rak' (deteksi pelayanan, kamera atas/top-down), "
            "'both' (keduanya aktif, default)"
        ),
    ),
):
    """
    Analisis klip video CCTV.

    - Unggah file .mp4 via multipart/form-data
    - Pilih jenis kamera untuk mengaktifkan deteksi yang sesuai
    - Proses sinkron — klip panjang (>2 menit) bisa memakan waktu beberapa menit
    - Kembalikan timeline kejadian + URL video beranotasi
    """
    # Validasi format file
    filename = file.filename or "video.mp4"
    suffix = Path(filename).suffix.lower()
    if suffix not in {".mp4", ".avi", ".mov", ".mkv"}:
        raise HTTPException(status_code=400, detail=f"Format tidak didukung: {suffix}. Gunakan .mp4")

    # Validasi camera_type
    if camera_type not in {"lorong", "rak", "both"}:
        raise HTTPException(status_code=400, detail="camera_type harus 'lorong', 'rak', atau 'both'.")

    # Simpan file upload
    uid = str(uuid.uuid4())[:8]
    stem = Path(filename).stem
    upload_path = UPLOADS_DIR / f"{stem}_{uid}.mp4"

    try:
        with open(upload_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        logger.info(f"Video diunggah: {upload_path.name} ({upload_path.stat().st_size // 1024} KB)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menyimpan file: {e}")

    # Bangun konfigurasi berdasarkan jenis kamera
    run_fall = camera_type in ("lorong", "both")
    run_interaction = camera_type in ("rak", "both")

    # Ambil fall_joints dari config model jika tersedia
    fall_joints = _state["fall_cfg"].get("fall_joints", list(range(5, 17)))



    cfg = {
        "run_fall": run_fall,
        "run_interaction": run_interaction,
        # Threshold deteksi jatuh
        "fall_thr":    0.80,
        "fall_angle":  35.0,        # turunkan dari 55° agar tidak false positive
        "fall_confirm": True,
        "fall_joints": fall_joints,
        # MERL classes: 0=background,1=reach,2=retract,3=hand_in_shelf,4=inspect_product,5=inspect_shelf
        # Ambil dari config model, JANGAN di-hardcode. Kepala Interaksi.ipynb
        # menetapkan INSPECT_IDX = [4, 5] ("aksi yang penting utk butuh bantuan")
        # dan menyimpannya ke interaction_head.json. Nilai [1, 3, 4, 5] yang
        # dipakai sebelumnya ikut memasukkan kelas 1 = "reach" — mengambil barang
        # dari rak adalah belanja normal, bukan tanda seseorang butuh bantuan,
        # sehingga deteksi jadi jauh lebih berisik daripada yang dimaksud tim.
        "inspect_idx": _state["inter_cfg"].get("inspect_idx", [4, 5]),
        # Untuk kamera rak: 1 window cukup (is_dwell di-skip, false positive rendah)
        # Untuk kamera lorong: butuh 2 window berturut (tanpa dwell skip)
        "help_min_win": 1 if camera_type == "rak" else 2,
        # Geometri diam/dwell — top-down: skip sepenuhnya (lihat analyze.py skip_dwell)
        "dwell_ratio": 3.0 if camera_type == "rak" else 0.4,
        # Pipeline normalisasi
        "target_fps": 15,
        "window": 45,
        "stride": 15,
        # Ekstraksi — filter false positive kamera sudut
        "min_track_frames": 10,
        "det_conf": 0.45,
        "min_bbox_ratio": 0.005 if camera_type == "rak" else 0.01,
        "min_kp_conf": 0.25,
        "min_visible_kp": 6,    # minimal 6 joint visible untuk bukan ghost
    }


    output_filename = f"{stem}_{uid}_anotasi.mp4"
    output_path = OUTPUTS_DIR / output_filename

    try:
        logger.info(f"Mulai analisis [{camera_type}]: {upload_path.name}")

        # Tentukan mode berdasarkan model yang tersedia
        effective_run_fall = run_fall and _state["fall_model"] is not None
        effective_run_inter = run_interaction and _state["inter_model"] is not None

        if not effective_run_fall and run_fall:
            logger.warning("fall_head.pt tidak tersedia — deteksi jatuh dilewati.")
        if not effective_run_inter and run_interaction:
            logger.warning("interaction_head.pt tidak tersedia — deteksi interaksi dilewati.")

        # Analisis — camera_type menentukan kepala mana yg aktif (rak=no fall, lorong=no inter)
        result = analyze(
            str(upload_path),
            cfg,
            fall_model=_state["fall_model"] if effective_run_fall else None,
            inter_model=_state["inter_model"] if effective_run_inter else None,
            camera_type=camera_type,
        )


        # Render video beranotasi
        render(str(upload_path), result, str(output_path), camera_type=camera_type)


        # Hitung ringkasan
        n_jatuh = sum(1 for e in result["timeline"] if e["tipe"] == "jatuh")
        n_bantuan = sum(1 for e in result["timeline"] if e["tipe"] == "butuh_bantuan")

        logger.info(f"Selesai: {n_jatuh} jatuh, {n_bantuan} butuh_bantuan → {output_filename}")

        return JSONResponse({
            "video": filename,
            "fps": result["src_fps"],
            "timeline": result["timeline"],
            "annotated_video_url": f"/outputs/{output_filename}",
            "model_mode": {
                "fall": effective_run_fall,
                "interaction": effective_run_inter,
            },
            "summary": {
                "jatuh": n_jatuh,
                "butuh_bantuan": n_bantuan,
                "total_track": len(set(e["track_id"] for e in result["timeline"])),
            },
        })

    except Exception as e:
        logger.exception(f"Error saat menganalisis {upload_path.name}: {e}")
        # Hapus output yang mungkin setengah jadi
        if output_path.exists():
            output_path.unlink()
        raise HTTPException(status_code=500, detail=f"Analisis gagal: {str(e)}")

    finally:
        # Selalu hapus file upload setelah selesai
        if upload_path.exists():
            upload_path.unlink()
