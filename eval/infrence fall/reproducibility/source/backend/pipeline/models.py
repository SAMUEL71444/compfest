"""
pipeline/models.py — SAPA

Definisi arsitektur & loader untuk dua kepala BiLSTM (FallLSTM & InteractionLSTM).
Arsitektur ini direkonstruksi langsung dari state_dict fall_head.pt dan
interaction_head.pt (bukan tebakan) — sudah diverifikasi load_state_dict(strict=True)
berhasil 100% match untuk keduanya, dan forward pass menghasilkan output shape yang benar.

PENTING:
- Head classifier pakai LayerNorm (BUKAN BatchNorm). File .pt tidak menyimpan
  running_mean/running_var, jadi kalau dipaksa pakai BatchNorm1d, load_state_dict
  akan gagal ("Missing key(s): head.0.running_mean, head.0.running_var").
- Agregasi temporal = MEAN-POOLING (lihat BiLSTMHead.forward). load_state_dict
  yang berhasil TIDAK membuktikan forward-pass sudah benar: mean-pooling dan
  hidden-state-terakhir memakai parameter yang identik, jadi keduanya lolos
  strict=True sekalipun hasilnya berbeda jauh. Rujukan kebenaran adalah kode
  training (Train_fall.ipynb / Kepala Interaksi.ipynb), bukan keberhasilan load.
- Fall head: input_dim=24 (12 sendi x 2 channel [x,y]), output 3 kelas
  (index 0=normal, 1=oleng, 2=jatuh).
- Interaction head: input_dim=51 (17 sendi x 3 channel [x,y,conf]), output 6 kelas
  (background, reach, retract, hand_in_shelf, inspect_product, inspect_shelf).
- Kedua kepala: BiLSTM hidden=128, num_layers=2, dropout=0.3, lalu ambil hidden
  state terakhir (forward ⊕ backward, 256-dim), masuk head Sequential
  [LayerNorm(256), Dropout(0.3), Linear(256, n_classes)].
"""

import json
import torch
import torch.nn as nn


class BiLSTMHead(nn.Module):
    """Arsitektur bersama untuk Kepala Jatuh maupun Kepala Interaksi."""

    def __init__(self, in_dim: int, hidden: int = 128, layers: int = 2,
                 n_classes: int = 3, dropout: float = 0.3):
        super().__init__()
        self.in_dim = in_dim
        self.hidden = hidden
        self.layers = layers
        self.n_classes = n_classes

        self.lstm = nn.LSTM(
            input_size=in_dim,
            hidden_size=hidden,
            num_layers=layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.LayerNorm(hidden * 2),
            nn.Dropout(dropout),
            nn.Linear(hidden * 2, n_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: [B, T, in_dim]  (T = jumlah frame per jendela, default 45)
        return: logits [B, n_classes]  (belum softmax — pakai torch.softmax saat inferensi)

        AGREGASI HARUS MEAN-POOLING SELURUH LANGKAH WAKTU.
        Ini bukan pilihan gaya — harus sama persis dengan saat training:

            Train_fall.ipynb      → out, _ = self.lstm(x); self.head(out.mean(dim=1))
            Kepala Interaksi.ipynb → out, _ = self.lstm(x); self.head(out.mean(dim=1))

        Versi sebelumnya memakai hidden state terakhir, cat(h_n[-2], h_n[-1]).
        Keduanya menghasilkan tensor [B, hidden*2] dari PARAMETER YANG SAMA
        PERSIS, sehingga load_state_dict(strict=True) tetap lolos dan tidak ada
        error apa pun yang muncul — tapi fitur yang dihitung berbeda, dan
        prediksinya ikut berbeda. Pada bobot fall_head, kedua varian hanya
        sepakat 46% dari waktu. Ini persis mode kegagalan senyap yang
        diperingatkan README: tidak error, tapi prediksi ngawur.
        """
        out, _ = self.lstm(x)          # [B, T, hidden*2]
        return self.head(out.mean(dim=1))


def load_head(weight_path: str, config_path: str, device: str = "cpu") -> tuple:
    """
    Load satu kepala (fall atau interaction) dari file .pt + .json config.

    Contoh:
        fall_model, fall_cfg = load_head("models/fall_head.pt", "models/fall_head.json")
        inter_model, inter_cfg = load_head("models/interaction_head.pt", "models/interaction_head.json")
    """
    with open(config_path, "r") as f:
        cfg = json.load(f)

    model = BiLSTMHead(
        in_dim=cfg["in_dim"],
        hidden=cfg.get("hidden", 128),
        layers=cfg.get("layers", 2),
        n_classes=cfg["n_classes"],
        dropout=cfg.get("dropout", 0.3),
    )
    state_dict = torch.load(weight_path, map_location=device, weights_only=False)
    model.load_state_dict(state_dict, strict=True)
    model.to(device)
    model.eval()
    return model, cfg


@torch.no_grad()
def predict_proba(model: BiLSTMHead, windows: torch.Tensor) -> torch.Tensor:
    """
    windows: [W, T, in_dim] — batch jendela hasil make_windows() (sudah dinormalisasi,
             di-resample ke 15fps, di-reshape sesuai in_dim kepala terkait).
    return: [W, n_classes] probabilitas (softmax).
    """
    model.eval()
    logits = model(windows)
    return torch.softmax(logits, dim=1)


# ------------------------------------------------------------------
# Verifikasi cepat kalau file ini dijalankan langsung (opsional, buat sanity check)
# ------------------------------------------------------------------
if __name__ == "__main__":
    import os

    base = os.path.dirname(os.path.dirname(__file__))

    fall_pt = os.path.join(base, "models", "fall_head.pt")
    fall_json = os.path.join(base, "models", "fall_head.json")
    inter_pt = os.path.join(base, "models", "interaction_head.pt")
    inter_json = os.path.join(base, "models", "interaction_head.json")

    if os.path.exists(fall_pt) and os.path.exists(fall_json):
        m, cfg = load_head(fall_pt, fall_json)
        dummy = torch.randn(2, cfg.get("window", 45), cfg["in_dim"])
        probs = predict_proba(m, dummy)
        print("Fall head OK. output shape:", probs.shape, "classes:", cfg["class_names"])

    if os.path.exists(inter_pt) and os.path.exists(inter_json):
        m, cfg = load_head(inter_pt, inter_json)
        dummy = torch.randn(2, cfg.get("window", 45), cfg["in_dim"])
        probs = predict_proba(m, dummy)
        print("Interaction head OK. output shape:", probs.shape)
