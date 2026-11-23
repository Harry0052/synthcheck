"""Load a local CSV bundle and collect integrity findings.

The loader never follows a path outside the bundle directory and never opens a
network location. Integrity problems are findings. Paths, hashes, size, and
the synthetic-only declaration are input errors.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

from synthcheck.contract import Contract, _reject_external
from synthcheck.errors import InvalidInput
from synthcheck.models import Bundle, Finding

_MAX_FINDINGS = 50


def load_bundle(root: Path, contract: Contract) -> Bundle:
    root = Path(root)
    if not root.is_dir():
        raise InvalidInput("invalid_path", f"Bundle directory does not exist: {root}")
    manifest = _read_json(root / "manifest.json", "manifest")
    _reject_external(manifest, "manifest")
    if manifest.get("synthetic_only") is not True:
        raise InvalidInput(
            "not_synthetic",
            "Bundle manifest must set synthetic_only to true. SynthCheck accepts only fully synthetic fixtures.",
        )
    generator = manifest.get("generator")
    if not isinstance(generator, dict):
        raise InvalidInput("malformed_contract", "Bundle manifest needs a generator object")
    _generator(generator)
    provenance_ref = manifest.get("provenance")
    if not isinstance(provenance_ref, dict) or not isinstance(provenance_ref.get("path"), str):
        raise InvalidInput("malformed_contract", "Bundle manifest needs provenance.path")
    provenance_path = _safe_path(root, provenance_ref["path"])
    provenance_bytes = _read_bytes(provenance_path, contract.max_csv_bytes, provenance_ref["path"])
    _check_hash(provenance_ref, provenance_bytes, provenance_ref["path"])
    provenance = _parse_json_bytes(provenance_bytes, "provenance")
    _reject_external(provenance, "provenance")
    if provenance.get("declaration") != "fully_synthetic" or provenance.get("contains_patient_rows") is not False:
        raise InvalidInput(
            "not_synthetic",
            "Provenance must declare fully_synthetic and contains_patient_rows false.",
        )
    tables_raw = manifest.get("tables")
    if not isinstance(tables_raw, dict):
        raise InvalidInput("malformed_contract", "Bundle manifest needs a tables object")
    if set(tables_raw) != set(contract.tables):
        raise InvalidInput(
            "malformed_contract",
            "Bundle tables must match the contract tables exactly: "
            + ", ".join(sorted(contract.tables)),
        )
    zone = ZoneInfo(contract.timezone)
    findings: list[Finding] = []
    tainted: set[str] = set()
    loaded: dict[str, list[dict]] = {}
    hashes: dict[str, str] = {}
    for table_name, table in contract.tables.items():
        spec = tables_raw[table_name]
        if not isinstance(spec, dict) or not isinstance(spec.get("path"), str):
            raise InvalidInput("malformed_contract", f"Manifest entry for {table_name} needs a path")
        path = _safe_path(root, spec["path"])
        payload = _read_bytes(path, contract.max_csv_bytes, spec["path"])
        digest = _check_hash(spec, payload, spec["path"])
        hashes[table_name] = digest
        rows, table_findings = _read_table(table_name, table, payload, contract.max_rows, zone)
        loaded[table_name] = rows
        findings.extend(table_findings)
        if any(item.code != "orphan_foreign_key" for item in table_findings):
            tainted.add(table_name)
    broken: set[str] = set()
    for table_name, table in contract.tables.items():
        for foreign_key in table.foreign_keys:
            orphan_findings = _orphan_findings(table_name, foreign_key, loaded)
            if orphan_findings:
                broken.add(foreign_key.name)
                findings.extend(orphan_findings)
    findings = _cap(findings)
    return Bundle(
        root=str(root),
        generator={
            "name": generator["name"],
            "version": generator["version"],
            "seed": generator["seed"],
        },
        table_hashes=hashes,
        provenance_sha256=hashlib.sha256(provenance_bytes).hexdigest(),
        tables=loaded,
        findings=findings,
        tainted_tables=tainted,
        broken_relationships=broken,
    )


def _generator(generator: dict) -> None:
    name = generator.get("name")
    version = generator.get("version")
    seed = generator.get("seed")
    if not isinstance(name, str) or not name.strip():
        raise InvalidInput("malformed_contract", "generator.name must be a non-empty string")
    if not isinstance(version, str) or not version.strip():
        raise InvalidInput("malformed_contract", "generator.version must be a non-empty string")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise InvalidInput("malformed_contract", "generator.seed must be an integer")


def _read_json(path: Path, label: str) -> dict:
    if not path.is_file():
        raise InvalidInput("invalid_path", f"Missing {label} file: {path.name}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise InvalidInput("malformed_contract", f"{label} is not UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise InvalidInput("malformed_contract", f"{label} is not JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise InvalidInput("malformed_contract", f"{label} must be a JSON object")
    return payload


def _parse_json_bytes(payload: bytes, label: str) -> dict:
    try:
        value = json.loads(payload.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise InvalidInput("malformed_contract", f"{label} is not UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise InvalidInput("malformed_contract", f"{label} is not JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise InvalidInput("malformed_contract", f"{label} must be a JSON object")
    return value


def _safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or relative == "":
        raise InvalidInput("invalid_path", "Bundle path is empty")
    if "\\" in relative or relative.startswith(("/", "\\")):
        raise InvalidInput("path_traversal", f"Bundle path must be a relative file inside the bundle: {relative}")
    if "://" in relative:
        raise InvalidInput("external_reference", f"Bundle path is an external reference: {relative}")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise InvalidInput("path_traversal", f"Bundle path leaves the bundle directory: {relative}")
    root_resolved = root.resolve()
    target = (root_resolved / Path(*pure.parts)).resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise InvalidInput("path_traversal", f"Bundle path leaves the bundle directory: {relative}")
    if not target.is_file():
        raise InvalidInput("invalid_path", f"Bundle file does not exist: {relative}")
    return target


def _read_bytes(path: Path, limit: int, label: str) -> bytes:
    size = path.stat().st_size
    if size > limit:
        raise InvalidInput(
            "oversized_input",
            f"{label} is {size} bytes, which is above the contract limit of {limit} bytes",
        )
    return path.read_bytes()


def _check_hash(spec: dict, payload: bytes, label: str) -> str:
    expected = spec.get("sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise InvalidInput("malformed_contract", f"{label} needs a lowercase sha256")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected:
        raise InvalidInput(
            "hash_mismatch",
            f"SHA-256 for {label} does not match the manifest. Refusing to evaluate a bundle that is not the declared input.",
        )
    return digest


def _read_table(table_name, table, payload: bytes, max_rows: int, zone: ZoneInfo):
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidInput("malformed_contract", f"{table_name} CSV is not UTF-8") from exc
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        raise InvalidInput("malformed_contract", f"{table_name} CSV has no header")
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise InvalidInput("malformed_contract", f"{table_name} CSV repeats a column name")
    findings: list[Finding] = []
    expected = set(table.columns)
    present = set(reader.fieldnames)
    for column in sorted(expected - present):
        findings.append(
            Finding(
                code="missing_column",
                message=f"Table {table_name} is missing declared column {column}.",
                table=table_name,
                column=column,
            )
        )
    for column in sorted(present - expected):
        findings.append(
            Finding(
                code="unexpected_column",
                message=f"Table {table_name} has unexpected column {column}. The value was not loaded.",
                table=table_name,
                column=column,
            )
        )
    rows: list[dict] = []
    for index, raw in enumerate(reader, start=2):
        if len(rows) >= max_rows:
            raise InvalidInput(
                "oversized_input",
                f"{table_name} has more than {max_rows} data rows, which is the contract row limit",
            )
        parsed = {}
        for column_name, column in table.columns.items():
            if column_name not in present:
                parsed[column_name] = None
                continue
            cell = raw.get(column_name)
            parsed[column_name] = _parse_cell(
                table_name, column, cell, index, zone, findings
            )
        rows.append(parsed)
    _primary_key_findings(table_name, table.primary_key, rows, findings)
    return rows, findings


def _parse_cell(table_name, column, cell, line: int, zone: ZoneInfo, findings: list[Finding]):
    if cell is None or cell == "":
        if not column.nullable:
            findings.append(
                Finding(
                    code="null_violation",
                    message=f"Table {table_name} column {column.name} is null at line {line}.",
                    table=table_name,
                    column=column.name,
                    key=str(line),
                    count=1,
                )
            )
        return None
    try:
        return _coerce(column.type_name, cell, zone)
    except ValueError:
        findings.append(
            Finding(
                code="type_mismatch",
                message=(
                    f"Table {table_name} column {column.name} at line {line} "
                    f"is not a {column.type_name}."
                ),
                table=table_name,
                column=column.name,
                key=str(line),
                count=1,
            )
        )
        return None


def _coerce(type_name: str, cell: str, zone: ZoneInfo):
    if type_name == "string":
        return cell
    if type_name == "integer":
        if not re.fullmatch(r"-?\d+", cell):
            raise ValueError(cell)
        return int(cell)
    if type_name == "number":
        if cell.lower() in {"nan", "inf", "infinity", "+inf", "-inf", "+infinity", "-infinity"}:
            raise ValueError(cell)
        if not re.fullmatch(r"-?\d+(\.\d+)?", cell):
            raise ValueError(cell)
        return cell
    if type_name == "boolean":
        if cell not in {"true", "false", "True", "False"}:
            raise ValueError(cell)
        return cell.lower() == "true"
    if type_name == "timestamp":
        return normalize_timestamp(cell, zone)
    raise ValueError(type_name)


def normalize_timestamp(value: str, zone: ZoneInfo) -> str:
    """Interpret a timestamp in the contract timezone and store the local wall time."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        moment = datetime.fromisoformat(text).replace(tzinfo=zone)
    else:
        moment = datetime.fromisoformat(text)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=zone)
        else:
            moment = moment.astimezone(zone)
    return moment.replace(tzinfo=None).isoformat(timespec="seconds")


