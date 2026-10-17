"""Draft event taxonomy from inspected sequences, deliberately separate from verified labels."""
import csv
from pipeline import ROOT,manifest

# These are visual hypotheses; none is a verified multiclass training target.
DRAFT={
1:('cash_handling','previous_cash_left_on_desk'),2:('cash_handling','previous_cash_left_on_desk'),
4:('customer_change_and_cash_handling','previous_cash_left_on_desk'),
11:('departure_and_lighting_change',''),13:('storage_door_manipulation',''),15:('cashier_departure',''),
17:('bag_handover','collection_bag_not_visibly_checked'),18:('additional_person_near_transaction',''),
20:('storage_door_manipulation',''),22:('cashier_departure',''),24:('cashier_departure',''),
26:('desk_cash_handling_before_departure','previous_cash_left_on_desk'),28:('departure_from_workstation',''),
30:('additional_person_enters_work_area',''),32:('cashier_return_to_workstation',''),33:('cashier_return_to_workstation',''),
34:('customer_departure_during_cash_handling','cash_count_without_customer'),
38:('customer_arrival_and_cash_handling','previous_cash_left_on_desk'),40:('bag_placed_on_desk',''),
44:('cash_handling',''),46:('hand_near_mouth',''),47:('cash_handling','previous_cash_left_on_desk')}

def main():
    records=manifest(ROOT/'open/open');dest=ROOT/'annotations/review_queue.csv';dest.parent.mkdir(exist_ok=True)
    with dest.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['video_ids','sha256','binary_label','timestamp_sec','draft_visual_action','candidate_rule_id',
                                     'review_status','confirmed_event_type','start_sec','end_sec','confirmed_rule_id','review_notes'])
        w.writeheader()
        for r in records:
            for t in r['timestamps_sec'] or [None]:
                vid=47 if r['video_ids']==[4,47] and t==68 else r['video_ids'][0]
                action,rule=DRAFT.get(vid,('normal_video_review',''))
                w.writerow(dict(video_ids=';'.join(map(str,r['video_ids'])),sha256=r['sha256'],binary_label=r['label'],
                                timestamp_sec=t,draft_visual_action=action,candidate_rule_id=rule,review_status='unreviewed'))
    print(dest)

if __name__=='__main__':main()
