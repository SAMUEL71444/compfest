"""Audit baseline: probabilitas dan filter, tanpa mengubah pipeline."""
import argparse
import importlib
import json
from pathlib import Path
from evaluate import Inference
from pipeline.geometry import window_torso_angle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    evidence = json.loads((args.run / 'evidence.json').read_text())
    cfg = evidence['config']
    predictor = Inference(cfg)
    module = importlib.import_module('pipeline.analyze')
    original_build, original_predict = module.build_windows_for_heads, module.predict_proba
    captured = []
    def build(raw, fps, **kwargs):
        result = original_build(raw, fps, **kwargs)
        captured.append({'pose_frames': len(raw), 'source_fps': fps,
            'effective_extraction_fps': fps / max(1, round(fps / 15)),
            'low_conf_key_frames': int((~(raw[:, [5,6,11,12], 2] > .2).all(axis=1)).sum()),
            'angles': [window_torso_angle(w) for w in result['raw_windows']]})
        return result
    def predict(model, inputs):
        result = original_predict(model, inputs)
        captured[-1]['probabilities'] = result.cpu().tolist()
        return result
    module.build_windows_for_heads, module.predict_proba = build, predict
    results = []
    try:
        for case in evidence['cases']:
            captured.clear()
            timeline = predictor(case['video'], case['camera'])
            windows = [(p[2], a) for track in captured for p,a in zip(track['probabilities'], track['angles'])]
            threshold, angle = cfg.get('fall_thr', .8), cfg.get('fall_angle', 35)
            detected = any(e['tipe'] == 'jatuh' for e in timeline)
            reason = 'detected' if detected else 'below_probability_threshold' if all(p < threshold for p,a in windows) else 'geometry_rejection'
            result = {'id': case['id'], 'video': Path(case['video']).name,
                'reproduced': detected == ('jatuh' in case['predicted']), 'reason': reason,
                'max_fall_probability': max((p for p,a in windows), default=None),
                'windows_above_threshold': sum(p >= threshold for p,a in windows),
                'windows_rejected_geometry': sum(p >= threshold and a < angle for p,a in windows),
                'tracks': list(captured)}
            results.append(result)
            print(case['id'], reason, result['max_fall_probability'], flush=True)
            (args.run / 'diagnostics.json').write_text(json.dumps(results, indent=2))
    finally:
        module.build_windows_for_heads, module.predict_proba = original_build, original_predict


if __name__ == '__main__':
    main()
