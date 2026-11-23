"""Compare two bundles and build the machine-readable report."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from synthcheck import __version__
from synthcheck.bundle import load_bundle
from synthcheck.contract import Query, load_contract
from synthcheck.engine import connect, evaluate_side
from synthcheck.models import Bundle

_LIMITATIONS = (
    "SynthCheck compares declared aggregates on fully synthetic bundles. "
    "It does not measure privacy, linkage, record similarity, or clinical correctness. "
    "A passing group means the declared tolerance held for that query."
)


def compare_paths(reference: Path, candidate: Path, contract_path: Path) -> dict:
    contract = load_contract(contract_path)
    reference_bundle = load_bundle(reference, contract)
    candidate_bundle = load_bundle(candidate, contract)
    connection = connect()
    try:
        queries = [
            _evaluate(connection, contract, reference_bundle, candidate_bundle, query)
            for query in contract.queries
        ]
    finally:
        connection.close()
    return _report(contract, reference_bundle, candidate_bundle, queries)


def _evaluate(connection, contract, reference: Bundle, candidate: Bundle, query: Query) -> dict:
    reference_side = evaluate_side(connection, contract, reference, query)
    candidate_side = evaluate_side(connection, contract, candidate, query)
    body = _query_header(query)
    if reference_side.state != "ok" or candidate_side.state != "ok":
        reasons = [f"reference: {reason}" for reason in reference_side.reasons]
        reasons.extend(f"candidate: {reason}" for reason in candidate_side.reasons)
        body.update({"state": "unavailable", "reasons": reasons, "groups": []})
        return body
    body.update(
        {
            "state": "ok",
            "reasons": [],
            "groups": _merge(query, reference_side.groups, candidate_side.groups),
        }
    )
    return body


def _query_header(query: Query) -> dict:
    grain = []
    for part in query.grain:
        if part.get("op") == "month":
            grain.append(part["alias"])
        else:
            grain.append(part["column"].split(".", 1)[1])
    return {
        "id": query.id,
        "formula": query.formula,
        "unit": query.unit,
        "grain": grain,
        "tolerance": {"kind": query.tolerance.kind, "value": query.tolerance.value},
    }


def _merge(query: Query, reference_groups: list[dict], candidate_groups: list[dict]) -> list[dict]:
    names = _query_header(query)["grain"]

    def identity(group: dict) -> tuple:
        return tuple(group["key"].get(name) for name in names)

    reference_map = {identity(group): group for group in reference_groups}
    candidate_map = {identity(group): group for group in candidate_groups}
    merged = []
    for key in sorted(set(reference_map) | set(candidate_map), key=lambda item: tuple("" if part is None else str(part) for part in item)):
        reference = reference_map.get(key)
        candidate = candidate_map.get(key)
        key_dict = {}
        for index, name in enumerate(names):
            key_dict[name] = key[index]
        merged.append(_group(query, key_dict, reference, candidate))
    return merged


def _group(query: Query, key: dict, reference: dict | None, candidate: dict | None) -> dict:
    reference_body = _side(reference)
    candidate_body = _side(candidate)
    absolute_delta = None
    relative_delta = None
    if reference_body["state"] == "ok" and candidate_body["state"] == "ok":
        reference_value = Decimal(reference_body["value"])
        candidate_value = Decimal(candidate_body["value"])
        absolute_delta = format(abs(candidate_value - reference_value), "f")
        if reference_value != 0:
            relative_delta = format(abs(candidate_value - reference_value) / abs(reference_value), "f")
        limit = Decimal(query.tolerance.value)
        if query.tolerance.kind == "absolute":
            decision = "fail" if Decimal(absolute_delta) > limit else "pass"
        else:
            decision = "fail" if relative_delta is None or Decimal(relative_delta) > limit else "pass"
    elif reference_body["state"] == "missing" or candidate_body["state"] == "missing":
        decision = "fail"
    else:
        decision = "unavailable"
    return {
        "key": key,
        "reference": reference_body,
        "candidate": candidate_body,
        "absolute_delta": absolute_delta,
        "relative_delta": relative_delta,
        "decision": decision,
    }


def _side(group: dict | None) -> dict:
    if group is None:
        return {"state": "missing", "value": None, "numerator": None, "denominator": None}
    return {
        "state": group["state"],
        "value": group["value"],
        "numerator": group["numerator"],
        "denominator": group["denominator"],
    }


def _report(contract, reference: Bundle, candidate: Bundle, queries: list[dict]) -> dict:
    group_fail = any(group["decision"] == "fail" for query in queries for group in query["groups"])
    unavailable = any(query["state"] == "unavailable" for query in queries) or any(
        group["decision"] == "unavailable" for query in queries for group in query["groups"]
    )
    integrity_fail = bool(reference.findings or candidate.findings)
    if integrity_fail or group_fail:
        status = "fail"
    elif unavailable:
        status = "unavailable"
    else:
        status = "pass"
    if group_fail:
        query_summary = "fail"
    elif unavailable:
        query_summary = "unavailable"
    else:
        query_summary = "pass"
    return {
        "report_version": "1",
        "synthcheck_version": __version__,
        "contract_version": contract.version,
        "contract_path": contract.path,
        "timezone": contract.timezone,
        "limitations": _LIMITATIONS,
        "reference": _bundle_summary(reference),
        "candidate": _bundle_summary(candidate),
        "integrity": {
            "reference": [finding.as_dict() for finding in reference.findings],
            "candidate": [finding.as_dict() for finding in candidate.findings],
        },
        "queries": queries,
        "summary": {
            "integrity": "fail" if integrity_fail else "pass",
            "queries": query_summary,
            "status": status,
        },
    }


def _bundle_summary(bundle: Bundle) -> dict:
    return {
        "path": bundle.root,
        "generator": bundle.generator,
        "row_counts": bundle.row_counts,
        "table_sha256": bundle.table_hashes,
        "provenance_sha256": bundle.provenance_sha256,
    }
