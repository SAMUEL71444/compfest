"""
eval/banding.py — bandingkan beberapa hasil run.

    python eval/banding.py                     # semua hasil di eval/hasil/
    python eval/banding.py a.json b.json       # dua run tertentu

Dipakai untuk menjawab "apakah perubahan ini memperbaiki atau memperburuk",
yang kalau dibandingkan manual antar-berkas JSON gampang keliru.
"""

import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent / "hasil"


def main():
    if len(sys.argv) > 1:
        berkas = [Path(a) if Path(a).exists() else DIR / a for a in sys.argv[1:]]
    else:
        berkas = sorted(DIR.glob("*.json"))

    berkas = [b for b in berkas if b.exists()]
    if not berkas:
        print("Belum ada hasil di eval/hasil/. Jalankan ./eval/uji dulu.")
        return 1

    run = []
    for b in berkas:
        try:
            run.append((b.name, json.loads(b.read_text())))
        except Exception as e:
            print(f"  ! {b.name} tidak terbaca: {e}")

    if not run:
        return 1

    print()
    print("=" * 96)
    print("  PERBANDINGAN RUN")
    print("=" * 96)
    print(f"  {'ambang':<34} {'jatuh':>22} {'bantuan':>22}")
    print(f"  {'':34} {'recall  prec    f1':>22} {'recall  prec    f1':>22}")
    print("  " + "-" * 92)

    for nama, k in run:
        a = k.get("ambang", {})
        tanda = (f"{a.get('preset','?')} "
                 f"{a.get('fall_thr','?')}/{a.get('fall_angle','?')}/"
                 f"{a.get('fall_speed','?')}")
        kolom = []
        for tipe in ("jatuh", "butuh_bantuan"):
            m = k.get("ringkasan", {}).get(tipe)
            kolom.append(f"{m['recall']:.3f}  {m['precision']:.3f}  {m['f1']:.3f}"
                         if m else f"{'-':>22}")
        print(f"  {tanda:<34} {kolom[0]:>22} {kolom[1]:>22}")

    # Selisih terhadap run pertama — arah perubahan lebih penting dari angkanya.
    if len(run) > 1:
        dasar = run[0][1].get("ringkasan", {}).get("jatuh")
        if dasar:
            print()
            print(f"  Selisih recall jatuh terhadap run pertama "
                  f"({run[0][1].get('ambang',{}).get('preset','?')}):")
            for nama, k in run[1:]:
                m = k.get("ringkasan", {}).get("jatuh")
                if not m:
                    continue
                d = m["recall"] - dasar["recall"]
                arah = "naik" if d > 0 else ("turun" if d < 0 else "sama")
                a = k.get("ambang", {})
                print(f"    {a.get('fall_thr','?')}/{a.get('fall_angle','?')}"
                      f"  {d:+.3f}  ({arah})")

    print()
    print("  Catatan: bila semua run memberi angka identik, kemungkinan klip uji")
    print("  belum memuat kasus batas — bukan berarti ambangnya setara.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
