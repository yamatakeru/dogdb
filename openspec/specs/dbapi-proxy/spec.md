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

### Requirement: 拡張設定の受け付けと後方互換
`wrap()` は追加設定として、全障害の重み辞書（既存 `faults` の拡張）、mood設定（有効化・epoch長・係数表）、自動返却設定、clock注入、スコーピング（`only_tables` / `exclude_tables`）を受け付けなければならない（SHALL）。すべての追加設定は省略可能で、省略時の挙動は本change導入前と完全に一致しなければならない（MUST）。既存の公開APIに **BREAKING** な変更を加えてはならない（MUST NOT）。

#### Scenario: 旧設定のままなら旧挙動
- **WHEN** MVP時代と同じ引数（seed・session_id・faults）だけで `wrap()` を呼ぶ
- **THEN** 追加機能はすべて無効で、実行結果・イベントの種類・順序・既存フィールドの値は本change導入前の実装と一致する。唯一の意図的なwire-level差分は `schema_version` が `2` になることである

#### Scenario: 未知の障害名は拒否する
- **WHEN** `faults={"ZOOMIES": 1}` のように未定義の障害名を渡す
- **THEN** 明示的な設定エラーが送出され、接続はラップされない

### Requirement: 分類・介入統計の参照
`conn.dolly.stats()` は、匿名fingerprint単位の分類結果（分類済みSELECT数、UNKNOWN数、介入された操作数）を構造化オブジェクトで返さなければならない（SHALL）。統計に生SQLや生パラメータを含んではならない（MUST NOT）。

#### Scenario: corpusの介入率を測る
- **WHEN** アプリのクエリ列を流した後に `conn.dolly.stats()` を呼ぶ
- **THEN** fingerprintごとの分類内訳と介入数が得られ、UNKNOWN率からparser導入判断の材料が取れる
