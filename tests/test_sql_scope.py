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
