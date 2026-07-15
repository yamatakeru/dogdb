# dbapi-proxy — DB-APIプロキシの公開表面

## Purpose

既存のDuckDB/SQLite接続を決定的な障害注入機能付きDB-APIプロキシとして公開し、通常の取得操作、トランザクション、およびDogDB固有の管理操作に一貫したインターフェースを提供する。

## Requirements

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
`executemany`（理由キー `executemany`）、名前付きパラメータを使う操作（理由キー `named_parameters`）、SQL分類器が分類できなかった文（理由キー `unknown_sql`）、SQL分類器がトランザクション文（BEGIN/COMMIT/ROLLBACK）と判定した文（理由キー `transaction_statement`）、およびパラメータfingerprintの入力域外の値を含む操作（理由キー `unsupported_parameter_type`）は、障害注入なしでバックエンドへ素通ししなければならない（SHALL）。素通しは既定（`on_passthrough="allow"`）では静かに行い、操作自体を失敗させてはならない（MUST NOT）。`on_passthrough="error"` による例外送出の意味論は「on_passthrough="error"時の実行前ブロック」Requirementに従う。素通し操作でも mood／自動返却の論理時計は前進しなければならない（SHALL）。素通し操作は occurrence を消費せず、decision・イベントを生成してはならない（MUST NOT）。素通しの発生は `conn.dolly.stats()` の素通し集計に、上記5つの理由キーそれぞれで理由別に記録されなければならず（SHALL）、この記録は `on_passthrough` の設定値（`"allow"` / `"warn"` / `"error"`）に関わらず常に行わなければならない（MUST）。集計に生パラメータや型名の値を含んではならない（MUST NOT）。

#### Scenario: executemanyは無介入
- **WHEN** `executemany("INSERT INTO t VALUES (?)", rows)` を実行する
- **THEN** 全行が挿入され、fault イベントは一件も記録されない

#### Scenario: 入力域外パラメータは実行を止めない
- **WHEN** 全障害確率0のプロキシで、生ドライバが受理する独自型パラメータのSELECTを実行する
- **THEN** 生接続と同一の結果が返り、`stats()` の `unsupported_parameter_type` が1増える

#### Scenario: 素通しでも論理時計は進む
- **WHEN** `auto_return={"min_operations": 1, "max_operations": 1}` のセッションでSTASHの宝物が存在する状態で、入力域外パラメータの操作を実行する
- **THEN** 論理操作数は前進し、自動返却の判定は素通し操作を1操作として数える

#### Scenario: 名前付きパラメータは理由別に記録される
- **WHEN** 既定設定のプロキシで、Mapping型のパラメータを使ってSELECTを実行する
- **THEN** 操作は生接続と同一の結果で成功し、`stats()` の `named_parameters` が1増える

#### Scenario: 分類不能SQLは理由別に記録される
- **WHEN** 既定設定のプロキシで、SQL分類器がUNKNOWNと判定する文（例: `PRAGMA user_version`）を実行する
- **THEN** 操作は生接続と同一の結果で成功し、`stats()` の `unknown_sql` が1増える

#### Scenario: トランザクション文は理由別に記録される
- **WHEN** 既定設定のプロキシで `BEGIN` を実行する
- **THEN** 操作は生接続と同一に成功し、`stats()` の `transaction_statement` が1増える

#### Scenario: executemanyは理由別に記録される
- **WHEN** 既定設定のプロキシで `executemany` を実行する
- **THEN** 全行が挿入され、`stats()` の `executemany` が1増える

### Requirement: 未定義属性のfail-closed既定
プロキシは、バックエンドごとに明示的に定義された公開表面以外の属性アクセスを、生接続へ静かに転送してはならない（MUST NOT）。DuckDB表面の公開表面は `execute`、`executemany`、`cursor`、`fetchall`、`fetchone`、`fetchmany`、`description`、`rowcount`、`in_transaction`、`commit`、`rollback`、`close`、`dolly`、およびコンテキストマネージャである（SHALL）。SQLite表面の公開表面は `execute`、`executemany`、`cursor`、`in_transaction`、`commit`、`rollback`、`close`、`dolly`、およびコンテキストマネージャである（SHALL）。既定では、公開表面外の属性アクセスは誘導メッセージ付きの `AttributeError` を送出しなければならない（MUST）。アダプタが宣言したSQL実行能力のある入口名のうち公開表面に含まれないもの（例: DuckDB の `sql`、SQLite の `executescript`）へのアクセスには、`execute()` の使用または `allow_native_passthrough=True` の指定を案内する専用メッセージを含めなければならない（SHALL）。エラーメッセージに生SQLや生パラメータを含んではならない（MUST NOT）。

