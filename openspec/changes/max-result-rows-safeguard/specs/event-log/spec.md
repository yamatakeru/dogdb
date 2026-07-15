# event-log — delta: max-result-rows-safeguard

## MODIFIED Requirements

### Requirement: 上限超過の警告イベント
結果行数上限の超過により障害注入を素通しした場合、または `max_result_rows` により読み取りを中断した場合、`limit_exceeded` イベントを記録しなければならない（SHALL）。イベントには対象の上限種別（`details.limit`、値は `max_intervention_rows` または `max_result_rows`）と観測値（`details.observed`）を含み、生の行値を含んではならない（MUST NOT）。`max_intervention_rows` 経路の `details.observed` はmaterialize済みの実際の行数（整数）でなければならず（SHALL）、`max_result_rows` 経路の `details.observed` は固定文字列 `"exceeded"` でなければならない（SHALL）——後者はアダプタが上限+1行目を観測した時点で取得を打ち切り、正確な総行数を把握しないことに対応する。`on_max_rows="error"` および `max_result_rows` 超過のいずれも、同一のイベントを先に記録し、その後に例外を送出しなければならない（SHALL）。警告イベントの `outcome` 語彙（`fault_skipped`、およびerrorモード用の語彙 `error`）は契約文書に列挙しなければならない（SHALL）。

#### Scenario: 大きすぎる獲物は見送る
- **WHEN** 行数上限を超える結果を返すSELECTを実行する
- **THEN** 結果は無改変で返り、`event_type: "limit_exceeded"` のイベントに上限種別と観測行数が記録される

#### Scenario: errorモードでもイベントが先
- **WHEN** `on_max_rows="error"` で行数上限を超えるSELECTを実行する
- **THEN** 例外送出の前に `limit_exceeded` イベントがログに記録されており、`dolly.log()` から参照できる

#### Scenario: max_result_rows超過はobservedが固定文字列になる
- **WHEN** `max_result_rows=2` の設定で3行を返すSELECTを実行する
- **THEN** 記録される `limit_exceeded` イベントの `details` は `{"limit": "max_result_rows", "configured": 2, "observed": "exceeded"}` を含み、`dolly.log()` から参照できる

#### Scenario: max_result_rows超過でもイベントが先
- **WHEN** `max_result_rows` 超過により読み取りが中断する
- **THEN** `DollyLimitError` の送出前に `limit_exceeded` イベントがログに記録されている
