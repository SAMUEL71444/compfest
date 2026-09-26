"""
eval/jalankan.py — test suite SAPA untuk klip video nyata.

CARA PAKAI (lihat eval/README.md untuk lengkapnya):
    python eval/jalankan.py                    # semua klip di eval/video/
    python eval/jalankan.py --klip Tes1.mp4    # satu klip saja
    python eval/jalankan.py --preset prob_saja # bandingkan preset ambang

APA YANG DIUKUR
---------------
recall       : dari sekian kejadian berlabel, berapa yang tertangkap sistem.
               Metrik UTAMA untuk jatuh — kejatuhan yang terlewat berarti orang
               tergeletak tanpa pertolongan, biayanya jauh lebih besar daripada
               satu alarm palsu yang tinggal diabaikan operator.
precision    : dari sekian deteksi, berapa yang benar. Diukur karena alarm
               palsu yang terlalu sering membuat operator berhenti percaya —
               recall tinggi jadi tidak ada artinya.
alarm_palsu  : deteksi pada klip yang dilabeli "kosong" (tidak ada kejadian).
               Dipisah dari precision supaya jelas mana yang murni derau.

Kecocokan deteksi-vs-label memakai TUMPANG TINDIH WAKTU, bukan titik persis:
satu kejatuhan berlangsung beberapa detik dan jendela model bergeser 1 detik,
jadi menuntut kecocokan detik-per-detik akan menghukum sistem untuk hal yang
tidak penting secara operasional.

YANG TIDAK TERTANGKAP SUITE INI
-------------------------------
- Kualitas YOLOv8-pose sendiri (keypoint goyah, ID tertukar) tidak dipisahkan
  dari kualitas kepala BiLSTM. Kalau recall rendah, suite ini tidak memberi
  tahu lapisan mana yang gagal — perlu diperiksa manual lewat --verbose.
- Hanya seakurat labelnya. Label yang salah menghasilkan angka yang salah.
"""

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
# Lokasi kode aplikasi. Di dalam container backend kodenya ada di /app;
# saat dijalankan langsung dari repo, ada di ../backend.
APP = Path("/app") if Path("/app/pipeline").is_dir() else (BASE.parent / "backend")
sys.path.insert(0, str(APP))

DIR_VIDEO = BASE / "video"
DIR_HASIL = BASE / "hasil"


def muat_label(path_csv: Path) -> dict:
    """Baca CSV label → {nama_video: [kejadian, ...]}."""
    label = defaultdict(list)
    if not path_csv.exists():
        return label
    with open(path_csv, newline="", encoding="utf-8") as f:
        baris = [b for b in f if not b.lstrip().startswith("#")]
    for row in csv.DictReader(baris):
        if not row.get("video"):
            continue
        label[row["video"].strip()].append({
            "tipe": (row.get("tipe") or "").strip(),
            "mulai": float(row.get("mulai") or 0),
            "akhir": float(row.get("akhir") or 0),
            "catatan": (row.get("catatan") or "").strip(),
        })
    return label


def _tumpang(a0, a1, b0, b1, toleransi=1.5):
    """Dua rentang waktu dianggap cocok bila beririsan (dengan toleransi)."""
    return not (a1 + toleransi < b0 or b1 + toleransi < a0)


def analisis_klip(path_video: Path, ambang: dict, cfg_extra: dict) -> dict:
    """Jalankan pipeline penuh pada satu klip. Mengembalikan timeline."""
    from pipeline.analyze import analyze

    cfg = {
        "run_fall": True, "run_interaction": True,
        "fall_thr": ambang["fall_thr"],
        "fall_angle": ambang["fall_angle"],
        "fall_speed": ambang["fall_speed"],
        "fall_confirm": True,
        "target_fps": 15, "window": 45, "stride": 15,
        "min_track_frames": 10, "det_conf": 0.45,
        "min_bbox_ratio": 0.01, "min_kp_conf": 0.25, "min_visible_kp": 6,
        "help_min_win": 2, "dwell_ratio": 0.4,
    }
    cfg.update(cfg_extra)

    from pipeline.models import load_head
    fall_pt = APP / "models" / "fall_head.pt"
    inter_pt = APP / "models" / "interaction_head.pt"
    fall_model = inter_model = None
    if fall_pt.exists():
        fall_model = load_head(str(fall_pt), str(APP / "models" / "fall_head.json"))[0]
    if inter_pt.exists():
        inter_model = load_head(str(inter_pt), str(APP / "models" / "interaction_head.json"))[0]

    return analyze(str(path_video), cfg,
                   fall_model=fall_model, inter_model=inter_model,
                   camera_type="both")


