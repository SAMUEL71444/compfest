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
MODEL_DIR = ROOT / 'models'
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


def build_training_report(reports):
    """Render the supplied training OOF matrix without inventing sample rows."""
    source=json.loads((ROOT/'training_artifacts/fall_cv_summary.json').read_text())
    thresholds=json.loads((ROOT/'training_artifacts/threshold_best_models.json').read_text())
    names=['normal','oleng','jatuh']
    matrix=np.asarray(source['oof_confusion_matrix_argmax'],dtype=int)
    if matrix.shape!=(3,3) or (matrix<0).any():raise ValueError('Invalid supplied OOF confusion matrix')
    per=[]
    for i,name in enumerate(names):
        tp=int(matrix[i,i]);fp=int(matrix[:,i].sum()-tp);fn=int(matrix[i,:].sum()-tp)
        precision=tp/(tp+fp) if tp+fp else None;recall=tp/(tp+fn) if tp+fn else None
        f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None
        per.append(dict(class_name=name,support=int(matrix[i,:].sum()),tp=tp,fp=fp,fn=fn,
                        precision=precision,recall=recall,f1=f1))
    summary=dict(n=int(matrix.sum()),accuracy=float(np.trace(matrix)/matrix.sum()),
                 macro_f1=float(sum(r['f1'] for r in per)/len(per)),per_class=per,
                 supplied_cross_validation=source['summary_mean_std'])
    out=reports/'training_oof';out.mkdir(parents=True,exist_ok=True)
    write_json(out/'metrics.json',summary);write_csv(out/'per_class.csv',per)
    write_csv(out/'threshold_candidates.csv',thresholds)
    fig,axes=plt.subplots(1,2,figsize=(12,5.2))
    normalized=matrix/matrix.sum(axis=1,keepdims=True)
    for ax,values,title,fmt in [(axes[0],matrix,'Jumlah sampel','d'),(axes[1],normalized,'Normalisasi per kelas','.2f')]:
        ax.imshow(values,cmap='Blues',vmin=0)
        ax.set(xticks=range(3),yticks=range(3),xticklabels=names,yticklabels=names,
               xlabel='Prediksi',ylabel='Aktual',title=title)
        for i in range(3):
            for j in range(3):
                ax.text(j,i,format(values[i,j],fmt),ha='center',va='center',
                        color='white' if values[i,j]>values.max()/2 else 'black')
    fig.suptitle('Model baru — confusion matrix OOF argmax')
    fig.tight_layout();fig.savefig(out/'confusion_matrix.png',dpi=170);plt.close(fig)
    rows=[[r['class_name'],r['support'],percent(r['precision']),percent(r['recall']),percent(r['f1'])] for r in per]
    readme='# Evaluasi training OOF — model baru\n\n'
    readme+='Angka berasal langsung dari `training_artifacts/fall_cv_summary.json`; ini bukan hasil inference video.\n\n'
    readme+='![Confusion matrix OOF](confusion_matrix.png)\n\n'
    readme+=md_table(['Kelas','Support','Precision','Recall','F1'],rows)
    readme+=f"\n\nAkurasi agregat: **{percent(summary['accuracy'])}**. Macro-F1 dari matriks agregat: **{percent(summary['macro_f1'])}**.\n\n"
    best=thresholds[0]
    readme+=f"Threshold rekomendasi artefak: `prob >= {best['T_prob']}`, `angle >= {best['T_angle']}`, `speed >= {best['T_speed']}`. "
    readme+=f"OOF biner yang dilaporkan: recall {percent(best['recall_jatuh'])}, precision {percent(best['precision_jatuh'])}, F1 {percent(best['f1_jatuh'])}, false-alarm rate {percent(best['false_alarm'])}.\n\n"
    readme+='[Semua kandidat threshold](threshold_candidates.csv) · [Metrik JSON](metrics.json) · [Metrik per kelas](per_class.csv)\n'
    (out/'README.md').write_text(readme,encoding='utf-8')
    return summary


