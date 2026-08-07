"""
production/api.py — SAPA Produksi

REST + WebSocket untuk dashboard operator (KONTEKS §6).

DUA BENTUK URL — JANGAN TERTUKAR
--------------------------------
Backend menyajikan route ini di bawah prefiks `/produksi`, mengikuti konvensi
endpoint lain (`/analyze`, `/health`) yang juga tanpa `/api`. Prefiks `/api`
adalah konvensi SISI FRONTEND: baik nginx (`location /api/`) maupun proxy dev
Vite membuangnya sebelum meneruskan ke backend.

    Langsung ke backend  :  http://localhost:8000/produksi/kamera
    Lewat dashboard      :  http://localhost:5173/api/produksi/kamera

Hal yang sama berlaku untuk WebSocket: backend melayani `/ws/produksi/alert`,
sedangkan browser menyambung ke `/api/ws/produksi/alert`.

Peta endpoint (relatif terhadap prefiks /produksi):
    GET    /kamera                    daftar kamera + status
    POST   /kamera                    tambah kamera
    GET    /kamera/{id}               detail satu kamera
    PATCH  /kamera/{id}               ubah profil (pekerja dinyalakan ulang otomatis)
    DELETE /kamera/{id}               hapus kamera
    POST   /kamera/{id}/mulai         nyalakan
    POST   /kamera/{id}/berhenti      matikan
    GET    /kamera/{id}/pratinjau     aliran MJPEG (kerangka saja secara default)
    GET    /kejadian                  log kejadian (metadata saja)
    POST   /kejadian/{id}/tanggapi    human-in-the-loop: konfirmasi / abaikan
    GET    /kesehatan                 kesehatan sistem & tiap kamera
    WS     /ws/produksi/alert         alert langsung ke dashboard

CATATAN KEAMANAN
----------------
Router ini TIDAK memiliki autentikasi. Untuk pemasangan nyata ia harus berada di
balik autentikasi + kontrol akses (KONTEKS §7: "kontrol akses & audit untuk siapa
yang melihat alert"), misalnya reverse proxy ber-auth di jaringan toko. Endpoint
di sini dapat menyalakan/mematikan kamera dan melihat pratinjau, jadi jangan
diekspos langsung ke internet.
"""

import asyncio
import logging

from fastapi import APIRouter, Body, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from .alerts import STATUS_DIABAIKAN, STATUS_DIKONFIRMASI
from .manager import CameraManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/produksi", tags=["produksi"])
ws_router = APIRouter(tags=["produksi"])

# Diisi app.py saat startup.
_manager: CameraManager | None = None

# Laju frame pratinjau. Sengaja lebih rendah dari laju proses: pratinjau untuk
# verifikasi mata manusia, bukan untuk analisis — tidak perlu memakan bandwidth.
_FPS_PRATINJAU = 8.0


def pasang_manager(m: CameraManager) -> None:
    global _manager
    _manager = m


def _mgr() -> CameraManager:
    if _manager is None:
        raise HTTPException(
            status_code=503,
            detail="Sistem produksi belum aktif. Set SAPA_PRODUKSI=1 lalu jalankan ulang backend.",
        )
    return _manager


# ── Kamera ────────────────────────────────────────────────────────────────────

@router.get("/kamera")
def daftar_kamera():
    """Semua kamera terdaftar beserta status berjalan/tidak."""
    m = _mgr()
    hasil = []
    for p in m.store.semua():
        d = p.to_dict()
        d["berjalan"] = m.berjalan(p.id)
        d["sumber"] = p.sumber_aman()      # jangan bocorkan kredensial RTSP
        hasil.append(d)
    return {"kamera": hasil, "jumlah": len(hasil)}


