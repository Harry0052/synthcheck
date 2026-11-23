# Overlap review

Access date: 2026-11-23.

Decision: **proceed** with a separate SynthCheck repository.

SynthCheck is a local check that two fully synthetic clinic bundles still satisfy one declared contract: typed keys and a small set of aggregate queries, including join-derived coverage with an explicit tolerance. The closest public tools measure statistical fidelity, warehouse assertions, or research benchmarks. None of them, on the shared fixture below, reports the clinic-specific coverage change with its formula, denominator, and five-percentage-point decision.

Searches used the playbook queries plus the named projects. The GitHub repository search API returned no hits for the three literal queries (`synthetic relational data query workload utility benchmark`, `synthetic EHR multi table integrity query utility`, `dbt compare aggregate outputs synthetic datasets`). Web search and primary docs identified the projects in the matrix. Redbench and RelBench appeared in those results and were set aside: Redbench synthesizes database workloads, and RelBench ranks relational machine-learning tasks. Neither checks a user-supplied synthetic bundle against a declared aggregate contract.

## Shared fixture and acceptance metric

The same fully synthetic input was used for every observed probe. No patient rows were downloaded. Placeholders are `P1`–`P10`, clinics `north` and `south`, visits `V1`–`V10`, and tasks of kind `follow_up`.

Both bundles have 10 patients, 10 visits, and 10 tasks. Visits are identical: five in each clinic, all on 2024-01-15. Task rows were moved so visit-level child counts change while table row counts stay equal.

| Clinic | Reference covered visits | Candidate covered visits | Reference coverage | Candidate coverage | Absolute delta | Breaches 0.05 |
| --- | --- | --- | --- | --- | --- | --- |
| north | 4 / 5 | 2 / 5 | 0.8 | 0.4 | 0.4 | yes |
| south | 4 / 5 | 5 / 5 | 0.8 | 1.0 | 0.2 | yes |

Reference child counts by visit: `2,1,1,1,0` in each clinic. Candidate counts: north `2,1,0,0,0` and south `2,2,1,1,1`. Hand count and a DuckDB 1.4.2 query agreed.

Acceptance metric held constant: exact group counts, and a failing decision where absolute coverage drift is greater than 0.05. Column-level sameness is not success.

## Capability matrix

| Capability | SDMetrics Quality Report 0.33.0 | dbt data tests (dbt-core 1.12.7) | SyntheRela 0.0.4 / repo `v0.2.0` | TabQueryBench | SynthCheck MVP |
| --- | --- | --- | --- | --- | --- |
| Two local CSV bundles, no warehouse | yes | no, needs a dbt project and adapter | yes, as a benchmark dataset | no, benchmark pipeline | yes |
| Declared primary and foreign keys | metadata only | `unique`, `not_null`, `relationships` | dataset metadata | not the product | yes, before queries |
| Declared aggregate query with formula and denominator | no | only if someone writes a singular SQL test | no | generated single-table SQL templates | yes |
| Tolerance per group, full outer groups | no | no | no | score agreement, not a user tolerance | yes |
| Zero denominator as unavailable | no | not in built-in tests | no | not claimed | yes |
| Synthetic-only input gate | no | no | no; paper uses real databases | no; real public tables | yes |
| Clinic coverage 0.8 vs 0.4 called out | not observed | not observed | not run; metric is not the product | joins are out of scope | target of the MVP |

## Probes

### SDMetrics Quality Report

- Primary docs: https://docs.sdv.dev/sdmetrics/data-metrics/quality/quality-report-api
- Source: https://github.com/sdv-dev/SDMetrics
- Package: `sdmetrics` 0.33.0 on PyPI, MIT. Requires Python `>=3.10,<3.15`.
- Source HEAD observed on the access date: `11fe47ab1455a7953d2cd8110ef20a775fb48dec` (2026-11-20). The executed artifact is the PyPI release, which may differ from that later commit.
- Dataset terms: none. The library compares caller-supplied tables. It does not ship a clinic dataset.
- Evidence: **observed run** of `sdmetrics.reports.QualityReport` 0.33.0.

Command shape: `QualityReport.generate(reference, candidate, metadata)` with patients, visits, and tasks, primary keys, and the two foreign keys. `verbose=False`.

| Property | Score | What the detail table contained |
| --- | --- | --- |
| Column Shapes | 1.00 | `clinic_id`, `visited_on`, and `kind` each scored 1.0 |
| Column Pair Trends | NaN | `ContingencySimilarity` on `visits.clinic_id` × `visited_on` raised `ValueError: Too many bins for data range` |
| Cardinality | 0.95 | patients→visits `CardinalityShapeSimilarity` 1.0; visits→tasks 0.9 |
| Intertable Trends | 1.00 | patients clinic×clinic scored 1.0; visits clinic×task kind did not meet the trend threshold and scored NaN |
| Overall | 0.9833333333333334 | no clinic key, no coverage, no tolerance |

Column shapes are identical, so the default distribution summary misses the coverage change. Cardinality falls to 0.9 for the visit–task relationship, which shows that some global child-count shape changed. That row has no clinic, no 4/5 versus 2/5, and no five-percentage-point rule. The serialized property and detail tables do not name `north`, `south`, or coverage. A 0.98 overall score would read as high fidelity.

Configurable properties are the four built-in properties above. The documented report does not take a user query contract. Higher-order combinations of three or more columns are explicitly outside the report (docs, same page).

### dbt data tests

