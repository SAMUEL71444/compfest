#!/usr/bin/env python3
"""Build reproducible tables, confusion matrices, and the evaluation README."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def pct(value):
    return "N/A" if value is None else f"{100 * value:.1f}%"


def combined_metrics(cases):
    tp = fp = fn = tn = 0
    for case in cases:
        actual = case["expected"] != "negative"
        predicted = case["predicted_combined"]
        if actual and predicted: tp += 1
        elif not actual and predicted: fp += 1
        elif actual and not predicted: fn += 1
        else: tn += 1
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision, "recall": recall, "f1": f1}


def draw_cm(matrix, labels, title, output):
    matrix = np.asarray(matrix, dtype=int)
    canvas = np.full((620, 720, 3), 255, dtype=np.uint8)
    cv2.putText(canvas, title, (50, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
    cv2.putText(canvas, "Prediksi", (350, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (20, 20, 20), 2)
    cv2.putText(canvas, "Aktual", (35, 320), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (20, 20, 20), 2)
    cell = 190
    x0, y0 = 245, 150
    maximum = max(int(matrix.max()), 1)
    for col, label in enumerate(labels):
        cv2.putText(canvas, label, (x0 + col * cell + 40, 130), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (20, 20, 20), 1)
    for row, label in enumerate(labels):
        cv2.putText(canvas, label, (95, y0 + row * cell + 105), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (20, 20, 20), 1)
    for row in range(2):
        for col in range(2):
            value = int(matrix[row, col])
            strength = int(235 - 170 * value / maximum)
            color = (235, strength + 15, strength)
            p1 = (x0 + col * cell, y0 + row * cell)
            p2 = (p1[0] + cell, p1[1] + cell)
            cv2.rectangle(canvas, p1, p2, color, -1)
            cv2.rectangle(canvas, p1, p2, (255, 255, 255), 2)
            cv2.putText(canvas, str(value), (p1[0] + 80, p1[1] + 105),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.1, (10, 10, 10), 2)
    cv2.imwrite(str(output), canvas)


def main():
    run_ref = (REPORTS / "latest_run.txt").read_text().strip()
    run_dir = ROOT / run_ref
    run_name = run_dir.name
    evidence = json.loads((run_dir / "evidence.json").read_text())
    notebook = json.loads((ROOT / "training_artifacts" / "notebook_metrics.json").read_text())

    REPORTS.mkdir(exist_ok=True)
    with (REPORTS / "hasil_per_video.csv").open("w", newline="") as handle:
        fields = ["video", "expected", "predicted_inspecting", "predicted_angkat_tangan",
                  "predicted_combined", "status_combined", "video_sha256", "seconds", "error"]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for case in evidence["cases"]:
            expected_positive = case["expected"] != "negative"
            row = {key: case[key] for key in fields if key not in {"status_combined"}}
            row["status_combined"] = "BENAR" if case["predicted_combined"] == expected_positive else "SALAH"
            writer.writerow(row)

    for key, title in (("inspecting", "Inference video: inspecting"),
                       ("angkat_tangan", "Inference video: angkat tangan"),
                       ("combined", "Inference video: butuh bantuan gabungan")):
        draw_cm(evidence["metrics"][key]["confusion_matrix"], ["Negatif", "Positif"],
                title, REPORTS / f"confusion_matrix_{key}.png")
    draw_cm(notebook["cv"]["confusion_matrix"], ["Other", "Inspecting"],
            "OOF 5-fold dari notebook training", REPORTS / "confusion_matrix_training_oof.png")
    draw_cm(notebook["holdout"]["confusion_matrix"], ["Other", "Inspecting"],
            "Holdout dari notebook training", REPORTS / "confusion_matrix_training_holdout.png")

    m = evidence["metrics"]
    cases = evidence["cases"]
    unique_hashes = len({case["video_sha256"] for case in cases})
    unique_cases = list({case["video_sha256"]: case for case in cases}.values())
    unique_combined = combined_metrics(unique_cases)
    case_rows = []
    for case in cases:
        expected_positive = case["expected"] != "negative"
        status = "BENAR" if case["predicted_combined"] == expected_positive else "SALAH"
        case_rows.append(
            f"| {case['video']} | {case['expected']} | "
            f"{'Ya' if case['predicted_inspecting'] else 'Tidak'} | "
            f"{'Ya' if case['predicted_angkat_tangan'] else 'Tidak'} | "
            f"{'Ya' if case['predicted_combined'] else 'Tidak'} | {status} |"
        )

    readme = f"""# Evaluasi inference butuh bantuan

