"""
production/ — SAPA Deployment CCTV Real-Time

Lapisan INFRASTRUKTUR untuk menjalankan SAPA sebagai perangkat lunak CCTV 24/7.
Sesuai KONTEKS §4, paket ini HANYA berisi bagian "BARU":

  1. stream.py    — konektor RTSP/webcam yang tahan-putus (reconnect otomatis)
  2. buffer.py    — buffer jendela geser per-track yang jalan kontinu
  3. alerts.py    — mesin alert + debounce + log kejadian + retensi
  4. worker.py    — satu pekerja per kamera: baca → pose+track → inferensi → alert
  5. manager.py   — manajemen multi-kamera
  6. profiles.py  — profil per kamera (jenis kamera → fitur mana yang aktif)
  7. api.py       — REST + WebSocket untuk dashboard operator

INTI AI TIDAK DIBANGUN ULANG. Paket ini mengimpor dan memakai `pipeline/`
apa adanya:
    pipeline.normalize.build_windows_for_heads   (normalisasi IDENTIK training)
    pipeline.models.predict_proba                (dua kepala BiLSTM)
    pipeline.geometry.window_torso_angle/is_dwell

Invarian yang dijaga (KONTEKS §11):
  - Modul normalisasi identik antara training, MVP offline, dan produksi.
  - 12 sendi (x,y) untuk Kepala Jatuh vs 17 sendi (x,y,conf) untuk Kepala Interaksi
    — dipenuhi otomatis oleh build_windows_for_heads().
  - Kepala Jatuh TIDAK PERNAH dijalankan pada kamera top-down (jenis="rak"),
    ditegakkan di profiles.py, bukan diserahkan ke konfigurasi operator.
  - "AI menandai, manusia memutuskan" — alert selalu menunggu tanggapan staf,
    sistem tidak pernah bertindak otomatis.

IMPOR MALAS (PEP 562)
---------------------
`worker` menarik torch + ultralytics dan `stream` menarik cv2 — bersama-sama
beberapa detik waktu impor dan ratusan MB memori. Perkakas yang hanya perlu
membaca profil kamera (mis. skrip setup lapangan atau uji unit) tidak boleh
membayar biaya itu. Karena itu simbol di bawah baru diimpor saat benar-benar
disentuh, lewat modul __getattr__.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:   # hanya untuk type checker, tidak dieksekusi saat runtime
    from .alerts import AlertEngine, EventLog, Kejadian
    from .buffer import TrackWindow, TrackWindowBuffer
    from .manager import CameraManager
    from .profiles import CameraProfile, ProfileStore, JENIS_LORONG, JENIS_RAK
    from .stream import FrameGrabber
    from .worker import CameraWorker

_ASAL = {
    "CameraProfile": ".profiles",
    "ProfileStore": ".profiles",
    "JENIS_LORONG": ".profiles",
    "JENIS_RAK": ".profiles",
    "TrackWindow": ".buffer",
    "TrackWindowBuffer": ".buffer",
    "AlertEngine": ".alerts",
    "EventLog": ".alerts",
    "Kejadian": ".alerts",
    "FrameGrabber": ".stream",
    "CameraWorker": ".worker",
    "CameraManager": ".manager",
}


def __getattr__(nama: str):
    modul = _ASAL.get(nama)
    if modul is None:
        raise AttributeError(f"module 'production' tidak punya atribut '{nama}'")
    from importlib import import_module
    return getattr(import_module(modul, __name__), nama)


def __dir__():
    return sorted(_ASAL)


__all__ = [
    "CameraProfile",
    "ProfileStore",
    "JENIS_LORONG",
    "JENIS_RAK",
    "FrameGrabber",
    "TrackWindowBuffer",
    "TrackWindow",
    "AlertEngine",
    "EventLog",
    "Kejadian",
    "CameraWorker",
    "CameraManager",
]
