# dbapi-proxy 差分 — バックエンド忠実表面への分岐

## ADDED Requirements

### Requirement: SQLite表面の忠実性
SQLite接続をラップしたプロキシ（SQLiteProxy）の公開表面は、`sqlite3.Connection` の表面と同型でなければならない（SHALL）。`execute(sql, params)` および `executemany(sql, params)` は毎回新規のカーソルプロキシを返さなければならず（MUST）、`execute(sql)` は `cursor().execute(sql)` と同じ観察可能挙動でなければならない（SHALL）。`cursor()` は未実行のカーソルプロキシを返さなければならない（SHALL）。結果状態はカーソルごとに独立でなければならず（MUST）、接続自身が結果状態（`fetchall`／`fetchone`／`fetchmany`／`description`／`rowcount`）を持ってはならない（MUST NOT）。

#### Scenario: executeは毎回独立したカーソルを返す
- **WHEN** SQLiteProxy で `c1 = conn.execute("SELECT 1")` と `c2 = conn.execute("SELECT 2")` を順に実行し、その後 `c1.fetchall()` を呼ぶ
- **THEN** `c1` と `c2` は別オブジェクトであり、`c1.fetchall()` は `SELECT 1` の結果を返す（後続の execute に踏み潰されない）

#### Scenario: 接続レベルの結果取得は存在しない
- **WHEN** SQLiteProxy に対して `conn.fetchall` へアクセスする
- **THEN** 誘導メッセージ付きの `AttributeError` が送出される

#### Scenario: cursor()経由でも介入コアを通る
- **WHEN** SQLiteProxy の `conn.cursor().execute(sql)` と `conn.execute(sql)` を同一seed・同一SQL列で比較する
- **THEN** 生成される decision・障害イベント列は一致する

### Requirement: SQLiteカーソルプロキシの表面
SQLite表面のカーソルプロキシは `execute`（介入コア経由で実行し自身を返す）、`fetchall`、`fetchone`、`fetchmany`、`__iter__`、`description`、`rowcount` を提供しなければならない（SHALL）。`__iter__` と `fetch*` は同一の消費位置を共有しなければならず（MUST）、その挙動は `sqlite3.Cursor` と同型でなければならない（SHALL）。カーソル経由の操作は接続経由の操作と同一の介入コア（decision・障害適用・イベント・統計・論理時計）を通らなければならない（MUST）。

#### Scenario: カーソルのexecuteは自身を返す
- **WHEN** `cur = conn.execute("SELECT ...")` の後に `cur.execute("SELECT ...")` を呼ぶ
- **THEN** 返り値は `cur` 自身であり、結果状態は2回目の実行結果で置き換わる

#### Scenario: イテレーションとfetchは消費位置を共有する
- **WHEN** 3行を返すSELECTの実行後、`next(iter(cur))` で1行消費してから `cur.fetchall()` を呼ぶ
- **THEN** `fetchall()` は残り2行を返す（sqlite3ネイティブと同型）

### Requirement: バックエンド別コンテキストマネージャ意味論
プロキシのコンテキストマネージャ意味論は、ラップ対象バックエンドのネイティブ接続と同型でなければならない（SHALL）。SQLite表面の `__exit__` は、例外なしで抜ける場合 `commit()`、例外で抜ける場合 `rollback()` を行い、接続を close してはならない（MUST NOT）。DuckDB表面の `__exit__` は接続を close しなければならない（SHALL）。

#### Scenario: SQLiteのwithはトランザクション管理
- **WHEN** `with dogdb.wrap(sqlite_conn, seed=1) as conn:` ブロック内でINSERTを実行し、例外なしでブロックを抜ける
- **THEN** 変更はcommitされ、接続は開いたままであり、ブロック後も `conn.execute(...)` が成功する

#### Scenario: SQLiteのwithは例外時にrollbackする
- **WHEN** 同ブロック内でINSERT後に例外を送出してブロックを抜ける
- **THEN** 変更はrollbackされ、接続は開いたままである

#### Scenario: DuckDBのwithはcloseする
- **WHEN** `with dogdb.wrap(duckdb_conn, seed=1) as conn:` ブロックを抜ける
- **THEN** 接続はcloseされる

### Requirement: SQLite表面のネイティブ並走一致
全障害確率0のSQLiteProxyは、同一操作列を素の `sqlite3` 接続に流した場合と表面挙動が一致しなければならない（MUST）。一致の検証対象は最低限、execute 返り値の独立性、カーソルのイテレーション・fetch挙動、`description`・`rowcount`、コンテキストマネージャ意味論を含まなければならない（SHALL）。この並走一致は自動テストとして機械検証されなければならない（MUST）。

#### Scenario: 並走テストが表面同型性を検証する
- **WHEN** 同一の操作列（execute・cursor・fetch各種・イテレーション・with）を素のsqlite3接続と全確率0のSQLiteProxyに流す
- **THEN** 両者の観察可能な表面挙動（返り値の構造・行・description・rowcount・トランザクション状態）は一致する

## MODIFIED Requirements

