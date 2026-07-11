# event-log — JSONLイベントログ

## Purpose

障害注入と宝物返却を、機密情報を漏らさず検査可能なJSONLイベントとして記録し、セッション内の順序保証、構造化された参照API、および破損行への耐性を提供する。

## Requirements

### Requirement: スキーマv2のイベント種別別フィールド表
すべてのイベントはコアフィールド `schema_version`、`event_id`、`session_id`、`seq`、`event_type` を含まなければならない（MUST）。コア以外の必須フィールドはイベント種別ごとに契約文書の表で定義しなければならず（SHALL）、`fault_injected` と `treasure_returned` の必須フィールド集合はv1と同一でなければならない（MUST）。`mood_changed` はfingerprint系フィールドを要求されてはならない（MUST NOT）。表に定義されないフィールドをreplay比較の対象にしてはならない（MUST NOT）。

#### Scenario: fault_injectedはv1と同じ形
- **WHEN** schema v2のwriterでSTASHが発火する
- **THEN** 追記行は `schema_version: 2` である点を除きv1と同じ必須フィールドをすべて含む

#### Scenario: mood_changedは身軽
- **WHEN** mood遷移イベントが記録される
- **THEN** コアフィールドと `details`（from / to / tick）を含み、`template_fingerprint` を含まなくても契約違反にならない

### Requirement: 機密情報の既定非記録
生SQL、生バインドパラメータ、生の行値は、既定設定においてイベントログへ記録されてはならない（MUST NOT）。パラメータはHMAC化された `parameter_fingerprint` としてのみ残さなければならない（SHALL）。

#### Scenario: 機密値がログに漏れない
- **WHEN** 機密文字列をパラメータに含むクエリでSTASHが発火する
- **THEN** イベントログファイルのどの行にもその文字列が平文で現れない

### Requirement: セッション内単調シーケンス
`seq` はセッション内で厳密に単調増加しなければならない（MUST）。MVPのログライターは単一writer契約とし、複数プロセスからの同時追記は非対応であることを文書化しなければならない（SHALL）。

#### Scenario: 欠番も逆行もない
- **WHEN** 1セッションで複数の障害イベントが記録される
- **THEN** `seq` は1ずつ増加する

### Requirement: テストから参照できるイベントAPI
`conn.dolly.log()` は記録済みイベントを構造化オブジェクトの列として返さなければならない（SHALL）。JSONLファイルの出力先は設定可能でなければならない（SHALL）。読み取り側は不正なJSON行および不正なUTF-8バイト列を含む行をスキップし、警告を発しつつ残りのイベントを返さなければならない（SHALL）。

#### Scenario: テストが障害発生をassertする
- **WHEN** テストコードが `conn.dolly.log()` を呼ぶ
- **THEN** `events[-1].fault == "STASH"` のような属性ベースの検証ができる

#### Scenario: 破損行があっても読める
- **WHEN** JSONLファイルの1行が途中で切れている
- **THEN** 読み取りは警告付きでその行をスキップし、他のイベントを返す

#### Scenario: 不正なUTF-8を含む行があっても読める
- **WHEN** JSONLファイルの1行に不正なUTF-8バイト列が含まれる
- **THEN** 読み取りは警告付きでその行だけをスキップし、前後の正常なイベントを返す

### Requirement: v1/v2混在ログの読み取り
読み取り側は `schema_version` が1と2の行が混在するログを受理し、両方を構造化イベントとして返さなければならない（SHALL）。未知の `schema_version` の行は警告付きでスキップしなければならない（MUST）。

#### Scenario: 旧ログも読める
- **WHEN** v1セッションのログにv2セッションのイベントが追記されたファイルを読む
- **THEN** 両セッションのイベントがすべて返り、エラーは発生しない

### Requirement: 上限超過の警告イベント
結果行数上限の超過により障害注入を素通しした場合、`limit_exceeded` イベントを記録しなければならない（SHALL）。イベントには対象の上限種別と観測値を含み、生の行値を含んではならない（MUST NOT）。警告イベントの `outcome` 語彙は契約文書に列挙しなければならない（SHALL）。

#### Scenario: 大きすぎる獲物は見送る
- **WHEN** 行数上限を超える結果を返すSELECTを実行する
- **THEN** 結果は無改変で返り、`event_type: "limit_exceeded"` のイベントに上限種別と観測行数が記録される

### Requirement: debugモードの決定イベント
debug設定が有効な場合に限り、発火しなかった障害決定も `decision_evaluated` イベントとして記録できなければならない（SHALL）。既定では発火したイベントのみを記録しなければならない（MUST）。debugイベントの有無はreplay比較の対象から除外されなければならない（MUST）。

#### Scenario: なぜ発火しなかったかを調べる
- **WHEN** debug設定を有効にして障害が発火しない操作を実行する
- **THEN** `decision_evaluated` イベントから decision_key と評価された障害を確認でき、debug無効の同一runと発火イベント列は一致する
