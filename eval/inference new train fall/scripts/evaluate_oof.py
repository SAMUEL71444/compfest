"""Evaluate real held-out predictions, join metadata by sample_id, report slices.
Input NPZ files are never loaded with pickle. See inputs/README.md for the schema.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import numpy as np
from metrics import binary_metrics, multiclass_metrics, pairwise_metrics, write_json, write_csv


def load_npz(path):
    with np.load(path, allow_pickle=False) as data:
        return {k: data[k] for k in data.files}


def ids(values, name):
    if values.ndim != 1 or values.dtype.kind not in 'US':
        raise ValueError(f'{name} must be a 1D string array (not object dtype)')
    result = [str(v).strip() for v in values]
    if any(not v for v in result) or len(set(result)) != len(result):
        raise ValueError(f'{name} must be nonempty and unique')
    return result


def aligned_inputs(dataset, oof, n_classes):
    sample_ids = ids(dataset['sample_id'], 'dataset.sample_id')
    prediction_ids = ids(oof['sample_id'], 'oof.sample_id')
    if set(sample_ids) != set(prediction_ids):
        raise ValueError('Dataset and OOF must cover exactly the same sample IDs')
    lookup = {key: i for i, key in enumerate(prediction_ids)}
    order = [lookup[key] for key in sample_ids]
    n = len(sample_ids)
    if n == 0:
        raise ValueError('Empty dataset')
    for label, values in dataset.items():
        if values.ndim != 1 or len(values) != n:
            raise ValueError(f'Dataset metadata {label} must be a 1D array of length N')
    y = dataset['y_true']
    if y.dtype.kind not in 'iu' or np.any((y < 0) | (y >= n_classes)):
        raise ValueError('y_true must contain integer class indices in range')
    folds = oof['fold']
    if folds.ndim != 1 or len(folds) != n or folds.dtype.kind not in 'iu' or (folds < 0).any() or len(set(folds.tolist())) < 2:
        raise ValueError('OOF needs at least two nonnegative integer held-out folds')
    folds = folds[order]
    if 'group_id' not in dataset or dataset['group_id'].dtype.kind not in 'US':
        raise ValueError('group_id string array required to check augmented-source leakage')
    seen = {}
    for group, fold in zip(dataset['group_id'].tolist(), folds.tolist()):
        if not str(group).strip():
            raise ValueError('group_id cannot be empty')
        if group in seen and seen[group] != fold:
            raise ValueError(f'Leakage: source group {group} occurs in multiple held-out folds')
        seen[group] = fold
    probability = None
    if 'y_prob' in oof:
        probability = oof['y_prob']
        if (probability.shape != (n, n_classes) or not np.isfinite(probability).all()
                or (probability < 0).any() or (probability > 1).any()
                or not np.allclose(probability.sum(axis=1), 1, atol=1e-5)):
            raise ValueError('y_prob must be finite N x C probabilities summing to one')
        probability = probability[order]
    if 'y_pred' in oof:
        pred = oof['y_pred']
        if pred.shape != (n,) or pred.dtype.kind not in 'iu' or ((pred < 0) | (pred >= n_classes)).any():
            raise ValueError('y_pred must contain integer class indices in range')
        pred = pred[order]
        if probability is not None and not np.array_equal(pred, probability.argmax(axis=1)):
            raise ValueError('Declared argmax decision differs between y_pred and y_prob')
    elif probability is not None:
        pred = probability.argmax(axis=1)
    else:
        raise ValueError('Provide y_pred or y_prob')
    return sample_ids, y.tolist(), pred.tolist(), folds.tolist()


def analyze(config_path, output):
    cfg = json.loads(config_path.read_text())
    if cfg.get('prediction_type') != 'oof' or cfg.get('decision_rule') != 'argmax':
        raise ValueError('This evaluator requires declared OOF argmax classification')
    if not str(cfg.get('training_provenance', '')).strip():
        raise ValueError('Document training/export provenance before evaluating OOF')
    task = cfg['task']
    if task not in ('fall', 'interaction'):
        raise ValueError('task must be fall or interaction')
    names = cfg['class_names']
    if not isinstance(names, list) or len(names) < 2 or len(set(names)) != len(names) or any(not isinstance(v, str) or not v for v in names):
        raise ValueError('class_names must be unique strings')
    data_path = (config_path.parent / cfg['dataset_npz']).resolve()
    oof_path = (config_path.parent / cfg['oof_npz']).resolve()
    data, pred = load_npz(data_path), load_npz(oof_path)
    sample_ids, y, p, folds = aligned_inputs(data, pred, len(names))
    output.mkdir(parents=True, exist_ok=False)
    full = multiclass_metrics(y, p, names)
    write_json(output / 'classification_report.json', full)
    write_csv(output / 'per_class.csv', [dict(class_name=k, **v) for k, v in full['per_class'].items()])
    write_csv(output / 'per_sample.csv', [dict(sample_id=s, actual=names[a], predicted=names[b], fold=f)
                                       for s, a, b, f in zip(sample_ids, y, p, folds)])
    missing, slices = [], []
    if task == 'fall':
        positive = cfg['positive_class_index']
        if not isinstance(positive, int) or positive not in range(len(names)):
            raise ValueError('Invalid positive_class_index')
        overall = binary_metrics([a == positive for a in y], [b == positive for b in p])
        write_json(output / 'fall_binary_metrics.json', overall)
        columns = {}
        for key in ('yaw_deg', 'pitch_deg', 'performer'):
            if key in data:
                values = data[key]
                if key.endswith('_deg'):
                    if values.dtype.kind not in 'fiu':
                        raise ValueError(f'{key} must be numeric degrees; use NaN for missing')
                    columns[key] = [None if not np.isfinite(v) else str(float(v)) for v in values]
                else:
                    if values.dtype.kind not in 'US':
                        raise ValueError('performer must be a string array')
                    columns[key] = [str(v).strip() or None for v in values]
            else:
                columns[key] = [None] * len(y)
            missing.append(dict(field=key, missing=sum(v is None for v in columns[key]), total=len(y)))
        columns['yaw_pitch'] = [f'{a}/{b}' if a is not None and b is not None else None
                               for a, b in zip(columns['yaw_deg'], columns['pitch_deg'])]
        for dimension, values in columns.items():
            for value in sorted(set(v for v in values if v is not None)):
                mask = [i for i, v in enumerate(values) if v == value]
                metric = binary_metrics([y[i] == positive for i in mask], [p[i] == positive for i in mask])
                slices.append(dict(dimension=dimension, value=value, **metric))
        write_csv(output / 'fall_slices.csv', slices, ['dimension','value', *overall.keys()])
    else:
        write_csv(output / 'class_pairs.csv', pairwise_metrics(y, p, names))
    write_json(output / 'metadata_coverage.json', missing)
    provenance = dict(config=cfg, n=len(y),
        sha256={str(path.name): hashlib.sha256(path.read_bytes()).hexdigest() for path in [config_path, data_path, oof_path]},
        limitations=['OOF provenance is supplied by the exporter; model training exclusion cannot be proven from predictions alone.',
                      'Augmentations sharing group_id must stay in one fold. Performer-disjointness is not guaranteed.',
                      'These are sample-level head predictions, not end-to-end video event detections.'])
    write_json(output / 'provenance.json', provenance)
    os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'sapa-mpl'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    matrix = np.asarray(full['confusion_matrix'])
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.imshow(matrix, cmap='Blues')
    ax.set(xticks=range(len(names)), yticks=range(len(names)), xticklabels=names,
           yticklabels=names, xlabel='Prediksi', ylabel='Aktual', title=f'{task}: confusion matrix OOF (n={len(y)})')
    plt.setp(ax.get_xticklabels(), rotation=40, ha='right')
    for i in range(len(names)):
        for j in range(len(names)):
            ax.text(j, i, str(matrix[i, j]), ha='center', va='center', color='white' if matrix[i,j] > matrix.max()/2 else 'black')
    fig.tight_layout(); fig.savefig(output / 'confusion_matrix.png', dpi=160); plt.close(fig)
    for dimension in ('yaw_deg', 'pitch_deg', 'yaw_pitch', 'performer'):
        subset = [r for r in slices if r['dimension'] == dimension and r['recall'] is not None]
        if not subset:
            continue
        if dimension in ('yaw_deg', 'pitch_deg'):
            subset.sort(key=lambda r: float(r['value']))
        fig, ax = plt.subplots(figsize=(max(7, len(subset) * .65), 5))
        ax.bar([r['value'] for r in subset], [r['recall'] for r in subset], color='#22577a')
        for i, r in enumerate(subset):
            ax.text(i, r['recall'] + .02, f"{r['tp']}/{r['positive_support']}", ha='center', fontsize=9)
        ax.set(ylim=(0,1.15), ylabel='Recall jatuh', xlabel=dimension, title=f'OOF slice: {dimension}')
        ax.tick_params(axis='x', labelrotation=35)
        fig.tight_layout(); fig.savefig(output / f'recall_{dimension}.png', dpi=160); plt.close(fig)
    return full


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    analyze(args.config.resolve(), args.output.resolve())
