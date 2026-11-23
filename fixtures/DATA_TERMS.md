# Fixture data terms

The CSV bundles under `fixtures/` are fully synthetic. They were written by `scripts/generate_fixtures.py`.

- Generator name: `synthcheck-fixture-generator`
- Generator version: `0.1.0`
- Seed: `16`
- The seed identifies this enumerated revision. The script does not sample rows and does not download data.
- Identifiers such as `P01` and `V01` are placeholders. They do not refer to real people.
- `contains_patient_rows` is false, and each manifest sets `synthetic_only` to true, except the intentional negative fixtures under `fixtures/invalid/`.
- No patient extract, public health dataset, or hospital file was copied into this repository.

You may use, modify, and redistribute these fixtures under the MIT license in the repository root. Do not replace them with real patient data and then treat the result as a SynthCheck fixture.
