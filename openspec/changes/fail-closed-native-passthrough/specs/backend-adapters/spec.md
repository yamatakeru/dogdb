# backend-adapters — delta: fail-closed-native-passthrough

## ADDED Requirements

### Requirement: SQL実行能力集合の宣言
各バックエンドアダプタは、生接続上でSQL文字列または同等のクエリ表現を実行しうる入口メソッド名の閉じた集合を宣言しなければならない（SHALL）。この集合はアダプタ側で定義し、core にバックエンド固有の名前をハードコードしてはならない（MUST NOT）。集合はプロキシの誘導メッセージ生成と、opt-out転送時の統計分類に使用される（SHALL）。集合に含まれない名前は「宣言外」として扱い、個別名では計数しない（SHALL）。

#### Scenario: DuckDBアダプタの宣言
- **WHEN** DuckDBアダプタのSQL実行能力集合を参照する
- **THEN** 少なくとも `cursor` と `sql` が含まれ、`commit` / `rollback` / `close` は含まれない

#### Scenario: SQLiteアダプタの宣言
- **WHEN** SQLiteアダプタのSQL実行能力集合を参照する
- **THEN** 少なくとも `cursor` と `executescript` が含まれる
