# backend-adapters — delta: max-result-rows-safeguard

## MODIFIED Requirements

### Requirement: アダプタ契約と論理結果セット
バックエンドアダプタは `execute(sql, params, *, row_cap: int | None = None) -> LogicalResult`、`executemany(sql, params) -> LogicalResult`、`close()`、`in_transaction` プロパティを実装しなければならない（MUST）。`row_cap` は省略可能なキーワード専用引数であり、`None`（既定）の場合、`execute` は本要件の `row_cap` 導入前と完全に同一の挙動（全行のmaterialize）を維持しなければならない（MUST）。`LogicalResult` は列名リスト、タプルの行リスト、rowcount、および省略可能な列型情報（バックエンドが `description` の第2スロットで返した値の列。型情報を返さないバックエンドでは None）を持つバックエンド中立の構造でなければならない（SHALL）。core は列型情報を不透明な値として扱い、その内容や表現形式に依存してはならない（MUST NOT）。DogDB core（決定エンジン、障害変換、house、イベントログ）はバックエンドモジュールをimportしてはならない（MUST NOT）。

#### Scenario: coreはバックエンドを知らない
- **WHEN** coreパッケージの依存関係を静的に検査する
- **THEN** `duckdb` および `sqlite3` への参照はアダプタモジュール以外に存在しない

#### Scenario: row_cap省略時は挙動不変
- **WHEN** `row_cap` を指定せずに `execute(sql, params)` を呼ぶ
- **THEN** 返る `LogicalResult` は `row_cap` 導入前と同一であり、結果は全行materializeされる

## ADDED Requirements

### Requirement: row_capによる中断的execute
アダプタの `execute` は、`row_cap` に正の整数が指定された場合、`fetchall` による一括取得ではなく `fetchmany` ループで結果を取得しなければならない（MUST）。取得の過程で `row_cap + 1` 行目を観測した時点で、それ以降の行を取得せずに取得を中断しなければならない（MUST）。中断した場合、アダプタは `LogicalResult` を返してはならず（MUST NOT）、呼び出し側が識別できる中断シグナルを送出しなければならない（SHALL）。中断はSQLite・DuckDB両アダプタで同一の観測可能挙動（何行目で中断するか）を持たなければならない（MUST）。`description` が `None` の文（行を返さない文）には中断は発生しない（SHALL NOT）。

#### Scenario: 上限+1行目で中断する
- **WHEN** `row_cap=2` を指定して3行を返すSELECTを `execute(sql, params, row_cap=2)` 経由で実行する
- **THEN** アダプタは3行目を観測した時点で取得を中断し、`LogicalResult` を返さず、呼び出し側へ中断シグナルを送出する

#### Scenario: 上限ちょうどは中断しない
- **WHEN** `row_cap=3` を指定して3行を返すSELECTを実行する
- **THEN** アダプタは中断せず、3行分の `LogicalResult` を通常どおり返す

#### Scenario: 両バックエンドで中断行数が一致する
- **WHEN** 同一 `row_cap` と同一件数の結果を返すSELECTを、SQLiteアダプタとDuckDBアダプタそれぞれで実行する
- **THEN** 両アダプタとも同じ行数目（`row_cap + 1` 行目）を観測した時点で中断する
