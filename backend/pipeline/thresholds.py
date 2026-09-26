"""
pipeline/thresholds.py — SAPA

Ambang deteksi jatuh, dipusatkan di satu tempat (bukan disebar di app.py,
live_server.py, production/profiles.py) supaya ketiga jalur (unggah, Mode
Live, Mode Produksi) memakai definisi yang sama dan mudah dibandingkan.

Kalibrasi berlaku untuk fall_head_dev80.pt (lihat models/fall_head.json,
field selected_fall_threshold) — hasil 5-fold OOF pada development set,
prob-only tanpa syarat sudut (fall_f1=0.8424 OOF, 0.8749 test holdout).

fall_angle di sini dikalibrasi terhadap window_torso_angle() versi
atan2(|dx|,|dy|) (rentang [0°,90°] — lihat pipeline/geometry.py), BUKAN
versi arccos lama (rentang [0°,180°]). Video jatuh nyata (video/Jatuh.mp4)
memberi sudut 72-73° pada window yang prob_jatuh-nya 0.88-0.92, jauh di
atas ambang manapun yang masuk akal di sini — fall_angle kecil (5°) dipilih
sebagai pengaman tambahan terhadap kasus di luar distribusi training,
tanpa menghalangi kasus jatuh nyata yang sudah diverifikasi.

fall_confirm mati (fall_angle diabaikan) untuk camera_type="rak": kamera
top-down membuat vektor bahu-pinggul tampak nyaris horizontal bahkan saat
orang berdiri membungkuk mengambil barang (terverifikasi: video normal
top-down bisa memberi angle 85-89°) — syarat sudut di situ tidak berguna,
sudah ditangani terpisah lewat run_fall=False untuk camera_type="rak".
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PresetAmbang:
    nama: str
    fall_thr: float
    fall_angle: float | None   # None = fall_confirm mati (prob-only)
    fall_speed: float | None   # None = syarat kecepatan mati


# T_prob=0.57 sesuai selected_fall_threshold di fall_head.json (training
# terbaru, prob-only). T_angle=5° mengikuti preset MASTER_PROMPT sebagai
# pengaman minimal — lihat docstring modul untuk bukti kalibrasi.
PRESET_PROB_SUDUT = PresetAmbang("prob_sudut", fall_thr=0.57, fall_angle=5.0, fall_speed=None)
PRESET_PROB_SAJA  = PresetAmbang("prob_saja",  fall_thr=0.57, fall_angle=None, fall_speed=None)

PRESETS: dict[str, PresetAmbang] = {
    "prob_sudut": PRESET_PROB_SUDUT,
    "prob_saja":  PRESET_PROB_SAJA,
}

DEFAULT_PRESET = "prob_sudut"


def ambil_preset(nama: str = DEFAULT_PRESET) -> PresetAmbang:
    """Ambil preset ambang berdasarkan nama; fallback ke default bila tidak ada."""
    return PRESETS.get(nama, PRESET_PROB_SUDUT)


def cfg_dari_preset(preset: PresetAmbang) -> dict:
    """Konversi preset ke potongan dict cfg yang dipakai analyze()."""
    return {
        "fall_thr": preset.fall_thr,
        "fall_confirm": preset.fall_angle is not None,
        "fall_angle": preset.fall_angle if preset.fall_angle is not None else 0.0,
    }