def build_comparison(reports, summaries):
    old_path=REPO/'eval/infrence fall/reports/summary.json'
    if not old_path.is_file():return []
    old=json.loads(old_path.read_text())['datasets'];rows=[]
    for dataset in NAMES:
        for metric in ('recall','f1'):
            rows.append(dict(dataset=dataset,metric=metric,old=old[dataset][metric],new=summaries[dataset][metric],
                             delta=summaries[dataset][metric]-old[dataset][metric]))
    write_csv(reports/'comparison_old_vs_new.csv',rows);write_json(reports/'comparison_old_vs_new.json',rows)
    fig,axes=plt.subplots(1,2,figsize=(11,4.8))
    for ax,metric in zip(axes,('recall','f1')):
        values=[r for r in rows if r['metric']==metric];x=np.arange(len(values));width=.34
        ax.bar(x-width/2,[r['old'] for r in values],width,label='Model lama',color='#6b7e89')
        ax.bar(x+width/2,[r['new'] for r in values],width,label='Model baru',color=BLUE)
        ax.set(xticks=x,xticklabels=[NAMES[r['dataset']] for r in values],ylim=(0,1.12),title=metric.upper())
        ax.legend()
        for i,r in enumerate(values):ax.text(i+width/2,r['new']+.025,percent(r['new']),ha='center',fontsize=9)
    fig.suptitle('Inference video yang sama — model lama vs model baru')
    fig.tight_layout();fig.savefig(ROOT/'figures/comparison_old_vs_new.png',dpi=170);plt.close(fig)
    return rows


