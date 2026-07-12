# event-log — delta for fault-taxonomy

## ADDED Requirements

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
