# max-rows-and-session-limits — Tasks

## 1. opt-in エラー化（非破壊部分を先行）

- [ ] 1.1 `errors.py` に上限例外型（候補: `DollyLimitError(DogDBError)`、`retryable=False`、メッセージに `max_intervention_rows` 調整の案内）を追加する
- [ ] 1.2 `wrap()` に `on_max_rows: str = "skip"` を追加し（許容値検証つき）、`FaultPolicy`／`FaultEngine` へ伝搬する
- [ ] 1.3 `FaultEngine.on_result` の超過分岐に error モードを実装する: `limit_exceeded` イベントを**先に**記録してから例外を送出する
- [ ] 1.4 error モードのテストを追加する: イベントが `dolly.log()` に残った上で例外が送出され、例外が `event_id` を持つこと（両バックエンド）。実行: `uv run pytest tests/ -k "max_rows or limit"`

## 2. 引数改名とエイリアス削除（破壊点）

- [ ] 2.1 `wrap()`／`connect()` の `max_rows` を `max_intervention_rows` に改名し、内部伝搬（`FaultEngine`、`StaleReadCache`）の名前も揃える
- [ ] 2.2 `event_log` エイリアス引数を削除し、`log_path` に一本化する
- [ ] 2.3 `limit_exceeded.details.limit` の識別子を `max_intervention_rows` に更新する
- [ ] 2.4 リポジトリ内の全参照（tests/、examples/、docs/、README）を一括更新し、旧名の残存ゼロを確認する（`grep -rn "max_rows\b|event_log=" --include='*.py' --include='*.md' .` が spec アーカイブ以外でヒットしないこと）

## 3. セッション資源の契約化

- [ ] 3.1 不退避テストを追加する: 大量テンプレート実行後も最初のテンプレートの再実行が `occurrence=2` になること
- [ ] 3.2 既存実装に退避・再初期化経路がないことをコードレビューで確認する（`HouseLedger` の上限は宝物数の上限であり occurrence とは別概念であることを確認）

## 4. 検証とドキュメント

- [ ] 4.1 既存テストスイート全通過（`uv run pytest`）と `openspec validate max-rows-and-session-limits` の通過を確認する
- [ ] 4.2 README の「限界と安全上の前提」を更新する: 新引数名、「メモリ保護ではない」の明記、`on_max_rows="error"` の紹介（実行済み後の例外である注意つき）、セッションはテスト単位で作り直す指針
- [ ] 4.3 `docs/contract-v2.md` を更新する: `details.limit` 識別子、`limit_exceeded` の outcome 語彙表への error モード追加、旧識別子の歴史注記
- [ ] 4.4 GitHub issue #5 に完了コメントを残し、統括 #11 のチェックボックスを更新する