#### Scenario: DuckDBの公開表面外のSQL実行能力のある入口は誘導付きで拒否される
- **WHEN** 既定設定のDuckDBプロキシに対して `conn.sql(...)` にアクセスする
- **THEN** `AttributeError` が送出され、メッセージには「DogDBはこの入口に注入できない」旨と `execute()` および `allow_native_passthrough=True` への誘導が含まれる

#### Scenario: DuckDBのcursorは拒否されない
- **WHEN** 既定設定のDuckDBプロキシに対して `conn.cursor()` を呼ぶ
- **THEN** クローンを包んだDuckDB表面プロキシが返り、`AttributeError` は送出されない

#### Scenario: SQLiteのcursorは拒否されない
- **WHEN** 既定設定のSQLiteプロキシに対して `conn.cursor()` を呼ぶ
- **THEN** カーソルプロキシが返り、`AttributeError` は送出されない

#### Scenario: 未知属性も拒否される
- **WHEN** 既定設定のプロキシに対して、公開表面にもアダプタ宣言集合にも含まれない属性（例: `conn.interrupt`）にアクセスする
- **THEN** `AttributeError` が送出され、操作は生接続へ到達しない

### Requirement: DuckDBカーソルクローンの包み直し
DuckDB表面の `cursor()` は、ネイティブ接続の `cursor()` が返すクローン接続（独立トランザクション文脈を持つ新しい接続）を、新しいDuckDB表面プロキシで包んで返さなければならない（SHALL）。クローンプロキシは親プロキシと同一の介入コア（decision・障害適用・イベント・統計・house・論理時計）を共有しなければならず（MUST）、occurrence は全カーソル横断の execute 呼び出しの全順序で数えられなければならない（MUST）。この変更で `POLICY_VERSION` を変更してはならない（MUST NOT）。クローンプロキシのSQL実行はクローン接続に対して行われなければならない（MUST）。クローンプロキシの `cursor()` も同様に包み直したクローンを返さなければならない（SHALL）。親子・クローン間のトランザクション分離はバックエンドの性質であり、DogDBはこれを変更・管理・検出してはならず（MUST NOT）、この不関知は契約文書に明記しなければならない（SHALL）。クローンプロキシの `close()` はクローン接続のみを閉じ、共有介入コア（イベントログ・house・統計）に影響を与えてはならない（MUST NOT）。

#### Scenario: クローン横断の決定性
- **WHEN** 同一seedの2セッションで同一SQL列を、一方は親接続のみで、他方は親と `cursor()` クローンへ交互に振り分けて同一順序で実行する
- **THEN** 生成される decision・障害イベント列は両セッションで一致する

#### Scenario: クローン経由の宝物は親から見える
- **WHEN** クローンプロキシで実行した操作でSTASHが発火する
- **THEN** 親の `conn.dolly.house()` に宝物が現れ、`conn.dolly.log()` に fault イベントが記録される

#### Scenario: トランザクション分離はネイティブ同型
- **WHEN** 素のduckdb接続とDogDBラップ接続のそれぞれで、親で未コミットのINSERTを行った後にクローンから同テーブルをSELECTする
- **THEN** 両者の観察結果は一致する（DogDBはバックエンドのトランザクション分離を変更しない）

#### Scenario: クローンのcloseは共有コアに影響しない
- **WHEN** クローンプロキシで操作を実行しイベントが記録された後、クローンの `close()` を呼ぶ
- **THEN** 親プロキシは引き続き操作でき、`conn.dolly.log()` にはクローン経由のイベントが残っている