Evaluasi ini menjalankan model interaksi yang diberikan pengguna dan aturan angkat tangan dari kode backend saat ini terhadap video di `eval/vidio butuh bantuan/`. Tidak ada threshold model atau arsitektur baru yang ditambahkan.

## Hasil utama

| Target evaluasi | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Inspecting (hanya video berlabel subtype) | {m['inspecting']['tp']} | {m['inspecting']['fp']} | {m['inspecting']['fn']} | {m['inspecting']['tn']} | {pct(m['inspecting']['precision'])} | {pct(m['inspecting']['recall'])} | {pct(m['inspecting']['f1'])} |
| Angkat tangan (hanya video berlabel subtype) | {m['angkat_tangan']['tp']} | {m['angkat_tangan']['fp']} | {m['angkat_tangan']['fn']} | {m['angkat_tangan']['tn']} | {pct(m['angkat_tangan']['precision'])} | {pct(m['angkat_tangan']['recall'])} | {pct(m['angkat_tangan']['f1'])} |
| Butuh bantuan gabungan | {m['combined']['tp']} | {m['combined']['fp']} | {m['combined']['fn']} | {m['combined']['tn']} | {pct(m['combined']['precision'])} | {pct(m['combined']['recall'])} | {pct(m['combined']['f1'])} |
| Gabungan, isi video unik | {unique_combined['tp']} | {unique_combined['fp']} | {unique_combined['fn']} | {unique_combined['tn']} | {pct(unique_combined['precision'])} | {pct(unique_combined['recall'])} | {pct(unique_combined['f1'])} |

Ada {len(cases)} nama file dan {unique_hashes} isi video unik. `vidio1.mp4`, `vidio2.mp4`, dan `vidio3.mp4` memiliki hash yang sama persis. Ketiganya terdeteksi positif melalui angkat tangan, tetapi tidak boleh dianggap sebagai tiga sampel independen.

![Confusion matrix gabungan](reports/confusion_matrix_combined.png)

## Hasil per video

| Video | Label | Inspecting | Angkat tangan | Gabungan | Status gabungan |
|---|---|---:|---:|---:|---:|
{chr(10).join(case_rows)}

Data lengkap tersedia di [`reports/hasil_per_video.csv`](reports/hasil_per_video.csv). Bukti frame setiap video berada di [`reports/frames/`](reports/frames/), sedangkan bukti mentah run berada di [`runs/{run_name}/evidence.json`](runs/{run_name}/evidence.json) dan [`execution.log`](runs/{run_name}/execution.log).

## Model dan logika inference

- Model interaksi mengikuti notebook: 17 keypoint x 3 fitur = 51 input, BiLSTM dua arah dengan hidden size 128 dan 2 layer, mean pooling, LayerNorm(256), dropout 0.3, lalu linear 2 kelas (`other`, `inspecting`).
- Bobot [`models/interaction2_head.pt`](models/interaction2_head.pt) mempunyai SHA-256 `{evidence['sha256']['models/interaction2_head.pt']}` dan identik dengan `backend/models/interaction_head.pt`.
- Keputusan kelas model memakai `argmax(softmax(logits))`, sama seperti notebook. Pipeline video memakai jendela 45 frame pada 15 FPS dan stride 15 dari kode proyek.
- Event `butuh_bantuan` baru dibentuk setelah **2 window inspecting aktif berturut-turut** (`help_min_win=2`), sama dengan konfigurasi aktual `backend/app.py`. Prediksi kelas model dan event akhir karena itu dicatat sebagai dua tahap yang berbeda.
- Angkat tangan memakai aturan geometri dan nilai default dari `backend/pipeline/gestures.py` milik perubahan teman.
- Prediksi gabungan bernilai positif jika pipeline menghasilkan event `butuh_bantuan` atau `angkat_tangan`.

