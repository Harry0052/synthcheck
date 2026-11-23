"""Compile the contract query language to parameterized read-only SQL."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import duckdb

from synthcheck.contract import IDENT, Contract, Query
from synthcheck.errors import InvalidInput
from synthcheck.models import Bundle

_SQL_TYPE = {
    "string": "VARCHAR",
    "integer": "BIGINT",
    "number": "VARCHAR",
    "boolean": "BOOLEAN",
    "timestamp": "VARCHAR",
}


@dataclass
class SideResult:
    state: str
    reasons: list[str]
    groups: list[dict]


def connect() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with file and network access disabled."""
    connection = duckdb.connect(database=":memory:")
    connection.execute("SET enable_external_access = false")
    connection.execute("SET enable_external_file_cache = false")
    return connection


def evaluate_side(connection, contract: Contract, bundle: Bundle, query: Query) -> SideResult:
    reads, relationships = _dependencies(contract, query)
    reasons = []
    for table in sorted(reads):
        if table in bundle.tainted_tables:
            reasons.append(f"integrity on {table}")
    for name in sorted(relationships):
        if name in bundle.broken_relationships:
            reasons.append(f"orphan_foreign_key {name}")
    if reasons:
        return SideResult("unavailable", reasons, [])
    _install_tables(connection, contract, bundle, reads)
    try:
        sql, params = _compile(contract, query)
        cursor = connection.execute(sql, params)
        names = [item[0] for item in cursor.description]
        fetched = cursor.fetchall()
    finally:
        for table in reads:
            connection.execute(f"DROP TABLE IF EXISTS {_quote(table)}")
    return SideResult("ok", [], [_groups_from_row(query, names, row) for row in fetched])


def _dependencies(contract: Contract, query: Query) -> tuple[set[str], set[str]]:
    measure_table = next(iter(_measure_tables(query.measure)))
    grain_table = _grain_table(query) or measure_table
    reads = {measure_table, grain_table}
    relationships: set[str] = set()
    if measure_table != grain_table:
        foreign_key = _foreign_key_between(contract, measure_table, grain_table)
        relationships.add(foreign_key.name)
    for arm in _arms(query.measure):
        where = arm.get("where")
        if isinstance(where, dict) and where.get("op") == "exists":
            child = where["child_table"]
            reads.add(child)
            foreign_key = _exists_key(contract, where, arm["column"].split(".", 1)[0])
            relationships.add(foreign_key.name)
    return reads, relationships


def _groups_from_row(query: Query, names: list[str], row: tuple) -> dict:
    record = dict(zip(names, row, strict=True))
    key = {}
    for name in _grain_names(query):
        key[name] = record[name]
    numerator = int(record["numerator"])
    denominator = int(record["denominator"])
    if query.measure["op"] == "ratio":
        if denominator == 0:
            return {
                "key": key,
                "state": "unavailable",
                "value": None,
                "numerator": numerator,
                "denominator": denominator,
            }
        value = format(Decimal(numerator) / Decimal(denominator), "f")
        return {
            "key": key,
            "state": "ok",
            "value": value,
            "numerator": numerator,
            "denominator": denominator,
        }
    return {
        "key": key,
        "state": "ok",
        "value": format(Decimal(numerator), "f"),
        "numerator": numerator,
        "denominator": None,
    }


def _compile(contract: Contract, query: Query) -> tuple[str, list]:
    measure_table = next(iter(_measure_tables(query.measure)))
    grain_table = _grain_table(query) or measure_table
    aliases = {grain_table: "b"}
    if measure_table == grain_table:
        from_sql = f"{_quote(grain_table)} AS b"
    else:
        foreign_key = _foreign_key_between(contract, measure_table, grain_table)
        aliases[measure_table] = "c"
        conditions = [
            f"c.{_quote(child)} = b.{_quote(parent)}"
            for child, parent in zip(foreign_key.columns, foreign_key.parent_columns, strict=True)
        ]
        from_sql = (
            f"{_quote(grain_table)} AS b LEFT JOIN {_quote(measure_table)} AS c "
            f"ON {' AND '.join(conditions)}"
        )
    selects = []
    for part in query.grain:
        if part.get("op") == "month":
            column = part["column"].split(".", 1)[1]
            selects.append(
                "strftime(date_trunc('month', CAST(b."
                f"{_quote(column)} AS TIMESTAMP)), '%Y-%m') AS {_quote(part['alias'])}"
            )
        else:
            column = part["column"].split(".", 1)[1]
            selects.append(f"b.{_quote(column)} AS {_quote(column)}")
    if query.measure["op"] == "ratio":
        numerator_sql, numerator_params = _count_sql(query.measure["numerator"], aliases)
        denominator_sql, denominator_params = _count_sql(query.measure["denominator"], aliases)
        params = numerator_params + denominator_params
    else:
        numerator_sql, params = _count_sql(query.measure, aliases)
        denominator_sql = numerator_sql
        params = params + params
    selects.extend([f"{numerator_sql} AS numerator", f"{denominator_sql} AS denominator"])
    group = ""
    if query.grain:
        ordinals = ", ".join(str(index) for index in range(1, len(query.grain) + 1))
        group = f" GROUP BY {ordinals} ORDER BY {ordinals}"
    sql = f"SELECT {', '.join(selects)} FROM {from_sql}{group}"
    return sql, params