def build_profile_comparison(reports):
    f1_path=ROOT/'profiles/f1_best_summary.json'
    recall_path=ROOT/'profiles/recall_priority_summary.json'
    if not f1_path.is_file() or not recall_path.is_file():return []
    f1_data=json.loads(f1_path.read_text())['datasets']
    recall_data=json.loads(recall_path.read_text())['datasets'];rows=[]
    for dataset in NAMES:
        for metric in ('recall','f1'):
            rows.append(dict(dataset=dataset,metric=metric,f1_best=f1_data[dataset][metric],
                             recall_priority=recall_data[dataset][metric],
                             delta=recall_data[dataset][metric]-f1_data[dataset][metric]))
    write_csv(reports/'comparison_threshold_profiles.csv',rows)
    write_json(reports/'comparison_threshold_profiles.json',rows)
    fig,axes=plt.subplots(1,2,figsize=(11,4.8))
    for ax,metric in zip(axes,('recall','f1')):
        values=[r for r in rows if r['metric']==metric];x=np.arange(len(values));width=.34
        ax.bar(x-width/2,[r['f1_best'] for r in values],width,label='F1 terbaik (0.65)',color='#6b7e89')
        ax.bar(x+width/2,[r['recall_priority'] for r in values],width,label='Recall prioritas (0.30)',color='#2f7d50')
        ax.set(xticks=x,xticklabels=[NAMES[r['dataset']] for r in values],ylim=(0,1.12),title=metric.upper())
        ax.legend(fontsize=8)
        for i,r in enumerate(values):ax.text(i+width/2,r['recall_priority']+.025,percent(r['recall_priority']),ha='center',fontsize=9)
    fig.suptitle('Model baru — perbandingan profil threshold resmi')
    fig.tight_layout();fig.savefig(ROOT/'figures/comparison_threshold_profiles.png',dpi=170);plt.close(fig)
    return rows


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
        for name in ('fall_head.pt','fall_head.json'):
            if sha(MODEL_DIR/name)!=evidence['sha256'][name]:raise ValueError('Model/config changed')
        for name,value in evidence['sha256'].items():
            if name.startswith('pipeline/') and sha(RUNTIME_BACKEND/name)!=value:raise ValueError('Pipeline changed')
        out=reports/dataset;out.mkdir(exist_ok=True);(out/'figures').mkdir(exist_ok=True)
        (out/'frames').mkdir(exist_ok=True)
        rows=[]
        for case in evidence['cases']:
            video=Path(case['video'])
            if not video.is_absolute():video=REPO/video
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
    required=[dict(slice='yaw/pitch kamera dan kombinasi yaw x pitch',status='unavailable',reason='Artefak hanya memuat confusion matrix agregat; metadata sudut per sampel tidak disertakan.'),
              dict(slice='performer',status='unavailable',reason='Artefak hanya memuat confusion matrix agregat; ID performer dan prediksi per sampel tidak disertakan.')]
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
    training_summary=build_training_report(reports)
    comparison=build_comparison(reports,summaries)
    profile_comparison=build_profile_comparison(reports)
    slice_md='# Analisis per-irisan data (SLICE)\n\nIrisan dihitung dari metadata video yang terukur, tanpa mengubah model. Hasil dipisahkan per dataset untuk menghindari pencampuran sumber.\n\n'
    slice_md+='![Recall per sumber](../figures/recall_by_dataset.png)\n\n![Recall per FPS](../figures/recall_slices_fps.png)\n\n'
    slice_md+=md_table(['Dataset','Irisan','Nilai','N positif','TP','FN','Recall'],[[r['dataset'],r['dimension'],r['value'],r['positive_support'],r['tp'],r['fn'],percent(r['recall'])] for r in slice_rows])
    slice_md+='\n\n## Status irisan yang diminta\n\n'
    for r in required:
        suffix=f" [Artefak]({r['artifact']})" if r.get('artifact') else ''
        slice_md+=f"- **{r['slice']} — {r['status']}**: {r['reason']}{suffix}\n"
    slice_md+='\nHipotesis bahwa yaw ekstrem menurunkan recall **belum diuji**. Dua belas/15 kombinasi augmentasi tidak boleh direkonstruksi dari nama file atau contoh video. Temuan dataset kecil ini bersifat deskriptif; FPS, resolusi, subjek, dan jenis gerakan bisa saling terkait. Tidak ada uji signifikansi atau klaim generalisasi.\n'
    (reports/'SLICE.md').write_text(slice_md,encoding='utf-8')
    model_cfg=json.loads((ROOT/'models/fall_head.json').read_text())
    deployed_cfg=json.loads((ROOT/'manifests/gmgcsa24.json').read_text())['config']
    candidates=json.loads((ROOT/'training_artifacts/threshold_best_models.json').read_text())
    active_candidates=[c for c in candidates if c['kandidat']==deployed_cfg.get('threshold_candidate')]
    if len(active_candidates)!=1:raise ValueError('Active threshold candidate missing or ambiguous')
    active_candidate=active_candidates[0]
    threshold=dict(T_prob=deployed_cfg['fall_thr'],T_angle=deployed_cfg['fall_angle'],T_speed=deployed_cfg['fall_speed'])
    gm,va=summaries['gmgcsa24'],summaries['vidio_asli']
    comparison_rows='\n'.join(f"- {NAMES[r['dataset']]} {r['metric']}: {percent(r['old'])} → {percent(r['new'])} ({r['delta']:+.2%})" for r in comparison)
    profile_rows='\n'.join(f"- {NAMES[r['dataset']]} {r['metric']}: {percent(r['f1_best'])} → {percent(r['recall_priority'])} ({r['delta']:+.2%})" for r in profile_comparison)
    readme = f'''# SAPA — inference model fall baru

Evaluasi ini terpisah dari `eval/infrence fall/`; model dan laporan lama tidak dihapus atau diubah.

- **GMGCSA24:** {gm['tp']} dari {gm['n']} video terdeteksi; recall {percent(gm['recall'])}; F1 {percent(gm['f1'])}.
- **Video asli:** {va['tp']} dari {va['n']} video terdeteksi; recall {percent(va['recall'])}; F1 {percent(va['f1'])}.

Semua klip berlabel positif jatuh. Precision 100% belum menguji alarm palsu karena tidak ada video negatif; specificity, false-positive rate, balanced accuracy, dan ROC-AUC tidak dapat dihitung dari kumpulan ini.

![Perbandingan model lama dan baru](figures/comparison_old_vs_new.png)

## Perbandingan terhadap inference lama

{comparison_rows}

## Konsistensi profil threshold model baru

![Perbandingan profil threshold](figures/comparison_threshold_profiles.png)

{profile_rows}

Profil aktif adalah **{deployed_cfg.get('threshold_candidate','tidak dicatat')}** dari `threshold_best_models.json` yang diberikan. Eksekusi default mengambil nama dan nilai `threshold_recommended` langsung dari `fall_head.json`; kandidat lain hanya dapat dipilih secara eksplisit melalui argumen `--candidate`.

## Navigasi

- [Evaluasi training OOF](reports/training_oof/README.md)
- [Laporan GMGCSA24](reports/gmgcsa24/README.md)
- [Laporan video asli](reports/vidio_asli/README.md)
- [Analisis per-irisan video](reports/SLICE.md)
- [Perbandingan CSV](reports/comparison_old_vs_new.csv)
- [Perbandingan profil threshold](reports/comparison_threshold_profiles.csv)
- [Bukti reproducibility](reproducibility/verification.json)
- [Kode training asli yang diberikan](source/new_train_now.py)
- [Audit kesesuaian kode dan artefak](SOURCE_ALIGNMENT.md)
- [Perubahan model AI dan logika inferensi](MODEL_AND_INFERENCE_CHANGES.md)

## Konfigurasi deployment yang diuji

Target {model_cfg['fps']} FPS, window {model_cfg['window']}, stride {model_cfg['stride']}, probabilitas jatuh ≥ {threshold['T_prob']}, sudut torso maksimum ≥ {threshold['T_angle']}°, dan kecepatan torso ≥ {threshold['T_speed']}. Geometri dihitung dari pose ternormalisasi sesuai kode training. Karena `T_speed=0`, syarat kecepatan tidak menyaring jendela pada profil aktif. Pada OOF training, profil aktif melaporkan recall {percent(active_candidate['recall_jatuh'])}, precision {percent(active_candidate['precision_jatuh'])}, F1 {percent(active_candidate['f1_jatuh'])}, dan false-alarm rate {percent(active_candidate['false_alarm'])}.

## Rumus metrik

- `Precision = TP / (TP + FP)`
- `Recall = TP / (TP + FN)`
- `F1 = 2TP / (2TP + FP + FN)`
- `Accuracy = (TP + TN) / (TP + TN + FP + FN)`
- `Specificity = TN / (TN + FP)`
- `False-positive rate = FP / (FP + TN)`
- `Balanced accuracy = (Recall + Specificity) / 2`
- `Macro-F1 = rata-rata F1 semua kelas`

Penyebut nol dilaporkan sebagai `N/A`, bukan diganti dengan nol. Pada evaluasi video positif saja, accuracy sama dengan recall dan tidak menggambarkan performa umum.

Confusion matrix OOF training berisi {training_summary['n']} jendela dengan akurasi agregat {percent(training_summary['accuracy'])} dan macro-F1 {percent(training_summary['macro_f1'])}. Angka OOF dan inference video tidak dibandingkan sebagai unit yang setara.

## Reproduksi

```bash
backend/.venv/bin/python "eval/inference new train fall/scripts/run_all.py"
```

```bash
backend/.venv/bin/python -m unittest discover -s "eval/inference new train fall/tests" -v
```

Cuplikan PNG berasal dari video sumber. Bukti itu menunjukkan input dan keputusan per klip, bukan anotasi waktu jatuh yang lengkap.
'''
    (ROOT/'README.md').write_text(readme,encoding='utf-8')
    aggregate_inputs={name:sha(ROOT/'training_artifacts'/name) for name in ('fall_cv_summary.json','threshold_best_models.json')}
    write_json(ROOT/'reproducibility/verification.json',dict(verified_at=datetime.now(timezone.utc).isoformat(),
        isolated_source_snapshot_matches=True,backend_production_untouched=True,
        all_video_hashes_match=True,all_manifest_hashes_match=True,
        supplied_training_artifacts_present=True,supplied_training_artifact_sha256=aggregate_inputs,
        configs_identical=all(json.loads((ROOT/'manifests'/f'{k}.json').read_text())['config']==json.loads((ROOT/'manifests/gmgcsa24.json').read_text())['config'] for k in NAMES),
        source_runs=source_runs,n_videos=len(all_rows)))
    # Static portable HTML with local image links and a TP/FN filter.
    blocks=[]
    for dataset,title in NAMES.items():
        m=summaries[dataset]
        clips=''.join(f'<article data-result="{r["result"]}"><h3>{html.escape(r["sample_id"])} · {r["result"]}</h3><p>{html.escape(r["video"])}</p><img loading="lazy" src="reports/{dataset}/frames/{r["sample_id"]}.png" alt="Cuplikan sumber {r["sample_id"]}"></article>' for r in all_rows if r['dataset']==dataset)
        blocks.append(f'<section><h2>{title}</h2><p class="lead">{m["tp"]}/{m["n"]} video terdeteksi · recall {percent(m["recall"])} · F1 {percent(m["f1"])}</p><p>Precision {percent(m["precision"])}; negatif n=0, alarm palsu belum terukur.</p><div class="plots"><img src="reports/{dataset}/figures/confusion_matrix.png" alt="Confusion matrix {title}"><img src="reports/{dataset}/figures/metrics.png" alt="Metrik {title}"></div><p><a href="reports/{dataset}/per_video.csv">CSV per video</a> · <a href="{source_runs[dataset]}/evidence.json">Evidence</a> · <a href="{source_runs[dataset]}/execution.log">Log</a></p>{clips}</section>')
    page='''<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>SAPA — Inference model fall baru</title><style>body{font:16px system-ui;color:#203340;max-width:1160px;margin:32px auto;padding:0 24px;line-height:1.55}h1{font-size:30px}h2{font-size:24px}h3{font-size:18px}.lead{font-size:20px;font-weight:600}aside{background:#fff3d3;padding:18px}section{margin-top:40px;border-top:1px solid #cad3d8;padding-top:20px}.plots{display:grid;grid-template-columns:1fr 1fr;gap:20px}img{max-width:100%;height:auto}article{margin:28px 0}button{padding:10px 16px;margin:10px 8px 0 0;background:white;border:1px solid #6b7e89;cursor:pointer}a{color:#215c80}@media(max-width:700px){.plots{grid-template-columns:1fr}}</style><h1>SAPA — Inference model fall baru</h1><p>Model baru dievaluasi pada video GMGCSA24 dan video asli yang sama dengan baseline lama.</p><aside>Seluruh video berlabel jatuh. Precision 100% bukan bukti bebas alarm palsu. Dataset GMGCSA24 telah dipilih ulang setelah hasil terdahulu; skor baru tidak membuktikan peningkatan model. Cuplikan bukan anotasi waktu jatuh.</aside><p><a href="README.md">README GitHub</a> · <a href="reports/video_slices.csv">SLICE CSV</a> · <a href="reports/requested_slices_status.json">Status metadata</a> · <a href="reports/training_oof/README.md">OOF training model baru</a></p><button onclick="filter('all')">Semua video</button><button onclick="filter('TP')">Terdeteksi</button><button onclick="filter('FN')">Terlewat</button>'''+''.join(blocks)+'''<section><h2>Analisis SLICE yang tersedia</h2><img src="figures/recall_by_dataset.png" alt="Recall per dataset"><img src="figures/recall_slices_fps.png" alt="Recall menurut FPS"><p>Confusion matrix OOF training tersedia. Yaw/pitch dan performer belum tersedia karena metadata per sampel tidak disertakan; hipotesis sudut ekstrem belum dapat dibuktikan.</p></section><script>function filter(value){document.querySelectorAll('article[data-result]').forEach(el=>el.hidden=value!=='all'&&el.dataset.result!==value);}</script></html>'''
    (ROOT/'index.html').write_text(page,encoding='utf-8')
    return summaries


if __name__=='__main__':
    print(json.dumps(build(),indent=2))