@router.post("/kamera", status_code=201)
def tambah_kamera(data: dict = Body(...)):
    """
    Tambah kamera baru.

    Wajib: id, nama, sumber
    Penting: jenis — "lorong" (kamera samping → deteksi jatuh) atau
             "rak" (kamera top-down → deteksi butuh bantuan).
             Salah memilih jenis membuat deteksi tidak berfungsi; lihat KONTEKS §5.
    Sisanya opsional dan memakai default sesuai jenis kamera.
    """
    m = _mgr()
    try:
        profil = m.tambah_kamera(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return profil.to_dict()


@router.get("/kamera/{camera_id}")
def detail_kamera(camera_id: str):
    m = _mgr()
    p = m.store.ambil(camera_id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Kamera '{camera_id}' tidak ditemukan.")
    d = p.to_dict()
    d["sumber"] = p.sumber_aman()
    d["berjalan"] = m.berjalan(camera_id)
    w = m.pekerja(camera_id)
    if w is not None:
        d["kesehatan"] = w.kesehatan()
    return d


@router.patch("/kamera/{camera_id}")
def ubah_kamera(camera_id: str, perubahan: dict = Body(...)):
    """
    Ubah sebagian profil kamera. Pekerja dinyalakan ulang agar perubahan berlaku.

    Mengubah `jenis` juga mengembalikan ambang yang bergantung jenis ke default
    jenis baru, kecuali disebut eksplisit di permintaan yang sama.
    """
    m = _mgr()
    try:
        profil = m.perbarui_kamera(camera_id, perubahan)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Kamera '{camera_id}' tidak ditemukan.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return profil.to_dict()


@router.delete("/kamera/{camera_id}")
def hapus_kamera(camera_id: str):
    m = _mgr()
    try:
        m.hapus_kamera(camera_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Kamera '{camera_id}' tidak ditemukan.")
    return {"status": "dihapus", "kamera_id": camera_id}


@router.post("/kamera/{camera_id}/mulai")
def mulai_kamera(camera_id: str):
    m = _mgr()
    try:
        m.mulai_kamera(camera_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Kamera '{camera_id}' tidak ditemukan.")
    return {"status": "berjalan", "kamera_id": camera_id}


@router.post("/kamera/{camera_id}/berhenti")
def hentikan_kamera(camera_id: str):
    m = _mgr()
    if m.store.ambil(camera_id) is None:
        raise HTTPException(status_code=404, detail=f"Kamera '{camera_id}' tidak ditemukan.")
    m.hentikan_kamera(camera_id)
    return {"status": "berhenti", "kamera_id": camera_id}


@router.get("/kamera/{camera_id}/pratinjau")
def pratinjau_kamera(camera_id: str):
    """
    Aliran MJPEG untuk dashboard.

    Secara default profil memakai preview="kerangka": yang dikirim hanya kerangka
    sendi di atas kanvas hitam — video mentah tidak pernah meninggalkan proses
    backend (KONTEKS §7). Pratinjau hanya digambar selama ada yang menonton,
    jadi tidak ada biaya CPU saat dashboard tertutup.
    """
    m = _mgr()
    p = m.store.ambil(camera_id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Kamera '{camera_id}' tidak ditemukan.")
    if p.preview == "mati":
        raise HTTPException(status_code=409, detail="Pratinjau dimatikan pada profil kamera ini.")

    w = m.pekerja(camera_id)
    if w is None or not w.is_alive():
        raise HTTPException(status_code=409, detail="Kamera sedang tidak berjalan.")

    async def aliran():
        w.tambah_penonton()
        try:
            jeda = 1.0 / _FPS_PRATINJAU
            while True:
                if not w.is_alive():
                    break
                jpeg = w.pratinjau_jpeg()
                if jpeg is not None:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                        + jpeg + b"\r\n"
                    )
                await asyncio.sleep(jeda)
        finally:
            # Dijalankan juga saat klien memutus koneksi (GeneratorExit).
            w.kurangi_penonton()

    return StreamingResponse(
        aliran(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


# ── Kejadian ──────────────────────────────────────────────────────────────────

@router.get("/kejadian")
def daftar_kejadian(
    kamera_id: str | None = Query(None),
    tipe: str | None = Query(None, description="'jatuh' | 'butuh_bantuan'"),
    status: str | None = Query(None, description="'baru' | 'dikonfirmasi' | 'diabaikan'"),
    batas: int = Query(100, ge=1, le=1000),
):
    """
    Log kejadian, terbaru lebih dulu.

    Isinya METADATA saja — tidak ada gambar, wajah, atau koordinat pose.
    Kejadian melewati masa retensi sudah dihapus otomatis.
    """
    m = _mgr()
    hasil = m.log.daftar(kamera_id=kamera_id, tipe=tipe, status=status, batas=batas)
    return {
        "kejadian": [k.to_dict() for k in hasil],
        "jumlah": len(hasil),
        "ringkasan": m.log.ringkasan(),
    }


@router.post("/kejadian/{kejadian_id}/tanggapi")
def tanggapi_kejadian(kejadian_id: str, data: dict = Body(...)):
    """
    Human-in-the-loop (KONTEKS §3 & §6): staf mengonfirmasi atau mengabaikan alert.

    Body: {"status": "dikonfirmasi" | "diabaikan", "oleh": "nama staf"}

    Tanggapan ini adalah bahan mentah untuk menyetel ambang: rasio "diabaikan"
    yang tinggi pada satu kamera berarti ambangnya terlalu longgar untuk sudut
    pemasangan itu.
    """
    m = _mgr()
    status = data.get("status")
    if status not in (STATUS_DIKONFIRMASI, STATUS_DIABAIKAN):
        raise HTTPException(
            status_code=400,
            detail=f"status harus '{STATUS_DIKONFIRMASI}' atau '{STATUS_DIABAIKAN}'.",
        )
    try:
        k = m.log.tanggapi(kejadian_id, status, oleh=data.get("oleh"))
    except KeyError:
        raise HTTPException(status_code=404, detail="Kejadian tidak ditemukan atau sudah kedaluwarsa.")
    return k.to_dict()


# ── Kesehatan ─────────────────────────────────────────────────────────────────

@router.get("/kesehatan")
def kesehatan():
    """Status seluruh sistem: tiap kamera, koneksi stream, model, dan log."""
    return _mgr().kesehatan()


# ── WebSocket alert ───────────────────────────────────────────────────────────

@ws_router.websocket("/ws/produksi/alert")
async def ws_alert(websocket: WebSocket):
    """
    Aliran alert langsung untuk dashboard operator.

    Server → Klien:
      {"type": "awal",      "kejadian": [...]}          snapshot saat tersambung
      {"type": "alert",     "kejadian": {...}}          alert baru (sudah di-debounce)
      {"type": "kesehatan", "ringkas": {...}}           denyut dari pengawas
    """
    await websocket.accept()

    if _manager is None:
        await websocket.send_json({"type": "error", "pesan": "Sistem produksi belum aktif."})
        await websocket.close()
        return

    m = _manager
    antrean: asyncio.Queue = asyncio.Queue()
    m.alert.berlangganan(antrean)

    async def _pantau_putus():
        """
        Menunggu pesan dari klien semata-mata untuk mendeteksi koneksi putus.
        Tanpa ini, koroutine akan menggantung di antrean.get() selamanya bila
        klien menutup tab dan tidak ada alert baru yang datang.
        """
        try:
            while True:
                await websocket.receive_text()
        except Exception:
            return

    tugas_putus = asyncio.create_task(_pantau_putus())

    try:
        await websocket.send_json({
            "type": "awal",
            "kejadian": [k.to_dict() for k in m.log.daftar(batas=50)],
            "ringkasan": m.log.ringkasan(),
        })

        while True:
            tugas_antrean = asyncio.create_task(antrean.get())
            selesai, tertunda = await asyncio.wait(
                {tugas_antrean, tugas_putus},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if tugas_putus in selesai:
                tugas_antrean.cancel()
                break

            payload = tugas_antrean.result()
            await websocket.send_json(payload)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"[ws-alert] Sesi berakhir: {e}")
    finally:
        tugas_putus.cancel()
        m.alert.berhenti_langganan(antrean)
        try:
            await websocket.close()
        except Exception:
            pass
