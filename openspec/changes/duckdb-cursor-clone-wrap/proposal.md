# duckdb-cursor-clone-wrap

## Why

W2（backend-faithful-surfaces）で DuckDB の `cursor()` は「W4-a まで暫定 fail-closed」とされた。しかし duckdb の `cursor()` はネイティブでクローン接続（独立トランザクション文脈を持つ新しい DuckDBPyConnection）を返す正当な公開表面であり、fail-closed のままでは `cursor()` を使う本番コード経路に障害を流せない。バックエンド忠実原則（決定性 ＞ 宣言表面の忠実性 ＞ 利便性）に従い、クローンを注入対象として包み直す。あわせて、duckdb はネイティブの `description` 第2スロットで型情報を返すのに対し現行実装はこれを `None` に潰しており、忠実性の欠落として同時に解消する。

## What Changes

- `DuckDBProxy` に `cursor()` を新設する。ネイティブの `connection.cursor()`（クローン接続）を新しい `DuckDBProxy` で包み直して返す（現状は `sql_capable_attrs` 経由の誘導付き fail-closed）。
- クローンは親と介入コア（DecisionEngine・EventLog・HouseLedger・FaultEngine・stats・論理時計）を**共有**する。セッション＝「全カーソル横断の execute 呼び出しの全順序」であり、occurrence はセッション共有のまま、`POLICY_VERSION` は据え置き。
- トランザクション分離（親の未コミット変更がクローンから見えない等）はバックエンドの性質であり、DogDB は関知しない（契約文書に明記するのみ）。
- duckdb `description` の型情報（第2スロット）を透過する。アダプタの `materialize()` が型を保存し、`LogicalResult` が運び、`DuckDBProxy` の `description` が露出する。sqlite3 はネイティブでも `(name, None×6)` のため、SQLite 側は現状維持が忠実。
- `sql()` / `query` / `table`（relation API）は引き続き fail-closed（遅延評価 relation は呼び出し回数≠実行回数のため注入対象外を維持）。
- 加算的・非破壊（W2 時点の暫定 fail-closed を解除する方向。エラーだった入口が機能するようになる）。

### Non-goals

- relation API（`sql`/`query`/`table`）の注入対応。
- SQLite 側 `description` の変更（`(name, None×6)` がネイティブ忠実）。
- クローン間のトランザクション整合の管理・検出（バックエンドの性質として不関知）。
- マルチスレッド並行実行での決定性保証（従来どおり単一スレッド前提）。

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

- `dbapi-proxy`: DuckDB 表面の公開表面に `cursor` を追加し、fail-closed の対象から外す。`cursor()` が返すクローンプロキシが親と同一の介入コアを共有する Requirement、および DuckDB `description` の型情報透過の Requirement を追加する。
- `backend-adapters`: DuckDB アダプタの正規化要件に `description` 型情報（第2スロット）の保存を追加する（`LogicalResult` の列表現の拡張）。

## Impact

- `src/dogdb/proxy/connection.py`: `DuckDBProxy.cursor()` 新設、既存 engine を再利用する生成経路（現状 `_EngineBackedSurface.__init__` は常に新規 engine を生成）、`DuckDBProxy.description` の型透過。
- `src/dogdb/adapters/base.py`: `materialize()` が `description` 第0スロットのみ抽出している箇所の拡張。
- `src/dogdb/core/models.py`: `LogicalResult` に型情報を運ぶ表現の追加（core 中立を維持）。
- `tests/test_native_passthrough.py`: `test_fail_closed_duckdb_cursor_does_not_reach_native_connection` は仕様反転のため置換。`sql` の fail-closed テストは維持。
- `tests/`: 親子で EventLog・House・decision 共有の決定性テスト（同一入力列→同一イベント列）、description 型透過テストを新設（合格ゲート）。
- `openspec/specs/dbapi-proxy/spec.md`・`openspec/specs/backend-adapters/spec.md`: delta による要件更新。
- `docs/contract-v2.md`（cursor/sql の fail-closed 記述）・`README.md`: 追随更新。
