"""Write the committed synthetic clinic fixtures.

Rows are enumerated in this file. Seed 16 identifies the fixture revision.
Nothing is sampled from a patient dataset, and the script does not use a
network connection.

Run from the repository root:

    python scripts/generate_fixtures.py
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
SEED = 16
VERSION = "0.1.0"
GENERATOR = "synthcheck-fixture-generator"

PATIENTS = [
    {"patient_id": f"P{index:02d}", "clinic_id": "north" if index <= 5 else "south"}
    for index in range(1, 11)
]
VISITS = [
    {
        "visit_id": f"V{index:02d}",
        "patient_id": f"P{index:02d}",
        "clinic_id": "north" if index <= 5 else "south",
        "visited_on": "2024-01-15",
    }
    for index in range(1, 11)
]
REFERENCE_TASKS = [
    {"task_id": "T01", "visit_id": "V01", "kind": "follow_up"},
    {"task_id": "T02", "visit_id": "V01", "kind": "follow_up"},
    {"task_id": "T03", "visit_id": "V02", "kind": "follow_up"},
    {"task_id": "T04", "visit_id": "V03", "kind": "follow_up"},
    {"task_id": "T05", "visit_id": "V04", "kind": "follow_up"},
    {"task_id": "T06", "visit_id": "V06", "kind": "follow_up"},
    {"task_id": "T07", "visit_id": "V06", "kind": "follow_up"},
    {"task_id": "T08", "visit_id": "V07", "kind": "follow_up"},
    {"task_id": "T09", "visit_id": "V08", "kind": "follow_up"},
    {"task_id": "T10", "visit_id": "V09", "kind": "follow_up"},
]
CHANGED_TASKS = [
    {"task_id": "T01", "visit_id": "V01", "kind": "follow_up"},
    {"task_id": "T02", "visit_id": "V01", "kind": "follow_up"},
    {"task_id": "T03", "visit_id": "V02", "kind": "follow_up"},
    {"task_id": "T04", "visit_id": "V06", "kind": "follow_up"},
    {"task_id": "T05", "visit_id": "V06", "kind": "follow_up"},
    {"task_id": "T06", "visit_id": "V07", "kind": "follow_up"},
    {"task_id": "T07", "visit_id": "V07", "kind": "follow_up"},
    {"task_id": "T08", "visit_id": "V08", "kind": "follow_up"},
    {"task_id": "T09", "visit_id": "V09", "kind": "follow_up"},
    {"task_id": "T10", "visit_id": "V10", "kind": "follow_up"},
]
PROVENANCE = {
    "contains_patient_rows": False,
    "declaration": "fully_synthetic",
    "description": (
        "Fictional clinic placeholders generated locally by "
        "synthcheck-fixture-generator. No real person is described."
    ),
}


def main() -> None:
    write_bundle(
        FIXTURES / "reference",
        {"patients": PATIENTS, "visits": VISITS, "tasks": REFERENCE_TASKS},
    )
    write_bundle(
        FIXTURES / "changed",
        {"patients": PATIENTS, "visits": VISITS, "tasks": CHANGED_TASKS},
    )
    write_bundle(
        FIXTURES / "extra_child",
        {
            "patients": PATIENTS,
            "visits": VISITS,
            "tasks": REFERENCE_TASKS
            + [{"task_id": "T11", "visit_id": "V01", "kind": "follow_up"}],
        },
    )
    orphan = [dict(row) for row in REFERENCE_TASKS]
    orphan[-1]["visit_id"] = "V99"
    write_bundle(
        FIXTURES / "orphan_tasks",
        {"patients": PATIENTS, "visits": VISITS, "tasks": orphan},
    )
    write_bundle(
        FIXTURES / "duplicate_visits",
        {
            "patients": PATIENTS,
            "visits": VISITS + [dict(VISITS[0])],
            "tasks": REFERENCE_TASKS,
        },
    )
    write_bundle(
        FIXTURES / "missing_column",
        {
            "patients": PATIENTS,
            "visits": VISITS,
            "tasks": [
                {"task_id": row["task_id"], "visit_id": row["visit_id"]}
                for row in REFERENCE_TASKS
            ],
        },
    )
    write_bundle(
        FIXTURES / "groups" / "reference",
        {
            "patients": [
                {"patient_id": "P1", "clinic_id": "north"},
                {"patient_id": "P2", "clinic_id": "west"},
            ],
            "visits": [
                {
                    "visit_id": "V1",
                    "patient_id": "P1",
                    "clinic_id": "north",
                    "visited_on": "2024-01-15",
                },
                {
                    "visit_id": "V2",
                    "patient_id": "P2",
                    "clinic_id": "west",
                    "visited_on": "2024-03-01",
                },
            ],
            "tasks": [{"task_id": "T1", "visit_id": "V1", "kind": "follow_up"}],
        },
    )
    write_bundle(
        FIXTURES / "groups" / "candidate",
        {
            "patients": [
                {"patient_id": "P1", "clinic_id": "north"},
                {"patient_id": "P3", "clinic_id": "east"},
            ],
            "visits": [
                {
                    "visit_id": "V1",
                    "patient_id": "P1",
                    "clinic_id": "north",
                    "visited_on": "2024-01-15",
                },
                {
                    "visit_id": "V3",
                    "patient_id": "P3",
                    "clinic_id": "east",
                    "visited_on": "2024-03-01",
                },
            ],
            "tasks": [{"task_id": "T1", "visit_id": "V1", "kind": "follow_up"}],
        },
    )
    write_bundle(
        FIXTURES / "invalid" / "not_synthetic",
        {"patients": PATIENTS, "visits": VISITS, "tasks": REFERENCE_TASKS},
        synthetic_only=False,
        provenance={
            "contains_patient_rows": False,
            "declaration": "unspecified",
            "description": "This fixture is intentionally not declared fully synthetic.",
        },
    )
    write_rejected_bundle(
        FIXTURES / "invalid" / "traversal",
        {"patients": "../patients.csv", "visits": "visits.csv", "tasks": "tasks.csv"},
    )
    write_rejected_bundle(
        FIXTURES / "invalid" / "external",
        {
            "patients": "https://example.invalid/patients.csv",
            "visits": "visits.csv",
            "tasks": "tasks.csv",
        },
    )
    print(f"wrote fixtures under {FIXTURES}")


def write_bundle(directory: Path, tables: dict, synthetic_only: bool = True, provenance: dict | None = None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    provenance_body = json.dumps(provenance or PROVENANCE, indent=2, sort_keys=True) + "\n"
    (directory / "provenance.json").write_text(provenance_body, encoding="utf-8")
    manifest_tables = {}
    for name, rows in tables.items():
        fieldnames = list(rows[0])
        payload = _csv_bytes(fieldnames, rows)
        filename = f"{name}.csv"
        (directory / filename).write_bytes(payload)
        manifest_tables[name] = {"path": filename, "sha256": hashlib.sha256(payload).hexdigest()}
    manifest = {
        "bundle_version": "1",
        "generator": {"name": GENERATOR, "seed": SEED, "version": VERSION},
        "provenance": {
            "path": "provenance.json",
            "sha256": hashlib.sha256(provenance_body.encode("utf-8")).hexdigest(),
        },
        "synthetic_only": synthetic_only,
        "tables": manifest_tables,
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_rejected_bundle(directory: Path, paths: dict[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    provenance_body = json.dumps(PROVENANCE, indent=2, sort_keys=True) + "\n"
    (directory / "provenance.json").write_text(provenance_body, encoding="utf-8")
    manifest = {
        "bundle_version": "1",
        "generator": {"name": GENERATOR, "seed": SEED, "version": VERSION},
        "provenance": {
            "path": "provenance.json",
            "sha256": hashlib.sha256(provenance_body.encode("utf-8")).hexdigest(),
        },
        "synthetic_only": True,
        "tables": {
            name: {"path": relative, "sha256": "0" * 64} for name, relative in paths.items()
        },
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _csv_bytes(fieldnames: list[str], rows: list[dict]) -> bytes:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


if __name__ == "__main__":
    main()
