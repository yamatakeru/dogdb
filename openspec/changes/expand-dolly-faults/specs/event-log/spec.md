# event-log — schema v2とイベント種別ごとのフィールド表

## REMOVED Requirements

### Requirement: スキーマv1の必須フィールド
**Reason**: 全イベント種別に同一の必須フィールド集合を課すv1契約は、fingerprintを持ち得ない `mood_changed` や警告イベントを表現できない。イベント種別ごとの必須フィールド表を持つschema v2へ昇格する。
**Migration**: `fault_injected` / `treasure_returned` のフィールド集合はv2でも同一。writerは `schema_version: 2` を書き、readerはv1行とv2行の両方を受理する。契約は `docs/contract-v2.md` に定義する。

## ADDED Requirements

### Requirement: スキーマv2のイベント種別別フィールド表
すべてのイベントはコアフィールド `schema_version`、`event_id`、`session_id`、`seq`、`event_type` を含まなければならない（MUST）。コア以外の必須フィールドはイベント種別ごとに契約文書の表で定義しなければならず（SHALL）、`fault_injected` と `treasure_returned` の必須フィールド集合はv1と同一でなければならない（MUST）。`mood_changed` はfingerprint系フィールドを要求されてはならない（MUST NOT）。表に定義されないフィールドをreplay比較の対象にしてはならない（MUST NOT）。

#### Scenario: fault_injectedはv1と同じ形
- **WHEN** schema v2のwriterでSTASHが発火する
- **THEN** 追記行は `schema_version: 2` である点を除きv1と同じ必須フィールドをすべて含む

#### Scenario: mood_changedは身軽
- **WHEN** mood遷移イベントが記録される
- **THEN** コアフィールドと `details`（from / to / tick）を含み、`template_fingerprint` を含まなくても契約違反にならない

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
