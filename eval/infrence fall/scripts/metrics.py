"""Metrics shared by clip reports and OOF analysis. No inference changes."""
import csv
import json
from pathlib import Path


def divide(n, d):
    return n / d if d else None


def binary_metrics(actual, predicted):
    if len(actual) != len(predicted):
        raise ValueError('Label and prediction lengths differ')
    if any(x not in (0, 1, False, True) for x in [*actual, *predicted]):
        raise ValueError('Binary labels must be 0/1')
    tp = sum(bool(a) and bool(p) for a, p in zip(actual, predicted))
    fn = sum(bool(a) and not p for a, p in zip(actual, predicted))
    fp = sum(not a and bool(p) for a, p in zip(actual, predicted))
    tn = sum(not a and not p for a, p in zip(actual, predicted))
    recall, specificity = divide(tp, tp + fn), divide(tn, tn + fp)
    return dict(n=len(actual), positive_support=tp + fn, negative_support=tn + fp,
                tp=tp, fn=fn, fp=fp, tn=tn, accuracy=divide(tp + tn, len(actual)),
                precision=divide(tp, tp + fp), recall=recall,
                f1=divide(2 * tp, 2 * tp + fp + fn), specificity=specificity,
                false_positive_rate=divide(fp, fp + tn), false_negative_rate=divide(fn, tp + fn),
                balanced_accuracy=(recall + specificity) / 2 if recall is not None and specificity is not None else None)


def multiclass_metrics(actual, predicted, class_names):
    if len(actual) != len(predicted) or not class_names:
        raise ValueError('Invalid label lengths/classes')
    k = len(class_names)
    if any(not isinstance(v, int) or v < 0 or v >= k for v in [*actual, *predicted]):
        raise ValueError('Labels must be integer class indices')
    matrix = [[0] * k for _ in range(k)]
    for a, p in zip(actual, predicted):
        matrix[a][p] += 1
    per_class = {name: binary_metrics([a == i for a in actual], [p == i for p in predicted])
                 for i, name in enumerate(class_names)}
    macro = sum(m['f1'] or 0 for m in per_class.values()) / k
    weighted = divide(sum((m['f1'] or 0) * m['positive_support'] for m in per_class.values()), len(actual))
    return dict(n=len(actual), class_names=class_names, confusion_matrix=matrix,
                accuracy=divide(sum(a == p for a, p in zip(actual, predicted)), len(actual)),
                macro_f1_zero_division_0=macro, weighted_f1_zero_division_0=weighted, per_class=per_class)


def pairwise_metrics(actual, predicted, names):
    """Restrict TRUE labels to each pair; predictions outside pair remain errors."""
    rows = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            subset = [(a, p) for a, p in zip(actual, predicted) if a in (i, j)]
            a, p = [v[0] for v in subset], [v[1] for v in subset]
            mi = binary_metrics([x == i for x in a], [x == i for x in p])
            mj = binary_metrics([x == j for x in a], [x == j for x in p])
            rows.append(dict(class_a=names[i], class_b=names[j], n=len(a),
                support_a=mi['positive_support'], support_b=mj['positive_support'],
                a_to_b=sum(x == i and y == j for x, y in subset),
                b_to_a=sum(x == j and y == i for x, y in subset),
                predictions_outside_pair=sum(y not in (i, j) for y in p),
                f1_a=mi['f1'], f1_b=mj['f1'],
                pair_macro_f1_zero_division_0=((mi['f1'] or 0) + (mj['f1'] or 0)) / 2 if a else None))
    return rows


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def write_csv(path, rows, fields=None):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    keys = fields or list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def percent(value):
    return 'N/A' if value is None else f'{value * 100:.2f}%'