### Requirement: DuckDB表面のdescription型情報の透過
DuckDB表面（接続レベルおよびカーソルクローン）の `description` は、列名に加えて、ネイティブDuckDB接続が同一クエリで返す型情報（第2スロット）を保持しなければならない（SHALL）。型情報の値は正規化せず、ネイティブが返す値をそのまま透過しなければならない（SHALL）。列名が障害により変異した場合、`description` の列名は変異後の値を反映し、型情報は列の位置に留まらなければならない（SHALL）。SQLite表面の `description` は sqlite3 ネイティブと同型の `(name, None, None, None, None, None, None)` を維持しなければならない（SHALL）。

#### Scenario: DuckDBのdescriptionはネイティブと一致する
- **WHEN** 全障害確率0のDuckDBプロキシと素のduckdb接続で同一のSELECTを実行し、`description` を比較する
- **THEN** 両者の `description` は列名・型情報（第2スロット）を含めて一致する

#### Scenario: SQLiteのdescriptionは変わらない
- **WHEN** 全障害確率0のSQLiteカーソルプロキシと素のsqlite3カーソルで同一のSELECTを実行し、`description` を比較する
- **THEN** 両者は一致し、型スロットはいずれも `None` である

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
`conn.dolly.stats()` は、匿名fingerprint単位の分類結果（分類済みSELECT数、UNKNOWN数、介入された操作数）を構造化オブジェクトで返さなければならない（SHALL）。対応範囲外操作は理由別の素通し集計で返さなければならない（SHALL）。素通し理由キーの語彙は `unsupported_parameter_type`・`named_parameters`・`unknown_sql`・`transaction_statement`・`executemany` の5種に閉じなければならず（SHALL）、この語彙を拡張・変更する場合はOpenSpec change経由で本Requirementを改訂しなければならない（MUST）。発生していない理由キーはsnapshotの素通し集計から省略してよく（MAY）、既存の疎な辞書形状（発生した理由キーのみを含む）を維持しなければならない（SHALL）。`allow_native_passthrough=True` のセッションでは、アダプタが宣言したSQL実行能力のある入口の呼び出し回数を入口名ごとに集計し、宣言外の転送呼び出しは集約カウンターで返さなければならない（SHALL）。集計は属性の取得時ではなく呼び出し時に行わなければならず（MUST）、`hasattr` 等による属性参照だけで計数が増えてはならない（MUST NOT）。統計に生SQL、生パラメータ、パラメータの型名、呼び出し引数を含んではならない（MUST NOT）。`stats()` のスナップショットは、診断用のメタ情報として分類器実装（sqlglot）のバージョンを1フィールド含まなければならない（SHALL）。このフィールドをdecision keyの入力に用いてはならず（MUST NOT）、イベントschemaへ影響を与えてはならない（MUST NOT）。`conn.dolly.stats()` のsnapshotが返すトップレベルおよびネストしたキー集合は、既存キーの削除・改名を行わずキー追加のみで後方互換を維持しなければならない（SHALL）。

#### Scenario: corpusの介入率を測る
- **WHEN** アプリのクエリ列を流した後に `conn.dolly.stats()` を呼ぶ
- **THEN** fingerprintごとの分類内訳と介入数が得られ、UNKNOWN率からsqlglotでも残る素通しの実態を把握できる

#### Scenario: 属性参照だけでは計数されない
- **WHEN** `allow_native_passthrough=True` のセッションで `hasattr(conn, "cursor")` を評価し、呼び出しは行わない
- **THEN** escape hatch 集計は増加しない

#### Scenario: 診断用メタ情報としてsqlglotバージョンが分かる
- **WHEN** `conn.dolly.stats()` を呼ぶ
- **THEN** スナップショットには分類器実装（sqlglot）のバージョンがメタフィールドとして含まれ、decision keyやイベントには影響しない

#### Scenario: 素通しが一切発生しない場合の集計は空
- **WHEN** 素通し対象操作を一度も実行していないセッションで `conn.dolly.stats()` を呼ぶ
- **THEN** 素通し集計は空の辞書であり、5つの理由キーはいずれも出現しない

