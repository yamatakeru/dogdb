# unsupported-param-passthrough — Tasks

## 1. 入力域判定

- [ ] 1.1 許可リストを単一の共有定数に抽出し、`params_in_fingerprint_domain(params) -> bool` の純粋関数を `fingerprints.py` に追加する（`_json_default` と同じ列挙を参照すること）
- [ ] 1.2 プロパティテストを追加する: 判定が True の任意のパラメータ列は `parameter_fingerprint` が例外なく計算できる。実行: `uv run pytest tests/ -k fingerprint`

## 2. 素通し分岐

- [ ] 2.1 `DBAPIProxy.execute()` の早期 return 群（Mapping／UNKNOWN／transaction）に入力域判定を追加する。`_begin_operation()` の後に置き、論理時計が進むことを既存素通しと揃える
- [ ] 2.2 `StatsTracker` に `passthrough` 集計（`unsupported_parameter_type`）を追加し、`dolly.stats()` の返り値に含める。型名・値は記録しない
- [ ] 2.3 混在パラメータ列（一部のみ入力域外）でも操作全体が素通しになることを実装で保証する

## 3. 契約テストの書き換えと検証

- [ ] 3.1 旧「TypeError 拒否」を固定していたテスト（`grep -rn "TypeError" tests/test_determinism.py tests/` で特定）を素通し検証へ書き換える
- [ ] 3.2 `__conform__` 型の実測ケースを回帰テスト化する: 全障害確率0のラッパーで生接続と同一結果、イベント不生成、`unsupported_parameter_type` が増分（両バックエンド）
- [ ] 3.3 occurrence 不変テストを追加する: 同一クエリA→素通し操作→クエリA で occurrence が 1, 2 のまま、decision_key が素通しなしの場合と一致すること
- [ ] 3.4 論理時計テストを追加する: auto_return 有効セッションで素通し操作が1論理操作として数えられること
- [ ] 3.5 既存テストスイート全通過（`uv run pytest`）と `openspec validate unsupported-param-passthrough` の通過を確認する

## 4. ドキュメント更新

- [ ] 4.1 README の「限界と安全上の前提」の素通し列挙に入力域外パラメータを追記し、「素通しでも論理時計は進む」の記述を更新する
- [ ] 4.2 `docs/contract-v2.md` に素通し統計と「将来この操作を注入対象化する場合は POLICY_VERSION 判断が必要」の注記を追加する
- [ ] 4.3 GitHub issue #4 に完了コメントを残し、統括 #11 のチェックボックスを更新する
