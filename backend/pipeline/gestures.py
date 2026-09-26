"""
pipeline/gestures.py — SAPA

Deteksi gestur "angkat tangan minta bantuan" via ATURAN GEOMETRI, bukan
model. Beroperasi pada urutan frame MENTAH (bukan window ternormalisasi),
karena butuh melacak durasi bertahan lintas banyak frame — mirip pola
akumulasi run_count di pipeline/analyze.py untuk butuh_bantuan.

KENAPA ATURAN, BUKAN MODEL:
Pose tangan pada "minta bantuan", "stretching", "meraih rak tinggi", dan
"tos" mirip semua (wrist di atas shoulder). Yang membedakan bukan pose
melainkan konteks — durasi, stabilitas, sedang menyentuh rak atau tidak.
Konteks itu bisa ditulis eksplisit sebagai aturan. Dataset "angkat tangan
minta bantuan di toko" juga tidak tersedia publik untuk melatih model.

EMPAT SYARAT per frame (semua harus terpenuhi untuk status "aktif"):
  1. Wrist di atas shoulder (>= 0.15 panjang torso)
  2. Ditahan & stabil (perpindahan wrist < 0.35 torso antar-frame berdekatan)
  3. Bukan sedang reach/hand_in_shelf/retract (label aksi dari Kepala Interaksi)
  4. Satu tangan saja (dua tangan terangkat = stretching/tos, bukan minta bantuan)
Plus: wrist tidak terlalu dekat hidung (< 0.45 torso = benerin rambut, bukan angkat tangan).

DUA BUG YANG WAJIB DITERAPKAN (tanpa ini, gestur nyaris tidak pernah lolos):

Bug A — jeda deteksi memutus gestur:
Deteksi pose YOLOv8 selalu berlubang (confidence turun sesaat). Tanpa
toleransi, satu gestur yang sebenarnya utuh 8 detik terpecah jadi banyak
runtun pendek yang masing-masing di bawah ambang durasi. angkat_toleransi_jeda
= 0.6 detik: jeda pendek TIDAK memutus rangkaian (dianggap kegagalan YOLO
sesaat, bukan tangan benar-benar turun). Meraih rak (syarat 3 gagal) tetap
memutus seketika — toleransi ini HANYA untuk jeda deteksi pose, bukan untuk
menutupi perubahan status gestur yang sebenarnya.

Bug B — pergantian sisi tangan memutus gestur:
Satu tangan yang diangkat bisa terbaca berganti sisi kiri->kanan->kiri
antar-frame karena pergelangan hilang-timbul (noise YOLO), bukan karena
orangnya benar-benar berganti tangan. Sisi (kiri/kanan) BOLEH berpindah
tanpa memutus rangkaian durasi. Syarat "satu tangan" tetap dijaga di
tingkat SATU FRAME oleh _status_satu_frame() — jadi stretching (dua tangan
naik bersamaan di frame yang sama) tetap ditolak, hanya pergantian sisi
antar-frame yang ditoleransi.
"""

import numpy as np

from .geometry import hip_center, torso_length

# Indeks sendi COCO-17
_NOSE = 0
_L_SHOULDER, _R_SHOULDER = 5, 6
_L_WRIST, _R_WRIST = 9, 10

CONF_MIN = 0.25   # minimum confidence keypoint agar dipakai

# Ambang geometri (fraksi panjang torso)
WRIST_ATAS_BAHU_MIN = 0.15
STABIL_MAKS_PERPINDAHAN = 0.35
WRIST_DEKAT_HIDUNG_MAKS = 0.45

# Label aksi dari Kepala Interaksi yang membatalkan gestur meski tangan naik
# (sesuai skema 2-kelas: hanya "inspecting" yang relevan sekarang, tapi
# nama lama disimpan untuk kompatibilitas bila skema 6-kelas dipakai lagi)
_AKSI_PEMBATAL = {"reach", "hand_in_shelf", "retract"}

