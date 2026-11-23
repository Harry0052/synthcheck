"""Human text and static HTML renderings. Percent rounding happens only here."""

from __future__ import annotations

import html
import json
from decimal import Decimal, ROUND_HALF_UP


def dump_json(report: dict) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def render_text(report: dict) -> str:
    lines = [
        f"SynthCheck {report['synthcheck_version']} contract {report['contract_version']}",
        f"Status: {report['summary']['status']}",
        f"Integrity: {report['summary']['integrity']}",
        report["limitations"],
        "",
    ]
    for side in ("reference", "candidate"):
        findings = report["integrity"][side]
        if not findings:
            lines.append(f"Integrity {side}: no findings")
            continue
        lines.append(f"Integrity {side}:")
        for finding in findings:
            lines.append(f"  - {finding['code']}: {finding['message']}")
    lines.append("")
    for query in report["queries"]:
        tolerance = query["tolerance"]
        lines.append(
            f"{query['id']}: {query['state']} [{query['formula']}] "
            f"tolerance {tolerance['kind']} {tolerance['value']} {query['unit']}"
        )
        for reason in query.get("reasons", []):
            lines.append(f"  unavailable: {reason}")
        for group in query["groups"]:
            lines.append("  " + _group_line(group, query["unit"]))
    return "\n".join(lines) + "\n"


def render_html(report: dict) -> str:
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>SynthCheck report</title>",
        "<style>",
        "body { font-family: sans-serif; margin: 2rem; line-height: 1.4; }",
        "table { border-collapse: collapse; margin: 1rem 0; }",
        "th, td { border: 1px solid #ccc; padding: 0.3rem 0.6rem; text-align: left; }",
        "</style>",
        "</head>",
        "<body>",
        "<h1>SynthCheck report</h1>",
        f"<p>Status: <strong>{_esc(report['summary']['status'])}</strong>. "
        f"Contract version {_esc(report['contract_version'])}. "
        f"Timezone {_esc(report['timezone'])}.</p>",
        f"<p>{_esc(report['limitations'])}</p>",
        "<h2>Provenance</h2>",
        "<ul>",
    ]
    for side in ("reference", "candidate"):
        bundle = report[side]
        generator = bundle["generator"]
        parts.append(
            "<li>"
            f"{_esc(side)} seed {_esc(generator['seed'])}, "
            f"generator {_esc(generator['name'])} {_esc(generator['version'])}, "
            f"rows {_esc(bundle['row_counts'])}"
            "</li>"
        )
    parts.append("</ul>")
    parts.append("<h2>Integrity</h2>")
    parts.append("<table><thead><tr><th>Side</th><th>Code</th><th>Finding</th></tr></thead><tbody>")
    empty = True
    for side in ("reference", "candidate"):
        for finding in report["integrity"][side]:
            empty = False
            parts.append(
                "<tr>"
                f"<td>{_esc(side)}</td>"
                f"<td>{_esc(finding['code'])}</td>"
                f"<td>{_esc(finding['message'])}</td>"
                "</tr>"
            )
    if empty:
        parts.append('<tr><td colspan="3">No integrity findings.</td></tr>')
    parts.append("</tbody></table>")
    for query in report["queries"]:
        parts.append(f"<h2>{_esc(query['id'])}</h2>")
        parts.append(
            f"<p>Formula: {_esc(query['formula'])}. Unit: {_esc(query['unit'])}. "
            f"Tolerance: {_esc(query['tolerance']['kind'])} {_esc(query['tolerance']['value'])}. "
            f"State: {_esc(query['state'])}.</p>"
        )
        if query.get("reasons"):
            parts.append("<ul>")
            for reason in query["reasons"]:
                parts.append(f"<li>{_esc(reason)}</li>")
            parts.append("</ul>")
        parts.append(
            "<table><thead><tr><th>Group</th><th>Reference</th><th>Candidate</th>"
            "<th>Denominator</th><th>Absolute delta</th><th>Decision</th></tr></thead><tbody>"
        )
        if not query["groups"]:
            parts.append('<tr><td colspan="6">No groups.</td></tr>')
        for group in query["groups"]:
            parts.append(
                "<tr>"
                f"<td>{_esc(_key_text(group['key']))}</td>"
                f"<td>{_esc(_presented(group['reference'], query['unit']))}</td>"
                f"<td>{_esc(_presented(group['candidate'], query['unit']))}</td>"
                f"<td>{_esc(_denominator(group))}</td>"
                f"<td>{_esc(group['absolute_delta'])}</td>"
                f"<td>{_esc(group['decision'])}</td>"
                "</tr>"
            )
        parts.append("</tbody></table>")
    parts.append("</body></html>\n")
    return "\n".join(parts)


def format_percent(value: str) -> str:
    """Round a proportion to a percentage for display. The stored value stays exact."""
    percent = (Decimal(value) * Decimal(100)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{percent}%"


def _presented(side: dict, unit: str) -> str:
    if side["state"] != "ok":
        return side["state"]
    if unit == "proportion":
        return f"{side['value']} ({format_percent(side['value'])})"
    return str(side["value"])


def _denominator(group: dict) -> str:
    parts = []
    for label, side in (("reference", group["reference"]), ("candidate", group["candidate"])):
        if side["denominator"] is None:
            continue
        numerator = side["numerator"]
        parts.append(f"{label} {numerator}/{side['denominator']}")
    return ", ".join(parts) if parts else ""


def _key_text(key: dict) -> str:
    if not key:
        return "(all)"
    return ", ".join(f"{name}={value}" for name, value in key.items())


def _group_line(group: dict, unit: str) -> str:
    return (
        f"{_key_text(group['key'])}: "
        f"reference {_presented(group['reference'], unit)}, "
        f"candidate {_presented(group['candidate'], unit)}, "
        f"denominator {_denominator(group) or 'n/a'}, "
        f"absolute delta {group['absolute_delta']}, "
        f"relative delta {group['relative_delta']}, "
        f"tolerance decision {group['decision']}"
    )


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))
