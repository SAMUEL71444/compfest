"""
production/alerts.py — SAPA Produksi

Mesin alert + log kejadian (KONTEKS §4 poin 3, §6, §7).

DUA ATURAN YANG MEMBENTUK MODUL INI
-----------------------------------
1. "Satu kejadian ≠ 10 notifikasi" (§6). Jendela geser memancarkan penilaian tiap
   ~1 detik. Orang yang jatuh dan tergeletak akan memicu kondisi jatuh di setiap
   jendela berikutnya selama ia masih di lantai. Tanpa debounce, staf menerima
   puluhan notifikasi untuk satu peristiwa dan berhenti mempercayainya.

   Debounce di sini dua lapis:
     - KONFIRMASI: butuh `confirm_windows` jendela berturut sebelum alert keluar.
       Meredam kedipan satu-jendela. Untuk jatuh dipasang 1 (kecepatan = nyawa),
       untuk butuh-bantuan 2.
     - COOLDOWN: setelah alert keluar, kombinasi (kamera, orang, jenis) yang sama
       dibungkam selama `cooldown_seconds`. Deteksi berulang selama masa itu
       tidak membuat alert baru, hanya memperpanjang alert yang sudah ada.

2. "AI menandai, manusia memutuskan" (§3). Alert TIDAK PERNAH memicu tindakan
   otomatis. Setiap alert lahir berstatus "baru" dan menunggu staf menanggapi
   (tanggapi() → "dikonfirmasi" | "diabaikan"). Tanggapan itu disimpan dan bisa
   dipakai menyetel ambang di kemudian hari (§6 human-in-the-loop).

PRIVASI (§7)
------------
Log kejadian menyimpan METADATA saja: jenis kejadian, waktu, id kamera, track_id
sementara, skor. TIDAK ada gambar, TIDAK ada wajah, TIDAK ada koordinat pose
mentah. `track_id` bersifat sementara dan hanya bermakna dalam satu sesi satu
kamera — ia bukan identitas orang dan tidak bisa dipakai melacak lintas kamera.
Retensi dibatasi `retensi_jam` dan kejadian kedaluwarsa dihapus otomatis.
"""

import json
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

# Prioritas alert → menentukan cara staf diberi tahu (§6)
PRIORITAS_KRITIS = "kritis"       # jatuh: bunyi + push HP + tanda dashboard
PRIORITAS_INFO = "informasi"      # butuh bantuan: notifikasi lembut ke staf lantai

_PRIORITAS_PER_TIPE = {
    "jatuh": PRIORITAS_KRITIS,
    "butuh_bantuan": PRIORITAS_INFO,
}

STATUS_BARU = "baru"
STATUS_DIKONFIRMASI = "dikonfirmasi"
STATUS_DIABAIKAN = "diabaikan"
STATUS_VALID = (STATUS_BARU, STATUS_DIKONFIRMASI, STATUS_DIABAIKAN)


