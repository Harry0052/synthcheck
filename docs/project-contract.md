# Project contract

Status: accepted for implementation after the P01 overlap review (`docs/overlap.md`).

## User and task

Health-data engineers who need a fully synthetic clinic dataset for development can check that a candidate bundle still preserves a reference bundle's declared joins and aggregate queries.

The user runs one contract over two local CSV bundles. SynthCheck reports integrity failures separately from query results, then reports each declared aggregate by group: formula, denominator, reference value, candidate value, absolute delta, and the tolerance decision.

## Product boundaries

In scope:

- Bundles the user generated, with an explicit fully synthetic declaration.
- Three tables for the clinic example: patient surrogates, visits, and follow-up tasks. Identifiers are fictional.
- Typed columns, non-null rules, primary keys, and foreign keys.
- A small query language that compiles to parameterized read-only SQL: distinct counts, month buckets, equality filters, exists-joins along declared foreign keys, and ratios.
- Full-outer comparison of groups, including groups that exist on only one side.
- A ratio with a zero denominator serialized as unavailable. Percentages are rounded only in text and HTML.
- Rejection of path traversal, oversized CSV files, unknown operators, and external-reference instructions.

Out of scope:

- Real patient data, extracts, and any bundle that is not declared fully synthetic.
- Record similarity, anonymization, linkage, membership inference, and leakage detection.
- Advice about clinical care.
- Arbitrary SQL, extension loading, and reads outside the bundle directory.

CohortShift, which asks whether a study sample represents a target population, is a different product and is not part of this contract.

## Minimum dependencies

- Python 3.12 is the tested runtime. The package requires Python 3.11 or newer.
- DuckDB, pinned, MIT licensed, used as an in-process read-only engine. No network connection and no extension install at run time.
- pytest, pinned, for the test extra. The demo itself does not need pytest.

No paid service, account, or remote dataset is required. SDMetrics, dbt, SyntheRela, and TabQueryBench are comparison points only.

## Measurable acceptance case

Fixture: `fixtures/reference` versus `fixtures/changed`, contract `fixtures/contract/clinic.json`, seed recorded in each manifest.

Hand-checked expectations:

- Each bundle has 10 patient rows, 10 visit rows, and 10 task rows.
- Distinct visits by clinic are 5 and 5 on both sides. Absolute tolerance is 0, so those groups pass.
- Visit-to-follow-up coverage for `north` in `2024-01` is 4/5 (0.8) in the reference and 2/5 (0.4) in the candidate. Absolute tolerance is 0.05, so the group fails.
- Coverage for `south` in `2024-01` is 4/5 (0.8) versus 5/5 (1.0) and also fails that tolerance.
- Distinct assigned tasks are 10 and 10 and pass.
- Both bundles pass integrity. The run fails because of the tolerance breaches.

The same contract must also flag, in separate fixtures, a duplicate visit primary key, an orphan task foreign key, and a missing referenced column. The orphan case reports that named foreign-key violation and marks the coverage query unavailable instead of treating it as a numeric miss.

## Non-goals for the first release

SynthCheck does not synthesize data. It only checks bundles the generator in this repository, or the user, has already written. It does not rank generative models or emit a single fidelity score.
