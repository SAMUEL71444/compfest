"""
eval/analisis_baseline.py — SAPA

Analisis baseline Fase Eval: metrik per kelas, pasangan kelas paling
tertukar, dan re-evaluasi 2-kelas untuk Kepala Interaksi — semua dihitung
ULANG dari confusion matrix OOF (bukan disalin dari ringkasan lama).

Sumber data:
    eval/fall_cv_summary.json         (Kepala Jatuh — 3 kelas)
    eval/interaction_cv_summary.json  (Kepala Interaksi — 6 kelas)

Keluaran:
    eval/hasil/baseline_analisis.json — angka mentah, untuk divisualisasikan
                                         di tempat lain (mis. Colab).

CARA PAKAI
    backend/.venv/bin/python eval/analisis_baseline.py
"""

import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
DIR_HASIL = BASE / "hasil"

FALL_CLASSES = ["normal", "oleng", "jatuh"]
# Urutan sesuai geometry.py INTERACTION_CLASS_NAMES
INTER_CLASSES = ["background", "reach", "retract", "hand_in_shelf",
                  "inspect_product", "inspect_shelf"]
INSPECT_IDX = [4, 5]  # inspect_product, inspect_shelf → gabung jadi "inspecting"


def metrik_per_kelas(cm: np.ndarray, nama_kelas: list) -> dict:
    """Precision/recall/F1 per kelas, dihitung ulang dari confusion matrix.

    cm[i, j] = jumlah sampel kelas asli i yang diprediksi sebagai kelas j.
    """
    n = len(nama_kelas)
    tp = np.diag(cm).astype(float)
    dukungan = cm.sum(axis=1).astype(float)   # jumlah sampel asli per kelas
    diprediksi = cm.sum(axis=0).astype(float)  # jumlah prediksi per kelas

    hasil = {}
    for i, kelas in enumerate(nama_kelas):
        recall = tp[i] / dukungan[i] if dukungan[i] > 0 else 0.0
        precision = tp[i] / diprediksi[i] if diprediksi[i] > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) > 0 else 0.0)
        hasil[kelas] = {
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "f1": round(float(f1), 4),
            "dukungan": int(dukungan[i]),
        }

    total = cm.sum()
    akurasi = float(tp.sum() / total) if total > 0 else 0.0
    macro_f1 = float(np.mean([hasil[k]["f1"] for k in nama_kelas]))

    return {
        "per_kelas": hasil,
        "akurasi": round(akurasi, 4),
        "macro_f1": round(macro_f1, 4),
    }


def top_pasangan_tertukar(cm: np.ndarray, nama_kelas: list, k: int = 3) -> list:
    """Top-k pasangan (asli, prediksi) off-diagonal dengan jumlah kesalahan
    terbanyak, digabung dua arah (i→j dan j→i) supaya "reach↔retract"
    tampil sebagai satu pasangan, bukan dua baris terpisah."""
    n = len(nama_kelas)
    pasangan = {}
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            key = tuple(sorted((i, j)))
            pasangan.setdefault(key, {"a_ke_b": 0, "b_ke_a": 0})
            if key == (i, j):
                pasangan[key]["a_ke_b"] += int(cm[i, j])
            else:
                pasangan[key]["b_ke_a"] += int(cm[i, j])

    daftar = []
    for (a, b), v in pasangan.items():
        total = v["a_ke_b"] + v["b_ke_a"]
        daftar.append({
            "kelas_a": nama_kelas[a],
            "kelas_b": nama_kelas[b],
            f"{nama_kelas[a]}_ke_{nama_kelas[b]}": v["a_ke_b"],
            f"{nama_kelas[b]}_ke_{nama_kelas[a]}": v["b_ke_a"],
            "total_tertukar": total,
        })
    daftar.sort(key=lambda x: x["total_tertukar"], reverse=True)
    return daftar[:k]


def reevaluasi_2kelas_interaksi(cm: np.ndarray) -> dict:
    """Gabung inspect_product + inspect_shelf → 'inspecting', sisanya
    'other'. Hitung ulang precision/recall/F1 dari confusion matrix asli
    (bukan re-run model), agar mencerminkan performa nyata fitur
    "butuh bantuan" yang benar-benar dipakai produk."""
    n = cm.shape[0]
    idx_inspecting = set(INSPECT_IDX)

    # Bangun confusion matrix 2x2: baris/kolom 0=other, 1=inspecting
    cm2 = np.zeros((2, 2), dtype=float)
    for i in range(n):
        gi = 1 if i in idx_inspecting else 0
        for j in range(n):
            gj = 1 if j in idx_inspecting else 0
            cm2[gi, gj] += cm[i, j]

    hasil = metrik_per_kelas(cm2, ["other", "inspecting"])
    hasil["confusion_matrix_2x2"] = cm2.astype(int).tolist()
    hasil["catatan"] = (
        "inspecting = inspect_product + inspect_shelf (indeks "
        f"{INSPECT_IDX}); other = 4 kelas lain. Ini metrik yang relevan "
        "untuk fitur 'butuh bantuan' karena pipeline (lihat analyze.py) "
        "hanya memakai argmax masuk ke inspect_idx, bukan 6 kelas penuh."
    )
    return hasil


