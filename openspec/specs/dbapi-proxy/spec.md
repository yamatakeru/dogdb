# dbapi-proxy — DB-APIプロキシの公開表面

## Purpose

既存のDuckDB/SQLite接続を決定的な障害注入機能付きDB-APIプロキシとして公開し、通常の取得操作、トランザクション、およびDogDB固有の管理操作に一貫したインターフェースを提供する。

## Requirements

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

### Requirement: 介入上限の意味論
`wrap()` は省略可能な引数 `max_intervention_rows`（既定 10,000）を受け付けなければならない（SHALL）。この値は on_result 障害を適用してよい materialize 済み結果の行数上限であり、取得件数・保持メモリの上限ではない（SHALL）。上限を超えた結果は切り詰めてはならず（MUST NOT）、既定では無改変で呼び出し側へ返し、`limit_exceeded` イベントを記録しなければならない（SHALL）。この意味論（メモリ保護ではないこと）は契約文書と README に明記しなければならない（SHALL）。

#### Scenario: 上限超過でも全行が返る
- **WHEN** `max_intervention_rows=2` の設定で3行を返すSELECTを実行する
- **THEN** 3行すべてが無改変で返り、fault は適用されず、`limit_exceeded` イベントが記録される

### Requirement: 上限超過時の任意エラー化
`wrap()` は省略可能な引数 `on_max_rows`（既定 `"skip"`、許容値 `"skip"` / `"error"`）を受け付けなければならない（SHALL）。`"error"` の場合、上限超過時に `limit_exceeded` イベントを記録した後、`DogDBError` 派生の構造化例外を送出しなければならない（SHALL）。この例外はバックエンドでの実行完了後に発生するものであり、その意味論（実行済みなのに例外）を契約文書に明記しなければならない（SHALL）。例外の送出は設定値と結果行数のみの純粋関数でなければならない（MUST）。

#### Scenario: errorモードは記録してから送出する
- **WHEN** `on_max_rows="error"` かつ `max_intervention_rows=2` の設定で3行を返すSELECTを実行する
- **THEN** `limit_exceeded` イベントが記録された上で `DogDBError` 派生例外が送出され、例外は `event_id` と `retryable` を持つ

### Requirement: イベントログ出力先の一意性
イベントログのファイル出力先を指定する `wrap()` の引数は `log_path` の一つでなければならない（SHALL）。同義のエイリアス引数を提供してはならない（MUST NOT）。

#### Scenario: 出力先指定はlog_pathのみ
- **WHEN** `wrap(raw, seed=1, event_log="x.jsonl")` を呼ぶ
- **THEN** `TypeError`（未知の引数）が送出され、接続はラップされない

### Requirement: 論理結果セットへの一回介入
障害の適用は操作（`execute` 1回）につき論理結果セットに対して一度だけ行われなければならない（MUST）。`fetchall` / `fetchone` ループ / `fetchmany` のいずれで消費しても、同一の決定キーに対する障害適用結果は同一でなければならない（MUST）。

#### Scenario: fetch方式によらず同一の障害結果
- **WHEN** 同一seed・同一クエリ列を、一方は `fetchall`、他方は `fetchone` ループで消費する
- **THEN** 隠された行・並び順・発生イベント列は両者で一致する

### Requirement: 対応範囲外操作の素通し
`executemany`、名前付きパラメータを使う操作、SQL分類器が分類できなかった文、およびパラメータfingerprintの入力域外の値を含む操作は、障害注入なしでバックエンドへ素通ししなければならない（SHALL）。素通しは静かに行い、操作自体を失敗させてはならない（MUST NOT）。素通し操作でも mood／自動返却の論理時計は前進しなければならない（SHALL）。素通し操作は occurrence を消費せず、decision・イベントを生成してはならない（MUST NOT）。素通しの発生は `conn.dolly.stats()` の素通し集計（入力域外パラメータについては `unsupported_parameter_type`）に記録されなければならず（SHALL）、集計に生パラメータや型名の値を含んではならない（MUST NOT）。

#### Scenario: executemanyは無介入
- **WHEN** `executemany("INSERT INTO t VALUES (?)", rows)` を実行する
- **THEN** 全行が挿入され、fault イベントは一件も記録されない

#### Scenario: 入力域外パラメータは実行を止めない
- **WHEN** 全障害確率0のプロキシで、生ドライバが受理する独自型パラメータのSELECTを実行する
- **THEN** 生接続と同一の結果が返り、`stats()` の `unsupported_parameter_type` が1増える

#### Scenario: 素通しでも論理時計は進む
- **WHEN** `auto_return={"min_operations": 1, "max_operations": 1}` のセッションでSTASHの宝物が存在する状態で、入力域外パラメータの操作を実行する
- **THEN** 論理操作数は前進し、自動返却の判定は素通し操作を1操作として数える

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

