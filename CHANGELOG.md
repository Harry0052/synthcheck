# Changelog

## 0.1.0

First working release.

- Load two local CSV bundles that declare themselves fully synthetic, and check SHA-256 manifests, types, primary keys, and foreign keys.
- Compare distinct visit counts, visit-to-follow-up coverage by month, and distinct assigned task counts with group-level tolerances.
- Write a JSON report and an HTML report. Percentages are rounded only in the text and HTML.
- Reject path traversal, oversized input, unknown query operators, and external-reference instructions.
