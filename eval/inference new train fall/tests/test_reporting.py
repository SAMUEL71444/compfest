import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from metrics import binary_metrics,pairwise_metrics,multiclass_metrics
from evaluate_oof import aligned_inputs


class ReportTests(unittest.TestCase):
    def test_positive_only_does_not_invent_specificity(self):
        m=binary_metrics([1]*6,[1,1,1,0,1,1])
        self.assertEqual(m['recall'],5/6)
        self.assertAlmostEqual(m['f1'],10/11)
        self.assertIsNone(m['specificity'])
        self.assertIsNone(m['false_positive_rate'])
        self.assertIsNone(m['balanced_accuracy'])

    def test_mixed_labels(self):
        m=binary_metrics([1,1,0,0],[1,0,1,0])
        for key in ('tp','fn','fp','tn'):self.assertEqual(m[key],1)
        self.assertEqual(m['f1'],.5)
        self.assertEqual(m['balanced_accuracy'],.5)

    def test_pair_does_not_discard_predictions_outside_pair(self):
        rows=pairwise_metrics([0,1],[2,1],['a','b','c'])
        self.assertEqual(rows[0]['predictions_outside_pair'],1)
        self.assertEqual(rows[0]['pair_macro_f1_zero_division_0'],.5)

    def test_confusion_orientation(self):
        m=multiclass_metrics([0,1,1],[1,1,0],['a','b'])
        self.assertEqual(m['confusion_matrix'],[[0,1],[1,1]])

    def test_oof_aligns_ids_not_positions(self):
        data=dict(sample_id=np.array(['a','b']),y_true=np.array([0,1]),group_id=np.array(['g1','g2']))
        oof=dict(sample_id=np.array(['b','a']),y_pred=np.array([1,0]),fold=np.array([1,0]))
        _,y,p,folds=aligned_inputs(data,oof,2)
        self.assertEqual(y,p)
        self.assertEqual(folds,[0,1])

    def test_oof_rejects_augmented_source_crossing_folds(self):
        data=dict(sample_id=np.array(['a','b']),y_true=np.array([0,1]),group_id=np.array(['same','same']))
        oof=dict(sample_id=np.array(['a','b']),y_pred=np.array([0,1]),fold=np.array([0,1]))
        with self.assertRaisesRegex(ValueError,'Leakage'):aligned_inputs(data,oof,2)

    def test_oof_rejects_missing_predictions(self):
        data=dict(sample_id=np.array(['a','b']),y_true=np.array([0,1]),group_id=np.array(['g1','g2']))
        oof=dict(sample_id=np.array(['a']),y_pred=np.array([0]),fold=np.array([0]))
        with self.assertRaisesRegex(ValueError,'same sample'):aligned_inputs(data,oof,2)

    def test_oof_rejects_nan_probabilities(self):
        data=dict(sample_id=np.array(['a','b']),y_true=np.array([0,1]),group_id=np.array(['g1','g2']))
        oof=dict(sample_id=np.array(['a','b']),y_prob=np.array([[float('nan'),1],[0,1]]),fold=np.array([0,1]))
        with self.assertRaisesRegex(ValueError,'probabilities'):aligned_inputs(data,oof,2)


if __name__=='__main__':unittest.main()
