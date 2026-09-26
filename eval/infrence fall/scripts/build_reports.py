"""Build reproducible GitHub reports from separate video runs; never modifies models."""
import csv
import hashlib
import html
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone
import cv2
import numpy as np
from metrics import binary_metrics, percent, write_csv, write_json

os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'sapa-mpl'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
BACKEND = REPO / 'backend'
RUNTIME_BACKEND = ROOT / 'reproducibility/source/backend'
NAMES = {'gmgcsa24': 'GMGCSA24', 'vidio_asli': 'Video asli'}
BLUE, RED = '#215c80', '#ae443e'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def md_table(headers, rows):
    def esc(v):
        return str(v).replace('|', '\\|').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(map(esc, headers)) + ' |',
                      '| ' + ' | '.join('---' for _ in headers) + ' |'] +
                     ['| ' + ' | '.join(map(esc, row)) + ' |' for row in rows])


def plot_confusion(metrics, title, path):
    values = np.array([[metrics['tp'], metrics['fn']], [metrics['fp'], metrics['tn']]])
    fig, ax = plt.subplots(figsize=(6.8, 5.7))
    ax.imshow(values, cmap='Blues', vmin=0, vmax=max(int(values.max()), 1))
    ax.set(xticks=[0,1], yticks=[0,1], xticklabels=['Jatuh','Tidak jatuh'],
           yticklabels=['Jatuh','Tidak jatuh'], xlabel='Prediksi per klip', ylabel='Label aktual', title=title)
    for i in range(2):
        for j in range(2):
            suffix = '\nTidak ada sampel' if i == 1 and metrics['negative_support'] == 0 else ''
            ax.text(j,i, f"{[['TP','FN'],['FP','TN']][i][j]} = {values[i,j]}{suffix}", ha='center', va='center',
                    fontsize=14, color='white' if values[i,j] > values.max()/2 else 'black')
    fig.text(.5,.025,'Unit: video. Label mengikuti keterangan pengguna.\nTidak mengukur ketepatan waktu deteksi.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.07,1,1]);fig.savefig(path,dpi=170);plt.close(fig)


def plot_metrics(metrics, title, path):
    labels = ['Precision*','Recall','F1 jatuh','Accuracy*']
    values = [metrics[key] for key in ('precision','recall','f1','accuracy')]
    fig, ax = plt.subplots(figsize=(7,4.5))
    ax.bar(labels,[v or 0 for v in values],color=BLUE,width=.6)
    for i,v in enumerate(values):ax.text(i,(v or 0)+.025,percent(v),ha='center')
    ax.set(ylim=(0,1.18), ylabel='Proporsi',title=title)
    fig.text(.5,.015,'* Dataset hanya positif: precision/accuracy tidak menunjukkan performa pada video normal.',ha='center',fontsize=8)
    fig.tight_layout(rect=[0,.05,1,1]);fig.savefig(path,dpi=170);plt.close(fig)


def contact_sheet(video, case, out):
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened(): raise ValueError(f'Video cannot be opened: {video}')
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS)); n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if fps <= 0 or n <= 0: raise ValueError(f'Invalid video metadata: {video}')
        timeline = [e for e in case.get('timeline',[]) if e['tipe']=='jatuh']
        fractions = [.15,.5,.85]
        indices = [int((n-1)*f) for f in fractions]
        if timeline:
            indices[1] = min(n-1,max(0,round((timeline[0]['t0']+timeline[0]['t1'])/2*fps)))
        fig, axes = plt.subplots(1,3,figsize=(12,3.7))
        sampled = []
        for j,(ax,index) in enumerate(zip(axes,indices)):
            cap.set(cv2.CAP_PROP_POS_FRAMES,index); ok, frame=cap.read()
            if not ok: raise ValueError(f'Cannot decode frame {index}: {video}')
            ax.imshow(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB));ax.axis('off')
            hint = 'midpoint jendela prediksi' if timeline and j==1 else 'cuplikan konteks'
            ax.set_title(f'{index/fps:.2f} s | frame {index}\n{hint}',fontsize=9)
            sampled.append(dict(frame_index=index,timestamp_seconds=index/fps,selection=hint))
        decision = 'TERDETEKSI (TP)' if 'jatuh' in case.get('predicted',[]) else 'TERLEWAT (FN)'
        fig.suptitle(f"{case['id']} | Label klip: jatuh | Prediksi klip: {decision}",fontsize=12)
        fig.text(.5,.01,'Cuplikan dari video sumber; bukan anotasi ground truth waktu kejadian atau overlay pose.',ha='center',fontsize=8)
        fig.tight_layout(rect=[0,.04,1,.93]);fig.savefig(out,dpi=125);plt.close(fig)
        return dict(fps=fps,frame_count=n,width=width,height=height,duration_seconds=n/fps,
                    sampled_frames=sampled)
    finally:
        cap.release()


