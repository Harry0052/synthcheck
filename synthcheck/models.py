"""Shared result records."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    table: str | None = None
    column: str | None = None
    constraint: str | None = None
    key: str | None = None
    count: int | None = None

    def as_dict(self) -> dict:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass
class Bundle:
    root: str
    generator: dict
    table_hashes: dict[str, str]
    provenance_sha256: str
    tables: dict[str, list[dict]]
    findings: list[Finding] = field(default_factory=list)
    tainted_tables: set[str] = field(default_factory=set)
    broken_relationships: set[str] = field(default_factory=set)

    @property
    def row_counts(self) -> dict[str, int]:
        return {name: len(rows) for name, rows in self.tables.items()}
