# dbapi-proxy — delta for duckdb-cursor-clone-wrap

## ADDED Requirements

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

## MODIFIED Requirements

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
