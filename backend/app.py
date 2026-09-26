"""
app.py — SAPA Backend (FastAPI)

Endpoint:
  POST /analyze      → analisis klip video (sinkron), return timeline + URL video beranotasi
  GET  /outputs/{fn} → sajikan video beranotasi
  WS   /ws/live      → mode live: terima frame webcam, kirim pose + event real-time

  Mode produksi CCTV (opsional, lihat production/):
  /api/produksi/*    → manajemen multi-kamera, log kejadian, kesehatan sistem
  WS /ws/produksi/alert → alert langsung ke dashboard operator

Model dimuat SEKALI saat startup (bukan per request).

MODE PRODUKSI DIMATIKAN SECARA DEFAULT.
Aktifkan dengan SAPA_PRODUKSI=1. Alasannya: yang dinilai lomba adalah MVP offline
(unggah klip), dan menyalakan pekerja kamera 24/7 di lingkungan penilaian hanya
akan memakan CPU tanpa gunanya. Dengan gerbang ini, perilaku default backend
sama persis seperti sebelum lapisan produksi ditambahkan.
"""

import asyncio
import os
import uuid
import shutil
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pipeline.models import load_head
from pipeline.analyze import analyze
from pipeline.render import render
from pipeline.thresholds import ambil_preset, cfg_dari_preset
from pipeline import uniform as _uniform
from live_server import router as live_router
from production.api import router as produksi_router, ws_router as produksi_ws_router
from production.api import pasang_manager
from production.manager import CameraManager

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
)
logger = logging.getLogger("sapa.app")

def setup_loggers():
    formatter = logging.Formatter(LOG_FORMAT)
    for handler in logging.root.handlers:
        handler.setFormatter(formatter)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sapa.app", "pipeline.analyze", "pipeline.render", "pipeline.extract"):
        l = logging.getLogger(name)
        l.setLevel(logging.INFO)
        for h in l.handlers:
            h.setFormatter(formatter)

setup_loggers()

# ── Path ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
MODELS_DIR = BASE_DIR / "models"
OUTPUTS_DIR = BASE_DIR / "outputs"
UPLOADS_DIR = BASE_DIR / "uploads"
DATA_DIR = BASE_DIR / "data"

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ── Mode produksi CCTV (opsional) ─────────────────────────────────────────────
PRODUKSI_AKTIF = os.getenv("SAPA_PRODUKSI", "0").lower() in ("1", "true", "yes", "on")
PROFIL_KAMERA = Path(os.getenv("SAPA_PROFIL_KAMERA", DATA_DIR / "cameras.json"))
LOG_KEJADIAN = Path(os.getenv("SAPA_LOG_KEJADIAN", DATA_DIR / "kejadian.jsonl"))
RETENSI_JAM = float(os.getenv("SAPA_RETENSI_JAM", "72"))

