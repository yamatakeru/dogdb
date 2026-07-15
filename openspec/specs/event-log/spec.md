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

### Requirement: fault_injectedイベントのtaxonomyフィールド
`fault_injected` イベントは、発火した障害の分類を任意フィールド `category` / `severity` として含まなければならない（SHALL）。これらのフィールドをいかなるイベント種別の必須フィールド集合にも追加してはならず（MUST NOT）、replay 比較の対象にしてはならない（MUST NOT）。このフィールド追加で `schema_version` を変更してはならない（MUST NOT）。`fault_injected` 以外のイベント種別（`treasure_returned`・`mood_changed`・`limit_exceeded`・`decision_evaluated`）にはこれらのフィールドを記録してはならない（MUST NOT）。

#### Scenario: 発火イベントに分類が載る
- **WHEN** SHUFFLE が発火し `fault_injected` イベントが記録される
- **THEN** 追記行は `category: "shape"` と `severity: "silent_corruption"` を含み、`schema_version` は 2 のままである

#### Scenario: 分類フィールドを持たない既存ログと互換
- **WHEN** category / severity を含まない既存の v2 ログを読み込み、同一セッションの再実行結果と replay 比較する
- **THEN** 比較は成功する（未定義フィールドは比較対象外）

#### Scenario: 宝物返却イベントには載らない
- **WHEN** STASH の宝物が返却され `treasure_returned` イベントが記録される
- **THEN** 追記行に `category` / `severity` は含まれない

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
結果行数上限の超過により障害注入を素通しした場合、または `max_result_rows` により読み取りを中断した場合、`limit_exceeded` イベントを記録しなければならない（SHALL）。イベントには対象の上限種別（`details.limit`、値は `max_intervention_rows` または `max_result_rows`）と観測値（`details.observed`）を含み、生の行値を含んではならない（MUST NOT）。`max_intervention_rows` 経路の `details.observed` はmaterialize済みの実際の行数（整数）でなければならず（SHALL）、`max_result_rows` 経路の `details.observed` は固定文字列 `"exceeded"` でなければならない（SHALL）——後者はアダプタが上限+1行目を観測した時点で取得を打ち切り、正確な総行数を把握しないことに対応する。`on_max_rows="error"` および `max_result_rows` 超過のいずれも、同一のイベントを先に記録し、その後に例外を送出しなければならない（SHALL）。警告イベントの `outcome` 語彙（`fault_skipped`、およびerrorモード用の語彙 `error`）は契約文書に列挙しなければならない（SHALL）。

#### Scenario: 大きすぎる獲物は見送る
- **WHEN** `max_intervention_rows` を超える結果を返すSELECTを実行する（`max_result_rows` は未設定、`on_max_rows` は既定の `"skip"`）
- **THEN** 結果は無改変で返り（部分結果や例外にはならない）、`event_type: "limit_exceeded"` のイベントに上限種別（`max_intervention_rows`）と観測行数が記録される

#### Scenario: errorモードでもイベントが先
- **WHEN** `on_max_rows="error"` で行数上限を超えるSELECTを実行する
- **THEN** 例外送出の前に `limit_exceeded` イベントがログに記録されており、`dolly.log()` から参照できる

#### Scenario: max_result_rows超過はobservedが固定文字列になる
- **WHEN** `max_result_rows=2` の設定で3行を返すSELECTを実行する
- **THEN** 記録される `limit_exceeded` イベントの `details` は `{"limit": "max_result_rows", "configured": 2, "observed": "exceeded"}` を含み、`dolly.log()` から参照できる

#### Scenario: max_result_rows超過でもイベントが先
- **WHEN** `max_result_rows` 超過により読み取りが中断する
- **THEN** `DollyLimitError` の送出前に `limit_exceeded` イベントがログに記録されている

### Requirement: debugモードの決定イベント
debug設定が有効な場合に限り、発火しなかった障害決定も `decision_evaluated` イベントとして記録できなければならない（SHALL）。既定では発火したイベントのみを記録しなければならない（MUST）。debugイベントの有無はreplay比較の対象から除外されなければならない（MUST）。

#### Scenario: なぜ発火しなかったかを調べる
- **WHEN** debug設定を有効にして障害が発火しない操作を実行する
- **THEN** `decision_evaluated` イベントから decision_key と評価された障害を確認でき、debug無効の同一runと発火イベント列は一致する
