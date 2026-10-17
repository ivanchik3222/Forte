import unittest

from interaction_timeline import build_timeline


def box(label,xyxy):
    return dict(label=label,xyxy=xyxy,confidence=.9)


class SequenceTests(unittest.TestCase):
    def test_cash_miss_breaks_visibility_evidence(self):
        report=dict(frames=[dict(timestamp_sec=t,boxes=[box('cash',[1,1,10,10])] if t!=1. else [])
                            for t in (0.,.5,1.,1.5,2.)])
        result=build_timeline(report)
        self.assertEqual(result['frames'][2]['cash_visibility'],'unconfirmed')
        self.assertEqual([(e['start_sec'],e['end_sec']) for e in result['events']],[(0.,.5),(1.5,2.)])

    def test_tracks_follow_positions_when_detector_order_changes(self):
        report=dict(frames=[dict(timestamp_sec=0.,boxes=[box('hand',[10,10,20,20]),box('hand',[100,10,110,20])]),
                            dict(timestamp_sec=.5,boxes=[box('hand',[102,10,112,20]),box('hand',[12,10,22,20])])])
        result=build_timeline(report)
        self.assertEqual([h['track_id'] for h in result['frames'][1]['hands']],[2,1])

    def test_unknown_never_becomes_violation(self):
        result=build_timeline(dict(frames=[dict(timestamp_sec=t,boxes=[]) for t in (0.,.5,1.)]))
        self.assertEqual(result['events'],[])
        self.assertEqual(result['rule_evaluation'],'not performed')
        with self.assertRaises(ValueError):
            build_timeline(dict(frames=[dict(timestamp_sec=1.,boxes=[]),dict(timestamp_sec=0.,boxes=[])]))


if __name__=='__main__':unittest.main()
