"""
statistik.py — SAPA
Log penanganan kejadian yang PERMANEN (bertahan lintas sesi Live/browser) +
timer "terlewat" yang diurus backend.

Kenapa di backend, bukan di browser:
- Statistik untuk manajer/bos harus bertahan walau tab Live ditutup. State React
  bersifat sementara; file di sini permanen.
- "Terlewat" (kejadian tak direspons dalam batas waktu) paling andal ditandai
  backend lewat timer, karena browser bisa saja sudah ditutup saat batas lewat.

Model data (satu baris JSON per kejadian di penanganan.jsonl):
  {
    "id":        "3__jatuh__12.0",     # kunci_kejadian (konsisten dgn frontend)
    "tipe":      "jatuh" | "butuh_bantuan",
    "track_id":  3,
    "t_muncul":  1730000000.0,          # epoch detik saat kejadian dicatat
    "skor":      0.88,
    "status":    "menunggu" | "ditangani" | "alarm_palsu" | "terlewat",
    "oleh":      "Budi" | null,          # nama staf (dari Telegram) bila ditangani
    "sumber":    "telegram" | "dashboard" | "sistem" | null,
    "respons_detik": 8.3 | null,         # t_selesai - t_muncul
    "t_selesai": 1730000008.3 | null,
  }

Setiap perubahan status menulis ULANG baris (append log + rekonstruksi state
saat baca), jadi file bersifat append-only dan aman terhadap crash.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Batas waktu respons; kejadian tak dikonfirmasi dalam durasi ini → "terlewat".
BATAS_TERLEWAT_DETIK = float(os.getenv("SAPA_BATAS_TERLEWAT", "60"))

# Lokasi file log (ikut folder data yang sudah di-mount & di-gitignore).
_DATA_DIR = Path(os.getenv("SAPA_DATA_DIR", Path(__file__).parent / "data"))
_LOG_PATH = Path(os.getenv("SAPA_LOG_PENANGANAN", _DATA_DIR / "penanganan.jsonl"))

_lock = threading.RLock()
# State terkini per id (rekonstruksi dari file saat start + update saat runtime).
_state: dict[str, dict] = {}
# Timer terlewat aktif per id, agar bisa dibatalkan bila keburu ditangani.
_timers: dict[str, threading.Timer] = {}
_dimuat = False


def _pastikan_dir():
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _tulis_baris(record: dict):
    """Append satu record ke file log (append-only, tahan crash)."""
    _pastikan_dir()
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _muat_state():
    """Rekonstruksi _state dari file saat pertama diakses (baris terakhir/id menang)."""
    global _dimuat
    if _dimuat:
        return
    _dimuat = True
    if not _LOG_PATH.exists():
        return
    try:
        with open(_LOG_PATH, "r", encoding="utf-8") as f:
            for baris in f:
                baris = baris.strip()
                if not baris:
                    continue
                try:
                    rec = json.loads(baris)
                except json.JSONDecodeError:
                    continue
                if "id" in rec:
                    _state[rec["id"]] = rec
    except Exception as e:
        logger.warning(f"[statistik] Gagal memuat log: {e}")


# Dedup berbasis waktu: kejadian dari window berturut untuk (track_id, tipe)
# yang sama dianggap SATU peristiwa selama jeda antar-kemunculan < ambang ini.
# Mengikuti logika dedupeEvents.js di frontend (jatuh rapat, bantuan lebih longgar).
GAP_GABUNG_DETIK = float(os.getenv("SAPA_GAP_GABUNG", "6"))

# Kejadian "aktif" per (track_id, tipe) → id record yang sedang berjalan + waktu
# kemunculan terakhir, untuk memutuskan gabung vs buat baru.
_aktif: dict[tuple, dict] = {}


def catat_muncul(event: dict, on_terlewat=None):
    """
    Catat kejadian muncul (status 'menunggu') + jadwalkan timer terlewat.

    DEDUP: kejadian dari window berturut untuk orang & tipe yang sama digabung
    jadi SATU record selama jeda antar-kemunculan < GAP_GABUNG_DETIK. Ini
    mencegah "spam" satu peristiwa berkelanjutan menjadi puluhan baris —
    menyamakan perilaku dengan panel Live yang memakai dedupeEvents.js.

    event    : dict punya id (kunci_kejadian), tipe, track_id, skor, t0
    on_terlewat: callback opsional dipanggil saat kejadian jadi terlewat.
    """
    _muat_state()
    kid = event["id"]
    tipe = event.get("tipe")
    track_id = event.get("track_id")
    kunci_aktif = (track_id, tipe)
    now = time.time()

    with _lock:
        # 1. Persis id yang sama sudah tercatat → abaikan (dedup lintas window identik).
        if kid in _state:
            return

        # 2. Ada kejadian berjalan untuk (orang, tipe) sama & masih dalam gap →
        #    perpanjang yang lama, JANGAN buat record baru.
        akt = _aktif.get(kunci_aktif)
        if akt is not None and (now - akt["last"]) <= GAP_GABUNG_DETIK:
            rec = _state.get(akt["id"])
            if rec is not None and rec["status"] == "menunggu":
                akt["last"] = now
                # Perbarui skor maksimum bila kejadian baru lebih yakin.
                if event.get("skor") is not None:
                    rec["skor"] = max(rec.get("skor") or 0, event["skor"])
                # Reset timer terlewat: selama peristiwa masih berlangsung,
                # hitungan 1 menit dimulai dari kemunculan terakhir.
                _batalkan_timer(akt["id"])
                t = threading.Timer(BATAS_TERLEWAT_DETIK, _tandai_terlewat, args=(akt["id"], on_terlewat))
                t.daemon = True
                _timers[akt["id"]] = t
                t.start()
                return

        # 3. Kejadian baru (atau peristiwa lama sudah selesai/direspons).
        rec = {
            "id": kid,
            "tipe": tipe,
            "track_id": track_id,
            "t_muncul": now,
            "skor": event.get("skor"),
            "status": "menunggu",
            "oleh": None,
            "sumber": None,
            "respons_detik": None,
            "t_selesai": None,
        }
        _state[kid] = rec
        _aktif[kunci_aktif] = {"id": kid, "last": now}
        _tulis_baris(rec)

        t = threading.Timer(BATAS_TERLEWAT_DETIK, _tandai_terlewat, args=(kid, on_terlewat))
        t.daemon = True
        _timers[kid] = t
        t.start()


def _batalkan_timer(kid: str):
    t = _timers.pop(kid, None)
    if t is not None:
        try:
            t.cancel()
        except Exception:
            pass


def _tandai_terlewat(kid: str, on_terlewat=None):
    with _lock:
        rec = _state.get(kid)
        if rec is None or rec["status"] != "menunggu":
            return  # sudah ditangani / palsu → tidak jadi terlewat
        rec["status"] = "terlewat"
        rec["t_selesai"] = time.time()
        _tulis_baris(rec)
        _timers.pop(kid, None)
        _lepas_aktif(kid)
    logger.info(f"[statistik] Kejadian {kid} TERLEWAT (>{BATAS_TERLEWAT_DETIK:.0f} dtk).")
    if on_terlewat:
        try:
            on_terlewat(kid)
        except Exception:
            pass


def _selesaikan(kid: str, status: str, oleh: str | None, sumber: str) -> dict | None:
    """Ubah status kejadian jadi final (ditangani/alarm_palsu). Idempoten."""
    _muat_state()
    with _lock:
        rec = _state.get(kid)
        if rec is None:
            # Kejadian tak dikenal (mis. muncul sebelum modul aktif) — buat minimal.
            rec = {
                "id": kid, "tipe": None, "track_id": None,
                "t_muncul": time.time(), "skor": None,
                "status": "menunggu", "oleh": None, "sumber": None,
                "respons_detik": None, "t_selesai": None,
            }
            _state[kid] = rec
        if rec["status"] in ("ditangani", "alarm_palsu"):
            return rec  # sudah final, jangan dobel
        _batalkan_timer(kid)
        now = time.time()
        rec["status"] = status
        rec["oleh"] = oleh
        rec["sumber"] = sumber
        rec["t_selesai"] = now
        rec["respons_detik"] = round(now - rec["t_muncul"], 1) if rec.get("t_muncul") else None
        _tulis_baris(rec)
        _lepas_aktif(kid)
        return rec


def _lepas_aktif(kid: str):
    """Lepas kejadian dari daftar aktif agar kemunculan berikutnya jadi record baru."""
    for k, v in list(_aktif.items()):
        if v.get("id") == kid:
            _aktif.pop(k, None)


def catat_ditangani(kid: str, oleh: str | None = None, sumber: str = "telegram"):
    """Tandai kejadian ditangani (mis. staf pencet tombol di Telegram)."""
    rec = _selesaikan(kid, "ditangani", oleh, sumber)
    if rec:
        logger.info(f"[statistik] {kid} DITANGANI oleh {oleh or '—'} ({sumber}), "
                    f"respons {rec.get('respons_detik')} dtk.")
    return rec


def catat_alarm_palsu(kid: str, sumber: str = "dashboard"):
    """Tandai kejadian sebagai alarm palsu (mis. pengawas di dashboard)."""
    rec = _selesaikan(kid, "alarm_palsu", None, sumber)
    if rec:
        logger.info(f"[statistik] {kid} ALARM PALSU ({sumber}).")
    return rec


def hapus_semua() -> int:
    """
    Hapus seluruh histori penanganan (kosongkan file + reset state in-memory).
    DESTRUKTIF & permanen. Kembalikan jumlah record yang dihapus.

    Timer 'terlewat' yang masih berjalan dibatalkan agar tidak menulis ulang
    record yang baru saja dihapus.
    """
    _muat_state()
    with _lock:
        jumlah = len(_state)
        # Batalkan semua timer terlewat yang masih aktif.
        for t in list(_timers.values()):
            try:
                t.cancel()
            except Exception:
                pass
        _timers.clear()
        _state.clear()
        _aktif.clear()
        try:
            if _LOG_PATH.exists():
                _LOG_PATH.unlink()
        except Exception as e:
            logger.warning(f"[statistik] Gagal menghapus file log: {e}")
    logger.info(f"[statistik] Histori penanganan dihapus ({jumlah} record).")
    return jumlah


def ringkasan() -> dict:
    """
    Rangkum seluruh log untuk halaman statistik.
    Aman bila belum ada data (kembalikan nol).
    """
    _muat_state()
    with _lock:
        rekaman = list(_state.values())

    total = len(rekaman)
    ditangani = [r for r in rekaman if r["status"] == "ditangani"]
    palsu     = [r for r in rekaman if r["status"] == "alarm_palsu"]
    terlewat  = [r for r in rekaman if r["status"] == "terlewat"]
    menunggu  = [r for r in rekaman if r["status"] == "menunggu"]

    respons = [r["respons_detik"] for r in ditangani if r.get("respons_detik") is not None]
    avg_respons = round(sum(respons) / len(respons), 1) if respons else None

    # Peringkat per staf (dari yang ditangani via Telegram).
    per_staf: dict[str, dict] = {}
    for r in ditangani:
        nama = r.get("oleh") or "Tak diketahui"
        s = per_staf.setdefault(nama, {"nama": nama, "ditangani": 0, "total_respons": 0.0, "n_respons": 0})
        s["ditangani"] += 1
        if r.get("respons_detik") is not None:
            s["total_respons"] += r["respons_detik"]
            s["n_respons"] += 1
    peringkat = []
    for s in per_staf.values():
        peringkat.append({
            "nama": s["nama"],
            "ditangani": s["ditangani"],
            "rata_respons": round(s["total_respons"] / s["n_respons"], 1) if s["n_respons"] else None,
        })
    peringkat.sort(key=lambda x: x["ditangani"], reverse=True)

    # Riwayat terbaru (maks 100, terbaru dulu).
    riwayat = sorted(rekaman, key=lambda r: r.get("t_muncul", 0), reverse=True)[:100]

    return {
        "total": total,
        "ditangani": len(ditangani),
        "alarm_palsu": len(palsu),
        "terlewat": len(terlewat),
        "menunggu": len(menunggu),
        "rata_respons_detik": avg_respons,
        "batas_terlewat_detik": BATAS_TERLEWAT_DETIK,
        "peringkat_staf": peringkat,
        "riwayat": riwayat,
    }