# Nama tipe di LABEL tidak sama dengan tipe di TIMELINE. Sistem mengeluarkan
# satu tipe kejadian pelayanan — "need_support_candidate" — lalu membedakan
# angkat tangan (sinyal "aktif") dari dwell+inspeksi (sinyal "pasif").
# Label ditulis manusia dengan istilah sehari-hari, jadi pemetaannya di sini.
_TIPE_KANDIDAT = ("need_support_candidate", "butuh_bantuan")


def _cocok_tipe(ev: dict, tipe_label: str) -> bool:
    t = ev.get("tipe")
    if tipe_label == "jatuh":
        return t == "jatuh"
    if t not in _TIPE_KANDIDAT and ev.get("tipe_lama") not in _TIPE_KANDIDAT:
        return False
    if tipe_label == "angkat_tangan":
        return ev.get("sinyal") == "aktif"
    if tipe_label == "butuh_bantuan":
        # Label "butuh_bantuan" menerima kedua sinyal: yang dinilai adalah
        # apakah sistem menandai orang itu sama sekali.
        return True
    return False


def nilai(timeline: list, label_klip: list, tipe: str) -> dict:
    """Cocokkan deteksi dengan label untuk satu tipe kejadian."""
    harap = [l for l in label_klip if l["tipe"] == tipe]
    deteksi = [e for e in timeline if _cocok_tipe(e, tipe)]

    cocok_label, cocok_deteksi = set(), set()
    for i, l in enumerate(harap):
        for j, d in enumerate(deteksi):
            if _tumpang(d["t0"], d["t1"], l["mulai"], l["akhir"]):
                cocok_label.add(i)
                cocok_deteksi.add(j)

    tp = len(cocok_label)
    fn = len(harap) - tp
    fp = len(deteksi) - len(cocok_deteksi)

    terlewat = [harap[i] for i in range(len(harap)) if i not in cocok_label]
    palsu = [deteksi[j] for j in range(len(deteksi)) if j not in cocok_deteksi]

    return {
        "tp": tp, "fn": fn, "fp": fp,
        "recall": round(tp / max(1, tp + fn), 3) if harap else None,
        "precision": round(tp / max(1, tp + fp), 3) if deteksi else None,
        "terlewat": terlewat,
        "palsu": [{"t0": round(p["t0"], 1), "t1": round(p["t1"], 1),
                   "skor": p.get("skor"), "track": p.get("track_id")} for p in palsu],
    }


def laporan_markdown(k: dict) -> str:
    """
    Laporan versi manusia. JSON bagus untuk dibaca mesin, tapi untuk dibaca
    orang atau disalin ke dokumen evaluasi ia harus dibuka dan diterjemahkan
    dulu — berkas ini menghilangkan langkah itu.
    """
    a = k["ambang"]
    b = []
    b.append(f"# Hasil Uji SAPA — {k['waktu']}")
    b.append("")
    b.append(f"**Ambang:** `{a['preset']}` — "
             f"prob ≥ {a['fall_thr']}, sudut ≥ {a['fall_angle']}°, "
             f"kecepatan ≥ {a['fall_speed']}"
             f"{' (mati)' if a['fall_speed'] == 0 else ''}")
    b.append("")

    if k["ringkasan"]:
        b.append("## Ringkasan")
        b.append("")
        b.append("| Kejadian | Recall | Precision | F1 | Tertangkap | Terlewat | Alarm palsu |")
        b.append("|---|---|---|---|---|---|---|")
        for tipe, m in k["ringkasan"].items():
            if tipe == "kosong":
                continue
            b.append(f"| {tipe} | {m['recall']:.3f} | {m['precision']:.3f} | "
                     f"{m['f1']:.3f} | {m['tp']} | {m['fn']} | {m['fp']} |")
        if "kosong" in k["ringkasan"]:
            kk = k["ringkasan"]["kosong"]
            b.append("")
            b.append(f"Klip tanpa kejadian: **{kk['alarm']} alarm palsu** "
                     f"dari {kk['klip']} klip.")
        b.append("")
    else:
        b.append("_Belum ada label — deteksi hanya dicatat, tidak dinilai._")
        b.append("")

    # Kegagalan lebih dulu: itu yang menunjukkan arah perbaikan.
    gagal = []
    for c in k["klip"]:
        for tipe in ("jatuh", "angkat_tangan", "butuh_bantuan"):
            n = c.get(tipe)
            if not isinstance(n, dict):
                continue
            for t in n.get("terlewat", []):
                gagal.append((c["klip"], tipe, "TERLEWAT",
                              f"{t['mulai']:.1f}-{t['akhir']:.1f}s", t.get("catatan", "")))
            for p in n.get("palsu", []):
                gagal.append((c["klip"], tipe, "alarm palsu",
                              f"{p['t0']:.1f}-{p['t1']:.1f}s", f"skor {p.get('skor')}"))
        if c.get("alarm_palsu"):
            gagal.append((c["klip"], "-", "alarm palsu",
                          f"{c['alarm_palsu']} deteksi", "klip dilabeli kosong"))

    b.append("## Kegagalan")
    b.append("")
    if gagal:
        b.append("| Klip | Jenis | Masalah | Waktu | Catatan |")
        b.append("|---|---|---|---|---|")
        for g in gagal:
            b.append("| " + " | ".join(str(x) for x in g) + " |")
    else:
        b.append("Tidak ada kejadian yang terlewat maupun alarm palsu "
                 "pada klip yang diuji.")
    b.append("")

    b.append("## Per klip")
    b.append("")
    b.append("| Klip | Deteksi | Waktu proses |")
    b.append("|---|---|---|")
    for c in k["klip"]:
        if c.get("error"):
            b.append(f"| {c['klip']} | GAGAL: {c['error']} | - |")
        else:
            b.append(f"| {c['klip']} | {c.get('n_deteksi', 0)} | "
                     f"{c.get('durasi_proses', 0)} detik |")
    b.append("")
    return "\n".join(b)


