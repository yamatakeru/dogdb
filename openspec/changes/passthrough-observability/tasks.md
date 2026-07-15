## 1. 設計判断の確定（実装着手前）

- [ ] 1.1 design.mdで確定済みの設計判断（統括レビュー2026-07-15: `DollyPassthroughError` は `DogDBError` を継承しない独立例外とし、契約上の必須属性は読み取り専用の `retryable`（`False` 固定）のみ）を実装の前提として確認する（specsは意図的にこの点へ沈黙しており変更不要）
- [ ] 1.2 design.mdで確定済みの理由決定の優先順位（統括レビュー2026-07-15: 既存の早期return条件の評価順 `named_parameters` → `unknown_sql` → `transaction_statement` → `unsupported_parameter_type`）をコード中のコメントとテストで固定する（spec本文は重複時の挙動へ意図的に沈黙しており変更不要）

## 2. 素通し理由5種の記録

- [ ] 2.1 `src/dogdb/core/stats.py`: `StatsTracker.record_passthrough` の呼び出し箇所を洗い出し、理由キー集合が `unsupported_parameter_type`・`named_parameters`・`unknown_sql`・`transaction_statement`・`executemany` の5種であることをコード上明示する（定数化を検討）
- [ ] 2.2 `src/dogdb/proxy/connection.py` の `_InterventionEngine.execute()`（137-155行付近の素通し分岐）で、Mapping判定・UNKNOWN判定・トランザクション判定・入力域外判定のそれぞれから対応する理由キーで `record_passthrough` を呼ぶよう変更する（1.2で決めた優先順位に従う）
- [ ] 2.3 `src/dogdb/proxy/connection.py` の `_InterventionEngine.executemany()`（242-246行）に `record_passthrough("executemany")` を追加する
- [ ] 2.4 `conn.dolly.stats()` の素通し集計が、発生した理由キーのみを含む疎な辞書形状（既存の `unsupported_parameter_type` 単独ケースと同型）を維持していることを確認する

## 3. on_passthroughの受け付けと発火対象の限定

- [ ] 3.1 `src/dogdb/proxy/connection.py` の `wrap()` に省略可能な引数 `on_passthrough: str = "allow"` を追加し、`"allow"` / `"warn"` / `"error"` 以外は明示的な設定エラー（`ValueError`）を送出するようにする
- [ ] 3.2 `on_passthrough` を `_InterventionEngine` へ伝搬する経路を実装する（`FaultPolicy` に含めるか独立フィールドにするかは、決定性・イベント導出に影響しない実装詳細として実装時に決定し、選択理由をコードコメントに残す）
- [ ] 3.3 発火対象を `unknown_sql`・`named_parameters`・`unsupported_parameter_type` の3種に固定し、`transaction_statement`・`executemany` は `on_passthrough` の値に関わらず常に無警告・無エラーで素通しするよう分岐を実装する

## 4. warnモード

- [ ] 4.1 `src/dogdb/core/errors.py`（または新規モジュール）に `DollyPassthroughWarning`（`Warning` 系統、`DogDBError` とは独立の階層）を追加する
- [ ] 4.2 `on_passthrough="warn"` 時、発火対象3種の素通しで `warnings.warn(msg, DollyPassthroughWarning)` を呼び、操作自体はこれまでどおりバックエンドへ委譲する分岐を実装する
- [ ] 4.3 `src/dogdb/__init__.py` の公開エクスポートに `DollyPassthroughWarning` を追加する

## 5. errorモード

- [ ] 5.1 `src/dogdb/core/errors.py` に `DollyPassthroughError`（1.1の設計判断に従った継承関係、`retryable=False` 固定）を追加する
- [ ] 5.2 `on_passthrough="error"` 時、発火対象3種の素通しをバックエンド実行前（`adapter.execute` 呼び出しの前）に検出し、`DollyPassthroughError` を送出して当該操作の文がバックエンドに到達しないようにする
- [ ] 5.3 `src/dogdb/__init__.py` の公開エクスポートに `DollyPassthroughError` を追加する

## 6. テスト

- [ ] 6.1 5理由すべての記録テストを追加する（`named_parameters`・`unknown_sql`・`transaction_statement`・`executemany` の新規4種、および既存 `unsupported_parameter_type` の回帰確認）。実行: `uv run pytest tests/ -k passthrough`
- [ ] 6.2 `on_passthrough` 3モード（`allow`／`warn`／`error`）のテストを追加する: 発火対象3種それぞれで期待どおり発火し（`warn`は`DollyPassthroughWarning`、`error`は`DollyPassthroughError`）、対象外2種（`transaction_statement`・`executemany`）ではいずれのモードでも発火しないこと。加えて、`on_passthrough` 省略時が `allow` 指定時と同一挙動（警告・例外なしの素通し）であることを検証する
- [ ] 6.3 `on_passthrough="error"` がバックエンド実行前に送出されること（文がバックエンドに到達しないこと）を、副作用が観測可能な操作（例: INSERT後の行数不変）で検証するテストを追加する
- [ ] 6.4 `on_passthrough` の未知の値を渡した場合に設定エラーになることのテストを追加する
- [ ] 6.5 `conn.dolly.stats()` のsnapshot後方互換テストを追加する: 本change導入前後で、素通しを伴わない操作列に対する既存キー・値が変わらないこと
- [ ] 6.6 既存テストスイート全通過（`uv run pytest`）を確認する

## 7. ドキュメント更新

- [ ] 7.1 `README.md` 132行付近の「理由別の匿名素通し件数」記述を実装と一致させ、素通し理由の正規語彙表（5種、理由キーと発生箇所）を追記する
- [ ] 7.2 `README.md` に `on_passthrough`（既定 `"allow"`、`"warn"`／`"error"`、発火対象3種・除外2種）の説明を追記する
- [ ] 7.3 `docs/contract-v2.md` を点検し、素通し理由の正規語彙5種とstats snapshotの後方互換（キー追加のみ）の注記を追加・更新する（READMEの変更と整合させる。該当記述の有無に関わらず点検の完了をタスク完了条件とする）

## 8. 検証とGitHub連携

- [ ] 8.1 `openspec validate passthrough-observability` が通ることを確認する
- [ ] 8.2 issue #22 へ完了コメントを投稿しクローズする（PRマージ後）
- [ ] 8.3 統括issue #19 のW6-3チェックボックスを更新する（PRマージ後）