# Durasi minimum tervalidasi pada klip nyata (lihat MASTER_PROMPT §4):
# gestur yang jelas disengaja berdurasi 2,40 detik; 2,5 melewatkannya,
# 2,0 masih jauh di atas tos (~0,5 detik).
DURASI_MIN_DEFAULT = 2.0
TOLERANSI_JEDA_DETIK = 0.6

# Mode Live: jendela live hanya 3 detik dan dievaluasi sendiri-sendiri,
# jadi 2,0 detik di dalam satu jendela sulit tercapai.
DURASI_MIN_LIVE = 1.2


def _status_satu_frame(kps: np.ndarray, action_label: str | None = None) -> dict:
    """
    Evaluasi 4 syarat pada SATU frame. Mengembalikan status per sisi supaya
    pemanggil bisa mengakumulasi durasi lintas frame dengan toleransi
    pergantian sisi (Bug B) tanpa kehilangan syarat "satu tangan" per frame.

    kps: [17, 3] — (x, y, confidence) koordinat MENTAH satu frame
    action_label: label aksi Kepala Interaksi pada frame ini (opsional)

    Returns dict:
      aktif: bool — status akhir frame ini (semua syarat terpenuhi)
      sisi: 'kiri' | 'kanan' | None — sisi yang terangkat bila aktif
    """
    torso = torso_length(kps)
    hip = hip_center(kps)
    shoulder_c = (kps[_L_SHOULDER, :2] + kps[_R_SHOULDER, :2]) / 2.0
    nose = kps[_NOSE]

    # Syarat 3: bukan sedang reach/hand_in_shelf/retract
    if action_label in _AKSI_PEMBATAL:
        return {"aktif": False, "sisi": None}

    sisi_terangkat = []
    for sisi, idx_wrist in (("kiri", _L_WRIST), ("kanan", _R_WRIST)):
        wrist = kps[idx_wrist]
        if wrist[2] < CONF_MIN or kps[_L_SHOULDER, 2] < CONF_MIN or kps[_R_SHOULDER, 2] < CONF_MIN:
            continue

        # Syarat 1: wrist di atas shoulder (koordinat image: y kecil = atas)
        tinggi_atas_bahu = (shoulder_c[1] - wrist[1]) / torso
        if tinggi_atas_bahu < WRIST_ATAS_BAHU_MIN:
            continue

        # Plus: wrist tidak terlalu dekat hidung (benerin rambut)
        if nose[2] >= CONF_MIN:
            jarak_hidung = float(np.linalg.norm(wrist[:2] - nose[:2])) / torso
            if jarak_hidung < WRIST_DEKAT_HIDUNG_MAKS:
                continue

        sisi_terangkat.append(sisi)

    # Syarat 4: satu tangan saja (dua tangan = stretching/tos)
    if len(sisi_terangkat) != 1:
        return {"aktif": False, "sisi": None}

    return {"aktif": True, "sisi": sisi_terangkat[0]}