def build():
    reports = ROOT/'reports';reports.mkdir(exist_ok=True)
    (ROOT/'metadata').mkdir(exist_ok=True)
    snapshots=json.loads((ROOT/'source_snapshot.json').read_text())
    for rel, expected in snapshots.items():
        isolated = ROOT/'reproducibility/source'/rel
        source = isolated if isolated.is_file() else REPO/rel
        if sha(source)!=expected: raise ValueError(f'Inference source changed: {rel}')
    all_rows=[]; summaries={}; source_runs={}; proof=[]
    for dataset,title in NAMES.items():
        available=sorted((ROOT/'runs'/dataset).glob('*/evidence.json'))
        if not available: raise ValueError(f'No completed run for {dataset}')
        evidence_path=available[-1];run=evidence_path.parent;source_runs[dataset]=str(run.relative_to(ROOT))
        evidence=json.loads(evidence_path.read_text()); manifest_path=ROOT/'manifests'/f'{dataset}.json'
        manifest=json.loads(manifest_path.read_text())
        if sha(manifest_path)!=evidence['sha256']['manifest']: raise ValueError('Manifest hash changed')
        if evidence.get('fatal_error'): raise ValueError(evidence['fatal_error'])
        if evidence['config']!=manifest['config']:raise ValueError('Config mismatch')
        expected_ids={c['id'] for c in manifest['cases']}
        if {c['id'] for c in evidence['cases']}!=expected_ids:raise ValueError('Case coverage mismatch')
        for name in ('fall_head.pt','interaction_head.pt','fall_head.json','interaction_head.json'):
            if sha(BACKEND/'models'/name)!=evidence['sha256'][name]:raise ValueError('Model/config changed')
        for name,value in evidence['sha256'].items():
            if name.startswith('pipeline/') and sha(RUNTIME_BACKEND/name)!=value:raise ValueError('Pipeline changed')
        out=reports/dataset;out.mkdir(exist_ok=True);(out/'figures').mkdir(exist_ok=True)
        (out/'frames').mkdir(exist_ok=True)
        rows=[]
        for case in evidence['cases']:
            video=Path(case['video'])
            if sha(video)!=case['video_sha256']:raise ValueError(f'Video changed: {video.name}')
            if case['status']!='ok':
                raise ValueError(f"Case error must be resolved/reported explicitly: {case['id']}")
            actual=int('jatuh' in case['expected']);pred=int('jatuh' in case['predicted'])
            if not actual:raise ValueError('Current proof captions assume user-supplied all-positive clips')
            photo=out/'frames'/f"{case['id']}.png"
            meta=contact_sheet(video,case,photo)
            outcome='TP' if actual and pred else 'FN' if actual else 'FP' if pred else 'TN'
            row=dict(dataset=dataset,sample_id=case['id'],video=video.name,
                     source_video=str(video.relative_to(REPO)),video_sha256=case['video_sha256'],
                     actual=actual,predicted=pred,result=outcome,processing_seconds=case['seconds'],
                     fps=meta['fps'],frame_count=meta['frame_count'],duration_seconds=meta['duration_seconds'],
                     resolution=f"{meta['width']}x{meta['height']}",fps_bin='<=20 FPS' if meta['fps']<=20 else '>20 FPS',
                     duration_bin='<10 s' if meta['duration_seconds']<10 else '>=10 s',
                     yaw_deg=None,pitch_deg=None,performer=None)
            rows.append(row);proof.append(dict(sample_id=case['id'],video_sha256=case['video_sha256'],
                figure=str(photo.relative_to(ROOT)),**meta))
        metrics=binary_metrics([r['actual'] for r in rows],[r['predicted'] for r in rows])
        summaries[dataset]=metrics;all_rows.extend(rows)
        write_json(out/'metrics.json',dict(dataset=dataset,unit='video',**metrics))
        write_csv(out/'metrics.csv',[dict(metric=k,value=v) for k,v in metrics.items()])
        write_csv(out/'per_video.csv',rows)
        write_csv(out/'confusion_matrix.csv',[{'actual':'jatuh','predicted_jatuh':metrics['tp'],'predicted_tidak_jatuh':metrics['fn']},
                   {'actual':'tidak_jatuh','predicted_jatuh':metrics['fp'],'predicted_tidak_jatuh':metrics['tn']}])
        plot_confusion(metrics,f'{title} — Confusion matrix ({metrics["n"]} video)',out/'figures/confusion_matrix.png')
        plot_metrics(metrics,f'{title} — Baseline jatuh',out/'figures/metrics.png')
        md=f'# Baseline jatuh — {title}\n\nEvaluasi keberadaan jatuh per video. Label positif diberikan pengguna; belum ada anotasi waktu kejadian.\n\n'
        md+=md_table(['Metrik','Hasil'],[[k,percent(metrics[k])] for k in ('precision','recall','f1','accuracy','specificity','false_positive_rate','balanced_accuracy')])
        md+=f'\n\nTP={metrics["tp"]}, FN={metrics["fn"]}, FP={metrics["fp"]}, TN={metrics["tn"]}. '
        md+='**Tidak ada video negatif.** FP/TN nol berarti belum diuji; precision 100% bukan bukti tidak ada alarm palsu. N/A berarti tidak dapat dihitung.\n\n'
        md+='![Confusion matrix](figures/confusion_matrix.png)\n\n![Metrik](figures/metrics.png)\n\n## Hasil per video\n\n'
        md+=md_table(['ID','File','Hasil'],[[r['sample_id'],r['video'],r['result']] for r in rows])
        md+='\n\n## Bukti visual\n\nCuplikan bersumber dari video asli. Titik tengah jendela prediksi ditampilkan untuk klip positif; gambar tidak membuktikan akurasi waktu deteksi.\n\n'
        for r in rows:md+=f"### {r['sample_id']} — {r['result']}\n\n{r['video']}\n\n![{r['sample_id']}](frames/{r['sample_id']}.png)\n\n"
        md+=f'## Bukti eksekusi\n\n- [Evidence JSON](../../{source_runs[dataset]}/evidence.json)\n- [Log](../../{source_runs[dataset]}/execution.log)\n- [Metrik JSON](metrics.json)\n- [CSV per video](per_video.csv)\n'
        (out/'README.md').write_text(md,encoding='utf-8')
    # Every metric slice is descriptive; no inference of yaw or performer from appearance.
    slice_rows=[]
    for dataset in NAMES:
        subset=[r for r in all_rows if r['dataset']==dataset]
        for dimension in ('dataset','resolution','fps_bin','duration_bin'):
            for value in sorted({r[dimension] for r in subset}):
                selected=[r for r in subset if r[dimension]==value]
                slice_rows.append(dict(dataset=dataset,dimension=dimension,value=value,
                    **binary_metrics([r['actual'] for r in selected],[r['predicted'] for r in selected])))
    write_csv(reports/'video_slices.csv',slice_rows)
    write_json(reports/'video_slices.json',slice_rows)
    write_csv(ROOT/'metadata/video_inventory.csv',all_rows)
    write_csv(ROOT/'metadata/slice_annotations.csv',[dict(sample_id=r['sample_id'],dataset=r['dataset'],video=r['video'],yaw_deg='',pitch_deg='',performer='',annotation_source='') for r in all_rows])
    write_json(ROOT/'metadata/frame_provenance.json',proof)
    required=[dict(slice='yaw/pitch kamera dan kombinasi yaw x pitch',status='unavailable',reason='Tidak ada metadata sudut atau NPZ augmentasi; arah jatuh pada nama file bukan sudut kamera.'),
              dict(slice='performer',status='unavailable',reason='Tidak ada ID subjek yang terverifikasi; tidak menebak identitas dari wajah/pakaian.'),
              dict(slice='F1 interaksi per pasangan kelas',status='unavailable',reason='Hanya video jatuh tersedia; kepala interaksi dinonaktifkan dan tidak ada label/prediksi OOF interaksi.')]
    write_json(reports/'requested_slices_status.json',required)
    fig,axes=plt.subplots(1,2,figsize=(11,4.6))
    for ax,dataset in zip(axes,NAMES):
        vals=[r for r in slice_rows if r['dataset']==dataset and r['dimension']=='fps_bin']
        ax.bar([r['value'] for r in vals],[r['recall'] or 0 for r in vals],color=BLUE)
        for i,r in enumerate(vals):ax.text(i,(r['recall'] or 0)+.03,f"{r['tp']}/{r['positive_support']} ({percent(r['recall'])})",ha='center',fontsize=9)
        ax.set(ylim=(0,1.17),title=NAMES[dataset],ylabel='Recall jatuh',xlabel='FPS sumber video')
    fig.suptitle('SLICE yang terukur — per FPS, terpisah per dataset')
    fig.text(.5,.01,'Pembagian deskriptif <=20 vs >20 FPS; bukan sudut kamera. Sampel sedikit, bukan bukti hubungan sebab-akibat.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.06,1,.93]);fig.savefig(ROOT/'figures/recall_slices_fps.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,4.7))
    vals=list(summaries.values());labels=list(NAMES.values())
    ax.bar(labels,[m['recall'] or 0 for m in vals],color=BLUE,width=.55)
    for i,m in enumerate(vals):ax.text(i,(m['recall'] or 0)+.03,f"{m['tp']}/{m['positive_support']} | {percent(m['recall'])}",ha='center')
    ax.set(ylim=(0,1.17),ylabel='Recall jatuh',title='Baseline terpisah berdasarkan sumber video')
    fig.text(.5,.01,'Bukan perbandingan model: bobot dan aturan sama, dataset berbeda. Semua label positif.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.06,1,1]);fig.savefig(ROOT/'figures/recall_by_dataset.png',dpi=170);plt.close(fig)
    write_json(reports/'summary.json',dict(datasets=summaries,source_runs=source_runs))
    slice_md='# Analisis per-irisan data (SLICE)\n\nIrisan dihitung dari metadata video yang terukur, tanpa mengubah model. Hasil dipisahkan per dataset untuk menghindari pencampuran sumber.\n\n'
    slice_md+='![Recall per sumber](../figures/recall_by_dataset.png)\n\n![Recall per FPS](../figures/recall_slices_fps.png)\n\n'
    slice_md+=md_table(['Dataset','Irisan','Nilai','N positif','TP','FN','Recall'],[[r['dataset'],r['dimension'],r['value'],r['positive_support'],r['tp'],r['fn'],percent(r['recall'])] for r in slice_rows])
    slice_md+='\n\n## Yang belum dapat dihitung\n\n'
    for r in required:slice_md+=f"- **{r['slice']}**: {r['reason']}\n"
    slice_md+='\nHipotesis bahwa yaw ekstrem menurunkan recall **belum diuji**. Dua belas/15 kombinasi augmentasi tidak boleh direkonstruksi dari nama file atau contoh video. Temuan dataset kecil ini bersifat deskriptif; FPS, resolusi, subjek, dan jenis gerakan bisa saling terkait. Tidak ada uji signifikansi atau klaim generalisasi.\n'
    (reports/'SLICE.md').write_text(slice_md,encoding='utf-8')
    readme = '''# SAPA — baseline inference jatuh

Paket ini mengevaluasi dua sumber secara terpisah dengan bobot dan aturan inferensi yang sama:

- **GMGCSA24:** 5 dari 6 video terdeteksi; recall 83,33%; F1 jatuh 90,91%.
- **Video asli:** 2 dari 4 video terdeteksi; recall 50,00%; F1 jatuh 66,67%.

Semua klip diberi label positif jatuh berdasarkan keterangan pengguna. Karena tidak ada video negatif, specificity, false-positive rate, balanced accuracy, dan ROC-AUC tidak dapat dihitung. Precision bernilai 100%, tetapi angka itu belum menguji alarm palsu. Accuracy pada kumpulan positif sama dengan recall dan tidak boleh dipakai sebagai gambaran performa umum.

Dataset GMGCSA24 saat ini telah dipilih ulang setelah evaluasi sebelumnya. Perbedaan skor terhadap run lama menggambarkan perubahan komposisi data, bukan peningkatan model.

Artefak sebelum pemindahan struktur dipertahankan di `archive/pre-structure/`. Hasil aktif memakai run terbaru yang tercantum di `reproducibility/verification.json`.

![Recall per sumber](figures/recall_by_dataset.png)

## Navigasi

- [Laporan interaktif lokal](index.html)
- [Laporan GMGCSA24](reports/gmgcsa24/README.md)
- [Laporan video asli](reports/vidio_asli/README.md)
- [Analisis per-irisan data](reports/SLICE.md)
- [Status irisan yang diminta](reports/requested_slices_status.json)
- [Inventaris video dan metadata](metadata/video_inventory.csv)
- [Bukti reproducibility](reproducibility/verification.json)
- [Log dan ringkasan validasi](reproducibility/README.md)
- [Format data OOF/NPZ untuk evaluasi lanjutan](inputs/README.md)

## Konfigurasi yang dikunci

Inference memakai target 15 FPS, window 45, stride 15, ambang probabilitas jatuh 0,80, konfirmasi sudut torso 35 derajat, dan kepala interaksi dinonaktifkan. Manifest, hash model, hash pipeline, hash video, environment, hasil per klip, serta log tersimpan di `runs/`.

## Analisis SLICE

Data yang tersedia mendukung irisan berdasarkan sumber dataset, resolusi, FPS, dan durasi. Hasilnya bersifat deskriptif karena hanya ada 10 video dan seluruhnya positif.

Yaw/pitch kamera, performer, dan pasangan kelas interaksi belum dapat dihitung karena metadata dan prediksi OOF belum tersedia. Nilai tersebut tidak diperkirakan dari nama file, wajah, pakaian, atau arah jatuh. `scripts/evaluate_oof.py` dan template di `inputs/` siap digunakan ketika data valid tersedia.

## Reproduksi

Jalankan dari root repository:

```bash
backend/.venv/bin/python "eval/infrence fall/scripts/run_all.py"
```

Untuk membuat ulang laporan dari run yang sudah ada tanpa inference:

```bash
backend/.venv/bin/python "eval/infrence fall/scripts/run_all.py" --reports-only
```

Tes pelaporan:

```bash
backend/.venv/bin/python -m unittest discover -s "eval/infrence fall/tests" -v
```

Cuplikan PNG di `reports/*/frames/` berasal dari video sumber dan disertai indeks frame serta timestamp. Cuplikan itu adalah bukti input dan keputusan per klip, bukan anotasi ground-truth waktu kejadian dan bukan bukti bahwa seluruh rentang prediksi tepat.
'''
    (ROOT/'README.md').write_text(readme,encoding='utf-8')
    write_json(ROOT/'reproducibility/verification.json',dict(verified_at=datetime.now(timezone.utc).isoformat(),
        isolated_source_snapshot_matches=True,backend_production_untouched=True,
        all_video_hashes_match=True,all_manifest_hashes_match=True,
        configs_identical=all(json.loads((ROOT/'manifests'/f'{k}.json').read_text())['config']==json.loads((ROOT/'manifests/gmgcsa24.json').read_text())['config'] for k in NAMES),
        source_runs=source_runs,n_videos=len(all_rows)))
    # Static portable HTML with local image links and a TP/FN filter.
    blocks=[]
    for dataset,title in NAMES.items():
        m=summaries[dataset]
        clips=''.join(f'<article data-result="{r["result"]}"><h3>{html.escape(r["sample_id"])} · {r["result"]}</h3><p>{html.escape(r["video"])}</p><img loading="lazy" src="reports/{dataset}/frames/{r["sample_id"]}.png" alt="Cuplikan sumber {r["sample_id"]}"></article>' for r in all_rows if r['dataset']==dataset)
        blocks.append(f'<section><h2>{title}</h2><p class="lead">{m["tp"]}/{m["n"]} video terdeteksi · recall {percent(m["recall"])} · F1 {percent(m["f1"])}</p><p>Precision {percent(m["precision"])}; negatif n=0, alarm palsu belum terukur.</p><div class="plots"><img src="reports/{dataset}/figures/confusion_matrix.png" alt="Confusion matrix {title}"><img src="reports/{dataset}/figures/metrics.png" alt="Metrik {title}"></div><p><a href="reports/{dataset}/per_video.csv">CSV per video</a> · <a href="{source_runs[dataset]}/evidence.json">Evidence</a> · <a href="{source_runs[dataset]}/execution.log">Log</a></p>{clips}</section>')
    page='''<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>SAPA — Baseline jatuh</title><style>body{font:16px system-ui;color:#203340;max-width:1160px;margin:32px auto;padding:0 24px;line-height:1.55}h1{font-size:30px}h2{font-size:24px}h3{font-size:18px}.lead{font-size:20px;font-weight:600}aside{background:#fff3d3;padding:18px}section{margin-top:40px;border-top:1px solid #cad3d8;padding-top:20px}.plots{display:grid;grid-template-columns:1fr 1fr;gap:20px}img{max-width:100%;height:auto}article{margin:28px 0}button{padding:10px 16px;margin:10px 8px 0 0;background:white;border:1px solid #6b7e89;cursor:pointer}a{color:#215c80}@media(max-width:700px){.plots{grid-template-columns:1fr}}</style><h1>SAPA — Baseline deteksi jatuh</h1><p>GMGCSA24 dan Video asli dievaluasi terpisah. Model dan aturan inferensi tetap.</p><aside>Seluruh video berlabel jatuh. Precision 100% bukan bukti bebas alarm palsu. Dataset GMGCSA24 telah dipilih ulang setelah hasil terdahulu; skor baru tidak membuktikan peningkatan model. Cuplikan bukan anotasi waktu jatuh.</aside><p><a href="README.md">README GitHub</a> · <a href="reports/video_slices.csv">SLICE CSV</a> · <a href="reports/requested_slices_status.json">Status metadata</a></p><button onclick="filter('all')">Semua video</button><button onclick="filter('TP')">Terdeteksi</button><button onclick="filter('FN')">Terlewat</button>'''+''.join(blocks)+'''<section><h2>Analisis SLICE yang tersedia</h2><img src="figures/recall_by_dataset.png" alt="Recall per dataset"><img src="figures/recall_slices_fps.png" alt="Recall menurut FPS"><p>Yaw/pitch, performer, dan OOF interaksi belum tersedia. Hipotesis sudut ekstrem belum dapat dibuktikan dari dataset ini.</p></section><script>function filter(value){document.querySelectorAll('article[data-result]').forEach(el=>el.hidden=value!=='all'&&el.dataset.result!==value);}</script></html>'''
    (ROOT/'index.html').write_text(page,encoding='utf-8')
    return summaries


if __name__=='__main__':
    print(json.dumps(build(),indent=2))
