# dbapi-proxy — DB-APIプロキシの公開表面

## Purpose

既存のDuckDB/SQLite接続を決定的な障害注入機能付きDB-APIプロキシとして公開し、通常の取得操作、トランザクション、およびDogDB固有の管理操作に一貫したインターフェースを提供する。

## Requirements

### Requirement: 接続のラップ
`dogdb.wrap(conn, seed=...)` は、既存のDuckDB/SQLite接続を包むDB-API互換プロキシを返さなければならない（SHALL）。`seed` は必須引数であり、暗黙の乱数源を持ってはならない（MUST NOT）。便宜関数 `dogdb.connect(path, backend=..., seed=...)` も同じプロキシを返さなければならず（SHALL）、`wrap` と同様に `seed` は必須であり、省略した呼び出しは拒否されなければならない（MUST）。

#### Scenario: DuckDB接続をラップする
- **WHEN** `dogdb.wrap(duckdb.connect(), seed=42)` を呼ぶ
- **THEN** 返るオブジェクトは `execute` / `fetchall` / `fetchone` / `fetchmany` / `close` を備え、障害が発火しない場合は素の接続と同一の結果を返す

#### Scenario: seed省略はエラー
- **WHEN** `dogdb.wrap(conn)` を seed なしで呼ぶ
- **THEN** `TypeError` または明示的な設定エラーが送出され、接続はラップされない

### Requirement: 論理結果セットへの一回介入
障害の適用は操作（`execute` 1回）につき論理結果セットに対して一度だけ行われなければならない（MUST）。`fetchall` / `fetchone` ループ / `fetchmany` のいずれで消費しても、同一の決定キーに対する障害適用結果は同一でなければならない（MUST）。

#### Scenario: fetch方式によらず同一の障害結果
- **WHEN** 同一seed・同一クエリ列を、一方は `fetchall`、他方は `fetchone` ループで消費する
- **THEN** 隠された行・並び順・発生イベント列は両者で一致する

### Requirement: 対応範囲外操作の素通し
`executemany`、名前付きパラメータを使う操作、およびSQL分類器が分類できなかった文は、障害注入なしでバックエンドへ素通ししなければならない（SHALL）。素通しは静かに行い、操作自体を失敗させてはならない（MUST NOT）。

#### Scenario: executemanyは無介入
- **WHEN** `executemany("INSERT INTO t VALUES (?)", rows)` を実行する
- **THEN** 全行が挿入され、fault イベントは一件も記録されない

### Requirement: conn.dolly 名前空間
ドリー操作はプロキシの `dolly` 属性に隔離されなければならない（SHALL）。最低限 `house()`（宝物一覧）、`return_all()`、`return_treasure(treasure_id)`、`log()`（イベント一覧）を提供しなければならない（SHALL）。

#### Scenario: STASH後にハウスを確認する
- **WHEN** STASHが発火した後に `conn.dolly.house()` を呼ぶ
- **THEN** 隠された宝物のエントリ（treasure_id、対象クエリのfingerprint、行位置を含む）が返る

### Requirement: トランザクションの素通し
`BEGIN` / `COMMIT` / `ROLLBACK` および接続の `commit()` / `rollback()` は無改変でバックエンドへ委譲しなければならない（SHALL）。MVPの障害はトランザクション状態を変更してはならない（MUST NOT）。

#### Scenario: トランザクション内のクエリが正常に確定する
- **WHEN** トランザクション内でINSERTを実行し `commit()` する
- **THEN** データは素の接続と同様に永続化される
