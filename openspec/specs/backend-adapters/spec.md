# backend-adapters — アダプタ契約とDuckDB/SQLite実装

## Purpose

DogDB coreからバックエンド固有処理を分離し、DuckDBとSQLiteで共通の論理結果と障害動作を提供する。

## Requirements

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

### Requirement: SQLiteアダプタ
SQLiteアダプタは、標準ライブラリ `sqlite3` の実行結果を `LogicalResult` に正規化しなければならない（SHALL）。追加の実行時依存を導入してはならない（MUST NOT）。

#### Scenario: SQLiteの結果が正規化される
- **WHEN** SQLiteアダプタ経由で同一クエリを実行する
- **THEN** DuckDBアダプタと同一構造の `LogicalResult` が得られる

### Requirement: 共通適合テストスイート
両アダプタは同一のシナリオスイート（スキーマ作成、データ投入、各障害の発火と検証）を通過しなければならない（MUST）。バックエンド間の一致要件は介入コアに限定される（SHALL）: 同一seed・同一session_id・同一障害設定・同一SQL列に対するdecisionとイベントログは、診断用タイムスタンプとbackend識別子を除いて両バックエンドで一致しなければならない（MUST）。このイベントログ一致はバックエンドの自然な行順序に依存しない — イベントは行値を含まず、詳細フィールド（行位置・件数・treasure_id 等）も決定キーと結果件数のみから導出されるため、ORDER BYのないクエリで両バックエンドが異なる順序の行を返してもイベントログは同一になる（SHALL）。論理結果への障害適用結果の一致は、ORDER BY等で行順序が決定的に定まるクエリに対して要求される（MUST）。行順序が定まらないクエリでは、行位置に基づく障害が両バックエンドの異なる論理行へ適用されうるため、障害適用後の行内容の一致は要求されない（SHALL NOT）。公開表面の挙動（execute の返り値型、結果取得の入口、コンテキストマネージャ意味論）はバックエンド間の一致対象ではなく（SHALL NOT）、各バックエンドのネイティブ表面との同型性で検証される（SHALL）。

#### Scenario: ドリーはDBを差別しない
- **WHEN** 共通適合スイートを同一seedでDuckDBとSQLiteに対して実行する
- **THEN** 両者のイベントログは診断用タイムスタンプとbackend識別子を除いて一致する

#### Scenario: 表面が分岐しても介入コアは一致する
- **WHEN** 同一seed・同一session_id・同一障害設定で、ORDER BYにより行順序が決定的に定まる同一SQL列を、DuckDBプロキシ（接続レベルfetch）とSQLiteプロキシ（カーソル経由fetch）というそれぞれの表面で実行する
- **THEN** 障害適用後の論理結果（隠蔽・値変異・行順序を含む）と障害イベント列は両バックエンドで一致する

### Requirement: SQL実行能力集合の宣言
各バックエンドアダプタは、生接続上でSQL文字列または同等のクエリ表現を実行しうる入口メソッド名の閉じた集合を宣言しなければならない（SHALL）。この集合はアダプタ側で定義し、core にバックエンド固有の名前をハードコードしてはならない（MUST NOT）。集合はプロキシの誘導メッセージ生成と、opt-out転送時の統計分類に使用される（SHALL）。集合に含まれない名前は「宣言外」として扱い、個別名では計数しない（SHALL）。

#### Scenario: DuckDBアダプタの宣言
- **WHEN** DuckDBアダプタのSQL実行能力集合を参照する
- **THEN** 少なくとも `cursor` と `sql` が含まれ、`commit` / `rollback` / `close` は含まれない

#### Scenario: SQLiteアダプタの宣言
- **WHEN** SQLiteアダプタのSQL実行能力集合を参照する
- **THEN** 少なくとも `cursor` と `executescript` が含まれる
