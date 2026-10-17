"""Create a separate, unlabelled interval-annotation queue from existing video tasks."""

import argparse
from collections import Counter
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EVENT_RULES = (
    "cash_count_without_customer",
    "previous_cash_left_on_desk",
    "cash_handover_without_visible_receipt",
    "collection_bag_not_visibly_checked",
    "counting_without_controller",
)
CONTEXT_RULES = ("cash_room_door_context", "storage_keys_context")
CHECKS = ("identity_document_presentation", "customer_hand_oscillation")


def event_template(rule_id):
    return {
        "rule_id": rule_id,
        "status": "unreviewed",
        "intervals": [],
        "evidence_frames_sec": [],
        "prerequisites": {},
        "exclusions": {},
        "actors": [],
        "objects": [],
        "visibility": "unreviewed",
        "reviewer_notes": "",
        "model_proposals": [],
        "use_as_training_label": False,
    }


def check_template(check_id):
    if check_id == "identity_document_presentation":
        return {
            "check_id": check_id,
            "status": "unreviewed",
            "presentation_type": "unknown",
            "physical_id_intervals": [],
            "phone_presentation_intervals": [],
            "evidence_frames_sec": [],
            "complete_relevant_transaction_visible": "unreviewed",
            "customer_role_verified": False,
            "cashier_role_verified": False,
            "screen_content_or_identity_read": False,
            "reviewer_notes": "",
        }
    return {
        "check_id": check_id,
        "status": "unreviewed",
        "intervals": [],
        "evidence_frames_sec": [],
        "customer_role_verified": False,
        "hand_and_wrist_visible": "unreviewed",
        "camera_motion_compensated": "unreviewed",
        "separated_from_gesture_or_reaching": "unreviewed",
        "original_fps_required": True,
        "is_violation_label": False,
        "reviewer_notes": "",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "annotations/action_review/tasks.json",
        help="Existing task list containing video SHA, splits, and weak source labels.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "annotations/action_review/rule_review_tasks.json",
    )
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Will not overwrite existing review queue: {args.output}")

    source = json.loads(args.source.read_text(encoding="utf-8"))
    rules_doc = json.loads((ROOT / "rules.json").read_text(encoding="utf-8"))
    known_rule_ids = {rule["id"] for rule in rules_doc["rules"]}
    expected = set(EVENT_RULES + CONTEXT_RULES)
    missing = expected - known_rule_ids
    if missing:
        raise ValueError(f"Rules missing from rules.json: {sorted(missing)}")

    tasks = []
    for original in source:
        task = {
            "video_ids": original["video_ids"],
            "source_sha256": original["source_sha256"],
            "source_file": original["source_file"],
            "split": original["split"],
            "duration_sec": original["duration_sec"],
            "original_fps": original["original_fps"],
            "weak_source_binary_label": original["source_binary_label"],
            "weak_source_positive_points_sec": original["source_positive_points_sec"],
            "source_label_is_not_rule_ground_truth": True,
            "transaction_intervals": [],
            "actors": {"cashier": [], "customer": [], "controller": [], "unassigned": []},
            "events": {rule_id: event_template(rule_id) for rule_id in EVENT_RULES},
            "context_observations": {rule_id: event_template(rule_id) for rule_id in CONTEXT_RULES},
            "checks": {check_id: check_template(check_id) for check_id in CHECKS},
            "review_status": "unreviewed",
            "legal_violation_verdict": None,
        }
        # The context candidates remain visible for annotation, but must never
        # become classifier targets before their policy basis is verified.
        for candidate in task["context_observations"].values():
            candidate["use_as_training_label"] = False
            candidate["rule_applicability"] = "requires_current_policy_review"
        tasks.append(task)

    hashes = [task["source_sha256"] for task in tasks]
    if len(set(hashes)) != len(hashes):
        raise ValueError("Input tasks contain duplicate source SHA-256 groups")
    split_counts = Counter(task["split"] for task in tasks)
    if split_counts != Counter({"train": 24, "val": 10, "test": 6}):
        raise ValueError(f"Unexpected frozen split counts: {dict(split_counts)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "task_count_unique_source_videos": len(tasks),
        "video_ids_in_tasks": sum(len(task["video_ids"]) for task in tasks),
        "split_counts": dict(split_counts),
        "primary_event_classes_per_video": len(EVENT_RULES),
        "context_only_candidates_per_video": len(CONTEXT_RULES),
        "separate_visual_checks_per_video": len(CHECKS),
        "reviewed_events": 0,
        "generated_ground_truth_labels": 0,
        "model_proposals_are_labels": False,
    }
    summary_path = args.output.with_name("rule_review_summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
