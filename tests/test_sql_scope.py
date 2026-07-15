from __future__ import annotations

import sqlite3

import dogdb
import pytest

from dogdb.core.sql import SQLKind, classify_sql


def _database() -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    raw.execute('create table "Orders"(id integer)')
    raw.execute("create table users(id integer)")
    raw.executemany('insert into "Orders" values (?)', [(1,), (2,), (3,)])
    raw.executemany("insert into users values (?)", [(1,), (2,), (3,)])
    return raw


def test_classifier_extracts_conservative_from_table_names():
    simple = classify_sql("select id from users")
    quoted = classify_sql('select id from "Orders"')
    nested = classify_sql("select id from (select id from users) nested")

    assert simple.kind is SQLKind.SELECT and simple.tables == frozenset({"users"})
    assert quoted.tables == frozenset({"orders"})
    assert nested.tables is None


def test_classifier_extracts_real_tables_from_ctes_and_excludes_aliases():
    classification = classify_sql(
        'with recent as (select id from "Orders"), '
        "joined as (select recent.id from recent join users on users.id = recent.id) "
        "select id from joined"
    )

    assert classification.kind is SQLKind.SELECT
    assert classification.tables == frozenset({"orders", "users"})


def test_classifier_follows_nested_cte_scopes_to_real_tables():
    classification = classify_sql(
        "with outer_cte as ("
        "with inner_cte as (select id from users) "
        "select id from inner_cte"
        ") select id from outer_cte"
    )

    assert classification.tables == frozenset({"users"})


@pytest.mark.parametrize("operator", ["union", "except", "intersect"])
def test_classifier_treats_set_operations_as_conservative_selects(operator):
    classification = classify_sql(
        f"select id from users {operator} select id from users limit 2 offset 1"
    )

    assert classification.kind is SQLKind.SELECT
    assert classification.has_top_level_order_by is False
    assert classification.tables is None
    assert classification.top_level_limit is None
    assert classification.top_level_offset is None


def test_classifier_detects_top_level_order_by_on_set_operation():
    classification = classify_sql(
        "select id from users union select id from users order by id"
    )
    assert classification.kind is SQLKind.SELECT
    assert classification.has_top_level_order_by is True


@pytest.mark.parametrize(
    "sql",
    [
        "insert into users values (4) returning id",
        "update users set id = 4 returning id",
    ],
)
def test_returning_dml_remains_other(sql):
    assert classify_sql(sql).kind is SQLKind.OTHER


@pytest.mark.parametrize(
    "sql",
    [
        "select 1; select 2;",
        "pragma table_info(users)",
        "explain select * from users",
        "select * from (",
    ],
)
def test_unsupported_or_invalid_sql_is_unknown(sql):
    assert classify_sql(sql).kind is SQLKind.UNKNOWN


def test_only_tables_applies_fault_only_to_matching_table():
    conn = dogdb.wrap(
        _database(), seed=42, faults={"SHUFFLE": 1}, only_tables=["orders"]
    )

    users = conn.execute("select id from users").fetchall()
    orders = conn.execute('select id from "Orders"').fetchall()

    assert users == [(1,), (2,), (3,)]
    assert orders != [(1,), (2,), (3,)]
    assert [event.fault for event in conn.dolly.log()] == ["SHUFFLE"]


def test_unextractable_table_is_outside_only_scope():
    conn = dogdb.wrap(
        _database(), seed=42, faults={"SHUFFLE": 1}, only_tables=["users"]
    )
    rows = conn.execute("select id from (select id from users) nested").fetchall()
    assert rows == [(1,), (2,), (3,)]
    assert conn.dolly.log() == []


def test_unextractable_table_remains_inside_exclude_scope():
    conn = dogdb.wrap(
        _database(), seed=42, faults={"SHUFFLE": 1}, exclude_tables=["orders"]
    )
    rows = conn.execute("select id from (select id from users) nested").fetchall()
    assert rows != [(1,), (2,), (3,)]
    assert [event.fault for event in conn.dolly.log()] == ["SHUFFLE"]


def test_only_and_exclude_scopes_are_mutually_exclusive():
    with pytest.raises(ValueError, match="mutually exclusive"):
        dogdb.wrap(
            _database(), seed=42, only_tables=["orders"], exclude_tables=["users"]
        )


def test_cte_select_is_eligible_for_stash():
    conn = dogdb.wrap(_database(), seed=42, faults={"STASH": 1})
    conn.execute("with scoped as (select id from users) select id from scoped").fetchall()
    assert [event.fault for event in conn.dolly.log()] == ["STASH"]


def test_unordered_union_is_eligible_for_shuffle():
    conn = dogdb.wrap(_database(), seed=42, faults={"SHUFFLE": 1})
    conn.execute(
        'select id from users union select id from "Orders"'
    ).fetchall()
    assert [event.fault for event in conn.dolly.log()] == ["SHUFFLE"]


@pytest.mark.parametrize(
    "sql",
    [
        "pragma user_version",
        "explain select * from users",
    ],
)
def test_unknown_sql_passthrough_does_not_inject(sql):
    conn = dogdb.wrap(_database(), seed=42, faults={"SHUFFLE": 1})
    conn.execute(sql).fetchall()
    assert conn.dolly.log() == []


@pytest.mark.parametrize("sql", ["select 1; select 2;", "select * from ("])
def test_invalid_or_multi_statement_passthrough_preserves_backend_error(sql):
    conn = dogdb.wrap(_database(), seed=42, faults={"SHUFFLE": 1})
    with pytest.raises(sqlite3.Error):
        conn.execute(sql)
    assert conn.dolly.log() == []