#### Scenario: snapshotはキー追加のみで後方互換を保つ
- **WHEN** 本change導入前後のそれぞれで、同一の操作列（素通し操作を含まない）を実行して `conn.dolly.stats()` を比較する
- **THEN** 導入前に存在した全キー・値は導入後も同一であり、導入によって既存キーの削除・改名は発生しない

### Requirement: ゼロ実効重み時の計算回避
実効重み（base重み × mood係数）が0の障害について、発火判定のための導出ハッシュを計算してはならない（MUST NOT）。操作のどの観測可能な出力（発火イベント・宝物・staleエントリ・デバッグイベント・介入上限超過のイベントとエラー・`include_params=True` の決定キー）にも寄与しない場合、decision keyおよびparameter fingerprintの導出を計算してはならない（MUST NOT）。この回避の下でも、SQL分類・統計記録・occurrenceカウント・論理時計の前進は全操作で維持されなければならない（MUST）。

#### Scenario: 重みの実行時変更後も決定キーは純関数として不変
- **WHEN** 全重み0で同一クエリを2回実行した後、ある障害の実効重みを非0へ変更して同じクエリを3回目に実行する
- **THEN** 3回目の操作のoccurrenceは3であり、その決定キーと発火判定は、最初から同じ重みが設定されていたセッションの3回目の操作と一致する

#### Scenario: ゼロ実効重みの操作でも分類統計は記録される
- **WHEN** 全障害の重みを0にし、`debug=False`（既定）のままラップした接続でSELECTを複数回実行する
- **THEN** イベントは記録されず、`dolly.stats()` には分類結果が全操作分記録される

#### Scenario: デバッグモードでは決定評価イベントが従来どおり記録される
- **WHEN** `debug=True` かつ全障害の実効重みが0の設定でSELECTを実行する
- **THEN** 発火しない決定にも `decision_evaluated` イベントがdecision key・parameter fingerprint付きで記録される

### Requirement: ゼロ実効重み時のオーバーヘッド上限
全障害の実効重みが0の設定における小さなSELECTの反復実行で、ラップ接続のオーバーヘッドは生接続の5倍以内でなければならない（SHALL）。判定は、固定した接続条件とクエリ列に対し、ウォームアップ後に複数回測定した所要時間の中央値の比によらなければならない（SHALL）。この測定手順は再現可能なベンチマークスクリプトとしてリポジトリに常置しなければならない（SHALL）。

#### Scenario: ゼロ確率導入時のオーバーヘッドが上限内に収まる
- **WHEN** 全障害の重みを0にしてラップした接続で、小さなSELECTを多数回（例: 2000回）実行し、同一クエリ列を生接続でも実行して、ウォームアップ後の複数回測定の中央値同士を比較する
- **THEN** ラップ接続の所要時間は生接続の5倍以内である

### Requirement: on_passthroughによる素通し発火モードの選択
`wrap()` は省略可能な引数 `on_passthrough`（既定 `"allow"`、許容値 `"allow"` / `"warn"` / `"error"`）を受け付けなければならない（SHALL）。命名は既存の `on_max_rows` と対称でなければならない（SHALL）。発火対象は `unknown_sql`・`named_parameters`・`unsupported_parameter_type` の3種に固定しなければならず（MUST）、`transaction_statement` と `executemany` は `on_passthrough` の値に関わらず常に無警告・無エラーで素通ししなければならない（MUST）。`"allow"`（既定）では、発火対象の素通しであっても警告・例外を発生させてはならない（MUST NOT）。`"warn"` では、発火対象の素通しが起きるたびにDogDB固有の警告カテゴリ `DollyPassthroughWarning` で `warnings.warn` を呼ばなければならない（SHALL）。いずれのモードでも、理由別のstats記録は「対応範囲外操作の素通し」Requirementに従い変わらず行われる（SHALL）。未知の値を渡した場合は明示的な設定エラーを送出し、接続をラップしてはならない（MUST NOT）。

#### Scenario: 既定allowは無警告
- **WHEN** 既定設定（`on_passthrough` 省略）のプロキシで名前付きパラメータの操作を実行する
- **THEN** 警告は発生せず、操作は生接続と同一の結果で成功し、`stats()` の `named_parameters` が1増える