Konfigurasi run direkam di [`evidence.json`](runs/{run_name}/evidence.json). Pengaturan yang diberikan evaluator hanya mengaktifkan interaksi dan gesture, menonaktifkan fall, serta memilih kelas inspecting; evaluator tidak menambahkan threshold probabilitas baru.

## Rumus

- Precision = TP / (TP + FP)
- Recall = TP / (TP + FN)
- F1 = 2 x Precision x Recall / (Precision + Recall)
- Confusion matrix disusun sebagai `[[TN, FP], [FN, TP]]`, dengan baris sebagai label aktual dan kolom sebagai prediksi.

Jika tidak ada satu pun prediksi positif, precision ditulis `N/A` karena penyebutnya nol. F1 tetap 0 ketika recall 0.

## Bukti hasil training dari notebook

Notebook melaporkan OOF 5-fold sebanyak {notebook['cv']['n_windows']:,} window: macro-F1 {notebook['cv']['macro_f1_mean']:.4f} dan recall inspecting {notebook['cv']['recall_inspecting_mean']:.3f}. Holdout sebanyak {notebook['holdout']['n_windows']:,} window: accuracy {notebook['holdout']['accuracy']:.3f}, macro-F1 {notebook['holdout']['macro_f1']:.3f}, dan recall inspecting {notebook['holdout']['recall_inspecting']:.3f}.

![Confusion matrix OOF](reports/confusion_matrix_training_oof.png)

![Confusion matrix holdout](reports/confusion_matrix_training_holdout.png)

Angka training di atas disalin dari output notebook, bukan dihitung ulang karena dataset training/OOF tidak disertakan. File sumber disimpan di [`source/`](source/).

## Kelemahan yang terlihat

- Pada run mode `both`, kedua video inspecting (`Jason (bingung)` dan `Mama (bingung)`) tidak menjadi event karena window yang diprediksi inspecting tidak sekaligus memenuhi rangkaian dua window aktif dan pemeriksaan dwell. [Uji diagnosis mode `rak`](reports/diagnosis_bingung.json) menunjukkan `Jason (bingung)` membentuk event, sedangkan `Mama (bingung)` tetap gagal karena tracking memecah prediksi positif menjadi track yang masing-masing hanya memiliki satu window. Model Mama tetap pernah memilih inspecting dengan probabilitas 0,983; kegagalannya berada pada agregasi event, bukan ketiadaan prediksi inspecting.
- `Mama (angkat tangan)` tidak terdeteksi, sedangkan `Mama (langsung ambil)` salah terdeteksi sebagai angkat tangan. Ini menunjukkan aturan geometri masih sensitif terhadap pose tangan yang mirip.
- Beberapa video pendek atau track terfragmentasi menghasilkan sangat sedikit window; `take(normal).mp4` bahkan tidak menghasilkan track valid. Kondisi ini membatasi keputusan model temporal.
- Tiga video bernama `vidio1/2/3` identik secara byte sehingga tidak menambah keragaman evaluasi. Untuk hasil lebih kuat, ganti dua salinan dengan rekaman berbeda.
- Sampel subtype hanya 2 positif per subtype. Metrik mudah berubah besar hanya karena satu video, sehingga belum cukup untuk menyimpulkan performa umum.

## Menjalankan ulang

Jalankan dari root repository:

```bash
backend/.venv/bin/python eval/hasilevaluasibutuhbantuan/tools/evaluate.py
backend/.venv/bin/python eval/hasilevaluasibutuhbantuan/tools/build_report.py
```

Evaluator membaca label dari [`labels/video_labels.csv`](labels/video_labels.csv), memeriksa setiap file berlabel tersedia, menyimpan hash artefak, dan membuat run baru tanpa menimpa bukti run sebelumnya.
"""
    (ROOT / "README.md").write_text(readme)
    print(ROOT / "README.md")


if __name__ == "__main__":
    main()