### Requirement: 接続のラップ
`dogdb.wrap(conn, seed=...)` は、既存のDuckDB/SQLite接続を包むプロキシを返さなければならない（SHALL）。プロキシの公開表面はバックエンドごとに分岐し、それぞれのネイティブ接続の表面と同型でなければならない（SHALL）。両プロキシは同一の介入コア（decision・障害適用・イベント・統計・house・論理時計）を共有しなければならない（MUST）。`seed` は必須引数であり、暗黙の乱数源を持ってはならない（MUST NOT）。便宜関数 `dogdb.connect(path, backend=..., seed=...)` も同じプロキシを返さなければならず（SHALL）、`wrap` と同様に `seed` は必須であり、省略した呼び出しは拒否されなければならない（MUST）。

#### Scenario: DuckDB接続をラップする
- **WHEN** `dogdb.wrap(duckdb.connect(), seed=42)` を呼ぶ
- **THEN** 返るプロキシは `execute` が自身を返し、接続レベルの `fetchall` / `fetchone` / `fetchmany` / `close` を備え、障害が発火しない場合は素の接続と同一の結果を返す

#### Scenario: SQLite接続をラップする
- **WHEN** `dogdb.wrap(sqlite3.connect(":memory:"), seed=42)` を呼ぶ
- **THEN** 返るプロキシは `execute` がカーソルプロキシを返し、`conn.execute(sql).fetchall()` は障害が発火しない場合、素の接続の `conn.execute(sql).fetchall()` と同一の結果を返す

#### Scenario: seed省略はエラー
- **WHEN** `dogdb.wrap(conn)` を seed なしで呼ぶ
- **THEN** `TypeError` または明示的な設定エラーが送出され、接続はラップされない

### Requirement: 未定義属性のfail-closed既定
プロキシは、バックエンドごとに明示的に定義された公開表面以外の属性アクセスを、生接続へ静かに転送してはならない（MUST NOT）。DuckDB表面の公開表面は `execute`、`executemany`、`fetchall`、`fetchone`、`fetchmany`、`description`、`rowcount`、`in_transaction`、`commit`、`rollback`、`close`、`dolly`、およびコンテキストマネージャである（SHALL）。SQLite表面の公開表面は `execute`、`executemany`、`cursor`、`in_transaction`、`commit`、`rollback`、`close`、`dolly`、およびコンテキストマネージャである（SHALL）。既定では、公開表面外の属性アクセスは誘導メッセージ付きの `AttributeError` を送出しなければならない（MUST）。アダプタが宣言したSQL実行能力のある入口名のうち公開表面に含まれないもの（例: DuckDB の `cursor`・`sql`、SQLite の `executescript`）へのアクセスには、`execute()` の使用または `allow_native_passthrough=True` の指定を案内する専用メッセージを含めなければならない（SHALL）。エラーメッセージに生SQLや生パラメータを含んではならない（MUST NOT）。

#### Scenario: DuckDBのSQL実行能力のある入口は誘導付きで拒否される
- **WHEN** 既定設定のDuckDBプロキシに対して `conn.cursor()` または `conn.sql(...)` にアクセスする
- **THEN** `AttributeError` が送出され、メッセージには「DogDBはこの入口に注入できない」旨と `execute()` および `allow_native_passthrough=True` への誘導が含まれる

#### Scenario: SQLiteのcursorは拒否されない
- **WHEN** 既定設定のSQLiteプロキシに対して `conn.cursor()` を呼ぶ
- **THEN** カーソルプロキシが返り、`AttributeError` は送出されない

#### Scenario: 未知属性も拒否される
- **WHEN** 既定設定のプロキシに対して、公開表面にもアダプタ宣言集合にも含まれない属性（例: `conn.interrupt`）にアクセスする
- **THEN** `AttributeError` が送出され、操作は生接続へ到達しない

### Requirement: 拡張設定の受け付けと後方互換
`wrap()` は追加設定として、全障害の重み辞書（既存 `faults` の拡張）、mood設定（有効化・epoch長・係数表）、自動返却設定、clock注入、スコーピング（`only_tables` / `exclude_tables`）を受け付けなければならない（SHALL）。すべての追加設定は省略可能でなければならない（MUST）。省略時、追加機能はすべて無効であり、介入コアの挙動（decision・イベントの種類・順序・既存フィールドの値）は追加設定の導入前と一致しなければならない（MUST）。公開表面の形状は本仕様のバックエンド別表面要件に従う（SHALL）。破壊的変更は破壊的変更ポリシー（タグ前は許可・ADR節必須、タグ後は禁止）に従わなければならない（MUST）。

#### Scenario: 旧設定のままなら介入コアは旧挙動
- **WHEN** MVP時代と同じ引数（seed・session_id・faults）だけで `wrap()` を呼び、同一SQL列を実行する
- **THEN** 追加機能はすべて無効で、イベントの種類・順序・既存フィールドの値は追加設定導入前の実装と一致する（wire-level差分は `schema_version` のみ）

#### Scenario: 未知の障害名は拒否する
- **WHEN** `faults={"ZOOMIES": 1}` のように未定義の障害名を渡す
- **THEN** 明示的な設定エラーが送出され、接続はラップされない