# ── State global (model dimuat sekali) ────────────────────────────────────────
_state: dict = {
    "fall_model": None,
    "inter_model": None,
    "fall_cfg": {},
    "inter_cfg": {},
    "manager": None,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model saat startup, bersihkan saat shutdown."""
    setup_loggers()
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

    # ── Mode produksi CCTV ────────────────────────────────────────────────────
    if PRODUKSI_AKTIF:
        try:
            manager = CameraManager(
                path_profil=PROFIL_KAMERA,
                path_log_kejadian=LOG_KEJADIAN,
                retensi_jam=RETENSI_JAM,
            )
            manager.pasang_model(
                fall_model=_state["fall_model"],
                inter_model=_state["inter_model"],
            )
            # Pekerja kamera berjalan di thread; mesin alert butuh referensi ke
            # event loop ini untuk menyiarkan alert ke WebSocket dengan aman.
            manager.alert.pasang_loop(asyncio.get_running_loop())
            manager.mulai()

            _state["manager"] = manager
            pasang_manager(manager)
            logger.info(
                f"🎥 Mode produksi AKTIF — profil: {PROFIL_KAMERA}, retensi: {RETENSI_JAM} jam."
            )
        except Exception as e:
            logger.exception(f"❌ Gagal menyalakan mode produksi: {e}")
    else:
        logger.info("Mode produksi nonaktif (set SAPA_PRODUKSI=1 untuk mengaktifkan).")

    yield  # aplikasi berjalan

    manager = _state.get("manager")
    if manager is not None:
        try:
            manager.berhenti()
        except Exception as e:
            logger.warning(f"Gagal menghentikan mode produksi dengan rapi: {e}")

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

# Mode Produksi CCTV — endpoint selalu terdaftar agar terdokumentasi di /docs,
# tapi mengembalikan 503 bila SAPA_PRODUKSI belum diaktifkan.
app.include_router(produksi_router)
app.include_router(produksi_ws_router)

# Sajikan folder outputs sebagai file statis
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")


# ── Endpoint ──────────────────────────────────────────────────────────────────

@app.get("/")
def akar():
    """
    Penunjuk arah, bukan halaman aplikasi.

    Membuka http://localhost:8000 di browser sebelumnya menghasilkan 404 karena
    backend memang tidak menyajikan halaman — antarmuka ada di frontend (port
    5173 saat dev, 80 di dalam Docker). 404 itu benar secara teknis tapi
    menyesatkan: ia tampak seperti aplikasi rusak, dan ikut terekam sebagai
    baris merah di log saat demonstrasi.
    """
    return {
        "layanan": "SAPA API",
        "status": "ok",
        "catatan": "Ini API, bukan antarmuka. Buka aplikasinya di http://localhost:5173",
        "dokumentasi": "/docs",
        "endpoint_utama": {
            "analisis_klip": "POST /analyze",
            "kesehatan": "GET /health",
        },
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Browser selalu meminta ini; balas 204 agar log tidak penuh 404 palsu."""
    return Response(status_code=204)


@app.get("/health")
def health():
    """Cek status server dan model."""
    manager = _state.get("manager")
    return {
        "status": "ok",
        "fall_model_loaded": _state["fall_model"] is not None,
        "inter_model_loaded": _state["inter_model"] is not None,
        "produksi_aktif": manager is not None,
        "kamera_berjalan": (
            manager.kesehatan()["kamera_berjalan"] if manager is not None else 0
        ),
    }


@app.get("/statistik")
def statistik_penanganan():
    """
    Ringkasan statistik penanganan kejadian (permanen, lintas sesi Live).
    Dibaca halaman /statistik untuk manajer. Aman bila belum ada data.

    Diakses frontend via /api/statistik (prefiks /api dibuang nginx & proxy Vite).
    """
    import statistik as _statistik
    return _statistik.ringkasan()


@app.delete("/statistik")
def hapus_statistik():
    """
    Hapus seluruh histori penanganan (DESTRUKTIF, permanen).
    Dipanggil dari halaman /statistik lewat tombol "Hapus Histori" (berkonfirmasi).
    """
    import statistik as _statistik
    import notifier as _notifier
    jumlah = _statistik.hapus_semua()
    # Bersihkan juga penanda kejadian yang sudah ditangani di notifier, agar
    # deteksi ulang setelah reset bisa diproses lagi.
    try:
        _notifier._sudah_ditangani.clear()
        _notifier._pesan_terkirim.clear()
    except Exception:
        pass
    return {"dihapus": jumlah}


SERAGAM_PATH = DATA_DIR / "seragam.json"


def _decode_gambar_upload(data: bytes):
    """Decode bytes upload jadi array BGR OpenCV. None bila gagal."""
    import cv2
    import numpy as np
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


async def _registrasi_seragam(
    nama: str,
    files: list,
    sudah_dicrop: bool,
):
    """Logika bersama untuk registrasi seragam — dipanggil dari kedua path
    (/seragam/frame dan /api/seragam/frame, lihat §3 KONTEKS soal proxy)."""
    if not files:
        raise HTTPException(status_code=400, detail="Minimal 1 foto/crop diperlukan.")
    if len(files) > 3:
        raise HTTPException(status_code=400, detail="Maksimal 3 foto per registrasi.")

    patches = []
    for f in files:
        data = await f.read()
        img = _decode_gambar_upload(data)
        if img is None:
            continue
        if sudah_dicrop:
            # Frontend sudah memotong area torso di browser — pakai langsung.
            patches.append(img)
        else:
            # Foto penuh: perlu deteksi pose dulu untuk menemukan torso.
            # Diminta eksplisit sudah_dicrop=True dari alur crop-di-browser
            # supaya backend tidak memotong ulang secara keliru; untuk foto
            # penuh tanpa crop, ekstraksi pose satu-frame belum diimplementasi
            # di endpoint ini — minta pemanggil crop dulu.
            raise HTTPException(
                status_code=400,
                detail="Kirim area yang sudah dipotong (torso) dengan sudah_dicrop=true. "
                       "Registrasi dari foto penuh belum didukung endpoint ini.",
            )

    sig = _uniform.buat_signature(patches)
    if sig is None:
        raise HTTPException(
            status_code=400,
            detail=f"Semua patch terlalu kecil (< {_uniform.MIN_TORSO_AREA_PX}px area) "
                   "untuk histogram yang stabil. Perbesar area crop atau dekatkan kamera.",
        )

    daftar = _uniform.muat_daftar_signature(SERAGAM_PATH)
    entry_id = str(uuid.uuid4())[:8]
    daftar.append({"id": entry_id, "nama": nama, "signature": sig.to_dict()})
    _uniform.simpan_daftar_signature(SERAGAM_PATH, daftar)

    # Privacy-by-design: foto/patch sumber TIDAK disimpan ke disk, hanya
    # signature (histogram + fitur pola) yang persisten. `patches` cuma
    # ada di memori proses ini dan dibuang begitu request selesai.
    return {"id": entry_id, "nama": nama, "n_sampel": sig.n_sampel, "total_terdaftar": len(daftar)}


@app.post("/seragam/frame")
async def daftar_seragam(
    nama: str = Form(...),
    files: list[UploadFile] = File(...),
    sudah_dicrop: bool = Form(True),
):
    """Registrasi seragam pegawai dari 1-3 crop torso. Lihat pipeline/uniform.py
    untuk detail cara kerja pencocokan."""
    return await _registrasi_seragam(nama, files, sudah_dicrop)


@app.post("/api/seragam/frame")
async def api_daftar_seragam(
    nama: str = Form(...),
    files: list[UploadFile] = File(...),
    sudah_dicrop: bool = Form(True),
):
    """Sama seperti /seragam/frame — didaftarkan dua path karena nginx dan
    Vite membuang prefiks /api sebelum permintaan sampai ke backend."""
    return await _registrasi_seragam(nama, files, sudah_dicrop)


def _daftar_pegawai_ringkas():
    daftar = _uniform.muat_daftar_signature(SERAGAM_PATH)
    return {"pegawai": [{"id": p["id"], "nama": p["nama"], "n_sampel": p["signature"].get("n_sampel", 1)} for p in daftar]}


@app.get("/seragam")
def daftar_seragam_terdaftar():
    """Daftar pegawai terdaftar (tanpa signature mentah, cuma ringkasan)."""
    return _daftar_pegawai_ringkas()


@app.get("/api/seragam")
def api_daftar_seragam_terdaftar():
    return _daftar_pegawai_ringkas()


@app.delete("/seragam/{pegawai_id}")
def hapus_seragam(pegawai_id: str):
    """Hapus satu pegawai terdaftar dari data/seragam.json."""
    daftar = _uniform.muat_daftar_signature(SERAGAM_PATH)
    sisa = [p for p in daftar if p["id"] != pegawai_id]
    if len(sisa) == len(daftar):
        raise HTTPException(status_code=404, detail="ID pegawai tidak ditemukan.")
    _uniform.simpan_daftar_signature(SERAGAM_PATH, sisa)
    return {"dihapus": pegawai_id, "sisa": len(sisa)}


@app.delete("/api/seragam/{pegawai_id}")
def api_hapus_seragam(pegawai_id: str):
    return hapus_seragam(pegawai_id)


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



    # Threshold deteksi jatuh — dipusatkan di pipeline/thresholds.py supaya
    # unggah, Live, dan Produksi memakai definisi yang sama. Lihat docstring
    # modul itu untuk kalibrasi & buktinya.
    preset_ambang = cfg_dari_preset(ambil_preset())

    cfg = {
        "run_fall": run_fall,
        "run_interaction": run_interaction,
        **preset_ambang,   # fall_thr, fall_confirm, fall_angle
        "fall_joints": fall_joints,
        # Model 2-kelas (other=0, inspecting=1) — lihat interaction_head.json.
        # Ambil dari config model, JANGAN di-hardcode.
        "inspect_idx": _state["inter_cfg"].get("inspect_idx", [1]),
        # Untuk kamera rak: 1 window cukup (is_dwell di-skip, false positive rendah)
        # Untuk kamera lorong: butuh 2 window berturut (tanpa dwell skip)
        # Minimal jendela berturut sebelum dianggap kejadian. Satu jendela
        # cukup untuk kedipan model; "butuh bantuan" secara konsep berarti
        # seseorang menimbang produk BEBERAPA SAAT, bukan sekilas menoleh.
        # Kepala Interaksi.ipynb memakai 3; di sini 2 sebagai kompromi, karena
        # jendela di web bergeser 1 detik (stride 15 @ 15fps) sehingga 2 jendela
        # sudah berarti aktivitas bertahan sekitar 2 detik.
        "help_min_win": 2,
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
        # Exclude pegawai terdaftar dari butuh_bantuan/angkat_tangan — lihat
        # pipeline/uniform.py. Path selalu dikirim; analyze() sendiri yang
        # memutuskan tidak ada apa-apa untuk dicek bila file belum ada/kosong.
        "path_seragam": SERAGAM_PATH,
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