def _primary_key_findings(table_name: str, primary_key, rows: list[dict], findings: list[Finding]) -> None:
    seen: dict[tuple, int] = {}
    for row in rows:
        key = tuple(row.get(column) for column in primary_key)
        if any(part is None for part in key):
            continue
        seen[key] = seen.get(key, 0) + 1
    for key, count in sorted(seen.items(), key=lambda item: _key_text(item[0])):
        if count > 1:
            rendered = _key_text(key)
            column = primary_key[0] if len(primary_key) == 1 else ",".join(primary_key)
            findings.append(
                Finding(
                    code="duplicate_primary_key",
                    message=(
                        f"Duplicate primary key {table_name}.{column} value {rendered} occurs {count} times."
                    ),
                    table=table_name,
                    column=column,
                    key=rendered,
                    count=count,
                )
            )


def _orphan_findings(table_name: str, foreign_key, loaded: dict[str, list[dict]]) -> list[Finding]:
    parent_rows = loaded.get(foreign_key.parent_table, [])
    parent_keys = set()
    for row in parent_rows:
        key = tuple(row.get(column) for column in foreign_key.parent_columns)
        if all(part is not None for part in key):
            parent_keys.add(key)
    counts: dict[tuple, int] = {}
    for row in loaded.get(table_name, []):
        key = tuple(row.get(column) for column in foreign_key.columns)
        if any(part is None for part in key):
            continue
        if key not in parent_keys:
            counts[key] = counts.get(key, 0) + 1
    findings = []
    column = foreign_key.columns[0] if len(foreign_key.columns) == 1 else ",".join(foreign_key.columns)
    for key, count in sorted(counts.items(), key=lambda item: _key_text(item[0])):
        rendered = _key_text(key)
        findings.append(
            Finding(
                code="orphan_foreign_key",
                message=(
                    f"Foreign key {foreign_key.name} on {table_name}.{column} "
                    f"value {rendered} has no parent {foreign_key.parent_table} row ({count} row(s))."
                ),
                table=table_name,
                column=column,
                constraint=foreign_key.name,
                key=rendered,
                count=count,
            )
        )
    return findings


def _key_text(key: tuple) -> str:
    return "|".join("" if part is None else str(part) for part in key)


def _cap(findings: list[Finding]) -> list[Finding]:
    if len(findings) <= _MAX_FINDINGS:
        return findings
    hidden = len(findings) - _MAX_FINDINGS
    return findings[:_MAX_FINDINGS] + [
        Finding(
            code="findings_truncated",
            message=f"{hidden} additional integrity findings were omitted from the report.",
            count=hidden,
        )
    ]
