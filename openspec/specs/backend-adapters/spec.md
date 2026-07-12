# backend-adapters — アダプタ契約とDuckDB/SQLite実装

## Purpose

DogDB coreからバックエンド固有処理を分離し、DuckDBとSQLiteで共通の論理結果と障害動作を提供する。

## Requirements

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
両アダプタは同一のシナリオスイート（スキーマ作成、データ投入、各障害の発火と検証）を通過しなければならない（MUST）。同一seed・同一SQL列に対する障害イベント列（fault、decision_key、outcome）は両バックエンドで一致しなければならない（MUST）。この一致要件はバックエンドの自然な行順序に依存しない — イベントは行値を含まず、行位置は決定キーのみから導出されるため、ORDER BYのないクエリで両バックエンドが異なる順序の行を返してもイベント列は同一になる。

#### Scenario: ドリーはDBを差別しない
- **WHEN** 共通適合スイートを同一seedでDuckDBとSQLiteに対して実行する
- **THEN** 両者のイベントログは診断用タイムスタンプとbackend識別子を除いて一致する

### Requirement: SQL実行能力集合の宣言
各バックエンドアダプタは、生接続上でSQL文字列または同等のクエリ表現を実行しうる入口メソッド名の閉じた集合を宣言しなければならない（SHALL）。この集合はアダプタ側で定義し、core にバックエンド固有の名前をハードコードしてはならない（MUST NOT）。集合はプロキシの誘導メッセージ生成と、opt-out転送時の統計分類に使用される（SHALL）。集合に含まれない名前は「宣言外」として扱い、個別名では計数しない（SHALL）。

#### Scenario: DuckDBアダプタの宣言
- **WHEN** DuckDBアダプタのSQL実行能力集合を参照する
- **THEN** 少なくとも `cursor` と `sql` が含まれ、`commit` / `rollback` / `close` は含まれない

#### Scenario: SQLiteアダプタの宣言
- **WHEN** SQLiteアダプタのSQL実行能力集合を参照する
- **THEN** 少なくとも `cursor` と `executescript` が含まれる