def main():
    ap = argparse.ArgumentParser(description="Test suite SAPA untuk klip video.")
    ap.add_argument("--klip", help="Nama satu file di eval/video/ (default: semua)")
    ap.add_argument("--label", default=str(BASE / "label.csv"),
                    help="CSV label (default: eval/label.csv)")
    ap.add_argument("--preset", default=None,
                    help="Preset ambang: prob_sudut | prob_saja | prob_kecepatan | prob_sudut_kecepatan")
    ap.add_argument("--fall-thr", type=float, help="Timpa ambang probabilitas")
    ap.add_argument("--fall-angle", type=float, help="Timpa ambang sudut torso")
    ap.add_argument("--fall-speed", type=float, help="Timpa ambang kecepatan")
    ap.add_argument("--verbose", action="store_true", help="Tampilkan semua deteksi")
    ap.add_argument("--simpan", default=None, help="Simpan hasil JSON ke berkas ini")
    args = ap.parse_args()

    from pipeline import thresholds as TH
    ambang = TH.resolve(args.preset or TH.PRESET_DEFAULT,
                        fall_thr=args.fall_thr,
                        fall_angle=args.fall_angle,
                        fall_speed=args.fall_speed)

    label = muat_label(Path(args.label))

    if args.klip:
        daftar = [DIR_VIDEO / args.klip]
    else:
        daftar = sorted([p for p in DIR_VIDEO.glob("*")
                         if p.suffix.lower() in {".mp4", ".avi", ".mov", ".mkv"}])

    if not daftar:
        print(f"Tidak ada klip di {DIR_VIDEO}/")
        print("Taruh file .mp4 di sana, lalu jalankan lagi.")
        return 1

    print()
    print("=" * 72)
    print("  TEST SUITE SAPA")
    print(f"  Ambang: {ambang['preset']}  "
          f"prob>={ambang['fall_thr']}  sudut>={ambang['fall_angle']}°  "
          f"speed>={ambang['fall_speed']}")
    print(f"  Klip  : {len(daftar)}   Label: {Path(args.label).name}"
          f"{'  (TIDAK ADA — hanya mencatat deteksi)' if not label else ''}")
    print("=" * 72)

    total = defaultdict(lambda: defaultdict(int))
    rincian = []

    for path in daftar:
        if not path.exists():
            print(f"\n  ! {path.name} tidak ditemukan — dilewati")
            continue

        t0 = time.time()
        print(f"\n  {path.name} ...", end="", flush=True)
        try:
            hasil = analisis_klip(path, ambang, {})
        except Exception as e:
            print(f" GAGAL: {e}")
            rincian.append({"klip": path.name, "error": str(e)})
            continue
        dt = time.time() - t0
        tl = hasil["timeline"]
        print(f" {dt:.0f} detik, {len(tl)} deteksi")

        lbl = label.get(path.name, [])
        klip_hasil = {"klip": path.name, "durasi_proses": round(dt, 1),
                      "n_deteksi": len(tl)}

        if not lbl:
            print(f"      (belum ada label — deteksi dicatat saja)")
            for e in tl[:10]:
                print(f"      · {e['tipe']:<14} {e['t0']:6.1f}-{e['t1']:6.1f}s "
                      f"skor={e.get('skor', 0):.2f} track={e.get('track_id')}")
            klip_hasil["deteksi"] = tl
            rincian.append(klip_hasil)
            continue

        kosong = any(l["tipe"] == "kosong" for l in lbl)
        if kosong:
            n_palsu = len(tl)
            total["kosong"]["klip"] += 1
            total["kosong"]["alarm"] += n_palsu
            tanda = "OK" if n_palsu == 0 else f"{n_palsu} ALARM PALSU"
            print(f"      klip kosong → {tanda}")
            for e in tl[:5]:
                print(f"      · {e['tipe']:<14} {e['t0']:6.1f}-{e['t1']:6.1f}s "
                      f"skor={e.get('skor', 0):.2f}")
            klip_hasil["alarm_palsu"] = n_palsu
            rincian.append(klip_hasil)
            continue

        for tipe in ("jatuh", "angkat_tangan", "butuh_bantuan"):
            if not any(l["tipe"] == tipe for l in lbl):
                continue
            n = nilai(tl, lbl, tipe)
            total[tipe]["tp"] += n["tp"]
            total[tipe]["fn"] += n["fn"]
            total[tipe]["fp"] += n["fp"]
            klip_hasil[tipe] = n

            status = "OK" if n["fn"] == 0 and n["fp"] == 0 else "ADA MASALAH"
            print(f"      {tipe:<14} tp={n['tp']} fn={n['fn']} fp={n['fp']}  {status}")
            for t in n["terlewat"]:
                print(f"         TERLEWAT  {t['mulai']:.1f}-{t['akhir']:.1f}s"
                      f"{'  — ' + t['catatan'] if t['catatan'] else ''}")
            for p in n["palsu"]:
                print(f"         PALSU     {p['t0']:.1f}-{p['t1']:.1f}s "
                      f"skor={p['skor']}")

        if args.verbose:
            print("      semua deteksi:")
            for e in tl:
                print(f"       · {e['tipe']:<14} {e['t0']:6.1f}-{e['t1']:6.1f}s "
                      f"skor={e.get('skor', 0):.2f} track={e.get('track_id')}")

        rincian.append(klip_hasil)

    # ── Ringkasan ────────────────────────────────────────────────────────────
    print()
    print("=" * 72)
    print("  RINGKASAN")
    print("=" * 72)
    ringkas = {}
    for tipe in ("jatuh", "angkat_tangan", "butuh_bantuan"):
        d = total.get(tipe)
        if not d or (d["tp"] + d["fn"] + d["fp"]) == 0:
            continue
        rec = d["tp"] / max(1, d["tp"] + d["fn"])
        pre = d["tp"] / max(1, d["tp"] + d["fp"])
        f1 = 2 * rec * pre / max(1e-9, rec + pre)
        ringkas[tipe] = {"recall": round(rec, 3), "precision": round(pre, 3),
                         "f1": round(f1, 3), **dict(d)}
        print(f"  {tipe:<15} recall {rec:.3f}   precision {pre:.3f}   f1 {f1:.3f}"
              f"   (tp={d['tp']} fn={d['fn']} fp={d['fp']})")
        if d["fn"]:
            print(f"                  → {d['fn']} kejadian TERLEWAT")

    if total.get("kosong"):
        k = total["kosong"]
        print(f"  {'klip kosong':<15} {k['alarm']} alarm palsu dari {k['klip']} klip")
        ringkas["kosong"] = dict(k)

    if not ringkas:
        print("  (belum ada label — isi eval/label.csv untuk mendapat metrik)")
    print()

    keluaran = {
        "waktu": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ambang": ambang,
        "ringkasan": ringkas,
        "klip": rincian,
    }
    DIR_HASIL.mkdir(exist_ok=True)

    # Nama berkas dibuat terbaca: tanggal-jam + ambang yang dipakai. Versi
    # sebelumnya memakai epoch (hasil_prob_sudut_1790318810.json) sehingga dua
    # run dengan ambang berbeda tapi preset sama tidak bisa dibedakan tanpa
    # membuka isinya.
    cap = time.strftime("%Y%m%d-%H%M")
    tanda = (f"thr{ambang['fall_thr']:.2f}_ang{ambang['fall_angle']:.0f}"
             f"_spd{ambang['fall_speed']:.2f}")
    dasar = args.simpan or f"{cap}_{ambang['preset']}_{tanda}"
    dasar = dasar[:-5] if dasar.endswith(".json") else dasar

    out = DIR_HASIL / f"{dasar}.json"
    out.write_text(json.dumps(keluaran, indent=2, ensure_ascii=False, default=str))

    out_md = DIR_HASIL / f"{dasar}.md"
    out_md.write_text(laporan_markdown(keluaran))

    print(f"  Hasil  → eval/hasil/{out.name}")
    print(f"  Laporan→ eval/hasil/{out_md.name}   (siap disalin ke laporan)")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
