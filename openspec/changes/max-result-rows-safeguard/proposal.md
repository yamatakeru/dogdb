## Why

DogDBは`execute()`のたびに結果を全件materializeし、既存の`max_intervention_rows`は「fault適用の対象行数上限」であって取得件数・保持メモリの上限ではない（README・contract-v2.mdに明記済みの既知の限界）。外部レビュー指摘4はこの点を正確に指摘しており、streaming介入（決定性のため却下済み）や切り詰め返却（W1-cでsilent corruptionとして却下済み）と矛盾しない唯一のメモリ保護方向として、opt-inの読み込み打ち切り安全弁`max_result_rows`を追加する。

## What Changes

- `wrap()`／`connect()` に新規opt-in引数 `max_result_rows: int | None = None` を追加する（既定 `None` ＝無効、挙動不変）。
- 指定時、対象は`max_intervention_rows`検査と同一スコープ（分類・スコープ済みのSELECT文）に限り、バックエンドから結果を読み取る過程で上限+1行目を観測した時点で読み取りを中断する。**部分結果は返さない**（切り詰め返却はW1-c却下のsilent corruptionを再導入するため）。
- 中断時は`limit_exceeded`イベント（既存event type再利用、`details`に`limit="max_result_rows"`・`configured`・`observed="exceeded"`）を記録した後、非retryableな`DollyLimitError`を送出する。この判定はバックエンド上でクエリが実行開始済みである状態で発生する点を契約文書・READMEに明記する。
- `max_intervention_rows`／`on_max_rows`とは独立の直交ノブとし、結合バリデーションは設けない（両方設定時もそれぞれ独立に評価される）。
- アダプタ契約 `execute(sql, params) -> LogicalResult` を `execute(sql, params, *, row_cap: int | None = None) -> LogicalResult` へ拡張し、SQLite/DuckDB両アダプタで`fetchmany`ベースの中断的取得を実装できるようにする（`row_cap=None`時は本change適用前と完全に同一の挙動を維持し、破壊的変更にならない）。
- 中断も決定的に再現する。occurrenceカウンタと論理時計（mood・自動返却）は他の操作と同様に前進する。中断時はon_result phaseの障害候補選択（`FaultEngine.on_result`）を評価しないため`decision_evaluated`イベントは記録されない（同一入力なら同一の欠落でreplay一貫）。before_execute系fault（BARK・GUARD_BOWL・IGNORE・SLOTH）は中断より先に発火し得る。
- `docs/contract-v2.md`（バックエンドアダプタ契約・イベントschema v2の`limit_exceeded`語彙表）と`README.md`の「限界と安全上の前提」節を改訂し、「真のメモリ上限はopt-inで提供される」ことを明記する。

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

- `backend-adapters`: アダプタ契約（`execute`）に省略可能な`row_cap`引数を追加し、`fetchmany`ベースの中断的取得（上限+1行目観測時点での中断、部分結果を返さない）をRequirementとして追加する。
- `dbapi-proxy`: `max_result_rows`ノブの意味論（既定None・中断条件・部分結果非返却・`max_intervention_rows`との直交性・中断時の決定性とイベント欠落・before_execute系faultとの順序）をRequirementとして追加する。
- `event-log`: 「上限超過の警告イベント」Requirementを改訂し、`limit_exceeded`の`details.limit`（`max_result_rows`を追加）と`details.observed`（`max_result_rows`経路では固定文字列`"exceeded"`）の語彙を拡張する。

## Impact

- **影響コード**: `src/dogdb/adapters/base.py`（`materialize`相当の中断的取得ヘルパー追加）、`src/dogdb/adapters/sqlite.py`／`src/dogdb/adapters/duckdb.py`（`execute`への`row_cap`受け入れと`fetchmany`ループ）、`src/dogdb/proxy/connection.py`（`wrap()`への`max_result_rows`追加と伝搬、中断シグナルの捕捉）、`src/dogdb/core/faults.py`（`limit_exceeded`イベント生成の共通化、`DollyLimitError`送出）、全テスト・examples。
- **影響契約**: `openspec/specs/backend-adapters/spec.md`、`openspec/specs/dbapi-proxy/spec.md`、`openspec/specs/event-log/spec.md`、`docs/contract-v2.md`、`README.md`。
- **non-goals**: streaming介入（却下判断は維持、本changeはその布石ではない）、切り詰め返却の導入、`max_intervention_rows`の既定挙動やfault適用ロジックの変更、`POLICY_VERSION`の更新（既定Noneで挙動不変、有効時も決定導出には無関係）、stale-read-cacheの特別扱い（中断した操作は`on_result`決定自体が発生しないため、自然にキャッシュへ記録されない——専用の仕様化は行わない）。
