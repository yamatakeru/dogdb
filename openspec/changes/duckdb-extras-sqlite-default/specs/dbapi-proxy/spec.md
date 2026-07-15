## MODIFIED Requirements

### Requirement: 接続のラップ
`dogdb.wrap(conn, seed=...)` は、既存のDuckDB/SQLite接続を包むプロキシを返さなければならない（SHALL）。プロキシの公開表面はバックエンドごとに分岐し、それぞれのネイティブ接続の表面と同型でなければならない（SHALL）。両プロキシは同一の介入コア（decision・障害適用・イベント・統計・house・論理時計）を共有しなければならない（MUST）。`seed` は必須引数であり、暗黙の乱数源を持ってはならない（MUST NOT）。便宜関数 `dogdb.connect(path, backend=..., seed=...)` も同じプロキシを返さなければならず（SHALL）、`wrap` と同様に `seed` は必須であり、省略した呼び出しは拒否されなければならない（MUST）。`dogdb.connect()` の `backend` を省略した場合の既定値は `"sqlite"` でなければならず（MUST）、追加のパッケージ導入なしに成功しなければならない（SHALL）。`backend="duckdb"` が指定され、かつ `duckdb` パッケージが利用不能な環境では、`connect()` は元の `ImportError` をchainした `ImportError` を送出しなければならず（MUST）、そのメッセージには `pip install "dogdb[duckdb]"` によるインストール手順を明記しなければならない（SHALL）。

#### Scenario: DuckDB接続をラップする
- **WHEN** `dogdb.wrap(duckdb.connect(), seed=42)` を呼ぶ
- **THEN** 返るプロキシは `execute` が自身を返し、接続レベルの `fetchall` / `fetchone` / `fetchmany` / `close` を備え、障害が発火しない場合は素の接続と同一の結果を返す

#### Scenario: SQLite接続をラップする
- **WHEN** `dogdb.wrap(sqlite3.connect(":memory:"), seed=42)` を呼ぶ
- **THEN** 返るプロキシは `execute` がカーソルプロキシを返し、`conn.execute(sql).fetchall()` は障害が発火しない場合、素の接続の `conn.execute(sql).fetchall()` と同一の結果を返す

#### Scenario: seed省略はエラー
- **WHEN** `dogdb.wrap(conn)` を seed なしで呼ぶ
- **THEN** `TypeError` または明示的な設定エラーが送出され、接続はラップされない

#### Scenario: backend省略時はSQLiteに接続する
- **WHEN** `duckdb` パッケージが利用不能な環境で `dogdb.connect(seed=42)` を `backend` 省略で呼ぶ
- **THEN** 呼び出しは成功し、返るプロキシはSQLite表面（`SQLiteProxy`）である

#### Scenario: duckdb未導入時のbackend="duckdb"は案内付きImportError
- **WHEN** `duckdb` パッケージが利用不能な環境で `dogdb.connect(backend="duckdb", seed=42)` を呼ぶ
- **THEN** 元の `ImportError` をchainした `ImportError` が送出され、メッセージには `pip install "dogdb[duckdb]"` が含まれる