### Requirement: SQLite表面の忠実性
SQLite接続をラップしたプロキシ（SQLiteProxy）の公開表面は、宣言した対応表面の範囲で、対応する `sqlite3.Connection` の操作と同型でなければならない（SHALL）。対応表面外の属性は「未定義属性のfail-closed既定」要件に従い、row_factory 等の非対応は明示的不忠実として文書化しなければならない（SHALL）。`execute(sql, params)` および `executemany(sql, params)` は毎回新規のカーソルプロキシを返さなければならず（MUST）、`execute(sql)` は `cursor().execute(sql)` と同じ観察可能挙動でなければならない（SHALL）。`cursor()` は未実行のカーソルプロキシを返さなければならない（SHALL）。結果状態はカーソルごとに独立でなければならず（MUST）、接続自身が結果状態（`fetchall`／`fetchone`／`fetchmany`／`description`／`rowcount`）を持ってはならない（MUST NOT）。

#### Scenario: executeは毎回独立したカーソルを返す
- **WHEN** SQLiteProxy で `c1 = conn.execute("SELECT 1")` と `c2 = conn.execute("SELECT 2")` を順に実行し、その後 `c1.fetchall()` を呼ぶ
- **THEN** `c1` と `c2` は別オブジェクトであり、`c1.fetchall()` は `SELECT 1` の結果を返す（後続の execute に踏み潰されない）

#### Scenario: 接続レベルの結果取得は存在しない
- **WHEN** SQLiteProxy に対して `conn.fetchall` へアクセスする
- **THEN** 誘導メッセージ付きの `AttributeError` が送出される

#### Scenario: cursor()経由でも介入コアを通る
- **WHEN** 同一seedで初期化した2つのSQLiteProxyの一方で `conn.cursor().execute(sql)`、他方で `conn.execute(sql)` により同一SQL列を実行して比較する
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

### Requirement: allow_native_passthroughによるopt-out転送
`wrap()` は省略可能な引数 `allow_native_passthrough`（既定 `False`）を受け付けなければならない（SHALL）。`True` の場合、未定義属性は生接続へ転送されなければならず（SHALL）、転送されたSQL実行能力のある入口の呼び出しは統計に記録されなければならない（MUST）。転送経路の操作は障害注入・イベント記録・論理時計・occurrence更新の対象外であることを契約文書に明記しなければならない（SHALL）。

#### Scenario: opt-outで転送され記録される
- **WHEN** `allow_native_passthrough=True` でラップした接続の `conn.cursor()` を呼び出す
- **THEN** 生カーソルが返り、`conn.dolly.stats()` の escape hatch 集計で `cursor` の呼び出しが1回記録される

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
`wrap()` は追加設定として、全障害の重み辞書（既存 `faults` の拡張）、mood設定（有効化・epoch長・係数表）、自動返却設定、clock注入、スコーピング（`only_tables` / `exclude_tables`）を受け付けなければならない（SHALL）。すべての追加設定は省略可能でなければならない（MUST）。省略時、追加機能はすべて無効であり、介入コアの挙動（decision・イベントの種類・順序・既存フィールドの値）は追加設定の導入前と一致しなければならない（MUST）。公開表面の形状は本仕様のバックエンド別表面要件に従う（SHALL）。破壊的変更は破壊的変更ポリシー（タグ前は許可・ADR節必須、タグ後は禁止）に従わなければならない（MUST）。

#### Scenario: 旧設定のままなら介入コアは旧挙動
- **WHEN** MVP時代と同じ引数（seed・session_id・faults）だけで `wrap()` を呼び、同一SQL列を実行する
- **THEN** 追加機能はすべて無効で、イベントの種類・順序・既存フィールドの値は追加設定導入前の実装と一致する（wire-level差分は `schema_version` のみ）

#### Scenario: 未知の障害名は拒否する
- **WHEN** `faults={"ZOOMIES": 1}` のように未定義の障害名を渡す
- **THEN** 明示的な設定エラーが送出され、接続はラップされない

### Requirement: 分類・介入統計の参照
`conn.dolly.stats()` は、匿名fingerprint単位の分類結果（分類済みSELECT数、UNKNOWN数、介入された操作数）を構造化オブジェクトで返さなければならない（SHALL）。対応範囲外操作は理由別の素通し集計で返さなければならない（SHALL）。`allow_native_passthrough=True` のセッションでは、アダプタが宣言したSQL実行能力のある入口の呼び出し回数を入口名ごとに集計し、宣言外の転送呼び出しは集約カウンターで返さなければならない（SHALL）。集計は属性の取得時ではなく呼び出し時に行わなければならず（MUST）、`hasattr` 等による属性参照だけで計数が増えてはならない（MUST NOT）。統計に生SQL、生パラメータ、パラメータの型名、呼び出し引数を含んではならない（MUST NOT）。

#### Scenario: corpusの介入率を測る
- **WHEN** アプリのクエリ列を流した後に `conn.dolly.stats()` を呼ぶ
- **THEN** fingerprintごとの分類内訳と介入数が得られ、UNKNOWN率からparser導入判断の材料が取れる

#### Scenario: 属性参照だけでは計数されない
- **WHEN** `allow_native_passthrough=True` のセッションで `hasattr(conn, "cursor")` を評価し、呼び出しは行わない
- **THEN** escape hatch 集計は増加しない
