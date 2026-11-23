"""Command line interface for SynthCheck."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from synthcheck import __version__
from synthcheck.bundle import load_bundle
from synthcheck.compare import compare_paths
from synthcheck.contract import load_contract
from synthcheck.errors import SynthCheckError
from synthcheck.report import dump_json, render_html, render_text


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            return _compare(args)
        if args.command == "validate":
            return _validate(args)
    except SynthCheckError as exc:
        print(f"synthcheck: {exc.category}: {exc.message}", file=sys.stderr)
        payload = {"status": "invalid_input", "category": exc.category, "message": exc.message}
        _write_optional(args.json_path, dump_json(payload))
        return exc.exit_code
    return 2


def _compare(args) -> int:
    report = compare_paths(Path(args.reference), Path(args.candidate), Path(args.contract))
    text = render_text(report)
    document = dump_json(report)
    _write_optional(args.json_path, document)
    if args.html:
        Path(args.html).write_text(render_html(report), encoding="utf-8")
    print(text, end="")
    return 1 if report["summary"]["status"] == "fail" else 0


def _validate(args) -> int:
    contract = load_contract(Path(args.contract))
    bundle = load_bundle(Path(args.bundle), contract)
    status = "fail" if bundle.findings else "pass"
    payload = {
        "report_version": "1",
        "synthcheck_version": __version__,
        "contract_version": contract.version,
        "status": status,
        "bundle": bundle.root,
        "row_counts": bundle.row_counts,
        "findings": [finding.as_dict() for finding in bundle.findings],
    }
    _write_optional(args.json_path, dump_json(payload))
    if status == "pass":
        print(f"valid: {bundle.root}")
        return 0
    print(f"integrity fail: {bundle.root}")
    for finding in bundle.findings:
        print(f"- {finding.code}: {finding.message}")
    return 1


def _write_optional(path: str | None, text: str) -> None:
    if not path:
        return
    if path == "-":
        print(text, end="")
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synthcheck",
        description=(
            "Compare two fully synthetic clinic CSV bundles against one typed query contract. "
            "Integrity findings stay separate from aggregate tolerance decisions."
        ),
    )
    parser.add_argument("--version", action="version", version=f"synthcheck {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    compare = sub.add_parser(
        "compare",
        help="Compare a reference bundle with a candidate bundle",
    )
    compare.add_argument("reference", help="Reference bundle directory")
    compare.add_argument("candidate", help="Candidate bundle directory")
    compare.add_argument("--contract", required=True, help="Path to the JSON contract")
    compare.add_argument("--json", dest="json_path", help="Write the machine-readable report to this path, or - for stdout")
    compare.add_argument("--html", help="Write an HTML report to this path")
    validate = sub.add_parser("validate", help="Validate one bundle against the contract")
    validate.add_argument("bundle", help="Bundle directory")
    validate.add_argument("--contract", required=True, help="Path to the JSON contract")
    validate.add_argument("--json", dest="json_path", help="Write the machine-readable result to this path, or - for stdout")
    return parser
