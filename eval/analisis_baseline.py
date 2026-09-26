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

import csv
import json
import os
from pathlib import Path
import tempfile

import numpy as np

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "sapa-mpl"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = Path(__file__).resolve().parent
DIR_HASIL = BASE / "hasil"

FALL_CLASSES = ["normal", "oleng", "jatuh"]
# Urutan sesuai geometry.py INTERACTION_CLASS_NAMES
INTER_CLASSES = ["background", "reach", "retract", "hand_in_shelf",
                  "inspect_product", "inspect_shelf"]
INSPECT_IDX = [4, 5]  # inspect_product, inspect_shelf → gabung jadi "inspecting"


def validasi_confusion_matrix(cm: np.ndarray, nama_kelas: list, sumber: Path) -> None:
    """Tolak matriks rusak agar laporan tidak diam-diam menghasilkan angka salah."""
    n = len(nama_kelas)
    if cm.shape != (n, n):
        raise ValueError(f"{sumber}: bentuk confusion matrix harus {n}x{n}, bukan {cm.shape}")
    if not np.issubdtype(cm.dtype, np.integer) or np.any(cm < 0):
        raise ValueError(f"{sumber}: confusion matrix harus berisi integer nonnegatif")
    if int(cm.sum()) == 0:
        raise ValueError(f"{sumber}: confusion matrix kosong")


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


def f1_per_pasangan_kelas(cm: np.ndarray, nama_kelas: list) -> list:
    """F1 setiap pasangan berdasarkan baris aktual A/B pada CM agregat.

    Prediksi ke kelas di luar pasangan tetap dihitung sebagai kesalahan. Definisi
    ini sama dengan evaluator OOF di ``infrence fall/scripts/metrics.py`` dan
    tidak membuang kesalahan ke kelas ketiga.
    """
    hasil = []
    for i in range(len(nama_kelas)):
        for j in range(i + 1, len(nama_kelas)):
            def metrik(kelas, lawan):
                tp = int(cm[kelas, kelas])
                fn = int(cm[kelas, :].sum() - tp)
                fp = int(cm[lawan, kelas])
                precision = tp / (tp + fp) if tp + fp else 0.0
                recall = tp / (tp + fn) if tp + fn else 0.0
                f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
                return precision, recall, f1

            pa, ra, fa = metrik(i, j)
            pb, rb, fb = metrik(j, i)
            outside = int(cm[[i, j], :].sum() - cm[i, i] - cm[i, j] - cm[j, i] - cm[j, j])
            hasil.append({
                "kelas_a": nama_kelas[i],
                "kelas_b": nama_kelas[j],
                "dukungan_a": int(cm[i, :].sum()),
                "dukungan_b": int(cm[j, :].sum()),
                "a_ke_b": int(cm[i, j]),
                "b_ke_a": int(cm[j, i]),
                "prediksi_di_luar_pasangan": outside,
                "precision_a": round(pa, 4),
                "recall_a": round(ra, 4),
                "f1_a": round(fa, 4),
                "precision_b": round(pb, 4),
                "recall_b": round(rb, 4),
                "f1_b": round(fb, 4),
                "macro_f1_pasangan": round((fa + fb) / 2, 4),
            })
    return sorted(hasil, key=lambda x: (x["macro_f1_pasangan"], x["kelas_a"], x["kelas_b"]))


