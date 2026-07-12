# backend-adapters — delta for duckdb-cursor-clone-wrap

## MODIFIED Requirements

### Requirement: アダプタ契約と論理結果セット
バックエンドアダプタは `execute(sql, params) -> LogicalResult`、`executemany(sql, params) -> LogicalResult`、`close()`、`in_transaction` プロパティを実装しなければならない（MUST）。`LogicalResult` は列名リスト、タプルの行リスト、rowcount、および省略可能な列型情報（バックエンドが `description` の第2スロットで返した値の列。型情報を返さないバックエンドでは None）を持つバックエンド中立の構造でなければならない（SHALL）。core は列型情報を不透明な値として扱い、その内容や表現形式に依存してはならない（MUST NOT）。DogDB core（決定エンジン、障害変換、house、イベントログ）はバックエンドモジュールをimportしてはならない（MUST NOT）。

#### Scenario: coreはバックエンドを知らない
- **WHEN** coreパッケージの依存関係を静的に検査する
- **THEN** `duckdb` および `sqlite3` への参照はアダプタモジュール以外に存在しない

### Requirement: DuckDBアダプタ
DuckDBアダプタは、DuckDB Python接続の実行結果（`description`、fetch結果）を `LogicalResult` に正規化しなければならない（SHALL）。正規化では、`description` 第2スロットの型情報を無変換で `LogicalResult` の列型情報として保存しなければならない（SHALL）。

#### Scenario: DuckDBの結果が正規化される
- **WHEN** DuckDBアダプタ経由で `SELECT 1 AS x, 'a' AS y` を実行する
- **THEN** `LogicalResult.columns == ["x", "y"]` かつ行はタプルのリストであり、列型情報にはネイティブ `description` 第2スロットの値がそのまま保存されている
