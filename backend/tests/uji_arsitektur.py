"""
Uji arsitektur — mengunci pipeline/models.py terhadap kode training.

KENAPA UJI INI ADA
------------------
BiLSTMHead pernah memakai hidden state terakhir, `cat(h_n[-2], h_n[-1])`,
padahal training memakai mean-pooling, `out.mean(dim=1)`. Kedua varian:

  - memakai PARAMETER yang persis sama,
  - menghasilkan tensor [B, hidden*2] yang sama bentuknya,
  - lolos load_state_dict(strict=True) tanpa peringatan apa pun.

Tidak ada error yang muncul. Yang berubah hanya prediksinya — pada bobot
fall_head kedua varian cuma sepakat 46% dari waktu. Karena itu "model berhasil
dimuat" TIDAK PERNAH cukup sebagai bukti; satu-satunya rujukan kebenaran adalah
kode training, dan uji ini menyalinnya apa adanya lalu membandingkan keluaran.

Butuh torch + bobot asli. Jalankan dengan venv backend:
    .venv/bin/python tests/uji_arsitektur.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except ImportError:
    print("torch tidak tersedia — uji arsitektur dilewati.")
    print("Jalankan dengan venv backend: .venv/bin/python tests/uji_arsitektur.py")
    sys.exit(0)


class ArsitekturTraining(nn.Module):
    """
    SALINAN PERSIS dari Train_fall.ipynb dan Kepala Interaksi.ipynb.
    Jangan "dirapikan" — nilainya justru pada kemiripan harfiahnya.
    """

    def __init__(self, in_dim, hidden=128, layers=2, n_classes=3, dropout=0.3):
        super().__init__()
        self.lstm = nn.LSTM(in_dim, hidden, layers, batch_first=True,
                            bidirectional=True, dropout=dropout if layers > 1 else 0.0)
        self.head = nn.Sequential(nn.LayerNorm(hidden * 2), nn.Dropout(dropout),
                                  nn.Linear(hidden * 2, n_classes))

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.head(out.mean(dim=1))


lulus, gagal = 0, 0


def cek(nama, kondisi, info=""):
    global lulus, gagal
    if kondisi:
        lulus += 1
        print(f"  ok   {nama}")
    else:
        gagal += 1
        print(f"  GAGAL {nama}  {info}")


def main():
    from pipeline.models import load_head

    torch.manual_seed(0)
    kepala = [
        ("Kepala Jatuh",    "fall_head.pt",        "fall_head.json"),
        ("Kepala Interaksi", "interaction_head.pt", "interaction_head.json"),
    ]

    for nama, pt, js in kepala:
        pt_path = os.path.join(BASE, "models", pt)
        js_path = os.path.join(BASE, "models", js)
        print(f"\n[{nama}]")

        if not (os.path.exists(pt_path) and os.path.exists(js_path)):
            print(f"  bobot tidak ada ({pt}) — dilewati.")
            continue

        cfg = json.load(open(js_path))
        repo, _ = load_head(pt_path, js_path)

        ref = ArsitekturTraining(cfg["in_dim"], cfg["hidden"], cfg["layers"],
                                 cfg["n_classes"], cfg["dropout"])
        ref.load_state_dict(
            torch.load(pt_path, map_location="cpu", weights_only=False), strict=True
        )
        ref.eval()

        x = torch.randn(256, cfg.get("window", 45), cfg["in_dim"])
        with torch.no_grad():
            a = F.softmax(repo(x), dim=1)
            b = F.softmax(ref(x), dim=1)

        selisih = (a - b).abs().max().item()
        sepakat = (a.argmax(1) == b.argmax(1)).float().mean().item()

        cek("keluaran identik dengan kode training", selisih < 1e-6, f"selisih maks={selisih:.3e}")
        cek("prediksi sepakat 100%", sepakat == 1.0, f"sepakat={sepakat*100:.1f}%")

        # Invarian bentuk masukan (KONTEKS §11): 12 sendi × x,y untuk jatuh,
        # 17 sendi × x,y,conf untuk interaksi.
        if "fall_joints" in cfg:
            cek("12 sendi × 2 channel = 24 dim",
                len(cfg["fall_joints"]) * cfg["use_channels"] == cfg["in_dim"],
                f"{len(cfg['fall_joints'])}×{cfg['use_channels']} != {cfg['in_dim']}")
            cek("sendi jatuh = indeks 5..16", cfg["fall_joints"] == list(range(5, 17)))
        if cfg["arch"] == "InteractionLSTM":
            # interaction_head.json tidak memuat daftar "joints", jadi jumlah
            # sendi diturunkan dari in_dim: 17 sendi × 3 channel = 51.
            cek("17 sendi × 3 channel = 51 dim",
                cfg["in_dim"] == 17 * cfg["use_channels"] == 51,
                f"in_dim={cfg['in_dim']} use_channels={cfg['use_channels']}")
            cek("inspect_idx = [4, 5] sesuai notebook training",
                cfg.get("inspect_idx") == [4, 5], f"config={cfg.get('inspect_idx')}")

    print(f"\n{'='*52}\nLULUS {lulus} / {lulus+gagal}"
          + (f"  — GAGAL {gagal}" if gagal else "  — semua lulus"))
    return 1 if gagal else 0


if __name__ == "__main__":
    sys.exit(main())
