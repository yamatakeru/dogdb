# fail-closed-native-passthrough — Tasks

## 1. アダプタの能力集合宣言

- [ ] 1.1 `adapters/base.py` に能力集合の契約（型と既定）を追加し、`DuckDBAdapter` に `sql_capable_attrs`（最低限 `cursor`, `sql` を含む閉集合。`commit`/`rollback`/`close` は含めない）、`SQLiteAdapter` に同（最低限 `cursor`, `executescript`）を宣言する
- [ ] 1.2 core がこの集合を名前として参照するだけでバックエンド名をハードコードしないことを確認する（`grep -rE "duckdb|sqlite" src/dogdb/core/ src/dogdb/proxy/` でアダプタ経由以外の参照が増えていないこと）

## 2. プロキシの fail-closed 化

- [ ] 2.1 `wrap()` に `allow_native_passthrough: bool = False` を追加し、`DBAPIProxy` へ伝搬する
- [ ] 2.2 `__getattr__` を差し替える: 既定では、アダプタ宣言集合内の名前に専用誘導メッセージ、それ以外の未知属性に汎用誘導メッセージを持つ `AttributeError` を送出する（メッセージに生SQL・生パラメータを含めない）
- [ ] 2.3 `allow_native_passthrough=True` の経路を実装する: 宣言集合内の callable は呼び出し時に stats を増分する薄いラッパで返し、宣言外は素のまま転送して集約カウンタ（`other`）で数える
- [ ] 2.4 `StatsTracker` に `escape_hatches` 集計（名前→呼び出し数、および `other`）を追加し、`dolly.stats()` の返り値に含める

## 3. 検証

- [ ] 3.1 fail-closed 回帰テストを追加する: 既定設定で `conn.cursor` / DuckDB `conn.sql` へのアクセスが誘導メッセージ付き `AttributeError` になり、生接続へ到達しないこと（両バックエンド）。実行: `uv run pytest tests/ -k "fail_closed or passthrough"`
- [ ] 3.2 未知属性（例: `conn.interrupt`）も既定で拒否されるテストを追加する
- [ ] 3.3 opt-out テストを追加する: `allow_native_passthrough=True` で `conn.cursor()` が生カーソルを返し、`stats()["escape_hatches"]["cursor"] == 1` になること
- [ ] 3.4 `hasattr(conn, "cursor")` だけでは計数が増えないテストを追加する（MUST NOT の検証）
- [ ] 3.5 既存テストスイート全通過を確認する（`uv run pytest`）。特に `conn._connection` 等の内部属性直接参照（test_conformance.py）が影響を受けていないこと
- [ ] 3.6 spec delta の検証: `openspec validate --change "fail-closed-native-passthrough"` が通ること

## 4. ドキュメント更新

- [ ] 4.1 README の「限界と安全上の前提」に、対応入口の一覧・未知属性の既定拒否・`allow_native_passthrough` の存在と「転送経路は注入対象外」である旨を追記する
- [ ] 4.2 `docs/contract-v2.md` に escape hatch 統計の意味（呼び出し数であり実行SQL数ではない。DuckDB `sql()` の遅延評価により回数≠実行数）を追記する
- [ ] 4.3 GitHub issue #3 に完了コメントを残し、統括 #11 のチェックボックスを更新する