def simpan_csv(path: Path, rows: list) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_confusion_matrix(cm: np.ndarray, nama_kelas: list, judul: str, path: Path) -> None:
    ukuran = max(6.5, len(nama_kelas) * 1.25)
    fig, ax = plt.subplots(figsize=(ukuran, ukuran * 0.86))
    ax.imshow(cm, cmap="Blues")
    ax.set(xticks=range(len(nama_kelas)), yticks=range(len(nama_kelas)),
           xticklabels=nama_kelas, yticklabels=nama_kelas,
           xlabel="Prediksi", ylabel="Aktual", title=judul)
    plt.setp(ax.get_xticklabels(), rotation=35, ha="right")
    ambang = float(cm.max()) / 2
    for i in range(len(nama_kelas)):
        for j in range(len(nama_kelas)):
            ax.text(j, i, str(int(cm[i, j])), ha="center", va="center",
                    color="white" if cm[i, j] > ambang else "black")
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def plot_f1_per_kelas(metrik: dict, judul: str, path: Path) -> None:
    nama = list(metrik["per_kelas"])
    nilai = [metrik["per_kelas"][k]["f1"] for k in nama]
    fig, ax = plt.subplots(figsize=(max(7, len(nama) * 1.35), 4.8))
    ax.bar(nama, nilai, color="#215c80")
    for i, value in enumerate(nilai):
        ax.text(i, value + 0.025, f"{value:.3f}", ha="center")
    ax.set(ylim=(0, 1.12), ylabel="F1", title=judul)
    ax.tick_params(axis="x", labelrotation=30)
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def plot_f1_pasangan(rows: list, judul: str, path: Path) -> None:
    """Tampilkan seluruh pasangan dari F1 terendah ke tertinggi."""
    labels = [f"{r['kelas_a']} × {r['kelas_b']}" for r in rows]
    values = [r["macro_f1_pasangan"] for r in rows]
    fig, ax = plt.subplots(figsize=(10, max(5, len(rows) * 0.46)))
    positions = np.arange(len(rows))
    ax.barh(positions, values, color="#ae443e")
    ax.set(yticks=positions, yticklabels=labels, xlim=(0, 1.08), xlabel="Macro-F1 pasangan", title=judul)
    ax.invert_yaxis()
    for y, value in zip(positions, values):
        ax.text(value + 0.012, y, f"{value:.3f}", va="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


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
    validasi_confusion_matrix(cm_fall, FALL_CLASSES, fall_path)
    validasi_confusion_matrix(cm_inter, INTER_CLASSES, inter_path)

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
            "f1_per_pasangan_kelas": f1_per_pasangan_kelas(cm_fall, FALL_CLASSES),
        },
        "kepala_interaksi": {
            "kelas": INTER_CLASSES,
            "confusion_matrix": cm_inter.tolist(),
            "metrik": metrik_per_kelas(cm_inter, INTER_CLASSES),
            "top_pasangan_tertukar": top_pasangan_tertukar(cm_inter, INTER_CLASSES, k=3),
            "f1_per_pasangan_kelas": f1_per_pasangan_kelas(cm_inter, INTER_CLASSES),
            "reevaluasi_2kelas_inspecting_vs_other": reevaluasi_2kelas_interaksi(cm_inter),
        },
        "keterbatasan": [
            "Metrik berasal dari confusion matrix OOF agregat; prediksi per sampel, fold, yaw/pitch, dan performer tidak tersedia.",
            "F1 pasangan mempertahankan prediksi ke kelas di luar pasangan sebagai kesalahan.",
            "Provenance training/fold tidak dapat dibuktikan ulang tanpa ekspor OOF mentah.",
        ],
    }

    DIR_HASIL.mkdir(exist_ok=True)
    out_path = DIR_HASIL / "baseline_analisis.json"
    out_path.write_text(json.dumps(hasil, indent=2, ensure_ascii=False))
    simpan_csv(DIR_HASIL / "fall_per_kelas.csv", [dict(kelas=k, **v) for k, v in hasil["kepala_jatuh"]["metrik"]["per_kelas"].items()])
    simpan_csv(DIR_HASIL / "interaction_per_kelas.csv", [dict(kelas=k, **v) for k, v in hasil["kepala_interaksi"]["metrik"]["per_kelas"].items()])
    simpan_csv(DIR_HASIL / "fall_f1_per_pasangan.csv", hasil["kepala_jatuh"]["f1_per_pasangan_kelas"])
    simpan_csv(DIR_HASIL / "interaction_f1_per_pasangan.csv", hasil["kepala_interaksi"]["f1_per_pasangan_kelas"])
    plot_confusion_matrix(cm_fall, FALL_CLASSES, "Kepala jatuh — confusion matrix OOF", DIR_HASIL / "fall_confusion_matrix.png")
    plot_confusion_matrix(cm_inter, INTER_CLASSES, "Kepala interaksi — confusion matrix OOF", DIR_HASIL / "interaction_confusion_matrix.png")
    plot_f1_per_kelas(hasil["kepala_jatuh"]["metrik"], "Kepala jatuh — F1 per kelas", DIR_HASIL / "fall_f1_per_kelas.png")
    plot_f1_per_kelas(hasil["kepala_interaksi"]["metrik"], "Kepala interaksi — F1 per kelas", DIR_HASIL / "interaction_f1_per_kelas.png")
    plot_f1_pasangan(hasil["kepala_jatuh"]["f1_per_pasangan_kelas"], "Kepala jatuh — F1 per pasangan kelas", DIR_HASIL / "fall_f1_per_pasangan.png")
    plot_f1_pasangan(hasil["kepala_interaksi"]["f1_per_pasangan_kelas"], "Kepala interaksi — F1 per pasangan kelas", DIR_HASIL / "interaction_f1_per_pasangan.png")
    weakest = hasil["kepala_interaksi"]["f1_per_pasangan_kelas"][0]
    (DIR_HASIL / "README.md").write_text(
        "# Baseline OOF agregat — kepala jatuh dan interaksi\n\n"
        "Angka dihitung ulang dari confusion matrix OOF agregat di `eval/fall_cv_summary.json` dan "
        "`eval/interaction_cv_summary.json`. Data prediksi per sampel dan metadata slice belum tersedia.\n\n"
        "## Kepala jatuh\n\n"
        "![Confusion matrix kepala jatuh](fall_confusion_matrix.png)\n\n"
        "![F1 kepala jatuh](fall_f1_per_kelas.png)\n\n"
        "![F1 pasangan kepala jatuh](fall_f1_per_pasangan.png)\n\n"
        "- [Metrik per kelas](fall_per_kelas.csv)\n"
        "- [F1 per pasangan kelas](fall_f1_per_pasangan.csv)\n\n"
        "## Kepala interaksi\n\n"
        "![Confusion matrix kepala interaksi](interaction_confusion_matrix.png)\n\n"
        "![F1 kepala interaksi](interaction_f1_per_kelas.png)\n\n"
        "![F1 pasangan kepala interaksi](interaction_f1_per_pasangan.png)\n\n"
        "- [Metrik per kelas](interaction_per_kelas.csv)\n"
        "- [F1 per pasangan kelas](interaction_f1_per_pasangan.csv)\n"
        "- [JSON lengkap](baseline_analisis.json)\n\n"
        f"Pasangan interaksi terlemah adalah **{weakest['kelas_a']} × {weakest['kelas_b']}** "
        f"dengan macro-F1 {weakest['macro_f1_pasangan']:.4f}. F1 pasangan dihitung pada baris aktual dua kelas terkait. Prediksi ke kelas lain tetap dihitung "
        "sebagai kesalahan. Hasil ini tidak dapat dipakai untuk analisis yaw/pitch atau performer karena "
        "metadata dan prediksi OOF mentah tidak tersedia.\n",
        encoding="utf-8",
    )

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