def _count_sql(arm: dict, aliases: dict[str, str]) -> tuple[str, list]:
    table_name, column = arm["column"].split(".", 1)
    alias = aliases[table_name]
    target = f"{alias}.{_quote(column)}"
    where = arm.get("where")
    if not where:
        return f"COUNT(DISTINCT {target})", []
    predicate, params = _predicate(where, aliases, table_name)
    return f"COUNT(DISTINCT CASE WHEN {predicate} THEN {target} END)", params


def _predicate(where: dict, aliases: dict[str, str], counted_table: str) -> tuple[str, list]:
    operator = where["op"]
    if operator == "eq":
        table_name, column = where["column"].split(".", 1)
        return f"{aliases[table_name]}.{_quote(column)} = ?", [_param(where["value"])]
    if operator == "month_eq":
        table_name, column = where["column"].split(".", 1)
        expression = (
            "strftime(date_trunc('month', CAST("
            f"{aliases[table_name]}.{_quote(column)} AS TIMESTAMP)), '%Y-%m') = ?"
        )
        return expression, [where["value"]]
    if operator == "exists":
        parts = []
        params = []
        parent_alias = aliases[counted_table]
        for child_column, parent_column in zip(
            where["child_columns"], where["parent_columns"], strict=True
        ):
            parts.append(f"e.{_quote(child_column)} = {parent_alias}.{_quote(parent_column)}")
        for item in where.get("filters", []):
            column = item["column"].split(".", 1)[1]
            parts.append(f"e.{_quote(column)} = ?")
            params.append(_param(item["value"]))
        sql = (
            f"EXISTS (SELECT 1 FROM {_quote(where['child_table'])} AS e "
            f"WHERE {' AND '.join(parts)})"
        )
        return sql, params
    raise InvalidInput("unknown_operator", f"Unknown filter operator {operator!r}")


def _param(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    return str(value)


def _install_tables(connection, contract: Contract, bundle: Bundle, tables: set[str]) -> None:
    for table_name in sorted(tables):
        table = contract.tables[table_name]
        column_sql = ", ".join(
            f"{_quote(column.name)} {_SQL_TYPE[column.type_name]}" for column in table.columns.values()
        )
        connection.execute(f"CREATE TABLE {_quote(table_name)} ({column_sql})")
        names = list(table.columns)
        placeholders = ", ".join(["?"] * len(names))
        column_list = ", ".join(_quote(name) for name in names)
        rows = [tuple(row.get(name) for name in names) for row in bundle.tables[table_name]]
        if rows:
            connection.executemany(
                f"INSERT INTO {_quote(table_name)} ({column_list}) VALUES ({placeholders})",
                rows,
            )


def _quote(name: str) -> str:
    if not IDENT.fullmatch(name):
        raise InvalidInput("invalid_identifier", f"Invalid identifier {name}")
    return f'"{name}"'


def _grain_table(query: Query) -> str | None:
    if not query.grain:
        return None
    return query.grain[0]["column"].split(".", 1)[0]


def _grain_names(query: Query) -> list[str]:
    names = []
    for part in query.grain:
        if part.get("op") == "month":
            names.append(part["alias"])
        else:
            names.append(part["column"].split(".", 1)[1])
    return names


def _measure_tables(measure: dict) -> set[str]:
    if measure["op"] == "count_distinct":
        return {measure["column"].split(".", 1)[0]}
    return _measure_tables(measure["numerator"]) | _measure_tables(measure["denominator"])


def _arms(measure: dict) -> list[dict]:
    if measure["op"] == "count_distinct":
        return [measure]
    return _arms(measure["numerator"]) + _arms(measure["denominator"])


def _foreign_key_between(contract: Contract, child: str, parent: str):
    for foreign_key in contract.tables[child].foreign_keys:
        if foreign_key.parent_table == parent:
            return foreign_key
    raise InvalidInput("malformed_contract", f"No foreign key from {child} to {parent}")


def _exists_key(contract: Contract, where: dict, parent: str):
    for foreign_key in contract.tables[where["child_table"]].foreign_keys:
        if (
            foreign_key.parent_table == parent
            and foreign_key.columns == tuple(where["child_columns"])
            and foreign_key.parent_columns == tuple(where["parent_columns"])
        ):
            return foreign_key
    raise InvalidInput("malformed_contract", "exists path is not a declared foreign key")
