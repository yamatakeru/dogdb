## 1. コアのfast path実装

- [ ] 1.1 `src/dogdb/core/faults.py` `_fires`: 実効確率のチェックを導出ハッシュ計算の前へ移し、確率0では導出しない
- [ ] 1.2 `src/dogdb/core/decision.py` `begin`: 計算済み `template_fingerprint` を受け取れるようにし、再計算を省く
- [ ] 1.3 `src/dogdb/core/decision.py`: `parameter_fingerprint` を1操作スコープのメモ化サプライヤで遅延評価にする（include_params決定入力・イベント・宝物・staleエントリ・デバッグイベントの初回参照で解決、1操作最大1回）
- [ ] 1.4 `src/dogdb/proxy/connection.py` `execute`: phaseごとの観測可能性述語（scoped・debug・実効重み・before_consumed・stale_cache×SELECT）で `decide()` の計算をスキップする
- [ ] 1.5 実効重み判定が操作ごと評価であること（wrap時キャッシュなし）、`mood.multiplier()` を読み取りのみで使うことを確認する

## 2. テスト

- [ ] 2.1 fast path固有テストを追加する: 全重み0で実行後に重みを非0へ変更した3回目の操作のoccurrence・decision keyが、最初から非0のセッションと一致する
- [ ] 2.2 fast path固有テストを追加する: `debug=True` かつ全重み0で `decision_evaluated` イベントが従来どおり記録される
- [ ] 2.3 fast path固有テストを追加する: `include_params=True` および OLD_BONE有効（stale cache）の各経路でイベント・stale参照が従来どおり生成される
- [ ] 2.4 全重み0の実行で `dolly.stats()` の分類集計が全操作分記録されることをテストする
- [ ] 2.5 既存全テスト（v3ゴールデン回帰テスト `tests/test_policy_regression.py` を含む）が**無変更で**通ることを確認する（`.venv/bin/pytest`）——byte-for-byte合格ゲート

## 3. ベンチマーク

- [ ] 3.1 `benchmarks/zero_weight_overhead.py` を新設する（`:memory:` SQLite・小SELECT×2000・素/ラップ複数回測定・中央値の比を報告、CI断言にはしない）
- [ ] 3.2 ベンチマークを実行し、ゼロ実効重み時のオーバーヘッドが素の5倍以内であることを確認して実測値を記録する（PR本文に転記）

## 4. 検証とGitHub連携

- [ ] 4.1 `openspec validate zero-weight-fast-path` が通ることを確認する
- [ ] 4.2 issue #8 へ完了コメント（ベンチ実測値を含む）を投稿しクローズする（PRマージ後）
- [ ] 4.3 統括issue #11 のW3-bチェックボックスを更新する（PRマージ後）
