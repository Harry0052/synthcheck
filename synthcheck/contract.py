"""Load the versioned JSON contract and reject anything outside the query language."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from decimal import Decimal

from synthcheck.errors import InvalidInput

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
COLUMN_TYPES = {"string", "integer", "number", "boolean", "timestamp"}
ABSOLUTE_MAX_CSV_BYTES = 5_000_000
ABSOLUTE_MAX_ROWS = 100_000
_EXTERNAL = re.compile(
    r"(?i)(://|\bread_csv\b|\bread_parquet\b|\bread_json\b|\bhttpfs\b|"
    r"\bparquet_scan\b|\binstall\s|\battach\s|\bpragma\b|\bcopy\s)"
)


@dataclass(frozen=True)
class Column:
    name: str
    type_name: str
    nullable: bool


@dataclass(frozen=True)
class ForeignKey:
    name: str
    columns: tuple[str, ...]
    parent_table: str
    parent_columns: tuple[str, ...]


@dataclass(frozen=True)
class Table:
    name: str
    columns: dict[str, Column]
    primary_key: tuple[str, ...]
    foreign_keys: tuple[ForeignKey, ...]


@dataclass(frozen=True)
class Tolerance:
    kind: str
    value: str


@dataclass(frozen=True)
class Query:
    id: str
    formula: str
    unit: str
    grain: tuple[dict, ...]
    measure: dict
    tolerance: Tolerance


@dataclass(frozen=True)
class Contract:
    version: str
    timezone: str
    max_csv_bytes: int
    max_rows: int
    tables: dict[str, Table]
    queries: tuple[Query, ...]
    path: str
    foreign_keys: dict[str, ForeignKey] = field(default_factory=dict)


def load_contract(path: Path) -> Contract:
    """Read one contract file. Raises InvalidInput with a stable category."""
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InvalidInput("invalid_path", f"Cannot read contract {path}: {exc.strerror}") from exc
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise InvalidInput("malformed_contract", f"Contract is not JSON: {exc.msg} at line {exc.lineno}") from exc
    if not isinstance(payload, dict):
        raise InvalidInput("malformed_contract", "Contract must be a JSON object")
    _reject_external(payload, "contract")
    return _parse_contract(payload, str(path))


def _reject_external(value, where: str) -> None:
    if isinstance(value, str):
        if _EXTERNAL.search(value):
            snippet = value if len(value) <= 80 else value[:77] + "..."
            raise InvalidInput(
                "external_reference",
                f"Unexpected external-reference instruction in {where}: {snippet}",
            )
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                _reject_external(key, where)
            _reject_external(item, where)
        return
    if isinstance(value, list):
        for item in value:
            _reject_external(item, where)


def _parse_contract(payload: dict, path: str) -> Contract:
    version = payload.get("contract_version")
    if version != "1":
        raise InvalidInput("malformed_contract", "contract_version must be \"1\"")
    timezone = payload.get("timezone")
    if not isinstance(timezone, str) or timezone == "":
        raise InvalidInput("malformed_contract", "timezone must be a non-empty string")
    _require_zone(timezone)
    max_csv_bytes = _bounded_int(payload.get("max_csv_bytes"), "max_csv_bytes", 1, ABSOLUTE_MAX_CSV_BYTES)
    max_rows = _bounded_int(payload.get("max_rows"), "max_rows", 1, ABSOLUTE_MAX_ROWS)
    tables_raw = payload.get("tables")
    if not isinstance(tables_raw, dict) or not tables_raw:
        raise InvalidInput("malformed_contract", "tables must be a non-empty object")
    tables = {name: _parse_table(name, body) for name, body in tables_raw.items()}
    _check_foreign_key_targets(tables)
    queries_raw = payload.get("queries")
    if not isinstance(queries_raw, list) or not queries_raw:
        raise InvalidInput("malformed_contract", "queries must be a non-empty list")
    queries = tuple(_parse_query(item, tables) for item in queries_raw)
    ids = [query.id for query in queries]
    if len(ids) != len(set(ids)):
        raise InvalidInput("malformed_contract", "query ids must be unique")
    foreign_keys = {}
    for table in tables.values():
        for foreign_key in table.foreign_keys:
            if foreign_key.name in foreign_keys:
                raise InvalidInput("malformed_contract", f"Duplicate foreign key name {foreign_key.name}")
            foreign_keys[foreign_key.name] = foreign_key
    return Contract(
        version=version,
        timezone=timezone,
        max_csv_bytes=max_csv_bytes,
        max_rows=max_rows,
        tables=tables,
        queries=queries,
        path=path,
        foreign_keys=foreign_keys,
    )


def _require_zone(name: str) -> None:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise InvalidInput("malformed_contract", f"Unknown timezone {name}") from exc


def _bounded_int(value, label: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidInput("malformed_contract", f"{label} must be an integer")
    if value < low or value > high:
        raise InvalidInput("malformed_contract", f"{label} must be between {low} and {high}")
    return value


def _parse_table(name: str, body) -> Table:
    if not isinstance(name, str) or not IDENT.fullmatch(name):
        raise InvalidInput("invalid_identifier", f"Invalid table name {name!r}")
    if not isinstance(body, dict):
        raise InvalidInput("malformed_contract", f"Table {name} must be an object")
    columns_raw = body.get("columns")
    if not isinstance(columns_raw, dict) or not columns_raw:
        raise InvalidInput("malformed_contract", f"Table {name} needs columns")
    columns = {}
    for column_name, spec in columns_raw.items():
        if not isinstance(column_name, str) or not IDENT.fullmatch(column_name):
            raise InvalidInput("invalid_identifier", f"Invalid column name {column_name!r}")
        if not isinstance(spec, dict):
            raise InvalidInput("malformed_contract", f"Column {name}.{column_name} must be an object")
        type_name = spec.get("type")
        nullable = spec.get("nullable")
        if type_name not in COLUMN_TYPES:
            raise InvalidInput("malformed_contract", f"Unsupported type for {name}.{column_name}")
        if not isinstance(nullable, bool):
            raise InvalidInput("malformed_contract", f"{name}.{column_name} nullable must be true or false")
        columns[column_name] = Column(column_name, type_name, nullable)
    primary_key = body.get("primary_key")
    if (
        not isinstance(primary_key, list)
        or not primary_key
        or any(not isinstance(column, str) for column in primary_key)
    ):
        raise InvalidInput("malformed_contract", f"Table {name} needs a primary_key list")
    for column in primary_key:
        if column not in columns:
            raise InvalidInput("malformed_contract", f"Primary key column {name}.{column} is not declared")
        if columns[column].nullable:
            raise InvalidInput("malformed_contract", f"Primary key {name}.{column} must be non-nullable")
    foreign_keys = []
    for spec in body.get("foreign_keys", []):
        foreign_keys.append(_parse_foreign_key(name, spec, columns))
    return Table(name, columns, tuple(primary_key), tuple(foreign_keys))


def _parse_foreign_key(table: str, spec, columns: dict[str, Column]) -> ForeignKey:
    if not isinstance(spec, dict):
        raise InvalidInput("malformed_contract", f"Foreign key on {table} must be an object")
    name = spec.get("name")
    if not isinstance(name, str) or not IDENT.fullmatch(name):
        raise InvalidInput("invalid_identifier", f"Invalid foreign key name on {table}")
    child_columns = spec.get("columns")
    references = spec.get("references")
    if not isinstance(child_columns, list) or not child_columns:
        raise InvalidInput("malformed_contract", f"Foreign key {name} needs columns")
    if not isinstance(references, dict):
        raise InvalidInput("malformed_contract", f"Foreign key {name} needs references")
    parent_table = references.get("table")
    parent_columns = references.get("columns")
    if not isinstance(parent_table, str) or not IDENT.fullmatch(parent_table):
        raise InvalidInput("invalid_identifier", f"Foreign key {name} has an invalid parent table")
    if not isinstance(parent_columns, list) or len(parent_columns) != len(child_columns):
        raise InvalidInput("malformed_contract", f"Foreign key {name} column lists must match in length")
    for column in child_columns:
        if column not in columns:
            raise InvalidInput("malformed_contract", f"Foreign key {name} column {column} is not declared")
    return ForeignKey(name, tuple(child_columns), parent_table, tuple(parent_columns))


def _parse_query(item, tables: dict[str, Table]) -> Query:
    if not isinstance(item, dict):
        raise InvalidInput("malformed_contract", "Each query must be an object")
    query_id = item.get("id")
    formula = item.get("formula")
    unit = item.get("unit")
    if not isinstance(query_id, str) or not IDENT.fullmatch(query_id):
        raise InvalidInput("invalid_identifier", "Each query needs an identifier id")
    if not isinstance(formula, str) or not formula.strip():
        raise InvalidInput("malformed_contract", f"Query {query_id} needs a formula")
    if not isinstance(unit, str) or not unit.strip():
        raise InvalidInput("malformed_contract", f"Query {query_id} needs a unit")
    grain = item.get("grain")
    if not isinstance(grain, list):
        raise InvalidInput("malformed_contract", f"Query {query_id} grain must be a list")
    parsed_grain = tuple(_parse_grain(part, tables, query_id) for part in grain)
    measure = item.get("measure")
    if not isinstance(measure, dict):
        raise InvalidInput("malformed_contract", f"Query {query_id} needs a measure")
    _parse_measure(measure, tables, query_id)
    tolerance_raw = item.get("tolerance")
    if not isinstance(tolerance_raw, dict):
        raise InvalidInput("malformed_contract", f"Query {query_id} needs a tolerance")
    kind = tolerance_raw.get("kind")
    value = tolerance_raw.get("value")
    if kind not in {"absolute", "relative"}:
        raise InvalidInput("malformed_contract", f"Query {query_id} tolerance kind is unsupported")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidInput("malformed_contract", f"Query {query_id} tolerance value must be a number")
    if value < 0:
        raise InvalidInput("malformed_contract", f"Query {query_id} tolerance value must be >= 0")
    tolerance = Tolerance(kind, _number_string(value))
    _check_query_shape(query_id, parsed_grain, measure, tables)
    return Query(query_id, formula.strip(), unit.strip(), parsed_grain, measure, tolerance)


def _parse_grain(part, tables: dict[str, Table], query_id: str) -> dict:
    if not isinstance(part, dict):
        raise InvalidInput("malformed_contract", f"Query {query_id} has a grain entry that is not an object")
    if "column" in part and "op" not in part:
        _require_column(part.get("column"), tables, query_id)
        return {"column": part["column"]}
    if part.get("op") == "month":
        column = part.get("column")
        alias = part.get("alias")
        _require_column(column, tables, query_id, expected_type="timestamp")
        if not isinstance(alias, str) or not IDENT.fullmatch(alias):
            raise InvalidInput("invalid_identifier", f"Query {query_id} month grain needs an alias")
        return {"op": "month", "column": column, "alias": alias}
    operator = part.get("op", "missing")
    raise InvalidInput("unknown_operator", f"Unknown grain operator {operator!r} in query {query_id}")


def _parse_measure(measure: dict, tables: dict[str, Table], query_id: str) -> None:
    operator = measure.get("op")
    if operator == "count_distinct":
        _require_column(measure.get("column"), tables, query_id)
        if "where" in measure:
            _parse_where(measure["where"], tables, query_id)
        return
    if operator == "ratio":
        numerator = measure.get("numerator")
        denominator = measure.get("denominator")
        if not isinstance(numerator, dict) or not isinstance(denominator, dict):
            raise InvalidInput("malformed_contract", f"Query {query_id} ratio needs numerator and denominator")
        _parse_measure(numerator, tables, query_id)
        _parse_measure(denominator, tables, query_id)
        if numerator.get("op") != "count_distinct" or denominator.get("op") != "count_distinct":
            raise InvalidInput("unknown_operator", f"Query {query_id} ratio arms must be count_distinct")
        return
    raise InvalidInput("unknown_operator", f"Unknown measure operator {operator!r} in query {query_id}")


def _parse_where(where, tables: dict[str, Table], query_id: str) -> None:
    if not isinstance(where, dict):
        raise InvalidInput("malformed_contract", f"Query {query_id} where must be an object")
    operator = where.get("op")
    if operator == "eq":
        _require_column(where.get("column"), tables, query_id)
        _literal(where.get("value"), query_id)
        return
    if operator == "month_eq":
        _require_column(where.get("column"), tables, query_id, expected_type="timestamp")
        value = where.get("value")
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
            raise InvalidInput("malformed_contract", f"Query {query_id} month_eq value must be YYYY-MM")
        return
    if operator == "exists":
        child = where.get("child_table")
        child_columns = where.get("child_columns")
        parent_columns = where.get("parent_columns")
        if child not in tables:
            raise InvalidInput("malformed_contract", f"Query {query_id} exists refers to unknown table {child}")
        if not isinstance(child_columns, list) or not isinstance(parent_columns, list):
            raise InvalidInput("malformed_contract", f"Query {query_id} exists needs column lists")
        if len(child_columns) != len(parent_columns) or not child_columns:
            raise InvalidInput("malformed_contract", f"Query {query_id} exists column lists must match")
        for column in child_columns:
            if column not in tables[child].columns:
                raise InvalidInput("malformed_contract", f"Query {query_id} exists uses unknown column {child}.{column}")
        filters = where.get("filters", [])
        if not isinstance(filters, list):
            raise InvalidInput("malformed_contract", f"Query {query_id} exists filters must be a list")
        for item in filters:
            if not isinstance(item, dict) or item.get("op") != "eq":
                raise InvalidInput("unknown_operator", f"Unknown exists filter operator in query {query_id}")
            _require_column(item.get("column"), tables, query_id)
            table_name, column_name = item["column"].split(".", 1)
            if table_name != child:
                raise InvalidInput(
                    "malformed_contract",
                    f"Query {query_id} exists filter must use {child}",
                )
            if column_name not in tables[child].columns:
                raise InvalidInput("malformed_contract", f"Unknown filter column {item['column']}")
            _literal(item.get("value"), query_id)
        return
    raise InvalidInput("unknown_operator", f"Unknown filter operator {operator!r} in query {query_id}")


def _check_query_shape(query_id: str, grain: tuple[dict, ...], measure: dict, tables: dict[str, Table]) -> None:
    """Reject joins that are not a declared foreign key or a single-table aggregate."""
    grain_tables = set()
    for part in grain:
        grain_tables.add(part["column"].split(".", 1)[0])
    if len(grain_tables) > 1:
        raise InvalidInput("malformed_contract", f"Query {query_id} grain must use one table")
    grain_names = []
    for part in grain:
        grain_names.append(part["alias"] if part.get("op") == "month" else part["column"].split(".", 1)[1])
    if len(grain_names) != len(set(grain_names)):
        raise InvalidInput("malformed_contract", f"Query {query_id} grain names must be unique")
    measure_tables = _measure_tables(measure)
    if len(measure_tables) != 1:
        raise InvalidInput("malformed_contract", f"Query {query_id} must aggregate one table")
    measure_table = next(iter(measure_tables))
    grain_table = next(iter(grain_tables)) if grain_tables else measure_table
    if measure_table != grain_table:
        parent = grain_table
        child = measure_table
        if not _matching_foreign_key(tables, child, parent):
            raise InvalidInput(
                "malformed_contract",
                f"Query {query_id} has no declared foreign key from {child} to {parent}",
            )
    for arm in _measure_arms(measure):
        where = arm.get("where")
        if isinstance(where, dict) and where.get("op") == "exists":
            counted = arm["column"].split(".", 1)[0]
            child = where["child_table"]
            if not _matching_exists(tables, where, counted):
                raise InvalidInput(
                    "malformed_contract",
                    f"Query {query_id} exists path is not a declared foreign key",
                )
            if child == counted:
                raise InvalidInput("malformed_contract", f"Query {query_id} exists cannot target its own table")


def _matching_foreign_key(tables: dict[str, Table], child: str, parent: str) -> ForeignKey | None:
    if child not in tables:
        return None
    for foreign_key in tables[child].foreign_keys:
        if foreign_key.parent_table == parent:
            return foreign_key
    return None


def _matching_exists(tables: dict[str, Table], where: dict, parent: str) -> bool:
    child = where["child_table"]
    if child not in tables:
        return False
    for foreign_key in tables[child].foreign_keys:
        if (
            foreign_key.parent_table == parent
            and foreign_key.columns == tuple(where["child_columns"])
            and foreign_key.parent_columns == tuple(where["parent_columns"])
        ):
            return True
    return False


def _measure_tables(measure: dict) -> set[str]:
    if measure["op"] == "count_distinct":
        return {measure["column"].split(".", 1)[0]}
    return _measure_tables(measure["numerator"]) | _measure_tables(measure["denominator"])


def _measure_arms(measure: dict) -> list[dict]:
    if measure["op"] == "count_distinct":
        return [measure]
    return _measure_arms(measure["numerator"]) + _measure_arms(measure["denominator"])


def _require_column(ref, tables: dict[str, Table], query_id: str, expected_type: str | None = None) -> None:
    if not isinstance(ref, str) or ref.count(".") != 1:
        raise InvalidInput("invalid_identifier", f"Query {query_id} has an invalid column reference")
    table_name, column_name = ref.split(".", 1)
    if not IDENT.fullmatch(table_name) or not IDENT.fullmatch(column_name):
        raise InvalidInput("invalid_identifier", f"Query {query_id} has an invalid column reference {ref}")
    table = tables.get(table_name)
    if table is None or column_name not in table.columns:
        raise InvalidInput("malformed_contract", f"Query {query_id} references unknown column {ref}")
    if expected_type and table.columns[column_name].type_name != expected_type:
        raise InvalidInput("malformed_contract", f"Query {query_id} column {ref} must be {expected_type}")


def _literal(value, query_id: str) -> None:
    if isinstance(value, bool) or isinstance(value, (int, str)):
        return
    if isinstance(value, float):
        return
    raise InvalidInput("malformed_contract", f"Query {query_id} filter value must be a scalar")


def _number_string(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    return format(Decimal(str(value)), "f")


def _check_foreign_key_targets(tables: dict[str, Table]) -> None:
    for table in tables.values():
        for foreign_key in table.foreign_keys:
            parent = tables.get(foreign_key.parent_table)
            if parent is None:
                raise InvalidInput(
                    "malformed_contract",
                    f"Foreign key {foreign_key.name} references unknown table {foreign_key.parent_table}",
                )
            for column in foreign_key.parent_columns:
                if column not in parent.columns:
                    raise InvalidInput(
                        "malformed_contract",
                        f"Foreign key {foreign_key.name} references unknown column {parent.name}.{column}",
                    )
            if foreign_key.parent_columns != parent.primary_key:
                raise InvalidInput(
                    "malformed_contract",
                    f"Foreign key {foreign_key.name} must reference the primary key of {parent.name}",
                )
