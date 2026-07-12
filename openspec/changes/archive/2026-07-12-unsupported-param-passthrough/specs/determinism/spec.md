# determinism — delta: unsupported-param-passthrough

## MODIFIED Requirements

### Requirement: パラメータfingerprintの入力域
`parameter_fingerprint` の計算は、次の閉じた許可リストの値のみを受け付けなければならない（MUST）: JSONネイティブ値（null・真偽値・数値・文字列）、および厳密な型一致による `bytes`・`bytearray`・`datetime.date`・`datetime.time`・`datetime.datetime`・`Decimal`・`UUID`。これらは決定的にエンコードされる（SHALL）。サブクラスや独自型を含む上記以外の値を持つ操作は、fingerprint を計算せず、対応範囲外操作としてバックエンドへ素通ししなければならない（SHALL）。素通しされた操作について decision・イベント・occurrence を生成してはならない（MUST NOT）。入力域外の値を理由に操作を失敗させてはならない（MUST NOT）。不安定な表現から fingerprint を導出してはならず（MUST NOT）、`repr`・pickle・型名によるフォールバック fingerprint を用いてはならない（MUST NOT）。この規則は `include_params` の設定に関わらず適用される — `parameter_fingerprint` は記録される全イベントの必須フィールドであるため、不安定なエンコードを排除する唯一の安全な方法は、当該操作をイベント系列自体に参加させないことである。

#### Scenario: 入力域外の値は素通しされる
- **WHEN** `__conform__` のみを定義した独自型をバインドパラメータとして渡す
- **THEN** 操作はバックエンドへ無介入で委譲され、生接続と同一の結果（または同一のバックエンド例外）が得られ、イベントは記録されない

#### Scenario: 素通しは後続の決定に影響しない
- **WHEN** 同一クエリAを実行し、入力域外パラメータの操作を挟み、再びクエリAを実行する
- **THEN** クエリAの2回の実行の `occurrence` は 1, 2 であり、素通し操作を挟まない場合と同一の `decision_key` になる

#### Scenario: 安定表現を持つ標準型は決定的に処理される
- **WHEN** datetime・Decimal・UUID・bytes を含むパラメータで同一クエリを2回実行する
- **THEN** 両実行のイベントの `parameter_fingerprint` は一致する