@dataclass
class Kejadian:
    """Satu kejadian terkonfirmasi. Metadata saja — lihat catatan PRIVASI."""

    id: str
    kamera_id: str
    kamera_nama: str
    tipe: str                       # "jatuh" | "butuh_bantuan"
    prioritas: str
    track_id: int
    skor: float
    t_mulai: float                  # epoch (time.time), agar bermakna lintas restart
    t_selesai: float
    status: str = STATUS_BARU
    detail: dict = field(default_factory=dict)
    t_ditanggapi: float | None = None
    ditanggapi_oleh: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class EventLog:
    """
    Log kejadian dengan retensi otomatis.

    Disimpan di memori (deque) dan opsional di-append ke berkas JSONL agar
    selamat dari restart. JSONL dipilih daripada database: tahan korup (satu baris
    rusak tidak merusak sisanya), mudah di-rotate, dan bisa dibaca `tail -f` saat
    uji lapangan tanpa tooling tambahan.
    """

    def __init__(
        self,
        retensi_jam: float = 72.0,
        maks_memori: int = 5000,
        path_jsonl: str | Path | None = None,
    ):
        self.retensi_detik = float(retensi_jam) * 3600.0
        self.path_jsonl = Path(path_jsonl) if path_jsonl else None
        self._lock = threading.RLock()
        self._kejadian: deque[Kejadian] = deque(maxlen=maks_memori)
        self._indeks: dict[str, Kejadian] = {}

        if self.path_jsonl is not None:
            self.path_jsonl.parent.mkdir(parents=True, exist_ok=True)
            self._muat_dari_jsonl()

    def _muat_dari_jsonl(self) -> None:
        """Pulihkan kejadian yang masih dalam masa retensi setelah restart."""
        if not self.path_jsonl or not self.path_jsonl.exists():
            return
        batas = time.time() - self.retensi_detik
        dipulihkan = 0
        try:
            with self.path_jsonl.open("r", encoding="utf-8") as f:
                for baris in f:
                    baris = baris.strip()
                    if not baris:
                        continue
                    try:
                        d = json.loads(baris)
                    except json.JSONDecodeError:
                        continue      # baris rusak (mis. mati listrik saat menulis)
                    if float(d.get("t_mulai", 0)) < batas:
                        continue
                    try:
                        k = Kejadian(**d)
                    except TypeError:
                        continue      # skema lama — lewati, jangan gagalkan startup
                    self._kejadian.append(k)
                    self._indeks[k.id] = k
                    dipulihkan += 1
        except Exception as e:
            logger.warning(f"[log] Gagal memulihkan {self.path_jsonl}: {e}")
        if dipulihkan:
            logger.info(f"[log] {dipulihkan} kejadian dipulihkan dari berkas.")

    def tambah(self, k: Kejadian) -> None:
        with self._lock:
            if len(self._kejadian) == self._kejadian.maxlen:
                terbuang = self._kejadian[0]
                self._indeks.pop(terbuang.id, None)
            self._kejadian.append(k)
            self._indeks[k.id] = k

        if self.path_jsonl is not None:
            try:
                with self.path_jsonl.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(k.to_dict(), ensure_ascii=False) + "\n")
            except Exception as e:
                logger.warning(f"[log] Gagal menulis kejadian ke berkas: {e}")

    def daftar(
        self,
        kamera_id: str | None = None,
        tipe: str | None = None,
        status: str | None = None,
        batas: int = 100,
    ) -> list[Kejadian]:
        """Kejadian terbaru lebih dulu."""
        with self._lock:
            hasil = list(self._kejadian)
        hasil.reverse()
        if kamera_id:
            hasil = [k for k in hasil if k.kamera_id == kamera_id]
        if tipe:
            hasil = [k for k in hasil if k.tipe == tipe]
        if status:
            hasil = [k for k in hasil if k.status == status]
        return hasil[:batas]

    def ambil(self, kejadian_id: str) -> Kejadian | None:
        with self._lock:
            return self._indeks.get(kejadian_id)

    def tanggapi(self, kejadian_id: str, status: str, oleh: str | None = None) -> Kejadian:
        """Human-in-the-loop: staf mengonfirmasi atau mengabaikan alert."""
        if status not in (STATUS_DIKONFIRMASI, STATUS_DIABAIKAN):
            raise ValueError(f"status harus '{STATUS_DIKONFIRMASI}' atau '{STATUS_DIABAIKAN}'")
        with self._lock:
            k = self._indeks.get(kejadian_id)
            if k is None:
                raise KeyError(kejadian_id)
            k.status = status
            k.t_ditanggapi = time.time()
            k.ditanggapi_oleh = oleh
            return k

    def buang_kedaluwarsa(self) -> int:
        """Hapus kejadian melewati masa retensi (§7 — retensi singkat & otomatis)."""
        batas = time.time() - self.retensi_detik
        with self._lock:
            n_awal = len(self._kejadian)
            tersisa = [k for k in self._kejadian if k.t_mulai >= batas]
            if len(tersisa) == n_awal:
                return 0
            self._kejadian.clear()
            self._kejadian.extend(tersisa)
            self._indeks = {k.id: k for k in tersisa}
            dibuang = n_awal - len(tersisa)

        # Tulis ulang berkas agar retensi juga berlaku di disk, bukan hanya memori.
        if self.path_jsonl is not None and dibuang:
            try:
                tmp = self.path_jsonl.with_suffix(".tmp")
                with tmp.open("w", encoding="utf-8") as f:
                    for k in tersisa:
                        f.write(json.dumps(k.to_dict(), ensure_ascii=False) + "\n")
                tmp.replace(self.path_jsonl)
            except Exception as e:
                logger.warning(f"[log] Gagal memangkas berkas kejadian: {e}")

        logger.info(f"[log] {dibuang} kejadian kedaluwarsa dihapus (retensi terpenuhi).")
        return dibuang

    def ringkasan(self) -> dict:
        with self._lock:
            semua = list(self._kejadian)
        return {
            "total": len(semua),
            "jatuh": sum(1 for k in semua if k.tipe == "jatuh"),
            "butuh_bantuan": sum(1 for k in semua if k.tipe == "butuh_bantuan"),
            "belum_ditanggapi": sum(1 for k in semua if k.status == STATUS_BARU),
            "retensi_jam": round(self.retensi_detik / 3600.0, 1),
        }


