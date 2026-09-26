"""Evaluasi video untuk inspecting BiLSTM + gestur angkat tangan SAPA."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import random
import sys
import time

import cv2
import numpy as np
import torch
import torch.nn as nn

os.environ.setdefault("MPLCONFIGDIR", "/tmp/sapa-mpl")

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
BACKEND = REPO / "backend"
VIDEO_DIR = REPO / "eval" / "vidio butuh bantuan"
sys.path.insert(0, str(BACKEND))


class InteractionLSTM2(nn.Module):
    """Salinan arsitektur dari BILSTMandOther_2Class (1).ipynb."""

    def __init__(self, in_dim=51, hidden=128, layers=2, n_classes=2, dropout=0.3):
        super().__init__()
        self.lstm = nn.LSTM(in_dim, hidden, layers, batch_first=True,
                            bidirectional=True, dropout=dropout if layers > 1 else 0.0)
        self.head = nn.Sequential(nn.LayerNorm(hidden * 2), nn.Dropout(dropout),
                                  nn.Linear(hidden * 2, n_classes))

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.head(out.mean(dim=1))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_labels() -> dict[str, dict]:
    with (ROOT / "labels/video_labels.csv").open(newline="", encoding="utf-8") as stream:
        return {row["video"]: row for row in csv.DictReader(stream)}


def load_model() -> InteractionLSTM2:
    model = InteractionLSTM2()
    state = torch.load(ROOT / "models/interaction2_head.pt", map_location="cpu", weights_only=False)
    model.load_state_dict(state, strict=True)
    model.eval()
    return model


def confusion(rows: list[dict], positive: str) -> dict:
    if positive == "combined":
        usable = [r for r in rows if r["expected"] != "unlabeled"]
        actual = lambda r: r["expected"] in {"inspecting", "angkat_tangan", "butuh_bantuan"}
        predicted = lambda r: r["predicted_combined"]
    elif positive == "inspecting":
        # Label generik butuh_bantuan tidak dipaksa menjadi subjenis inspecting.
        usable = [r for r in rows if r["expected"] in {"inspecting", "negative"}]
        actual = lambda r: r["expected"] == positive
        predicted = lambda r: r["predicted_inspecting"]
    else:
        # Label generik butuh_bantuan tidak dipaksa menjadi subjenis angkat tangan.
        usable = [r for r in rows if r["expected"] in {"angkat_tangan", "negative"}]
        actual = lambda r: r["expected"] == positive
        predicted = lambda r: r["predicted_angkat_tangan"]
    tp = sum(actual(r) and predicted(r) for r in usable)
    fp = sum(not actual(r) and predicted(r) for r in usable)
    fn = sum(actual(r) and not predicted(r) for r in usable)
    tn = len(usable) - tp - fp - fn
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "support": tp + fn,
            "precision": precision, "recall": recall, "f1": f1,
            "confusion_matrix_labels": ["negative", "positive"],
            "confusion_matrix": [[tn, fp], [fn, tp]]}


def contact_sheet(video: Path, row: dict, output: Path) -> None:
    cap = cv2.VideoCapture(str(video))
    fps = float(cap.get(cv2.CAP_PROP_FPS)); count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = []
    for fraction in (0.15, 0.5, 0.85):
        idx = max(0, int((count - 1) * fraction)); cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if ok:
            frame = cv2.resize(frame, (400, 225))
            cv2.putText(frame, f"{idx / fps:.1f}s", (12, 28), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (255, 255, 255), 2, cv2.LINE_AA)
            frames.append(frame)
    cap.release()
    if frames:
        banner = np.zeros((55, 1200, 3), dtype=np.uint8)
        text = (f"label={row['expected']} | inspecting={row['predicted_inspecting']} | "
                f"angkat_tangan={row['predicted_angkat_tangan']}")
        cv2.putText(banner, text, (12, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                    (255, 255, 255), 2, cv2.LINE_AA)
        cv2.imwrite(str(output), np.vstack([banner, np.hstack(frames)]))


def main() -> int:
    from pipeline.analyze import analyze
    from pipeline import extract
    from ultralytics import YOLO

    random.seed(42); np.random.seed(42); torch.manual_seed(42); torch.set_num_threads(1)
    labels = load_labels(); model = load_model()
    run = ROOT / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    frames_dir = ROOT / "reports/frames"
    run.mkdir(parents=True); frames_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO,
                        handlers=[logging.FileHandler(run / "execution.log"), logging.StreamHandler()],
                        force=True)

    # Nilai bentuk input berasal dari notebook/config model. help_min_win=2
    # ditulis eksplisit agar sama dengan konfigurasi aktual backend/app.py.
    # Aturan dwell dan angkat tangan memakai pipeline backend yang sudah ada.
    cfg = {"run_fall": False, "run_interaction": True, "run_gestures": True,
           "target_fps": 15, "window": 45, "stride": 15, "inspect_idx": [1],
           "help_min_win": 2}
    rows = []
    for video in sorted(VIDEO_DIR.glob("*.mp4")):
        started = time.perf_counter(); error = None; timeline = []
        try:
            # Instans baru mencegah state tracker berpindah antar-klip dan
            # memakai bobot lokal yang memang sudah ada di repository.
            extract._yolo_model = YOLO(str(BACKEND / "yolov8n-pose.pt"))
            result = analyze(str(video), cfg, fall_model=None, inter_model=model, camera_type="both")
            timeline = [e for e in result["timeline"] if e["tipe"] in {"butuh_bantuan", "angkat_tangan"}]
        except Exception as exc:
            logging.exception("Gagal: %s", video.name); error = str(exc)
        expected = labels.get(video.name, {"expected": "unlabeled"})["expected"]
        row = {"video": video.name, "video_sha256": sha256(video), "expected": expected,
               "predicted_inspecting": any(e["tipe"] == "butuh_bantuan" for e in timeline),
               "predicted_angkat_tangan": any(e["tipe"] == "angkat_tangan" for e in timeline),
               "predicted_combined": bool(timeline), "events": timeline,
               "seconds": time.perf_counter() - started, "error": error}
        rows.append(row); contact_sheet(video, row, frames_dir / f"{video.stem}.jpg")
        logging.info("%s expected=%s inspecting=%s angkat=%s", video.name, expected,
                     row["predicted_inspecting"], row["predicted_angkat_tangan"])

    metrics = {name: confusion(rows, name) for name in ("inspecting", "angkat_tangan", "combined")}
    evidence = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "decision": {
            "interaction_model": "argmax kelas 1 (inspecting), sesuai notebook; event butuh bantuan membutuhkan 2 window aktif berturut-turut sesuai backend/app.py",
            "angkat_tangan": "aturan geometri backend/pipeline/gestures.py dengan konstanta default kode teman",
            "combined": "positif bila inspecting atau angkat_tangan terdeteksi"
        },
        "config": cfg,
        "sha256": {
            "models/interaction2_head.pt": sha256(ROOT / "models/interaction2_head.pt"),
            "source/BILSTMandOther_2Class.ipynb": sha256(ROOT / "source/BILSTMandOther_2Class.ipynb"),
            "source/Preprocess_new_class.ipynb": sha256(ROOT / "source/Preprocess_new_class.ipynb"),
            "backend/models/interaction_head.pt": sha256(BACKEND / "models/interaction_head.pt"),
            "backend/pipeline/analyze.py": sha256(BACKEND / "pipeline/analyze.py"),
            "backend/pipeline/gestures.py": sha256(BACKEND / "pipeline/gestures.py")
        },
        "metrics": metrics,
        "cases": rows,
    }
    (run / "evidence.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "reports/latest_run.txt").write_text(str(run.relative_to(ROOT)) + "\n")
    print(run)
    return 1 if any(r["error"] for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
