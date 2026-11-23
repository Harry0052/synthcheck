# Grokbot progress

| Phase | Status | Next |
| --- | --- | --- |
| P01 | PASS | P02 |
| P02 | PASS | P03 |
| P03 | PASS | P04 |
| P04 | PASS | P05 |
| P05 | PASS | P06 |
| P06 | PASS | P07 |
| P07 | PASS | none |

## P01 — Research overlap and confirm the MVP

**Phase and status:** P01 PASS

**Files changed:**

- `docs/overlap.md`
- `docs/project-contract.md`
- `docs/grokbot-progress.md`

**Commands and results:**

- GitHub repository search API for the three playbook queries returned `total_count: 0`. Web search was used for discovery.
- Installed `sdmetrics==0.33.0` and `duckdb==1.4.2` under `/tmp/pydeps` (research only; not a project dependency).
- Observed `sdmetrics.reports.QualityReport` on the shared equal-marginal fixture. Overall score `0.9833333333333334`. Column Shapes `1.00`. Cardinality `0.95`, with visits→tasks `CardinalityShapeSimilarity` `0.9`. Detail tables did not name a clinic or a coverage value. Column Pair Trends raised `ValueError: Too many bins for data range`.
- Observed the published dbt `unique`, `not_null`, and `relationships` selects on DuckDB 1.4.2. Both bundles returned zero failing rows. The same connection reported north coverage `0.8` versus `0.4` (absolute delta `0.4`) and south `0.8` versus `1.0` (absolute delta `0.2`).
- dbt CLI, dbt-audit-helper, SyntheRela, and TabQueryBench were not executed. Reasons and licenses are in `docs/overlap.md`.

**Artifact paths:**

- `docs/overlap.md`
- `docs/project-contract.md`

**Open issues:**

- dbt CLI execution remains unresolved. The published test SQL was executed instead.
- SDMetrics column-pair trends are inconclusive on this one-day fixture because of a binning error.

**Next phase:** P02

**Decision:** proceed. Existing tools do not cover the acceptance case. Fixtures will be generated locally. Runtime dependencies are Python and DuckDB.

## P02 — Create the repository and data contracts

**Phase and status:** P02 PASS

**Files changed:**

- `pyproject.toml`
- `synthcheck/` package, including contract loading and bundle validation
- `fixtures/contract/clinic.json`
- `fixtures/reference/` and `fixtures/invalid/traversal/`
- `scripts/generate_fixtures.py`
- `README.md` install and validate commands

**Commands and results:**

- `python scripts/generate_fixtures.py` wrote the local bundles. Generator `synthcheck-fixture-generator` 0.1.0, seed 16.
- `python -m pip install -e ".[dev]"` installed the package with DuckDB 1.4.2 and pytest 9.2.0.
- `python -m synthcheck validate fixtures/reference --contract fixtures/contract/clinic.json` exited `0` and printed `valid: fixtures/reference`.
- `python -m synthcheck validate fixtures/invalid/traversal --contract fixtures/contract/clinic.json` exited `2` and printed `path_traversal: Bundle path leaves the bundle directory: ../patients.csv`.

**Artifact paths:**

- `fixtures/reference/`
- `fixtures/invalid/traversal/`
- `fixtures/contract/clinic.json`
- `fixtures/DATA_TERMS.md`

**Open issues:** none for this gate.

**Next phase:** P03

## P03 — Build the working core

**Phase and status:** P03 PASS

**Files changed:**

- `synthcheck/engine.py`
- `synthcheck/compare.py`
- `fixtures/changed/`, `fixtures/orphan_tasks/`, and the hand oracle
- `tests/test_acceptance.py`

**Commands and results:**

- `python -m pytest tests/test_acceptance.py` covered the proof cases. The full suite later reported `17 passed`.
- Reference versus changed: integrity pass, row counts 10/10/10 on both sides, north coverage `0.8` versus `0.4` (decision fail, tolerance 0.05), south `0.8` versus `1` (decision fail), distinct visits 5 and 5 (pass), distinct tasks 10 and 10 (pass).
- Orphan fixture: finding `orphan_foreign_key` / `tasks_visit_id_fkey` / key `V99`. Coverage state `unavailable`.

**Artifact paths:**

- `fixtures/oracle/reference_vs_changed.json`
- `fixtures/changed/`
- `fixtures/orphan_tasks/`

**Open issues:** none for this gate.

**Next phase:** P04

## P04 — Ship the user workflow and reports

**Phase and status:** P04 PASS

**Files changed:**

- `synthcheck/cli.py`
- `synthcheck/report.py`
- `docs/evidence/p04-demo.json`
- `docs/evidence/p04-demo.html`
- `README.md` demo section

**Commands and results:**

```text
python -m synthcheck compare fixtures/reference fixtures/changed \
  --contract fixtures/contract/clinic.json \
  --json reports/demo.json \
  --html reports/demo.html
```