#### Scenario: warnは発火対象で警告する
- **WHEN** `on_passthrough="warn"` のプロキシで分類不能SQLを実行する
- **THEN** `DollyPassthroughWarning` カテゴリの警告が1件発生し、操作自体は成功して結果が返る

#### Scenario: warnは除外対象で警告しない
- **WHEN** `on_passthrough="warn"` のプロキシで `executemany` またはトランザクション文（`BEGIN` 等）を実行する
- **THEN** 警告は発生しない

#### Scenario: 未知の値は拒否される
- **WHEN** `on_passthrough="block"` のように未定義の値を渡して `wrap()` を呼ぶ
- **THEN** 明示的な設定エラーが送出され、接続はラップされない

### Requirement: on_passthrough="error"時の実行前ブロック
`on_passthrough="error"` の場合、発火対象3種（`unknown_sql`・`named_parameters`・`unsupported_parameter_type`）の素通しは、バックエンドでの実行に先立って検出されなければならない（MUST）。検出した場合、非retryableな例外 `DollyPassthroughError` を送出しなければならず（SHALL）、当該操作の文はバックエンドに到達してはならない（MUST NOT）。この例外は少なくとも読み取り専用の `retryable` 属性（`False` 固定）を持たなければならない（SHALL）。`transaction_statement` と `executemany` は `on_passthrough="error"` でも例外を送出せず、常に無介入で実行されなければならない（MUST）。

#### Scenario: errorは実行前に送出され、バックエンドに到達しない
- **WHEN** `on_passthrough="error"` のプロキシで、名前付きパラメータを使うINSERT文を実行する
- **THEN** `DollyPassthroughError` が送出され、対象テーブルに行は挿入されない（文がバックエンドに到達していないことが行数の不変で観測できる）

#### Scenario: errorでも除外対象は素通しされる
- **WHEN** `on_passthrough="error"` のプロキシで `executemany` を実行する
- **THEN** 例外は送出されず、全行が挿入される

#### Scenario: errorでもトランザクション文は素通しされる
- **WHEN** `on_passthrough="error"` かつ全障害の発火確率0のプロキシで `BEGIN` を実行してからINSERTし `commit()` する
- **THEN** 例外は送出されず、データは永続化される

### Requirement: 障害設定引数の一意性
`wrap()` の障害ごとの発火確率を渡す引数は `faults` の一つでなければならない（SHALL）。同義のエイリアス引数（`fault_probabilities` を含む）を提供してはならない（MUST NOT）。

#### Scenario: 旧エイリアスは受け付けない
- **WHEN** `wrap(raw, seed=1, fault_probabilities={"STASH": 0.1})` を呼ぶ
- **THEN** `TypeError`（未知の引数）が送出され、接続はラップされない

#### Scenario: 正規の引数名は動作する
- **WHEN** `wrap(raw, seed=1, faults={"STASH": 0.1})` を呼ぶ
- **THEN** 接続は正常にラップされ、STASHの発火確率は0.1として設定される

### Requirement: max_result_rowsによる中断的読み取り
`wrap()` は省略可能な引数 `max_result_rows`（既定 `None`）を受け付けなければならない（SHALL）。`None`（既定）の場合、挙動は本Requirement導入前と完全に同一でなければならない（MUST）。値を指定した場合、対象は `max_intervention_rows` 検査と同一のスコープ（分類器がSELECTと判定し、`only_tables` / `exclude_tables` スコープに含まれる操作）に限る（SHALL）。バックエンドから結果を読み取る過程で `max_result_rows + 1` 行目を観測した時点で読み取りを中断しなければならず（MUST）、それ以降の行を取得してはならない（MUST NOT）。中断時、呼び出し側へ部分的な結果を返してはならない（MUST NOT）。中断が発生した場合、`limit_exceeded` イベント（`details.limit = "max_result_rows"`、`details.configured` に設定値、`details.observed = "exceeded"`）を記録した上で（SHALL）、非retryableな `DollyLimitError` を送出しなければならない（SHALL）。この判定はバックエンド上でクエリの実行が開始済みである状態で発生する点を契約文書とREADMEに明記しなければならない（SHALL）。

