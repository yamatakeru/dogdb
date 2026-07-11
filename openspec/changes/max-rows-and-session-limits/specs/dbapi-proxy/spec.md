# dbapi-proxy — delta: max-rows-and-session-limits

## ADDED Requirements

### Requirement: 介入上限の意味論
`wrap()` は省略可能な引数 `max_intervention_rows`（既定 10,000）を受け付けなければならない（SHALL）。この値は on_result 障害を適用してよい materialize 済み結果の行数上限であり、取得件数・保持メモリの上限ではない（SHALL）。上限を超えた結果は切り詰めてはならず（MUST NOT）、既定では無改変で呼び出し側へ返し、`limit_exceeded` イベントを記録しなければならない（SHALL）。この意味論（メモリ保護ではないこと）は契約文書と README に明記しなければならない（SHALL）。

#### Scenario: 上限超過でも全行が返る
- **WHEN** `max_intervention_rows=2` の設定で3行を返すSELECTを実行する
- **THEN** 3行すべてが無改変で返り、fault は適用されず、`limit_exceeded` イベントが記録される

### Requirement: 上限超過時の任意エラー化
`wrap()` は省略可能な引数 `on_max_rows`（既定 `"skip"`、許容値 `"skip"` / `"error"`）を受け付けなければならない（SHALL）。`"error"` の場合、上限超過時に `limit_exceeded` イベントを記録した後、`DogDBError` 派生の構造化例外を送出しなければならない（SHALL）。この例外はバックエンドでの実行完了後に発生するものであり、その意味論（実行済みなのに例外）を契約文書に明記しなければならない（SHALL）。例外の送出は設定値と結果行数のみの純粋関数でなければならない（MUST）。

#### Scenario: errorモードは記録してから送出する
- **WHEN** `on_max_rows="error"` かつ `max_intervention_rows=2` の設定で3行を返すSELECTを実行する
- **THEN** `limit_exceeded` イベントが記録された上で `DogDBError` 派生例外が送出され、例外は `event_id` と `retryable` を持つ

### Requirement: イベントログ出力先の一意性
イベントログのファイル出力先を指定する `wrap()` の引数は `log_path` の一つでなければならない（SHALL）。同義のエイリアス引数を提供してはならない（MUST NOT）。

#### Scenario: 出力先指定はlog_pathのみ
- **WHEN** `wrap(raw, seed=1, event_log="x.jsonl")` を呼ぶ
- **THEN** `TypeError`（未知の引数）が送出され、接続はラップされない
