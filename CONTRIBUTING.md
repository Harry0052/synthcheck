# Contributing

Issues and pull requests are welcome on https://github.com/Harry0052/synthcheck.

1. Use Python 3.11 or newer.
2. Install the developer extra: `python -m pip install -e ".[dev]"`.
3. Run `python -m pytest` before opening a pull request.
4. Keep new bundled rows fully synthetic. Update `scripts/generate_fixtures.py`, regenerate with `python scripts/generate_fixtures.py`, and adjust the hand-written oracle if a declared count changes.
5. Do not add credentials, access tokens, or data extracted from a real clinical system.
6. Keep the query language an allowlist. Do not pass contract text through to DuckDB as SQL text.

The maintained branch history uses conventional commit subjects (`feat`, `fix`, `docs`, `test`, `ci`).