#### Scenario: 上限未満は中断しない
- **WHEN** `max_result_rows=5` の設定で3行を返すSELECTを実行する
- **THEN** 中断は発生せず、3行が通常どおり返る

#### Scenario: 上限ちょうどは中断しない
- **WHEN** `max_result_rows=3` の設定で3行を返すSELECTを実行する
- **THEN** 中断は発生せず、3行が通常どおり返る

#### Scenario: 上限超過は部分結果なしで中断する
- **WHEN** `max_result_rows=2` の設定で3行を返すSELECTを実行する
- **THEN** 3行目の観測時点で読み取りが中断し、呼び出し側は行を1件も受け取らず、`details` に `limit="max_result_rows"`・`configured=2`・`observed="exceeded"` を含む `limit_exceeded` イベントが記録された上で、非retryableな `DollyLimitError` が送出される

### Requirement: max_result_rowsとmax_intervention_rowsの直交性
`max_result_rows` と `max_intervention_rows` は独立したノブでなければならず（MUST）、両者の間に結合バリデーションを設けてはならない（MUST NOT）。一方の設定値が他方の挙動を変えてはならない（MUST NOT）。両方を同時に設定できなければならない（SHALL）。

#### Scenario: 両方設定時も独立に評価される
- **WHEN** `max_intervention_rows=2` かつ `max_result_rows=10` の設定で5行を返すSELECTを実行する
- **THEN** `max_result_rows` は超過しないため読み取りは中断されず、`max_intervention_rows` 超過による通常の `limit_exceeded`（`details.limit="max_intervention_rows"`）経路のみが独立に評価される

#### Scenario: 設定値の組み合わせを拒否しない
- **WHEN** `max_result_rows=100` かつ `max_intervention_rows=100000`（大小関係が逆転する設定）で `wrap()` を呼ぶ
- **THEN** 設定エラーは発生せず、接続は正常にラップされる

### Requirement: max_result_rows中断時の決定性とfault評価順序
`max_result_rows` による中断は、同一DB状態・同一seed・同一session_id・同一入力列であれば決定的に再現しなければならない（MUST）。中断が発生した操作でも、occurrenceカウンタと論理時計（mood・自動返却）は他の操作と同様に前進しなければならない（MUST）。中断時は `on_result` phaseの障害候補選択（`FaultEngine.on_result` によるfault適用の評価）を行ってはならず（MUST NOT）、当該操作について `decision_evaluated` イベントを記録してはならない（MUST NOT）。`before_execute` phaseの障害（BARK・GUARD_BOWL・IGNORE・SLOTH）は、`max_result_rows` による中断より先に評価され得る（SHALL）。

#### Scenario: 中断も決定的に再現する
- **WHEN** 同一seed・同一DB状態・同一SQL列で `max_result_rows` 超過を2回再現する
- **THEN** 両回とも同一occurrenceで中断し、記録される `limit_exceeded` イベントは診断用タイムスタンプを除く全フィールドで一致する

#### Scenario: occurrenceと論理時計は中断時も進む
- **WHEN** mood有効時のセッションで、同一テンプレートを2回実行し、2回目で `max_result_rows` 超過による中断が発生する
- **THEN** 2回目の操作の `occurrence` は2であり、mood遷移の論理時計は中断した操作も1操作として数える

#### Scenario: BARKは中断より先に発火し得る
- **WHEN** `before_execute` phaseでBARKが発火する設定かつ `max_result_rows` 超過が見込まれるSELECTを実行する
- **THEN** `DollyBarkError` が送出され、バックエンドへ文は送られず、`max_result_rows` による中断（`limit_exceeded` イベント・`DollyLimitError`）は発生しない

#### Scenario: 中断時はdecision_evaluatedが記録されない
- **WHEN** `debug=True` かつ `max_result_rows` 超過による中断が発生する
- **THEN** `limit_exceeded` イベントは記録されるが、当該操作について `decision_evaluated` イベントは記録されない
