"""Acceptance checks for the clinic contract. Expected counts are hand-written."""

from __future__ import annotations

import json
from pathlib import Path

from synthcheck.compare import compare_paths

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "fixtures" / "contract" / "clinic.json"
ORACLE = json.loads((ROOT / "fixtures" / "oracle" / "reference_vs_changed.json").read_text(encoding="utf-8"))


def _report(candidate: str, contract: Path = CONTRACT, reference: str = "fixtures/reference") -> dict:
    return compare_paths(ROOT / reference, ROOT / candidate, contract)


def _query(report: dict, query_id: str) -> dict:
    return next(query for query in report["queries"] if query["id"] == query_id)


def test_reference_changed_matches_hand_oracle():
    report = _report("fixtures/changed")
    assert report["summary"]["integrity"] == "pass"
    assert report["summary"]["status"] == "fail"
    assert report["reference"]["row_counts"] == {"patients": 10, "visits": 10, "tasks": 10}
    assert report["candidate"]["row_counts"] == {"patients": 10, "visits": 10, "tasks": 10}

    visits = _query(report, "distinct_visits_by_clinic")
    assert visits["state"] == "ok"
    assert [
        {
            "clinic_id": group["key"]["clinic_id"],
            "reference": group["reference"]["value"],
            "candidate": group["candidate"]["value"],
            "decision": group["decision"],
        }
        for group in visits["groups"]
    ] == [
        {"clinic_id": row["clinic_id"], "reference": row["reference"], "candidate": row["candidate"], "decision": row["decision"]}
        for row in ORACLE["distinct_visits_by_clinic"]
    ]

    coverage = _query(report, "visit_follow_up_coverage_by_month")
    assert coverage["formula"].startswith("distinct visits")
    observed = []
    for group in coverage["groups"]:
        observed.append(
            {
                "clinic_id": group["key"]["clinic_id"],
                "month": group["key"]["month"],
                "reference": group["reference"]["value"],
                "candidate": group["candidate"]["value"],
                "reference_numerator": group["reference"]["numerator"],
                "reference_denominator": group["reference"]["denominator"],
                "candidate_numerator": group["candidate"]["numerator"],
                "candidate_denominator": group["candidate"]["denominator"],
                "absolute_delta": group["absolute_delta"],
                "relative_delta": group["relative_delta"],
                "decision": group["decision"],
            }
        )
    expected = [
        {key: value for key, value in row.items() if key != "case"}
        for row in ORACLE["visit_follow_up_coverage_by_month"]
    ]
    assert observed == expected

    tasks = _query(report, "distinct_assigned_tasks")
    assert tasks["groups"][0]["reference"]["value"] == "10"
    assert tasks["groups"][0]["candidate"]["value"] == "10"
    assert tasks["groups"][0]["decision"] == "pass"
    assert "80.0%" not in json.dumps(report)


def test_extra_child_keeps_visit_coverage_and_changes_task_count():
    report = _report("fixtures/extra_child")
    coverage = _query(report, "visit_follow_up_coverage_by_month")
    for group in coverage["groups"]:
        assert group["reference"]["value"] == group["candidate"]["value"] == "0.8"
        assert group["decision"] == "pass"
    tasks = _query(report, "distinct_assigned_tasks")
    assert tasks["groups"][0]["reference"]["value"] == "10"
    assert tasks["groups"][0]["candidate"]["value"] == "11"
    assert tasks["groups"][0]["decision"] == "fail"
    assert _query(report, "distinct_visits_by_clinic")["groups"][0]["decision"] == "pass"


def test_duplicate_primary_key_is_separate_from_task_count():
    report = _report("fixtures/duplicate_visits")
    findings = report["integrity"]["candidate"]
    assert any(
        item["code"] == "duplicate_primary_key" and item["key"] == "V01" and item["table"] == "visits"
        for item in findings
    )
    assert _query(report, "distinct_visits_by_clinic")["state"] == "unavailable"
    assert _query(report, "visit_follow_up_coverage_by_month")["state"] == "unavailable"
    tasks = _query(report, "distinct_assigned_tasks")
    assert tasks["state"] == "ok"
    assert tasks["groups"][0]["decision"] == "pass"
    assert report["summary"]["status"] == "fail"


def test_orphan_foreign_key_makes_coverage_unavailable():
    report = _report("fixtures/orphan_tasks")
    findings = report["integrity"]["candidate"]
    assert any(
        item["code"] == "orphan_foreign_key"
        and item["constraint"] == "tasks_visit_id_fkey"
        and item["key"] == "V99"
        for item in findings
    )
    coverage = _query(report, "visit_follow_up_coverage_by_month")
    assert coverage["state"] == "unavailable"
    assert any("tasks_visit_id_fkey" in reason for reason in coverage["reasons"])
    assert coverage["groups"] == []
    assert _query(report, "distinct_visits_by_clinic")["state"] == "ok"
    assert _query(report, "distinct_assigned_tasks")["state"] == "ok"


def test_missing_column_is_its_own_finding():
    report = _report("fixtures/missing_column")
    assert any(
        item["code"] == "missing_column" and item["column"] == "kind" and item["table"] == "tasks"
        for item in report["integrity"]["candidate"]
    )
    assert _query(report, "visit_follow_up_coverage_by_month")["state"] == "unavailable"
    assert _query(report, "distinct_assigned_tasks")["state"] == "unavailable"
    assert _query(report, "distinct_visits_by_clinic")["state"] == "ok"


def test_groups_only_on_one_side_are_preserved():
    report = _report("fixtures/groups/candidate", reference="fixtures/groups/reference")
    visits = _query(report, "distinct_visits_by_clinic")
    by_clinic = {group["key"]["clinic_id"]: group for group in visits["groups"]}
    assert set(by_clinic) == {"north", "west", "east"}
    assert by_clinic["north"]["decision"] == "pass"
    assert by_clinic["west"]["candidate"]["state"] == "missing"
    assert by_clinic["west"]["decision"] == "fail"
    assert by_clinic["east"]["reference"]["state"] == "missing"
    assert by_clinic["east"]["decision"] == "fail"


def test_zero_denominator_is_unavailable_not_a_percentage():
    report = _report(
        "fixtures/changed",
        contract=ROOT / "fixtures" / "contract" / "zero_denominator.json",
    )
    query = report["queries"][0]
    assert query["state"] == "ok"
    assert {group["key"]["clinic_id"] for group in query["groups"]} == {"north", "south"}
    for group in query["groups"]:
        assert group["reference"]["denominator"] == 0
        assert group["reference"]["state"] == "unavailable"
        assert group["reference"]["value"] is None
        assert group["candidate"]["state"] == "unavailable"
        assert group["decision"] == "unavailable"
    assert report["summary"]["status"] == "unavailable"
    assert "80.0%" not in json.dumps(report)