def main():
    fall_path = BASE / "fall_cv_summary.json"
    inter_path = BASE / "interaction_cv_summary.json"

    fall_cv = json.loads(fall_path.read_text())
    inter_cv = json.loads(inter_path.read_text())

    cm_fall = np.array(fall_cv["oof_confusion_matrix"])
    cm_inter = np.array(inter_cv["oof_confusion_matrix"])

    hasil = {
        "sumber": {
            "fall": str(fall_path.relative_to(BASE.parent)),
            "interaction": str(inter_path.relative_to(BASE.parent)),
        },
        "kepala_jatuh": {
            "kelas": FALL_CLASSES,
            "confusion_matrix": cm_fall.tolist(),
            "metrik": metrik_per_kelas(cm_fall, FALL_CLASSES),
            "top_pasangan_tertukar": top_pasangan_tertukar(cm_fall, FALL_CLASSES, k=3),
        },
        "kepala_interaksi": {
            "kelas": INTER_CLASSES,
            "confusion_matrix": cm_inter.tolist(),
            "metrik": metrik_per_kelas(cm_inter, INTER_CLASSES),
            "top_pasangan_tertukar": top_pasangan_tertukar(cm_inter, INTER_CLASSES, k=3),
            "reevaluasi_2kelas_inspecting_vs_other": reevaluasi_2kelas_interaksi(cm_inter),
        },
    }

    DIR_HASIL.mkdir(exist_ok=True)
    out_path = DIR_HASIL / "baseline_analisis.json"
    out_path.write_text(json.dumps(hasil, indent=2, ensure_ascii=False))

    # Ringkasan singkat ke terminal supaya bisa langsung dibaca tanpa buka JSON
    print(f"Ditulis ke {out_path.relative_to(BASE.parent)}\n")

    print("== Kepala Jatuh (3 kelas) ==")
    for kelas, m in hasil["kepala_jatuh"]["metrik"]["per_kelas"].items():
        print(f"  {kelas:10s}  precision={m['precision']:.3f}  recall={m['recall']:.3f}  "
              f"f1={m['f1']:.3f}  n={m['dukungan']}")
    print(f"  akurasi={hasil['kepala_jatuh']['metrik']['akurasi']:.3f}  "
          f"macro_f1={hasil['kepala_jatuh']['metrik']['macro_f1']:.3f}")
    print("  Top pasangan tertukar:")
    for p in hasil["kepala_jatuh"]["top_pasangan_tertukar"]:
        print(f"    {p['kelas_a']} <-> {p['kelas_b']}: total {p['total_tertukar']}")

    print("\n== Kepala Interaksi (6 kelas) ==")
    for kelas, m in hasil["kepala_interaksi"]["metrik"]["per_kelas"].items():
        print(f"  {kelas:16s}  precision={m['precision']:.3f}  recall={m['recall']:.3f}  "
              f"f1={m['f1']:.3f}  n={m['dukungan']}")
    print(f"  akurasi={hasil['kepala_interaksi']['metrik']['akurasi']:.3f}  "
          f"macro_f1={hasil['kepala_interaksi']['metrik']['macro_f1']:.3f}")
    print("  Top pasangan tertukar:")
    for p in hasil["kepala_interaksi"]["top_pasangan_tertukar"]:
        print(f"    {p['kelas_a']} <-> {p['kelas_b']}: total {p['total_tertukar']}")

    print("\n== Re-evaluasi 2 kelas: inspecting vs other ==")
    r2 = hasil["kepala_interaksi"]["reevaluasi_2kelas_inspecting_vs_other"]
    for kelas, m in r2["per_kelas"].items():
        print(f"  {kelas:12s}  precision={m['precision']:.3f}  recall={m['recall']:.3f}  "
              f"f1={m['f1']:.3f}  n={m['dukungan']}")
    print(f"  akurasi={r2['akurasi']:.3f}  macro_f1={r2['macro_f1']:.3f}")


if __name__ == "__main__":
    main()
