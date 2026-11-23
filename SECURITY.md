# Security policy

## Reporting

Report a vulnerability in this repository through GitHub private vulnerability reporting on `Harry0052/synthcheck`:

https://github.com/Harry0052/synthcheck/security/advisories/new

Please do not attach real patient data, credentials, or a proof that includes secrets.

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | yes |

## What SynthCheck limits

The checker reads only files inside the bundle directory you pass. It rejects `..`, absolute paths, URL-shaped paths, and instructions such as `INSTALL httpfs` or `read_csv`. CSV size and row count are bounded by the contract, with hard caps of 5,000,000 bytes and 100,000 rows. Queries are compiled from an allowlist to parameterized SQL. The DuckDB connection disables external file access. Reports name keys and finding codes. They do not dump raw table rows.

## Out of scope

SynthCheck is not an anonymization tool. A passing report does not mean a dataset is safe to share, and the project does not accept real patient rows for testing.
