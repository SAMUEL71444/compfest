"""
pipeline/uniform.py — SAPA

Pengenalan pegawai via kecocokan pakaian ("seragam"), dengan OpenCV murni
(cv2.calcHist + cv2.compareHist) — NOL model, NOL training.

KENAPA "LEVEL 1.5" (histogram DAN pola, bukan warna dominan tunggal):
Kaus biru polos vs seragam biru+pink memberi korelasi histogram HSV 0,919
— cukup tinggi untuk lolos ambang 0,60 sendirian. Yang menolaknya adalah
syarat pola (jumlah warna dominan, rasio antar-warna, hue tiap warna, blok
terbagi horizontal). Tanpa syarat pola, pelanggan berkaus polos warna mirip
akan dianggap pegawai.

HSV, bukan RGB — hue relatif stabil saat pencahayaan berubah (diverifikasi:
kaus seragam tetap dikenali di kondisi cahaya redup, skor histogram 0,671).

CAKUPAN — PENTING, jangan sampai salah pakai:
Tanda pegawai HANYA mengecualikan dari butuh-bantuan. Deteksi jatuh TIDAK
PERNAH memeriksa status ini — pegawai yang jatuh tetap dianggap darurat.
Pemanggil (analyze.py) bertanggung jawab menjaga pemisahan ini; modul ini
hanya menjawab "apakah patch ini cocok pegawai terdaftar", tidak tahu
konteks jatuh/interaksi.

BATAS UKURAN TORSO >= 1200 PIKSEL:
Torso 37x21 px (dari orang yang sama, real) memberi skor 0,705 / -0,009 /
-0,009 / 0,164 di empat frame berdekatan — histogram dari patch sekecil
itu tidak stabil, hanya menyumbang suara acak. Di bawah ambang ini, cek
DILEWATI (kembalikan None / "tidak dapat dinilai"), bukan dipaksakan
memberi jawaban ya/tidak. Konsekuensinya disengaja: orang jauh dari kamera
tidak dikenali pegawai — arahnya aman, dia diperlakukan sebagai pelanggan
biasa (tetap dicek butuh-bantuan, bukan otomatis darurat).

PRIVACY-BY-DESIGN: registrasi menyimpan SIDIK (histogram + fitur pola),
bukan foto. Foto sumber dihapus setelah signature dihitung.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

# Torso di bawah ini terlalu kecil untuk histogram yang stabil — lewati.
MIN_TORSO_AREA_PX = 1200

# Ambang korelasi histogram HSV — perlu DAN dengan syarat pola (lihat
# _pola_cocok) supaya kaus polos warna mirip tidak lolos sendirian.
AMBANG_HISTOGRAM = 0.60

# Toleransi syarat pola.
TOLERANSI_JUMLAH_WARNA = 1        # beda jumlah warna dominan maks 1
TOLERANSI_RASIO_WARNA  = 0.25     # beda rasio area warna dominan maks 25%
TOLERANSI_HUE_DERAJAT  = 20.0     # beda hue (0-180 di OpenCV) maks 20°
N_WARNA_DOMINAN = 3
N_BLOK_VERTIKAL = 3                # bagi torso jadi N blok horizontal utk pola


@dataclass
class SignatureSeragam:
    """Sidik satu seragam — hasil gabung 1-3 foto/crop registrasi."""
    histogram: np.ndarray            # histogram HSV rata-rata, dinormalisasi
    warna_dominan_hue: list          # [hue1, hue2, ...] median tiap blok
    warna_dominan_rasio: list        # [rasio1, rasio2, ...] median tiap blok
    n_sampel: int = 1

    def to_dict(self) -> dict:
        return {
            "histogram": self.histogram.tolist(),
            "warna_dominan_hue": self.warna_dominan_hue,
            "warna_dominan_rasio": self.warna_dominan_rasio,
            "n_sampel": self.n_sampel,
        }

    @staticmethod
    def from_dict(d: dict) -> "SignatureSeragam":
        return SignatureSeragam(
            histogram=np.array(d["histogram"], dtype=np.float32),
            warna_dominan_hue=list(d["warna_dominan_hue"]),
            warna_dominan_rasio=list(d["warna_dominan_rasio"]),
            n_sampel=int(d.get("n_sampel", 1)),
        )


def _torso_area(x0: int, y0: int, x1: int, y1: int) -> int:
    return max(0, x1 - x0) * max(0, y1 - y0)


def crop_torso(frame: np.ndarray, keypoints: np.ndarray) -> np.ndarray | None:
    """
    Potong area torso (bahu ke pinggul) dari satu frame BGR, untuk dijadikan
    patch analisis pakaian. Kembalikan None bila terlalu kecil (lihat
    MIN_TORSO_AREA_PX) atau keypoint kunci tidak cukup yakin.

    frame: citra BGR
    keypoints: [17, 3] — (x, y, confidence), koordinat MENTAH
    """
    l_sh, r_sh, l_hip, r_hip = keypoints[5], keypoints[6], keypoints[11], keypoints[12]
    if min(l_sh[2], r_sh[2], l_hip[2], r_hip[2]) < 0.25:
        return None

    h, w = frame.shape[:2]
    x0 = int(np.clip(min(l_sh[0], r_sh[0], l_hip[0], r_hip[0]), 0, w - 1))
    x1 = int(np.clip(max(l_sh[0], r_sh[0], l_hip[0], r_hip[0]), 0, w))
    y0 = int(np.clip(min(l_sh[1], r_sh[1]), 0, h - 1))
    y1 = int(np.clip(max(l_hip[1], r_hip[1]), 0, h))

    if _torso_area(x0, y0, x1, y1) < MIN_TORSO_AREA_PX:
        return None
    if x1 <= x0 or y1 <= y0:
        return None

    return frame[y0:y1, x0:x1]


def _histogram_hsv(patch: np.ndarray) -> np.ndarray:
    """Histogram HSV 2D (hue x saturation), dinormalisasi. HSV dipilih
    karena hue relatif stabil terhadap perubahan pencahayaan (lihat
    docstring modul)."""
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
    cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    return hist


def _fitur_pola(patch: np.ndarray) -> tuple:
    """
    Ekstrak fitur pola sederhana dari patch torso, dibagi N_BLOK_VERTIKAL
    blok horizontal (kepala->pinggul) — pakaian bermotif/berpola punya
    hue berbeda antar-blok, kaus polos punya hue nyaris sama di semua blok.

    Returns: (list hue dominan per blok, list rasio area warna dominan per blok)
    """
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    h = hsv.shape[0]
    tinggi_blok = max(1, h // N_BLOK_VERTIKAL)

    hues, rasios = [], []
    for i in range(N_BLOK_VERTIKAL):
        y0 = i * tinggi_blok
        y1 = h if i == N_BLOK_VERTIKAL - 1 else (i + 1) * tinggi_blok
        blok = hsv[y0:y1]
        if blok.size == 0:
            hues.append(0.0)
            rasios.append(0.0)
            continue

        hue_blok = blok[:, :, 0].flatten()
        # Warna dominan blok ini = median hue (tahan terhadap noise/highlight)
        hue_dominan = float(np.median(hue_blok))
        # Rasio piksel yang dekat dengan hue dominan (dalam +-15 derajat)
        dekat = np.abs(hue_blok.astype(np.int16) - int(hue_dominan)) <= 15
        rasio = float(np.mean(dekat))

        hues.append(hue_dominan)
        rasios.append(rasio)

    return hues, rasios


def _pola_cocok(hue_a: list, rasio_a: list, hue_b: list, rasio_b: list) -> bool:
    """Syarat pola: hue tiap blok dan rasio tiap blok harus mirip — bukan
    cuma warna dominan tunggal. Ini yang menolak kaus polos berwarna mirip
    seragam berpola (lihat docstring modul)."""
    if len(hue_a) != len(hue_b):
        return False

    for ha, hb, ra, rb in zip(hue_a, hue_b, rasio_a, rasio_b):
        beda_hue = min(abs(ha - hb), 180 - abs(ha - hb))  # hue melingkar 0-180
        if beda_hue > TOLERANSI_HUE_DERAJAT:
            return False
        if abs(ra - rb) > TOLERANSI_RASIO_WARNA:
            return False

    return True


def buat_signature(patches: list) -> SignatureSeragam | None:
    """
    Gabung 1-3 patch torso jadi satu signature: histogram dirata-rata lalu
    dinormalisasi ulang, fitur pola diambil median per blok (median, bukan
    rata-rata, supaya satu foto dengan pencahayaan aneh tidak mendominasi).

    patches: list of np.ndarray BGR (crop torso dari crop_torso() atau area
             yang sudah dipotong manual di browser, sudah_dicrop=True)
    Returns: SignatureSeragam, atau None bila semua patch terlalu kecil.
    """
    histograms, hues_list, rasios_list = [], [], []
    for patch in patches:
        if patch is None or patch.size == 0:
            continue
        if _torso_area(0, 0, patch.shape[1], patch.shape[0]) < MIN_TORSO_AREA_PX:
            continue
        histograms.append(_histogram_hsv(patch))
        hues, rasios = _fitur_pola(patch)
        hues_list.append(hues)
        rasios_list.append(rasios)

    if not histograms:
        return None

    hist_gabung = np.mean(histograms, axis=0)
    cv2.normalize(hist_gabung, hist_gabung, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

    hues_arr = np.array(hues_list)     # [n_sampel, N_BLOK_VERTIKAL]
    rasios_arr = np.array(rasios_list)
    hue_median = np.median(hues_arr, axis=0).tolist()
    rasio_median = np.median(rasios_arr, axis=0).tolist()

    return SignatureSeragam(
        histogram=hist_gabung.astype(np.float32),
        warna_dominan_hue=hue_median,
        warna_dominan_rasio=rasio_median,
        n_sampel=len(histograms),
    )


def cocokkan_seragam(patch: np.ndarray, signature: SignatureSeragam) -> bool | None:
    """
    Bandingkan satu patch torso terhadap satu signature terdaftar.

    Returns:
      True  — cocok (histogram DAN pola sama-sama lolos ambang)
      False — tidak cocok
      None  — tidak dapat dinilai (patch di bawah MIN_TORSO_AREA_PX)
    """
    if patch is None or _torso_area(0, 0, patch.shape[1], patch.shape[0]) < MIN_TORSO_AREA_PX:
        return None

    hist_patch = _histogram_hsv(patch)
    skor_histogram = float(cv2.compareHist(hist_patch, signature.histogram, cv2.HISTCMP_CORREL))
    if skor_histogram < AMBANG_HISTOGRAM:
        return False

    hue_patch, rasio_patch = _fitur_pola(patch)
    return _pola_cocok(hue_patch, rasio_patch, signature.warna_dominan_hue, signature.warna_dominan_rasio)


def cocokkan_seragam_terdaftar(patch: np.ndarray, daftar_signature: list) -> bool | None:
    """
    Cocokkan satu patch terhadap SEMUA signature terdaftar (mis. beberapa
    pegawai). Cocok dengan salah satu saja sudah cukup.

    Returns True/False/None dengan semantik sama seperti cocokkan_seragam().
    None hanya bila patch tidak dapat dinilai sama sekali (torso kecil);
    bila patch valid tapi daftar_signature kosong, kembalikan False.
    """
    if patch is None or _torso_area(0, 0, patch.shape[1], patch.shape[0]) < MIN_TORSO_AREA_PX:
        return None
    if not daftar_signature:
        return False

    for sig in daftar_signature:
        hasil = cocokkan_seragam(patch, sig)
        if hasil:
            return True
    return False


# ── Penyimpanan (privacy-by-design: sidik saja, bukan foto) ────────────────

def muat_daftar_signature(path: Path) -> list:
    """
    Muat daftar signature terdaftar dari data/seragam.json. Format:
    {"pegawai": [{"id": str, "nama": str, "signature": {...}}, ...]}

    Kembalikan list kosong bila file belum ada — belum ada pegawai
    terdaftar bukan error, itu kondisi awal yang wajar.
    """
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return data.get("pegawai", [])


def simpan_daftar_signature(path: Path, daftar_pegawai: list) -> None:
    """Simpan daftar pegawai (dengan signature-nya) ke data/seragam.json."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pegawai": daftar_pegawai}, indent=2, ensure_ascii=False))


def daftar_signature_objects(daftar_pegawai: list) -> list:
    """Konversi daftar dict (dari JSON) jadi list SignatureSeragam siap
    dipakai cocokkan_seragam_terdaftar()."""
    return [SignatureSeragam.from_dict(p["signature"]) for p in daftar_pegawai if "signature" in p]
