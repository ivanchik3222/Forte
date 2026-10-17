import unittest
from evaluate_detector import fixed_counts


class EvaluationTests(unittest.TestCase):
    def test_duplicate_predictions_do_not_match_one_object_twice(self):
        truth=[dict(label='cash',xyxy=[0,0,10,10])]
        predictions=[dict(label='cash',xyxy=[0,0,10,10],confidence=.9),
                     dict(label='cash',xyxy=[1,1,10,10],confidence=.7)]
        self.assertEqual(fixed_counts(truth,predictions,['cash']),
                         {'cash':dict(tp=1,fp=1,fn=0)})

    def test_correct_location_wrong_class_is_false_positive_and_miss(self):
        truth=[dict(label='cash',xyxy=[0,0,10,10])]
        predictions=[dict(label='hand',xyxy=[0,0,10,10],confidence=.9)]
        self.assertEqual(fixed_counts(truth,predictions,['cash','hand']),
                         {'cash':dict(tp=0,fp=0,fn=1),'hand':dict(tp=0,fp=1,fn=0)})


if __name__=='__main__':
    unittest.main()
