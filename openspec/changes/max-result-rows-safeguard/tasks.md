## 1. アダプタ層: row_capによる中断的取得

- [x] 1.1 `src/dogdb/adapters/base.py` に、内部限定の中断シグナル例外（`row_cap`超過を伝える軽量例外、`dogdb.__init__`のpublic exportに含めない）を追加する
- [x] 1.2 `src/dogdb/adapters/base.py` に、`row_cap`指定時に`fetchmany`ループで結果を取得し、`row_cap + 1`行目を観測した時点で中断してシグナル例外を送出する共通ヘルパーを追加する（`row_cap=None`時は既存の`materialize`と完全に同一の経路を通ること）
- [x] 1.3 `src/dogdb/adapters/sqlite.py` の `execute()` に `row_cap: int | None = None` キーワード専用引数を追加し、1.2のヘルパーを使う
- [x] 1.4 `src/dogdb/adapters/duckdb.py` の `execute()` に同様に `row_cap` を追加する
- [x] 1.5 `description`が`None`の文（行を返さない文）へ`row_cap`を渡しても中断が発生しないことを確認する

## 2. コア層: limit_exceededイベントとDollyLimitError

- [x] 2.1 `src/dogdb/core/faults.py`（または`proxy/connection.py`）に、`max_result_rows`超過時の`limit_exceeded`イベント構築処理を追加する: `DecisionEngine.decide(phase="on_result", ...)`でdecision_keyを導出するが、`FaultEngine.on_result`（fault候補選択・`_debug_decision`フォールバック）は呼び出さない（design.md D3）
- [x] 2.2 上記イベントの`details`に`limit="max_result_rows"`・`configured=<設定値>`・`observed="exceeded"`（固定文字列）を設定する
- [x] 2.3 イベント記録後に非retryableな`DollyLimitError`を送出する（`category`/`severity`を渡さないことで既存のfault-injection spec「介入上限超過ではcategory/severityはNone」を満たすことを確認する。新たなspec変更は不要）
- [x] 2.4 中断時、当該操作について`decision_evaluated`イベントが（`debug=True`でも）記録されないことを確認する

## 3. proxyレイヤ: wrap()と配線

- [x] 3.1 `src/dogdb/proxy/connection.py` の `wrap()` に `max_result_rows: int | None = None` を追加し、`None`以外では正の整数であることを検証する（`require_positive_int`等の既存バリデーションヘルパーを再利用）
- [x] 3.2 `max_result_rows`を`_InterventionEngine`/`FaultEngine`相当の層へ伝搬する
- [x] 3.3 `execute()`内で、既存の`oversized_result`計算と同一スコープ（`scoped_select = scoped and classification.kind is SQLKind.SELECT`）に限り、`adapter.execute(sql, params, row_cap=max_result_rows)`を呼ぶ（design.md D2: 素通し経路・UNKNOWN分類・トランザクション文には適用しない）
- [x] 3.4 1.1のシグナル例外を捕捉し、2.のイベント生成・`DollyLimitError`送出を呼び出す
- [x] 3.5 `max_result_rows`と`max_intervention_rows`の間に結合バリデーションを設けないこと（互いの設定値を読み取らないこと）をコードレビューで確認する
- [x] 3.6 `before_execute` phaseの評価（BARK等）が`row_cap`の付与・中断より先に行われる既存の呼び出し順序を変更しないことを確認する

## 4. テスト（受け入れ基準の写像、両バックエンド）

- [x] 4.1 `max_result_rows`が上限未満・ちょうど・超過の3ケースで正しく動作するテストを両バックエンドで追加する（超過時のみ中断、それ以外は全行が通常どおり返る）
- [x] 4.2 超過時に部分結果が一切呼び出し側へ渡らないこと、`limit_exceeded`イベントの`details`（`limit="max_result_rows"`・`configured`・`observed="exceeded"`）が正しいことを検証するテストを追加する
- [x] 4.3 超過時もoccurrenceカウンタと論理時計（mood・自動返却が有効な設定）が他の操作と同様に前進することを検証するテストを追加する
- [x] 4.4 `before_execute`系fault（BARK）が`max_result_rows`超過より先に発火し、その場合は中断（`limit_exceeded`・`DollyLimitError`）が発生しないことを検証するテストを追加する
- [x] 4.5 `max_intervention_rows`と`max_result_rows`を両方設定した場合の直交動作（互いに影響しないこと）を検証するテストを追加する
- [x] 4.6 同一seed・同一DB状態・同一入力列での中断の決定的再現性（replay一致）を検証するテストを追加する
- [x] 4.7 実行: `uv run pytest tests/ -k "max_result_rows"` および既存テストスイート全体 `uv run pytest` が通過することを確認する

## 5. ドキュメント更新

- [x] 5.1 `docs/contract-v2.md` のアダプタ契約記述（`execute(sql, params) -> LogicalResult`）を `execute(sql, params, *, row_cap: int | None = None) -> LogicalResult` に改訂し、`row_cap`の意味論（`fetchmany`ベースの中断、`None`時は非破壊）を追記する
- [x] 5.2 `docs/contract-v2.md` の「イベント schema v2」`limit_exceeded`語彙節を改訂し、`details.limit`に`max_result_rows`を追加、`details.observed`の型分岐（`max_intervention_rows`は整数、`max_result_rows`は固定文字列`"exceeded"`）を明記する
- [x] 5.3 `docs/contract-v2.md` に、`max_result_rows`と`max_intervention_rows`が独立ノブであり結合バリデーションがないこと、両者の評価順序（`row_cap`中断はバックエンド読み取り中に先に発生しうること）を明記する
- [x] 5.4 `README.md`「限界と安全上の前提」節（149-150行付近）を改訂し、`max_result_rows`によって真のメモリ上限をopt-inで提供できることを明記する（`max_intervention_rows`がメモリ保護でない旨の既存記述は維持する）

## 6. 検証とクローズ

- [x] 6.1 `openspec validate max-result-rows-safeguard`（または`openspec validate --change max-result-rows-safeguard`）を実行しエラーがないことを確認する
- [x] 6.2 全テストスイート（`uv run pytest`）が通過することを確認する
- [ ] 6.3 GitHub issue #24 に実装完了コメントを残す
- [ ] 6.4 統括issue #19 のW6-5チェックボックスを更新する
