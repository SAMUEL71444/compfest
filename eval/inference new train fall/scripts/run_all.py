"""Regenerate manifests, execute unchanged backend, then build all reports.
Run from any working directory using the backend virtualenv.
"""
import argparse
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]
BACKEND=REPO/'backend'
DATA_ROOT=REPO/'eval/infrence fall/data'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports-only',action='store_true',help='Rebuild figures from completed, hash-verified runs')
    parser.add_argument('--candidate',default=None,
                        help='Nama kandidat dari threshold_best_models.json; default mengikuti threshold_recommended di fall_head.json')
    args=parser.parse_args()
    for directory in ('manifests','runs','reports','figures','metadata'):
        (ROOT/directory).mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'sapa-mpl'))
    if not args.reports_only:
        model_cfg=json.loads((ROOT/'models/fall_head.json').read_text())
        candidates=json.loads((ROOT/'training_artifacts/threshold_best_models.json').read_text())
        candidate_name=args.candidate or model_cfg['threshold_recommended']['dari_kandidat']
        matches=[row for row in candidates if row['kandidat']==candidate_name]
        if len(matches)!=1:raise ValueError(f'Kandidat threshold tidak unik/tidak ditemukan: {candidate_name}')
        threshold=matches[0]
        recommended=model_cfg['threshold_recommended']
        if args.candidate is None and any(float(threshold[k]) != float(recommended[k]) for k in ('T_prob','T_angle','T_speed')):
            raise ValueError('threshold_recommended tidak cocok dengan kandidat yang dirujuk fall_head.json')
        config=dict(target_fps=model_cfg['fps'],window=model_cfg['window'],stride=model_cfg['stride'],
                    fall_thr=threshold['T_prob'],fall_angle=threshold['T_angle'],
                    fall_speed=threshold['T_speed'],fall_confirm=True,
                    threshold_candidate=threshold['kandidat'],run_fall=True,run_interaction=False)
        for dataset,folder in [('gmgcsa24','vidio-gmgcsa24'),('vidio_asli','vidio-asli')]:
            videos=sorted((DATA_ROOT/folder).glob('*.mp4'))
            if not videos:raise ValueError(f'No MP4 files in {folder}')
            existing=ROOT/'manifests'/f'{dataset}.json'
            manifest=dict(dataset=dataset,source_folder=folder,
                label_source='Keterangan pengguna: video jatuh. Belum anotasi waktu kejadian.',config=config,
                cases=[dict(id=f'{dataset}-{i:02d}',video=f'../../infrence fall/data/{folder}/{p.name}',camera='lorong',expected=['jatuh'])
                       for i,p in enumerate(videos,1)])
            existing.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
            subprocess.run([sys.executable,str(ROOT/'tools/evaluate.py'),'--manifest',str(existing),
                            '--output',str(ROOT/'runs'/dataset)],cwd=BACKEND,check=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/build_reports.py')],check=True)


if __name__=='__main__':main()
