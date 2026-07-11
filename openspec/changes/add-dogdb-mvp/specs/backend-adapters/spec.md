# backend-adapters — アダプタ契約とDuckDB/SQLite実装

## ADDED Requirements

### Requirement: アダプタ契約と論理結果セット
バックエンドアダプタは `execute(sql, params) -> LogicalResult`、`close()`、`in_transaction` プロパティを実装しなければならない（MUST）。`LogicalResult` は列名リスト、タプルの行リスト、rowcount を持つバックエンド中立の構造でなければならない（SHALL）。DogDB core（決定エンジン、障害変換、house、イベントログ）はバックエンドモジュールをimportしてはならない（MUST NOT）。

#### Scenario: coreはバックエンドを知らない
- **WHEN** coreパッケージの依存関係を静的に検査する
- **THEN** `duckdb` および `sqlite3` への参照はアダプタモジュール以外に存在しない

### Requirement: DuckDBアダプタ
DuckDBアダプタは、DuckDB Python接続の実行結果（`description`、fetch結果）を `LogicalResult` に正規化しなければならない（SHALL）。

#### Scenario: DuckDBの結果が正規化される
- **WHEN** DuckDBアダプタ経由で `SELECT 1 AS x, 'a' AS y` を実行する
- **THEN** `LogicalResult.columns == ["x", "y"]` かつ行はタプルのリストである

### Requirement: SQLiteアダプタ
SQLiteアダプタは、標準ライブラリ `sqlite3` の実行結果を `LogicalResult` に正規化しなければならない（SHALL）。追加の実行時依存を導入してはならない（MUST NOT）。

#### Scenario: SQLiteの結果が正規化される
- **WHEN** SQLiteアダプタ経由で同一クエリを実行する
- **THEN** DuckDBアダプタと同一構造の `LogicalResult` が得られる

### Requirement: 共通適合テストスイート
両アダプタは同一のシナリオスイート（スキーマ作成、データ投入、各障害の発火と検証）を通過しなければならない（MUST）。同一seed・同一SQL列に対する障害イベント列（fault、decision_key、outcome）は両バックエンドで一致しなければならない（MUST）。

#### Scenario: ドリーはDBを差別しない
- **WHEN** 共通適合スイートを同一seedでDuckDBとSQLiteに対して実行する
- **THEN** 両者のイベントログは診断用タイムスタンプとbackend識別子を除いて一致する
