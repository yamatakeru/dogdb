from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

import dogdb
import pytest

from dogdb.core.faults import _INELIGIBLE, _chew_value

def _raw() -> sqlite3.Connection:
    raw = sqlite3.connect(":memory:")
    raw.execute("create table t(id integer, secret text, amount real, payload blob)")
    raw.executemany(
        "insert into t values (?, ?, ?, ?)",
        [
            (1, "alpha-secret", 123.45, b"alpha-blob"),
            (2, "beta-secret", 678.91, b"beta-blob"),
            (3, "gamma-secret", 246.81, b"gamma-blob"),
        ],
    )
    return raw


@pytest.mark.parametrize(
    ("profile", "sql", "assertion"),
    [
        (
            "utf8_truncate",
            "select secret from t where id = 1",
            lambda value: value == "alpha-secre",
        ),
        (
            "precision_loss",
            "select amount from t where id = 1",
            lambda value: value == 123.0,
        ),
        (
            "nullify",
            "select payload from t where id = 1",
            lambda value: value is None,
        ),
    ],
)
def test_chew_closed_profiles_mutate_an_eligible_cell(profile, sql, assertion):
    conn = dogdb.wrap(
        _raw(), seed=42, faults={"CHEW": 1}, chew_profiles=(profile,)
    )
    value = conn.execute(sql).fetchone()[0]
    event = conn.dolly.log()[0]

    assert assertion(value)
    assert event.outcome == "value_corrupted"
    assert event.details == {"row_index": 0, "column_index": 0, "profile": profile}
    assert conn.dolly.house() == []


def test_chew_without_eligible_cell_yields_to_later_fault():
    conn = dogdb.wrap(
        _raw(),
        seed=42,
        faults={"CHEW": 1, "WRONG_COUNT": 1},
        chew_profiles=("utf8_truncate",),
    )
    rows = conn.execute("select id from t order by id").fetchall()

    assert rows == [(1,), (2,), (3,)]
    assert [event.fault for event in conn.dolly.log()] == ["WRONG_COUNT"]


def test_chew_value_profiles_cover_decimal_timezone_and_blob_cases():
    aware = datetime(2026, 7, 12, 12, 30, tzinfo=timezone.utc)

    assert _chew_value("precision_loss", Decimal("123.45")) == Decimal("123")
    assert _chew_value("precision_loss", Decimal("NaN")) is _INELIGIBLE
    assert _chew_value("nullify", aware) is None
    assert _chew_value("nullify", b"\x00\xff") is None
    assert _chew_value("utf8_truncate", b"\x00\xff") is _INELIGIBLE


@pytest.mark.parametrize(
    "profiles",
    [("arbitrary_mutation",), ()],
)
def test_chew_profile_configuration_is_closed(profiles):
    with pytest.raises(ValueError, match=r"CHEW profiles|must not be empty"):
        dogdb.wrap(_raw(), seed=42, chew_profiles=profiles)


def test_chew_log_contains_neither_original_nor_mutated_value(tmp_path):
    path = tmp_path / "events.jsonl"
    original = "alpha-secret"
    mutated = "alpha-secre"
    conn = dogdb.wrap(
        _raw(),
        seed=42,
        faults={"CHEW": 1},
        chew_profiles=("utf8_truncate",),
        log_path=path,
    )
    assert conn.execute("select secret from t where id = 1").fetchone() == (mutated,)

    contents = path.read_text()
    assert original not in contents
    assert mutated not in contents
    assert set(conn.dolly.log()[0].details) == {
        "row_index",
        "column_index",
        "profile",
    }


def test_tangled_leash_swaps_adjacent_labels_without_moving_values():
    conn = dogdb.wrap(_raw(), seed=42, faults={"TANGLED_LEASH": 1})
    cursor = conn.execute("select 1 as a, 2 as b")
    event = conn.dolly.log()[0]

    assert [column[0] for column in cursor.description] == ["b", "a"]
    assert cursor.fetchall() == [(1, 2)]
    assert event.details == {"column_indices": [0, 1]}
    assert conn.dolly.house() == []


def test_wrong_count_changes_only_logical_rowcount():
    raw = _raw()
    conn = dogdb.wrap(raw, seed=42, faults={"WRONG_COUNT": 1})
    cursor = conn.execute("select id from t order by id")
    rows = cursor.fetchall()
    event = conn.dolly.log()[0]

    assert rows == [(1,), (2,), (3,)]
    assert cursor.rowcount != 3
    assert event.details == {
        "actual_rowcount": 3,
        "reported_rowcount": cursor.rowcount,
    }
    assert raw.execute("select count(*) from t").fetchone() == (3,)
    assert conn.dolly.house() == []


def test_wrong_count_delta_is_derived_within_configured_bound():
    conn = dogdb.wrap(
        _raw(), seed=42, faults={"WRONG_COUNT": 1}, wrong_count_max_delta=3
    )
    cursor = conn.execute("select id from t order by id")

    assert 1 <= abs(cursor.rowcount - 3) <= 3


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_wrong_count_delta_bound_must_be_a_positive_integer(value):
    with pytest.raises(ValueError, match="wrong_count_max_delta"):
        dogdb.wrap(_raw(), seed=42, wrong_count_max_delta=value)


def test_echo_precedes_chew_in_actual_result_processing():
    conn = dogdb.wrap(
        _raw(),
        seed=42,
        faults={"ECHO": 1, "CHEW": 1},
        chew_profiles=("utf8_truncate",),
    )
    rows = conn.execute("select secret from t order by id").fetchall()

    assert len(rows) == 4
    assert all(value[0].endswith("-secret") for value in rows)
    assert [event.fault for event in conn.dolly.log()] == ["ECHO"]


@pytest.mark.parametrize(
    ("fault", "options", "sql"),
    [
        (
            "CHEW",
            {"chew_profiles": ("utf8_truncate",)},
            "select secret from t order by id",
        ),
        ("TANGLED_LEASH", {}, "select id, secret from t order by id"),
        ("WRONG_COUNT", {}, "select id from t order by id"),
    ],
)
def test_value_faults_are_deterministic(fault, options, sql):
    runs = []
    for _ in range(2):
        conn = dogdb.wrap(
            _raw(),
            seed=42,
            session_id=f"value-{fault}",
            faults={fault: 1},
            **options,
        )
        cursor = conn.execute(sql)
        runs.append((cursor.description, cursor.fetchall(), cursor.rowcount, conn.dolly.log()))
        assert conn.dolly.house() == []
    assert runs[0] == runs[1]
