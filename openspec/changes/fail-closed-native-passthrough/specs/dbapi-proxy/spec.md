# dbapi-proxy — delta: fail-closed-native-passthrough

## ADDED Requirements

### Requirement: 未定義属性のfail-closed既定
プロキシは、明示的に定義された公開表面（`execute`、`executemany`、`fetchall`、`fetchone`、`fetchmany`、`description`、`rowcount`、`in_transaction`、`commit`、`rollback`、`close`、`dolly`、およびコンテキストマネージャ）以外の属性アクセスを、生接続へ静かに転送してはならない（MUST NOT）。既定では、未定義属性へのアクセスは誘導メッセージ付きの `AttributeError` を送出しなければならない（MUST）。アダプタが宣言したSQL実行能力のある入口名（例: `cursor`、`sql`）へのアクセスには、`execute()` の使用または `allow_native_passthrough=True` の指定を案内する専用メッセージを含めなければならない（SHALL）。エラーメッセージに生SQLや生パラメータを含んではならない（MUST NOT）。

#### Scenario: SQL実行能力のある入口は誘導付きで拒否される
- **WHEN** 既定設定のプロキシに対して `conn.cursor()` または DuckDB の `conn.sql(...)` にアクセスする
- **THEN** `AttributeError` が送出され、メッセージには「DogDBはこの入口に注入できない」旨と `execute()` および `allow_native_passthrough=True` への誘導が含まれる

#### Scenario: 未知属性も拒否される
- **WHEN** 既定設定のプロキシに対して、公開表面にもアダプタ宣言集合にも含まれない属性（例: `conn.interrupt`）にアクセスする
- **THEN** `AttributeError` が送出され、操作は生接続へ到達しない

### Requirement: allow_native_passthroughによるopt-out転送
`wrap()` は省略可能な引数 `allow_native_passthrough`（既定 `False`）を受け付けなければならない（SHALL）。`True` の場合、未定義属性は生接続へ転送されなければならず（SHALL）、転送されたSQL実行能力のある入口の呼び出しは統計に記録されなければならない（MUST）。転送経路の操作は障害注入・イベント記録・論理時計・occurrence更新の対象外であることを契約文書に明記しなければならない（SHALL）。

#### Scenario: opt-outで転送され記録される
- **WHEN** `allow_native_passthrough=True` でラップした接続の `conn.cursor()` を呼び出す
- **THEN** 生カーソルが返り、`conn.dolly.stats()` の escape hatch 集計で `cursor` の呼び出しが1回記録される

## MODIFIED Requirements

### Requirement: 分類・介入統計の参照
`conn.dolly.stats()` は、匿名fingerprint単位の分類結果（分類済みSELECT数、UNKNOWN数、介入された操作数）を構造化オブジェクトで返さなければならない（SHALL）。`allow_native_passthrough=True` のセッションでは、アダプタが宣言したSQL実行能力のある入口の呼び出し回数を入口名ごとに集計し、宣言外の転送呼び出しは集約カウンタで返さなければならない（SHALL）。集計は属性の取得時ではなく呼び出し時に行わなければならず（MUST）、`hasattr` 等による属性参照だけで計数が増えてはならない（MUST NOT）。統計に生SQL、生パラメータ、呼び出し引数を含んではならない（MUST NOT）。

#### Scenario: corpusの介入率を測る
- **WHEN** アプリのクエリ列を流した後に `conn.dolly.stats()` を呼ぶ
- **THEN** fingerprintごとの分類内訳と介入数が得られ、UNKNOWN率からparser導入判断の材料が取れる

#### Scenario: 属性参照だけでは計数されない
- **WHEN** `allow_native_passthrough=True` のセッションで `hasattr(conn, "cursor")` を評価し、呼び出しは行わない
- **THEN** escape hatch 集計は増加しない
