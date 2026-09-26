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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports-only',action='store_true',help='Rebuild figures from completed, hash-verified runs')
    args=parser.parse_args()
    os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'sapa-mpl'))
    if not args.reports_only:
        config=dict(target_fps=15,window=45,stride=15,fall_thr=.8,fall_angle=35.0,
                    fall_confirm=True,run_fall=True,run_interaction=False)
        for dataset,folder in [('gmgcsa24','vidio-gmgcsa24'),('vidio_asli','vidio-asli')]:
            videos=sorted((ROOT/'data'/folder).glob('*.mp4'))
            if not videos:raise ValueError(f'No MP4 files in {folder}')
            existing=ROOT/'manifests'/f'{dataset}.json'
            manifest=dict(dataset=dataset,source_folder=folder,
                label_source='Keterangan pengguna: video jatuh. Belum anotasi waktu kejadian.',config=config,
                cases=[dict(id=f'{dataset}-{i:02d}',video=f'../data/{folder}/{p.name}',camera='lorong',expected=['jatuh'])
                       for i,p in enumerate(videos,1)])
            existing.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
            subprocess.run([sys.executable,str(ROOT/'tools/evaluate.py'),'--manifest',str(existing),
                            '--output',str(ROOT/'runs'/dataset)],cwd=BACKEND,check=True)
    # Regenerate the aggregate OOF fall/interaction report first so every link
    # in the checkpoint is backed by current, validated source matrices.
    subprocess.run([sys.executable, str(REPO/'eval/analisis_baseline.py')], check=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/build_reports.py')],check=True)


if __name__=='__main__':main()
