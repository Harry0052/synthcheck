# Validation

Access date: 2026-11-23. Scope: the fully synthetic fixtures in this repository. No external clinical dataset was used.

## Environment

- Host: Linux 6.12.113+ x86_64, glibc 2.39 (`Linux-6.12.113+-x86_64-with-glibc2.39`)
- Python: 3.12.3
- DuckDB: 1.4.2
- pytest: 9.2.0
- setuptools: 84.2.1 (build backend only)

OSV.dev queries for those three versions, ecosystem PyPI, returned no vulnerability entries on the access date.

## Fixture

`fixtures/` is 24,161 bytes. The CSV files together are 4,560 bytes. The demo bundles each have 10 patient rows, 10 visit rows, and 10 task rows. Generator `synthcheck-fixture-generator` 0.1.0, seed 16. Counts below were calculated from the enumerated rows and checked against `fixtures/oracle/reference_vs_changed.json`.

## Commands and observed results

Install and tests:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Observed: `17 passed`.

Valid bundle:

```bash
python -m synthcheck validate fixtures/reference --contract fixtures/contract/clinic.json
```

Observed: exit `0`, stdout `valid: fixtures/reference`.

Traversal:

```bash
python -m synthcheck validate fixtures/invalid/traversal --contract fixtures/contract/clinic.json
```

Observed: exit `2`, stderr `path_traversal: Bundle path leaves the bundle directory: ../patients.csv`.

Demo:

```bash
python -m synthcheck compare fixtures/reference fixtures/changed \
  --contract fixtures/contract/clinic.json \
  --json reports/demo.json \
  --html reports/demo.html
```

Observed: exit `1`.

| Check | Expected | Observed |
| --- | --- | --- |
| Integrity | pass | pass |
| Row counts | 10, 10, 10 on both sides | 10, 10, 10 on both sides |
| North distinct visits | 5 vs 5, pass | 5 vs 5, pass |
| South distinct visits | 5 vs 5, pass | 5 vs 5, pass |
| North coverage, 2024-01 | 4/5 = 0.8 vs 2/5 = 0.4, absolute delta 0.4, fail | same, decision fail |
| South coverage, 2024-01 | 4/5 = 0.8 vs 5/5 = 1, absolute delta 0.2, fail | same, decision fail |
| Distinct tasks | 10 vs 10, pass | 10 vs 10, pass |
| JSON percentage text | absent | `80.0%` is absent from the JSON |
| HTML percentage | rounded in the report | `80.0%` and `40.0%` present |

Other acceptance cases are asserted in `tests/test_acceptance.py` and `tests/test_cli_safety.py`:

- An extra follow-up task on visit `V01` leaves coverage at 0.8 and changes the task count from 10 to 11.
- Duplicate primary key `visits.visit_id` `V01` is reported on its own. Visit queries become unavailable. The task-count query still runs.
- Orphan foreign key `tasks_visit_id_fkey` value `V99` is reported, and coverage is unavailable rather than a numeric miss.
- A tasks file without `kind` is `missing_column`, separate from the key findings.
- Clinics `west` and `east` appear when they exist on only one side, with decision `fail`.
- February coverage has denominator 0 and state `unavailable`. The JSON value is null. The run status is `unavailable`, not a tolerance failure.
- Unknown operator, `INSTALL httpfs`, an `https://` manifest path, a non-synthetic declaration, a hash mismatch, and a file over `max_csv_bytes` exit `2` with a named category.
- A filter value `follow_up' OR '1'='1` matches 0 tasks. It is bound as a parameter.
- An extra CSV column value `RAWROWSECRET` does not appear in the JSON or HTML report.
- `read_csv_auto('/etc/passwd')` on the engine connection is rejected because external access is disabled.
- `2024-02-01T04:30:00Z` normalized in `America/New_York` is `2024-01-31T23:30:00`.

## Performance budget

The supported demo is the comparison above. Five successive in-process runs took 0.0564, 0.0523, 0.0538, 0.0533, and 0.0526 seconds. The budget is 5 seconds, which leaves room for a cold process and a small CI runner while still failing a hang or an accidental full-table dump. The budget applies to this fixture, not to a 100,000-row bundle. The contract refuses inputs above its `max_csv_bytes` and `max_rows`, and the code additionally refuses limits above 5,000,000 bytes or 100,000 rows.

## Domain safeguard

Marginal counts on the demo bundles match. The coverage query still fails because its grain is clinic and month, the denominator is distinct visits, and the numerator is distinct visits that have a follow-up task. Invalid keys do not become a fake ratio: a duplicate visit key or a missing column taints the tables that query reads, and an orphan on a foreign key the query uses marks that query unavailable. SQL text from the contract is not executed. Only allowlisted operators are compiled, and values are parameters.

## Residual limitations

- The performance number is a local measurement on the synthetic demo, not a certified throughput.
- OSV showed no published advisories for the pinned versions on the access date. That is not a permanent guarantee.
- The dbt CLI was not used as a product dependency. P01 executed the published built-in test SQL on DuckDB and recorded that those tests do not emit this tolerance decision.
- SynthCheck will not detect a privacy failure, a linkage, or a clinically wrong code. The report states that limit next to the findings.
