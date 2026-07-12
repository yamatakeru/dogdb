# dbapi-proxy — delta: unsupported-param-passthrough

## MODIFIED Requirements

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