- Primary docs: https://docs.getdbt.com/docs/build/data-tests and https://docs.getdbt.com/reference/resource-properties/data-tests
- Package: `dbt-core` 1.12.7 on PyPI, Apache-2.0. Requires Python `>=3.10`.
- Source repository observed: https://github.com/dbt-labs/dbt at `ef3cbabc4e408a64b99de83278be4ae5543b4d4f` (2026-11-21). License text retrieved from `dbt-labs/dbt-core` is Apache-2.0, copyright 2026 dbt Labs, Inc.
- Related comparison macros: https://github.com/dbt-labs/dbt-audit-helper at `71817f0a7fa3df9f63adb90db0cf28f7423f720b` (2026-05-19), Apache-2.0. `compare_queries` summarizes row overlap (`in_a`, `in_b`, `count`). It does not evaluate a metric formula against a tolerance.
- Dataset terms: none. dbt tests the relations in the user's warehouse.
- Evidence: **documentation** for the CLI and macros, plus an **observed run** of the published built-in test queries on DuckDB 1.4.2. The dbt CLI and `dbt-audit-helper` were not installed. That CLI check is unresolved.

Built-in tests are `unique`, `not_null`, `accepted_values`, and `relationships`. A test passes when its select returns zero rows. On both bundles the following returned zero rows:

- `visit_id` grouped with `having count(*) > 1`
- `visit_id is null`
- `tasks.visit_id` not in `visits.visit_id`

So the integrity tests pass, correctly, and still do not report the 0.8 versus 0.4 coverage delta. A singular test or a generic test can contain any select, so dbt can be made to compute this delta inside a warehouse project. That is a new SQL test per project, not one versioned contract that loads two CSV bundles, rejects a non-synthetic declaration, and emits group-level tolerance decisions. Setup adds an adapter, profiles, and a project. The playbook's acceptance case is not met by the built-in contract.

### SyntheRela

- Primary: https://github.com/martinjurkovic/syntherela and the paper https://arxiv.org/abs/2410.03411
- Package: `syntherela` 0.0.4 on PyPI, MIT classifier. Repository HEAD `4db94dfcf1b3c3f6bac692ec90a6633dd80b72a1` is labeled `v0.2.0` (2026-03-01), ahead of the PyPI release. GitHub license is MIT.
- Dataset terms: the benchmark and paper use real relational databases (AirBnB, Rossmann, Walmart, and others). Those terms do not allow vendoring the rows into this repository.
- Evidence: **documentation**. Not run. The install pulls SDV, pinned scientific stacks, and optional GPU libraries. Utility in the paper is predictive performance and feature rank correlation, plus statistical metrics such as cardinality shape and aggregation detection. Users can add metrics, but the shipped product does not check a declared clinic query at a five-percentage-point tolerance, and it does not separate orphan-key failures from unavailable ratios.

### TabQueryBench

- Primary code: https://github.com/TabQueryBench/TabQueryBench at `30d2c06dff175ba50c630e7ac58ce1b907292fe7` (2026-09-26).
- Paper: https://arxiv.org/html/2607.03926v2
- License: no `LICENSE` file in the repository root. The Hugging Face dataset `TabQueryBench2026/TabQueryBench` had no declared license in a 2026-11-05 license check (https://datalicense.uk/d/TabQueryBench2026/TabQueryBench/).
- Dataset terms: large generated artifacts and public source tables live on Hugging Face. Not a viable provenance path for this repo.
- Evidence: **documentation**. Not run. The paper's scope section says relational joins are outside the current evaluation, which is single-table analytical templates. It cannot represent visit-to-task coverage.

## What already matches

- SDMetrics already scores multi-table cardinality and column distributions, and it is the right library when the question is statistical fidelity. It is not a query contract.
- dbt already asserts uniqueness, nullability, and relationships, and it can host a custom select. It is not a two-bundle synthetic CSV runner.
- SyntheRela and TabQueryBench already argue, from research benchmarks, that statistical similarity and query answers can diverge. Their datasets and scopes do not implement this MVP.

## Recommendation

Do not implement the MVP by extending SDMetrics or by asking users to adopt a dbt project. A contribution there would still leave the CSV bundle, the synthetic-only gate, unavailable ratios, and the group tolerance report undone. Keep DuckDB as a read-only execution engine inside SynthCheck. Do not depend on SDMetrics, dbt, SyntheRela, or TabQueryBench at runtime.

## Remaining uncertainties

- dbt CLI behavior was not executed in this session. The conclusion uses the published test SQL, which was executed, and the current docs.
- `dbt-audit-helper` was read from its README and not executed. Row-diff output would likely show that individual task rows changed. That is a different artifact from coverage with a denominator and a tolerance.
- SyntheRela was not executed. A custom metric could be written against its API. That would still be a benchmark harness over datasets we cannot redistribute.
- TabQueryBench was not executed. License and the stated exclusion of joins are enough to hold it out.
- SDMetrics column-pair trends aborted with a binning error on a single calendar day. That property is inconclusive on this fixture. It is not evidence that the report found the clinic coverage change.

## Provenance path for the MVP

Generate every bundled row locally from an original schema. Record the generator name, version, and seed in each bundle manifest. Ship no patient extract. Runtime dependencies intended for the build are Python and DuckDB. DuckDB is MIT licensed (https://github.com/duckdb/duckdb). Tests use pytest, which is MIT licensed. SDMetrics was used only for this research probe and is not a project dependency.