def deteksi_angkat_tangan(
    frames: list,
    fps: float,
    action_labels: dict | None = None,
    durasi_min: float = DURASI_MIN_DEFAULT,
    toleransi_jeda: float = TOLERANSI_JEDA_DETIK,
) -> list:
    """
    Deteksi kejadian "angkat tangan minta bantuan" pada satu track penuh.

    frames: list of (frame_idx, keypoints[17,3]) — urutan MENTAH satu track,
            SUDAH terurut naik berdasar frame_idx (lihat extract.py).
    fps: laju frame ASLI video (bukan dst_fps) — dipakai untuk konversi
         jarak antar-frame dan ambang durasi ke satuan waktu nyata.
    action_labels: dict opsional {frame_idx: label} dari Kepala Interaksi,
                   untuk syarat 3. Tanpa ini, syarat 3 dilewati (selalu lolos).
    durasi_min: ambang durasi minimum gestur (detik). Pakai DURASI_MIN_LIVE
                untuk Mode Live.
    toleransi_jeda: jeda maksimum (detik) antar-frame status aktif yang
                    TIDAK memutus rangkaian (Bug A).

    Returns: list of {"tipe": "angkat_tangan", "t0": float, "t1": float,
                       "track_id": diisi pemanggil, "durasi": float}
             (t0/t1 dalam detik relatif terhadap awal video)
    """
    if len(frames) < 2:
        return []

    action_labels = action_labels or {}

    # Evaluasi status tiap frame + cek stabilitas (syarat 2) terhadap frame
    # SEBELUMNYA yang statusnya juga aktif di sisi yang sama — bukan wrist
    # mana pun, supaya Bug B (pergantian sisi) tidak ikut menghitung
    # perpindahan besar antara wrist kiri dan wrist kanan yang berbeda.
    kejadian = []
    run_awal_t = None
    run_akhir_t = None
    prev_wrist_pos = None
    prev_sisi = None
    prev_t = None

    for frame_idx, kps in frames:
        t = frame_idx / fps
        label = action_labels.get(frame_idx)
        status = _status_satu_frame(kps, label)

        stabil = True
        if status["aktif"] and prev_wrist_pos is not None and status["sisi"] == prev_sisi:
            # Syarat 2: perpindahan wrist antar-frame BERDEKATAN dalam sisi yang sama
            idx_wrist = _L_WRIST if status["sisi"] == "kiri" else _R_WRIST
            wrist_now = kps[idx_wrist, :2]
            torso = torso_length(kps)
            perpindahan = float(np.linalg.norm(wrist_now - prev_wrist_pos)) / torso
            stabil = perpindahan < STABIL_MAKS_PERPINDAHAN

        aktif_final = status["aktif"] and stabil

        if aktif_final:
            if run_awal_t is None:
                run_awal_t = t
            elif prev_t is not None and (t - prev_t) > toleransi_jeda:
                # Jeda lebih lama dari toleransi — anggap rangkaian baru,
                # tutup dulu yang lama bila sudah cukup panjang.
                if run_akhir_t is not None and (run_akhir_t - run_awal_t) >= durasi_min:
                    kejadian.append({
                        "tipe": "angkat_tangan",
                        "t0": run_awal_t, "t1": run_akhir_t,
                        "durasi": run_akhir_t - run_awal_t,
                    })
                run_awal_t = t
            run_akhir_t = t

            idx_wrist = _L_WRIST if status["sisi"] == "kiri" else _R_WRIST
            prev_wrist_pos = kps[idx_wrist, :2]
            prev_sisi = status["sisi"]
            prev_t = t
        else:
            # Tidak aktif frame ini — cek toleransi jeda sebelum menutup rangkaian.
            if run_awal_t is not None and prev_t is not None and (t - prev_t) <= toleransi_jeda:
                # Masih dalam toleransi jeda (Bug A) — biarkan rangkaian
                # tetap terbuka, tunggu frame aktif berikutnya.
                pass
            else:
                if run_awal_t is not None and run_akhir_t is not None and (run_akhir_t - run_awal_t) >= durasi_min:
                    kejadian.append({
                        "tipe": "angkat_tangan",
                        "t0": run_awal_t, "t1": run_akhir_t,
                        "durasi": run_akhir_t - run_awal_t,
                    })
                run_awal_t = None
                run_akhir_t = None
                prev_wrist_pos = None
                prev_sisi = None
            # prev_t TIDAK direset di sini — dibutuhkan untuk mengukur jeda
            # ke frame aktif berikutnya bila rangkaian masih terbuka.
            if run_awal_t is None:
                prev_t = None
            else:
                prev_t = t

    # Flush rangkaian yang masih terbuka di akhir sekuens.
    if run_awal_t is not None and run_akhir_t is not None and (run_akhir_t - run_awal_t) >= durasi_min:
        kejadian.append({
            "tipe": "angkat_tangan",
            "t0": run_awal_t, "t1": run_akhir_t,
            "durasi": run_akhir_t - run_awal_t,
        })

    return kejadian
