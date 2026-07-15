## 1. パッケージング

- [x] 1.1 `pyproject.toml`: `[project] dependencies` からduckdbのみを除去する（W6-1で追加されたsqlglot等、他の通常依存は維持する）
- [x] 1.2 `pyproject.toml`: `[project.optional-dependencies] duckdb = ["duckdb"]` を追加する
- [x] 1.3 `pyproject.toml`: `[dependency-groups] dev` を `dev = ["pytest", "duckdb"]` へ更新する

## 2. `connect()` の既定バックエンド変更

- [x] 2.1 `src/dogdb/proxy/connection.py`: `connect()` の `backend` 既定値を `"duckdb"` から `"sqlite"` へ変更する
- [x] 2.2 `src/dogdb/proxy/connection.py`: `connect()` 内の `import duckdb` を `try/except ImportError` で囲み、元の `ImportError` をchainした案内付き `ImportError`（メッセージに `pip install "dogdb[duckdb]"` を含む）を送出する
- [x] 2.3 `src/dogdb/proxy/connection.py`: `connect()` に、`backend` の既定値が `"sqlite"` である旨を明記する最小のdocstringを追加する（design.md D5）
- [x] 2.4 `_adapter_for` / `src/dogdb/adapters/__init__.py` / `DuckDBAdapter` 本体は変更しないことを確認する（design.md D3: いずれも `duckdb` をimportしないため対象外）

## 3. ドキュメント更新

- [x] 3.1 `README.md`: クイックスタート（`import duckdb` を使う例）の直前に `pip install "dogdb[duckdb]"` のインストール行を追記する
- [x] 3.2 `README.md`: 「バックエンド別の接続表面」節の導入文へ、`connect()` の既定バックエンドがSQLiteである旨を追記する
- [x] 3.3 `README.md`: クイックスタート直後の `connect()` 案内文（`backend="sqlite"` / `backend="duckdb"` の説明行）を、既定値の言及を含む形へ更新する
- [x] 3.4 `examples/` 配下に `dogdb.connect()` 呼び出しや既定バックエンドを前提にした表記が無いことを確認する（現状ゼロ件。あれば同様に更新する）

## 4. テスト

- [x] 4.1 `sys.modules` monkeypatchでduckdb未導入を再現し、`import dogdb` とSQLite経由の最小フロー（`dogdb.connect(seed=...)` の既定呼び出しを含む）が成功することを検証するテストを追加する
- [x] 4.2 同様のmonkeypatchで `dogdb.connect(backend="duckdb", seed=...)` を呼び、案内付き `ImportError` が送出されることを検証するテストを追加する
- [x] 4.3 上記4.2のテストで、`ImportError` メッセージに `pip install "dogdb[duckdb]"` が含まれること、および `__cause__`（chainされた元の `ImportError`）が設定されていることを検証する
- [x] 4.4 既存テストスイートを実行し、全て従来どおり通過することを確認する（`.venv/bin/pytest`）

## 5. 検証

- [x] 5.1 `openspec validate --change duckdb-extras-sqlite-default`（形式が異なる場合は `openspec validate duckdb-extras-sqlite-default`）を実行しエラーがないことを確認する
- [x] 5.2 duckdb除去後の `[project] dependencies` にsqlglot（W6-1でマージ済み）が維持されていることを差分で確認する

## 6. GitHub連携

- [ ] 6.1 issue #21 へ完了コメントを投稿しクローズする（PRマージ後）
- [ ] 6.2 統括issue #19 のW6-2チェックボックスを更新する（PRマージ後）
