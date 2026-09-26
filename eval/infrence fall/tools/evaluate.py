"""Inference dan evaluasi otomatis SAPA.

python backend/evaluate.py --manifest backend/evaluation/suite.example.json
python backend/evaluate.py --video video.mp4 --camera lorong

Label adalah keberadaan kejadian pada seluruh klip, bukan kelas aksi/window.
Output tiap run: evidence.json, baseline.json, weaknesses.json, execution.log.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import platform
import random
import sys
import time
import traceback

CHECKPOINT = Path(__file__).resolve().parents[1]
REPO = CHECKPOINT.parents[1]
BACKEND = REPO / "backend"
RUNTIME_BACKEND = CHECKPOINT / "reproducibility/source/backend"
sys.path.insert(0, str(RUNTIME_BACKEND))
LABELS = ("jatuh", "butuh_bantuan")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def metrics(rows):
    valid = [r for r in rows if r["status"] == "ok" and r.get("expected") is not None]
    per_label = {}
    for label in LABELS:
        tp = sum(label in r["expected"] and label in r["predicted"] for r in valid)
        fp = sum(label not in r["expected"] and label in r["predicted"] for r in valid)
        fn = sum(label in r["expected"] and label not in r["predicted"] for r in valid)
        tn = len(valid) - tp - fp - fn
        per_label[label] = dict(tp=tp, fp=fp, fn=fn, tn=tn,
            support=tp + fn, precision=tp / (tp + fp) if tp + fp else None,
            recall=tp / (tp + fn) if tp + fn else None,
            f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None)
    f1s = [v["f1"] for v in per_label.values() if v["f1"] is not None]
    return {"scope": "clip_level_multilabel", "total": len(rows),
        "errors": sum(r["status"] == "error" for r in rows), "scored": len(valid),
        "coverage": len(valid) / len(rows) if rows else 0,
        "exact_match": sum(set(r["expected"]) == set(r["predicted"]) for r in valid) / len(valid) if valid else None,
        "macro_f1_defined_labels": sum(f1s) / len(f1s) if f1s else None,
        "per_label": per_label}


class Inference:
    def __init__(self, cfg):
        import numpy as np
        import torch
        from pipeline.models import load_head
        random.seed(42)
        np.random.seed(42)
        torch.manual_seed(42)
        torch.set_num_threads(1)
        self.fall, _ = load_head(str(BACKEND / "models/fall_head.pt"), str(BACKEND / "models/fall_head.json"))
        self.inter, _ = load_head(str(BACKEND / "models/interaction_head.pt"), str(BACKEND / "models/interaction_head.json"))
        self.cfg = cfg

    def __call__(self, path, camera):
        from pipeline.analyze import analyze
        from pipeline import extract
        # Hindari tracker persist membawa identitas dari klip sebelumnya.
        extract._yolo_model = None
        result = analyze(str(path), self.cfg, self.fall, self.inter, camera)
        if not result["frame_annotations"]:
            raise ValueError("Tidak ada pose valid; hasil tidak dianggap prediksi normal.")
        return result["timeline"]


def load_suite(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases wajib berupa list yang tidak kosong")
    ids = set()
    for case in cases:
        if not isinstance(case.get("id"), str) or not case["id"] or case["id"] in ids:
            raise ValueError("Setiap case wajib punya id string unik")
        ids.add(case["id"])
        if case.get("camera", "both") not in ("both", "lorong", "rak"):
            raise ValueError("camera harus both, lorong, atau rak")
        expected = case.get("expected")
        if expected is not None and (not isinstance(expected, list) or any(x not in LABELS for x in expected)):
            raise ValueError("expected harus list jatuh/butuh_bantuan; [] berarti negatif")
        if not isinstance(case.get("video"), str) or not case["video"]:
            raise ValueError("video wajib berupa path string")
        case["video"] = str((path.parent / case["video"]).resolve())
    cfg = data.get("config", {})
    if not isinstance(cfg, dict):
        raise ValueError("config harus object")
    return cases, cfg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path)
    source.add_argument("--video", type=Path)
    parser.add_argument("--camera", choices=["lorong", "rak", "both"], default="both")
    parser.add_argument("--output", type=Path, default=CHECKPOINT / "runs/manual")
    args = parser.parse_args()
    run = args.output / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run.mkdir(parents=True, exist_ok=False)
    logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler(run / "execution.log"), logging.StreamHandler()], force=True)
    rows, hashes, cfg = [], {}, {}
    fatal = None
    try:
        if args.manifest:
            cases, cfg = load_suite(args.manifest.resolve())
            hashes["manifest"] = digest(args.manifest)
        else:
            cases = [{"id": "inference", "video": str(args.video.resolve()), "camera": args.camera}]
        for asset in sorted((BACKEND / "models").glob("*")):
            if asset.suffix in (".pt", ".json"):
                hashes[asset.name] = digest(asset)
        for source_file in sorted((RUNTIME_BACKEND / "pipeline").glob("*.py")):
            hashes[f"pipeline/{source_file.name}"] = digest(source_file)
        predictor = None
        for case in cases:
            start = time.perf_counter()
            row = dict(case, expected=case.get("expected"), status="error")
            try:
                row["video_sha256"] = digest(case["video"])
                if predictor is None:
                    predictor = Inference(cfg)
                events = predictor(case["video"], case.get("camera", "both"))
                row.update(status="ok", timeline=events, predicted=sorted({e["tipe"] for e in events}))
                if row["expected"] is not None:
                    row["false_positive"] = sorted(set(row["predicted"]) - set(row["expected"]))
                    row["false_negative"] = sorted(set(row["expected"]) - set(row["predicted"]))
            except Exception as exc:
                row.update(error=str(exc), traceback=traceback.format_exc())
                logging.exception("Case %s gagal", case["id"])
            row["seconds"] = time.perf_counter() - start
            rows.append(row)
            logging.info("Case %s: %s (%.3fs)", case["id"], row["status"], row["seconds"])
    except Exception as exc:
        fatal = str(exc)
        logging.exception("Suite gagal")
    for yolo in (Path("yolov8n-pose.pt"), BACKEND / "yolov8n-pose.pt"):
        if yolo.is_file():
            hashes[str(yolo.resolve())] = digest(yolo)
    score = metrics(rows)
    score["status"] = "invalid" if fatal or not score["scored"] else "partial" if score["coverage"] < 1 else "complete"
    packages = {}
    from importlib.metadata import version, PackageNotFoundError
    for package in ("torch", "numpy", "ultralytics", "opencv-python-headless"):
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = None
    save(run / "evidence.json", dict(created_at=datetime.now(timezone.utc).isoformat(),
        command=sys.argv, python=sys.version, platform=platform.platform(), packages=packages,
        seed=42, device="cpu", config=cfg, sha256=hashes, fatal_error=fatal, cases=rows))
    save(run / "baseline.json", score)
    save(run / "weaknesses.json", {
        "observed": [{"id": r["id"], "error": r.get("error"), "false_positive": r.get("false_positive", []),
            "false_negative": r.get("false_negative", [])} for r in rows
            if r["status"] == "error" or r.get("false_positive") or r.get("false_negative")],
        "limitations": ["Skor hanya keberadaan kejadian per klip; tidak mengukur ketepatan waktu atau track.",
            "Error tidak diberi skor; periksa coverage agar baseline tidak menyesatkan.",
            "Label yang tidak punya positif maupun prediksi positif memiliki F1 null.",
            "Deteksi jatuh dinonaktifkan pada kamera rak oleh pipeline.",
            "Butuh bantuan adalah proksi inspeksi produk/rak, perlu validasi manusia.",
            "Waktu eksekusi termasuk load model pada klip pertama dan load YOLO tiap klip."],
        "missing_positive_labels": [k for k, v in score["per_label"].items() if not v["support"]],
        "required_next": "Gunakan klip uji berlabel yang terpisah dari data training, termasuk contoh negatif dan berbagai sudut kamera."})
    print(str(run.resolve()))
    return 1 if fatal or any(r["status"] == "error" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
