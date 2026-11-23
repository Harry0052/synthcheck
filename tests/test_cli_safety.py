"""CLI, rejection, and trust-boundary checks."""

from __future__ import annotations

import csv
import hashlib
import json
import time
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from synthcheck.bundle import normalize_timestamp
from synthcheck.cli import main
from synthcheck.compare import compare_paths
from synthcheck.engine import connect
from synthcheck.report import render_html

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "fixtures" / "contract" / "clinic.json"


def test_validate_accepts_reference_and_rejects_traversal(capsys):
    assert main(["validate", str(ROOT / "fixtures" / "reference"), "--contract", str(CONTRACT)]) == 0
    assert "valid:" in capsys.readouterr().out
    assert (
        main(
            ["validate", str(ROOT / "fixtures" / "invalid" / "traversal"), "--contract", str(CONTRACT)]
        )
        == 2
    )
    error = capsys.readouterr().err
    assert "path_traversal" in error
    assert "leaves the bundle" in error


def test_cli_compare_exit_code_help_and_reports(tmp_path, capsys):
    json_path = tmp_path / "report.json"
    html_path = tmp_path / "report.html"
    code = main(
        [
            "compare",
            str(ROOT / "fixtures" / "reference"),
            str(ROOT / "fixtures" / "changed"),
            "--contract",
            str(CONTRACT),
            "--json",
            str(json_path),
            "--html",
            str(html_path),
        ]
    )
    assert code == 1
    text = capsys.readouterr().out
    assert "80.0%" in text
    assert "40.0%" in text
    document = json.loads(json_path.read_text(encoding="utf-8"))
    assert document["summary"]["status"] == "fail"
    assert "80.0%" not in json_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    assert "80.0%" in html
    assert "distinct visits with a follow_up task" in html
    assert "fully synthetic" in html.lower() or "synthetic" in html.lower()
    assert "V01,P01" not in html
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0


def test_reject_unknown_operator_external_reference_and_not_synthetic(capsys):
    assert (
        main(
            [
                "validate",
                str(ROOT / "fixtures" / "reference"),
                "--contract",
                str(ROOT / "fixtures" / "contract" / "unknown_op.json"),
            ]
        )
        == 2
    )
    assert "unknown_operator" in capsys.readouterr().err
    assert (
        main(
            [
                "validate",
                str(ROOT / "fixtures" / "reference"),
                "--contract",
                str(ROOT / "fixtures" / "contract" / "external_instruction.json"),
            ]
        )
        == 2
    )
    assert "external_reference" in capsys.readouterr().err
    assert (
        main(
            [
                "validate",
                str(ROOT / "fixtures" / "invalid" / "external"),
                "--contract",
                str(CONTRACT),
            ]
        )
        == 2
    )
    assert "external_reference" in capsys.readouterr().err
    assert (
        main(
            [
                "validate",
                str(ROOT / "fixtures" / "invalid" / "not_synthetic"),
                "--contract",
                str(CONTRACT),
            ]
        )
        == 2
    )
    assert "not_synthetic" in capsys.readouterr().err


def test_hash_mismatch_refuses_the_bundle(tmp_path, capsys):
    bundle = tmp_path / "bundle"
    _copy_bundle(ROOT / "fixtures" / "reference", bundle)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tables"]["visits"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert main(["validate", str(bundle), "--contract", str(CONTRACT)]) == 2
    assert "hash_mismatch" in capsys.readouterr().err


def test_reject_oversized_csv(tmp_path, capsys):
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    contract["max_csv_bytes"] = 32
    path = tmp_path / "small.json"
    path.write_text(json.dumps(contract), encoding="utf-8")
    assert main(["validate", str(ROOT / "fixtures" / "reference"), "--contract", str(path)]) == 2
    error = capsys.readouterr().err
    assert "oversized_input" in error
    assert "32" in error


def test_filter_value_is_bound_not_concatenated(tmp_path):
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    contract["queries"] = [
        {
            "id": "injected",
            "formula": "distinct tasks whose kind equals the bound literal",
            "unit": "tasks",
            "grain": [],
            "measure": {
                "op": "count_distinct",
                "column": "tasks.task_id",
                "where": {"op": "eq", "column": "tasks.kind", "value": "follow_up' OR '1'='1"},
            },
            "tolerance": {"kind": "absolute", "value": 0},
        }
    ]
    path = tmp_path / "inject.json"
    path.write_text(json.dumps(contract), encoding="utf-8")
    report = compare_paths(ROOT / "fixtures" / "reference", ROOT / "fixtures" / "reference", path)
    group = report["queries"][0]["groups"][0]
    assert group["reference"]["value"] == "0"
    assert group["decision"] == "pass"


def test_unexpected_column_is_not_copied_into_the_report(tmp_path):
    bundle = tmp_path / "bundle"
    _copy_bundle(ROOT / "fixtures" / "reference", bundle)
    tasks = bundle / "tasks.csv"
    rows = list(csv.DictReader(tasks.read_text(encoding="utf-8").splitlines()))
    for row in rows:
        row["note"] = "RAWROWSECRET"
    payload = _csv_bytes(["task_id", "visit_id", "kind", "note"], rows)
    tasks.write_bytes(payload)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tables"]["tasks"]["sha256"] = hashlib.sha256(payload).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = compare_paths(ROOT / "fixtures" / "reference", bundle, CONTRACT)
    rendered = json.dumps(report) + render_html(report)
    assert "RAWROWSECRET" not in rendered
    assert any(item["code"] == "unexpected_column" for item in report["integrity"]["candidate"])


def test_external_file_access_is_disabled():
    connection = connect()
    with pytest.raises(Exception) as caught:
        connection.execute("SELECT * FROM read_csv_auto('/etc/passwd')")
    assert "disabled" in str(caught.value).lower() or "permission" in str(caught.value).lower()


def test_timestamp_normalization_uses_the_contract_zone():
    assert normalize_timestamp("2024-01-15", ZoneInfo("UTC")) == "2024-01-15T00:00:00"
    assert (
        normalize_timestamp("2024-02-01T04:30:00Z", ZoneInfo("America/New_York"))
        == "2024-01-31T23:30:00"
    )


def test_demo_finishes_within_the_budget():
    started = time.perf_counter()
    report = compare_paths(ROOT / "fixtures" / "reference", ROOT / "fixtures" / "changed", CONTRACT)
    elapsed = time.perf_counter() - started
    assert report["summary"]["status"] == "fail"
    assert elapsed < 5.0


def _copy_bundle(source: Path, dest: Path) -> None:
    dest.mkdir()
    for path in source.iterdir():
        (dest / path.name).write_bytes(path.read_bytes())


def _csv_bytes(fieldnames: list[str], rows: list[dict]) -> bytes:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")
