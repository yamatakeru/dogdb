# dbapi-proxy — delta: passthrough-observability

## MODIFIED Requirements

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

### Requirement: 分類・介入統計の参照
`conn.dolly.stats()` は、匿名fingerprint単位の分類結果（分類済みSELECT数、UNKNOWN数、介入された操作数）を構造化オブジェクトで返さなければならない（SHALL）。対応範囲外操作は理由別の素通し集計で返さなければならない（SHALL）。素通し理由キーの語彙は `unsupported_parameter_type`・`named_parameters`・`unknown_sql`・`transaction_statement`・`executemany` の5種に閉じなければならず（SHALL）、この語彙を拡張・変更する場合はOpenSpec change経由で本Requirementを改訂しなければならない（MUST）。発生していない理由キーはsnapshotの素通し集計から省略してよく（MAY）、既存の疎な辞書形状（発生した理由キーのみを含む）を維持しなければならない（SHALL）。`allow_native_passthrough=True` のセッションでは、アダプタが宣言したSQL実行能力のある入口の呼び出し回数を入口名ごとに集計し、宣言外の転送呼び出しは集約カウンターで返さなければならない（SHALL）。集計は属性の取得時ではなく呼び出し時に行わなければならず（MUST）、`hasattr` 等による属性参照だけで計数が増えてはならない（MUST NOT）。統計に生SQL、生パラメータ、パラメータの型名、呼び出し引数を含んではならない（MUST NOT）。`conn.dolly.stats()` のsnapshotが返すトップレベルおよびネストしたキー集合は、既存キーの削除・改名を行わずキー追加のみで後方互換を維持しなければならない（SHALL）。

#### Scenario: corpusの介入率を測る
- **WHEN** アプリのクエリ列を流した後に `conn.dolly.stats()` を呼ぶ
- **THEN** fingerprintごとの分類内訳と介入数が得られ、UNKNOWN率からparser導入判断の材料が取れる

#### Scenario: 属性参照だけでは計数されない
- **WHEN** `allow_native_passthrough=True` のセッションで `hasattr(conn, "cursor")` を評価し、呼び出しは行わない
- **THEN** escape hatch 集計は増加しない

#### Scenario: 素通しが一切発生しない場合の集計は空
- **WHEN** 素通し対象操作を一度も実行していないセッションで `conn.dolly.stats()` を呼ぶ
- **THEN** 素通し集計は空の辞書であり、5つの理由キーはいずれも出現しない

#### Scenario: snapshotはキー追加のみで後方互換を保つ
- **WHEN** 本change導入前後のそれぞれで、同一の操作列（素通し操作を含まない）を実行して `conn.dolly.stats()` を比較する
- **THEN** 導入前に存在した全キー・値は導入後も同一であり、導入によって既存キーの削除・改名は発生しない

## ADDED Requirements

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
- **WHEN** `on_passthrough="error"` のプロキシで `BEGIN` を実行してからINSERTし `commit()` する
- **THEN** 例外は送出されず、データは永続化される
