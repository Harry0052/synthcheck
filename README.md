# SynthCheck

SynthCheck compares two fully synthetic clinic CSV bundles against one typed contract. It checks keys and foreign keys before it runs a small set of aggregate queries, then reports group-level drift against an explicit tolerance.

The bundled demo keeps patient, visit, and task row counts equal while moving follow-up tasks. Distinct visits by clinic stay the same. Visit-to-follow-up coverage for the `north` clinic in `2024-01` changes from 4/5 (0.8) to 2/5 (0.4) and fails a five-percentage-point tolerance.

SynthCheck does not accept real patient rows, and it does not give clinical advice. There is no separate hardware or model demo.

## Requirements

- Python 3.11 or newer. The commands below were run on Python 3.12.3.
- No database server, account, or network access at run time.

Runtime dependency: [DuckDB](https://duckdb.org) 1.4.2 (MIT). Tests use pytest 9.2.0 (MIT). The package build uses setuptools 84.2.1 (MIT).

## Install

From a checkout of this repository:

```bash
python -m pip install -e ".[dev]"
```

Omit `.[dev]` if you only want to run the demo and do not need pytest.

## Demo

```bash
python -m synthcheck compare fixtures/reference fixtures/changed \
  --contract fixtures/contract/clinic.json \
  --json reports/demo.json \
  --html reports/demo.html
```

Expected result:

- Exit code `1`. The candidate breaches the contract. Exit code `0` would mean every declared group was inside tolerance and both bundles passed integrity.
- `reports/demo.json` is the machine-readable report. Proportions are exact strings such as `"0.8"`. Percentages are not stored there.
- `reports/demo.html` is the human report. Coverage is shown as `0.8 (80.0%)` and `0.4 (40.0%)`, with denominators `4/5` and `2/5`.
- Integrity is `pass` for both bundles. `distinct_visits_by_clinic` passes at 5 and 5. `distinct_assigned_tasks` passes at 10 and 10. `visit_follow_up_coverage_by_month` fails for `north` (absolute delta `0.4`) and `south` (absolute delta `0.2`). The tolerance is absolute `0.05`.
- A saved copy of this run is in `docs/evidence/p04-demo.json` and `docs/evidence/p04-demo.html`.

`python -m synthcheck --help` lists the commands. Diagnostics go to stderr. The JSON file is the stable machine output.

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | Integrity passed, and no group breached its tolerance. A ratio with a zero denominator is `unavailable`, which is not a breach. |
| 1 | Integrity finding or tolerance breach. |
| 2 | The input cannot be evaluated: bad path, traversal, oversized file, hash mismatch, unknown operator, external reference, or a bundle that is not declared fully synthetic. |

Check one bundle:

```bash
python -m synthcheck validate fixtures/reference --contract fixtures/contract/clinic.json
python -m synthcheck validate fixtures/invalid/traversal --contract fixtures/contract/clinic.json
```

The first command exits `0`. The second exits `2` and names `path_traversal`.

## Tests

```bash
python -m pytest
```

The hand-counted oracle for the demo is `fixtures/oracle/reference_vs_changed.json`.

## Fixture data

Every bundled row is fictional and was written by `scripts/generate_fixtures.py` (generator `synthcheck-fixture-generator` 0.1.0, seed `16`). The rows are enumerated in that script. The seed names the revision; it is not a draw from a patient extract. Terms are in `fixtures/DATA_TERMS.md`. Regenerate with:

```bash
python scripts/generate_fixtures.py
```

## Contract

`fixtures/contract/clinic.json` is version `1`. It declares column types, primary keys, foreign keys, and three queries:

- distinct visits grouped by clinic
- visit-to-follow-up coverage by clinic and month
- distinct assigned tasks

The query language allows `count_distinct`, `ratio`, `month`, `eq`, `month_eq`, and `exists` along a declared foreign key. Other operators are rejected. Timestamps are interpreted in the contract timezone (`UTC` in the demo) before the month bucket is taken.

## License

This repository is [MIT](LICENSE), copyright 2026 Harry Malhi. DuckDB, pytest, and setuptools are third-party MIT packages and are not vendored.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). The version history is [CHANGELOG.md](CHANGELOG.md).
