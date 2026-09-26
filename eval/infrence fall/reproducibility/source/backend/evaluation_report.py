"""Buat PNG, HTML, CSV, dan JSON evaluasi dari evidence.json tanpa inference ulang.
Usage: backend/.venv/bin/python backend/evaluation_report.py PATH_TO_RUN
"""
import argparse
import csv
import html
import json
import os
from pathlib import Path
import tempfile


def generate(run):
    evidence = json.loads((run / 'evidence.json').read_text())
    cases = evidence['cases']
    valid = [r for r in cases if r['status'] == 'ok' and r.get('expected') is not None]
    tp = sum('jatuh' in r['expected'] and 'jatuh' in r['predicted'] for r in valid)
    fn = sum('jatuh' in r['expected'] and 'jatuh' not in r['predicted'] for r in valid)
    fp = sum('jatuh' not in r['expected'] and 'jatuh' in r['predicted'] for r in valid)
    tn = len(valid) - tp - fn - fp
    def ratio(a, b):
        return a / b if b else None
    scores = dict(accuracy=ratio(tp + tn, len(valid)), precision=ratio(tp, tp + fp),
                  recall=ratio(tp, tp + fn), f1=ratio(2 * tp, 2 * tp + fp + fn),
                  false_negative_rate=ratio(fn, tp + fn), specificity=ratio(tn, tn + fp),
                  false_positive_rate=ratio(fp, fp + tn))
    warning = ('Tidak ada klip negatif: specificity, false positive rate, dan ROC-AUC tidak dapat diukur. '
               'Precision 100% (jika muncul) tidak membuktikan ketahanan terhadap alarm palsu.'
               if tn + fp == 0 else 'Skor dihitung per klip, bukan per frame atau per kejadian.')
    payload = dict(scope='binary_fall_clip_level', actual_rows=['jatuh', 'tidak_jatuh'],
                   predicted_columns=['jatuh', 'tidak_jatuh'], matrix=[[tp, fn], [fp, tn]],
                   metrics=scores, scored=len(valid), total=len(cases), warning=warning)
    (run / 'classification_report.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    with (run / 'per_video.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['id', 'video', 'actual_fall', 'predicted_fall', 'result', 'seconds'])
        for r in cases:
            actual = 'jatuh' in r.get('expected', []) if r.get('expected') is not None else None
            pred = 'jatuh' in r.get('predicted', []) if r['status'] == 'ok' else None
            outcome = 'ERROR' if r['status'] != 'ok' else 'UNLABELED' if actual is None else ('TP' if pred else 'FN') if actual else ('FP' if pred else 'TN')
            writer.writerow([r['id'], Path(r['video']).name, actual, pred, outcome, round(r['seconds'], 3)])
    os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'sapa-mpl'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 6.5))
    ax.imshow([[tp, fn], [fp, tn]], cmap='Blues', vmin=0, vmax=max(tp, fn, fp, tn, 1))
    ax.set(xticks=[0, 1], yticks=[0, 1], xticklabels=['Jatuh', 'Tidak jatuh'],
           yticklabels=['Jatuh', 'Tidak jatuh'], xlabel='Prediksi model', ylabel='Label aktual')
    for i, row in enumerate([[tp, fn], [fp, tn]]):
        for j, value in enumerate(row):
            label = [['TP', 'FN'], ['FP', 'TN']][i][j]
            suffix = '\nTidak ada sampel' if i == 1 and tn + fp == 0 else ''
            ax.text(j, i, f'{label} = {value}{suffix}', ha='center', va='center', fontsize=15,
                    color='white' if value > max(tp, fn, fp, tn, 1) / 2 else 'black')
    ax.set_title(f'SAPA — Confusion Matrix ({len(valid)} klip)', pad=16)
    fig.text(0.5, 0.025, 'Evaluasi per klip • Baris = aktual; kolom = prediksi\nTidak ada klip negatif; alarm palsu belum terukur.' if tn + fp == 0 else 'Evaluasi per klip', ha='center', fontsize=10)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(run / 'confusion_matrix.png', dpi=180)
    plt.close(fig)
    def percent(v):
        return 'Tidak terukur' if v is None else f'{v * 100:.2f}%'
    metric_rows = ''.join(f'<tr><td>{html.escape(k)}</td><td>{percent(v)}</td></tr>' for k, v in scores.items())
    rows = ''.join('<tr>' + ''.join(f'<td>{html.escape(str(v))}</td>' for v in [r['id'], Path(r['video']).name, 'Error' if r['status'] != 'ok' else 'Terdeteksi' if 'jatuh' in r['predicted'] else 'Tidak terdeteksi', f"{r['seconds']:.2f}"]) + '</tr>' for r in cases)
    report = f'''<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>SAPA — Baseline</title>
<style>body{{font:16px system-ui;max-width:1050px;margin:40px auto;padding:0 24px;color:#172b3a}}h1{{font-size:28px}}img{{max-width:700px;width:100%}}table{{border-collapse:collapse;width:100%;margin:20px 0}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #ddd}}aside{{padding:18px;background:#fff4d6}}small{{color:#555}}</style>
<h1>SAPA — Hasil baseline deteksi jatuh</h1><p>{len(valid)} dari {len(cases)} klip dinilai. TP {tp} · FN {fn} · FP {fp} · TN {tn}.</p>
<aside>{html.escape(warning)}</aside><img src="confusion_matrix.png" alt="Confusion matrix deteksi jatuh">
<h2>Metrik</h2><table><tr><th>Metrik</th><th>Nilai</th></tr>{metric_rows}</table>
<p>Label mengikuti keterangan pengguna. Prediksi positif berarti minimal satu event jatuh pada klip. Skor tidak memvalidasi waktu kejadian. Kepala interaksi tidak dievaluasi pada run ini.</p>
<h2>Rincian video</h2><table><tr><th>ID</th><th>Video</th><th>Prediksi</th><th>Durasi proses (s)</th></tr>{rows}</table>
<h2>Kelemahan dan tindak lanjut</h2><p>{fn} klip jatuh tidak terdeteksi. Penyebab belum dapat ditentukan dari hasil akhir saja; perlu pemeriksaan pose, jendela waktu, probabilitas model, dan filter geometri. Tambahkan video aktivitas normal serta anotasi waktu kejadian untuk evaluasi lebih lengkap. Gunakan data validasi terpisah untuk memilih threshold.</p>
<small>Sumber: evidence.json · waktu eksekusi {html.escape(evidence['created_at'])} · <a href="per_video.csv">Unduh CSV</a> · <a href="classification_report.json">Metrik JSON</a> · <a href="execution.log">Log eksekusi</a></small></html>'''
    (run / 'report.html').write_text(report, encoding='utf-8')
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    print(json.dumps(generate(args.run), indent=2))