Observed exit code `1`. Stdout names the formula, denominators `4/5` and `2/5`, values `0.8 (80.0%)` and `0.4 (40.0%)`, and the tolerance decisions. The JSON stores `"0.8"` and `"0.4"` and does not contain `80.0%`. The HTML report includes the formula, the rounded percentages, provenance, and the synthetic-data limitation.

Traversal through the same CLI exits `2` with `path_traversal` on stderr.

`python -m synthcheck --help` exits `0`.

**Artifact paths:**

- `docs/evidence/p04-demo.json`
- `docs/evidence/p04-demo.html`

**Open issues:** none for this gate. `reports/` is a local output directory and is gitignored.

**Next phase:** P05

## P05 — Verify correctness, security, and performance

**Phase and status:** P05 PASS

**Files changed:**

- `tests/test_cli_safety.py`
- `docs/validation.md`

**Commands and results:**

- `python -m pytest` observed `17 passed` in about 0.60 seconds.
- Five demo comparisons took 0.0564, 0.0523, 0.0538, 0.0533, and 0.0526 seconds. Budget is 5 seconds.
- OSV.dev returned no advisories for `duckdb` 1.4.2, `pytest` 9.2.0, or `setuptools` 84.2.1.
- Rejection and safeguard checks observed in the suite: duplicate key, orphan key, missing column, one-sided groups, zero denominator, traversal, oversized CSV, unknown operator, external instruction, hash mismatch, bound filter value, suppressed extra-column value, and disabled DuckDB external file access.

**Artifact paths:**

- `docs/validation.md`

**Open issues:**

- The timing budget is for the shipped demo only.
- Advisory results are for the access date 2026-11-23.

**Next phase:** P06

## P06 — Prepare a reproducible open-source release

**Phase and status:** P06 PASS

**Files changed:**

- `README.md`
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `fixtures/DATA_TERMS.md`
- `.github/workflows/ci.yml`
- `LICENSE` (unchanged MIT)

**Commands and results:**

- A clean copy was taken with `tar` to `/tmp/synthcheck-clean`, excluding `.git`, caches, and `reports/`.
- `PYTHONNOUSERSITE=1 python -m pip install --target /tmp/clean-deps '.[dev]'` from that copy.
- `PYTHONNOUSERSITE=1 PYTHONPATH=/tmp/clean-deps python -m pytest` observed `17 passed`.
- The README demo command from that copy exited `1`. The JSON report status was `fail`, and north coverage was `0.8` versus `0.4` with decision `fail`.
- A search of the tree for token and private-key patterns found no matches.
- GitHub Actions uses `contents: read`, pinned action SHAs, and no secrets. Hosted CI is the P07 gate.

**Artifact paths:**

- `.github/workflows/ci.yml`
- `README.md`
- `SECURITY.md`

**Open issues:** none for this gate. Hosted CI is recorded in P07.

**Next phase:** P07

## P07 — Publish and verify on GitHub

**Phase and status:** P07 PASS

**Files changed:**

- `docs/grokbot-progress.md` (this record, committed after the tag)

**Commands and results:**

- Authorized destination: `https://github.com/Harry0052/synthcheck`, public, MIT. `gh repo view` reported `visibility: PUBLIC`. The tag URL `https://raw.githubusercontent.com/Harry0052/synthcheck/v0.1.0/LICENSE` starts with `MIT License`.
- Remote `origin` is `https://github.com/Harry0052/synthcheck`. Push of `cursor/synthcheck-mvp-8f4d` succeeded. `GET /user` returned HTTP 403 for this token, so the login name was not readable. The remote and the public repository match the authorized destination.
- Pull request: https://github.com/Harry0052/synthcheck/pull/1
- Tested commit: `2fac23d2993206d5df0b986ba18430fdfbf534f9`
- Push CI: https://github.com/Harry0052/synthcheck/actions/runs/45116663002 success
- Pull request CI: https://github.com/Harry0052/synthcheck/actions/runs/45116677258 success (`test` passed)
- Annotated tag `v0.1.0` points at that commit. `git rev-parse v0.1.0^{}` is `2fac23d2993206d5df0b986ba18430fdfbf534f9`. The tag was pushed. `main` was not updated.
- Fresh clone of `v0.1.0` into `/tmp/synthcheck-tag`, install with `PYTHONNOUSERSITE=1`, and the README demo exited `1`. North coverage was `0.8` versus `0.4` (fail) and south was `0.8` versus `1` (fail). Integrity was pass.

**Artifact paths:**

- Tag `v0.1.0`
- https://github.com/Harry0052/synthcheck/pull/1
- https://github.com/Harry0052/synthcheck/actions/runs/45116677258

**Open issues:**

- This progress commit is newer than the tag. It does not change the checker. The owner merges the pull request.

**Next phase:** none. The owner merges.

**Demo command from the tag:**

```bash
git clone --branch v0.1.0 --depth 1 https://github.com/Harry0052/synthcheck
cd synthcheck
python -m pip install -e ".[dev]"
python -m synthcheck compare fixtures/reference fixtures/changed \
  --contract fixtures/contract/clinic.json \
  --json reports/demo.json \
  --html reports/demo.html
```
