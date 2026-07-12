# event-log — delta: max-rows-and-session-limits

## MODIFIED Requirements

### Requirement: 上限超過の警告イベント
結果行数上限の超過により障害注入を素通しした場合、`limit_exceeded` イベントを記録しなければならない（SHALL）。イベントには対象の上限種別（`details.limit`、値は `max_intervention_rows`）と観測値を含み、生の行値を含んではならない（MUST NOT）。`on_max_rows="error"` の場合も同一のイベントを先に記録し、その後に例外を送出しなければならない（SHALL）。警告イベントの `outcome` 語彙（`fault_skipped`、およびerrorモード用の語彙）は契約文書に列挙しなければならない（SHALL）。

#### Scenario: 大きすぎる獲物は見送る
- **WHEN** 行数上限を超える結果を返すSELECTを実行する
- **THEN** 結果は無改変で返り、`event_type: "limit_exceeded"` のイベントに上限種別と観測行数が記録される

#### Scenario: errorモードでもイベントが先
- **WHEN** `on_max_rows="error"` で行数上限を超えるSELECTを実行する
- **THEN** 例外送出の前に `limit_exceeded` イベントがログに記録されており、`dolly.log()` から参照できる
