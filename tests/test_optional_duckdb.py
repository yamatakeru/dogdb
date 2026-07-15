from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from types import ModuleType

import pytest


@contextmanager
def _dogdb_without_duckdb(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[ModuleType]:
    dogdb_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "dogdb" or name.startswith("dogdb.")
    }
    for name in dogdb_modules:
        sys.modules.pop(name)
    monkeypatch.setitem(sys.modules, "duckdb", None)

    try:
        yield importlib.import_module("dogdb")
    finally:
        for name in tuple(sys.modules):
            if name == "dogdb" or name.startswith("dogdb."):
                sys.modules.pop(name)
        sys.modules.update(dogdb_modules)


def test_import_and_default_sqlite_flow_work_without_duckdb(monkeypatch):
    with _dogdb_without_duckdb(monkeypatch) as dogdb:
        connection = dogdb.connect(seed=42)

        assert type(connection).__name__ == "SQLiteProxy"
        assert connection.execute("select 1").fetchall() == [(1,)]
        connection.close()


def test_duckdb_backend_gives_install_guidance_without_duckdb(monkeypatch):
    with _dogdb_without_duckdb(monkeypatch) as dogdb:
        with pytest.raises(ImportError) as caught:
            dogdb.connect(backend="duckdb", seed=42)

        assert 'pip install "dogdb[duckdb]"' in str(caught.value)
        assert isinstance(caught.value.__cause__, ImportError)