class AlertEngine:
    """
    Menerima deteksi mentah per jendela dari pekerja kamera, mengeluarkan alert
    yang sudah di-debounce, dan menyiarkannya ke pelanggan (dashboard WebSocket).

    Dipanggil dari THREAD pekerja kamera, sementara pelanggan hidup di event loop
    asyncio. Penyeberangan itu dilakukan lewat loop.call_soon_threadsafe() —
    memanggil asyncio.Queue.put_nowait() langsung dari thread lain tidak aman
    dan bisa membuat pelanggan tidak pernah terbangun.
    """

    def __init__(self, event_log: EventLog):
        self.log = event_log
        self._lock = threading.Lock()
        # {(kamera_id, track_id, tipe): {"streak", "t_alert_terakhir", "t_lihat_terakhir", "id_aktif"}}
        self._debounce: dict[tuple, dict] = {}
        self._pelanggan: list = []          # list[asyncio.Queue]
        self._loop = None                   # asyncio loop utama, di-set saat startup
        self._n_ditekan = 0

    # ── Integrasi asyncio ─────────────────────────────────────────────────────
    def pasang_loop(self, loop) -> None:
        """Dipanggil sekali saat startup FastAPI."""
        self._loop = loop

    def berlangganan(self, antrean) -> None:
        with self._lock:
            self._pelanggan.append(antrean)

    def berhenti_langganan(self, antrean) -> None:
        with self._lock:
            if antrean in self._pelanggan:
                self._pelanggan.remove(antrean)

    def _siarkan(self, payload: dict) -> None:
        with self._lock:
            pelanggan = list(self._pelanggan)
        loop = self._loop
        if loop is None or not pelanggan:
            return
        for antrean in pelanggan:
            try:
                loop.call_soon_threadsafe(antrean.put_nowait, payload)
            except RuntimeError:
                pass    # loop sudah ditutup saat shutdown — abaikan

    def siarkan_status(self, payload: dict) -> None:
        """Kirim pesan non-alert (mis. status kesehatan kamera) ke dashboard."""
        self._siarkan(payload)

    # ── Jalur utama ───────────────────────────────────────────────────────────
    def ajukan(
        self,
        kamera_id: str,
        kamera_nama: str,
        tipe: str,
        track_id: int,
        skor: float,
        confirm_windows: int,
        cooldown_seconds: float,
        detail: dict | None = None,
        t_mulai: float | None = None,
        t_selesai: float | None = None,
    ) -> Kejadian | None:
        """
        Ajukan satu deteksi tingkat-jendela. Kembalikan Kejadian bila lolos
        debounce dan alert benar-benar dikeluarkan, None bila ditekan.
        """
        sekarang = time.time()
        kunci = (kamera_id, int(track_id), tipe)

        with self._lock:
            st = self._debounce.get(kunci)
            if st is None:
                st = {"streak": 0, "t_alert_terakhir": 0.0, "t_lihat_terakhir": 0.0}
                self._debounce[kunci] = st

            # Streak putus bila deteksi tidak berurutan. Ambang kelonggaran
            # sengaja longgar (5 dtk) supaya satu jendela yang meleset karena
            # occlusion tidak mengulang hitungan konfirmasi dari nol.
            if st["t_lihat_terakhir"] and (sekarang - st["t_lihat_terakhir"]) > 5.0:
                st["streak"] = 0

            st["streak"] += 1
            st["t_lihat_terakhir"] = sekarang

            # Lapis 1 — konfirmasi jendela berturut
            if st["streak"] < confirm_windows:
                self._n_ditekan += 1
                return None

            # Lapis 2 — cooldown
            sejak = sekarang - st["t_alert_terakhir"]
            if st["t_alert_terakhir"] and sejak < cooldown_seconds:
                self._n_ditekan += 1
                # Perpanjang kejadian yang sedang berjalan agar durasinya jujur,
                # tanpa memunculkan alert baru.
                id_aktif = st.get("id_aktif")
                if id_aktif:
                    k = self.log.ambil(id_aktif)
                    if k is not None:
                        k.t_selesai = t_selesai or sekarang
                        k.skor = max(k.skor, round(float(skor), 3))
                return None

            st["t_alert_terakhir"] = sekarang
            st["streak"] = 0     # mulai hitung ulang untuk kejadian berikutnya

        kejadian = Kejadian(
            id=uuid.uuid4().hex[:12],
            kamera_id=kamera_id,
            kamera_nama=kamera_nama,
            tipe=tipe,
            prioritas=_PRIORITAS_PER_TIPE.get(tipe, PRIORITAS_INFO),
            track_id=int(track_id),
            skor=round(float(skor), 3),
            t_mulai=t_mulai or sekarang,
            t_selesai=t_selesai or sekarang,
            detail=detail or {},
        )

        with self._lock:
            self._debounce[kunci]["id_aktif"] = kejadian.id

        self.log.tambah(kejadian)
        self._siarkan({"type": "alert", "kejadian": kejadian.to_dict()})

        logger.info(
            f"[alert] {kejadian.prioritas.upper()} {tipe} "
            f"kamera={kamera_id} track={track_id} skor={kejadian.skor}"
        )
        return kejadian

    # ── Perawatan ─────────────────────────────────────────────────────────────
    def bersihkan_debounce(self, umur_maks: float = 300.0) -> int:
        """Buang state debounce untuk track yang sudah lama tidak muncul."""
        sekarang = time.time()
        with self._lock:
            mati = [
                k for k, st in self._debounce.items()
                if sekarang - max(st["t_lihat_terakhir"], st["t_alert_terakhir"]) > umur_maks
            ]
            for k in mati:
                del self._debounce[k]
        return len(mati)

    def lupakan_kamera(self, kamera_id: str) -> None:
        """Bersihkan state saat kamera dihentikan, agar tidak bocor memori."""
        with self._lock:
            for k in [k for k in self._debounce if k[0] == kamera_id]:
                del self._debounce[k]

    def statistik(self) -> dict:
        with self._lock:
            return {
                "kunci_debounce_aktif": len(self._debounce),
                "deteksi_ditekan": self._n_ditekan,
                "pelanggan_dashboard": len(self._pelanggan),
            }
