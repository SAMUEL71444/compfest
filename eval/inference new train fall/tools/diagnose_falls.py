"""Audit baseline: probabilitas dan filter, tanpa mengubah pipeline."""
import argparse
import importlib
import json
import os
from pathlib import Path
from evaluate import Inference, BACKEND, REPO
from pipeline.analyze import window_fall_geometry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--case', action='append', help='Batasi diagnosis ke ID tertentu')
    args = parser.parse_args()
    args.run = args.run.resolve()
    evidence = json.loads((args.run / 'evidence.json').read_text())
    cfg = evidence['config']
    os.environ.setdefault('MPLCONFIGDIR', '/tmp/sapa-mpl')
    os.chdir(BACKEND)
    predictor = Inference(cfg)
    module = importlib.import_module('pipeline.analyze')
    original_build, original_predict = module.build_windows_for_heads, module.predict_proba
    captured = []
    def build(raw, fps, **kwargs):
        result = original_build(raw, fps, **kwargs)
        captured.append({'pose_frames': len(raw), 'source_fps': fps,
            'effective_extraction_fps': fps / max(1, round(fps / 15)),
            'low_conf_key_frames': int((~(raw[:, [5,6,11,12], 2] > .2).all(axis=1)).sum()),
            'geometry': [window_fall_geometry(w, kwargs.get('dst_fps', 15.0)) for w in result['fall_input']]})
        return result
    def predict(model, inputs):
        result = original_predict(model, inputs)
        captured[-1]['probabilities'] = result.cpu().tolist()
        return result
    module.build_windows_for_heads, module.predict_proba = build, predict
    results = []
    try:
        for case in evidence['cases']:
            if args.case and case['id'] not in args.case:
                continue
            captured.clear()
            video = Path(case['video'])
            if not video.is_absolute():
                video = REPO / video
            timeline = predictor(video, case['camera'])
            windows = [(p[2], a, s) for track in captured for p,(a,s) in zip(track['probabilities'], track['geometry'])]
            threshold, angle, speed = cfg.get('fall_thr', .8), cfg.get('fall_angle', 35), cfg.get('fall_speed', 0)
            detected = any(e['tipe'] == 'jatuh' for e in timeline)
            reason = ('detected' if detected else
                      'below_probability_threshold' if all(p < threshold for p,a,s in windows) else
                      'angle_rejection' if all(p < threshold or a < angle for p,a,s in windows) else
                      'speed_rejection')
            result = {'id': case['id'], 'video': Path(case['video']).name,
                'reproduced': detected == ('jatuh' in case['predicted']), 'reason': reason,
                'max_fall_probability': max((p for p,a,s in windows), default=None),
                'max_angle': max((a for p,a,s in windows), default=None),
                'max_speed': max((s for p,a,s in windows), default=None),
                'windows_above_threshold': sum(p >= threshold for p,a,s in windows),
                'windows_rejected_angle': sum(p >= threshold and a < angle for p,a,s in windows),
                'windows_rejected_speed': sum(p >= threshold and a >= angle and s < speed for p,a,s in windows),
                'tracks': list(captured)}
            results.append(result)
            print(case['id'], reason, result['max_fall_probability'], flush=True)
            (args.run / 'diagnostics.json').write_text(json.dumps(results, indent=2))
    finally:
        module.build_windows_for_heads, module.predict_proba = original_build, original_predict


if __name__ == '__main__':
    main()
