## 1. コア導出の正規化

- [x] 1.1 `src/dogdb/core/decision.py`: `POLICY_VERSION` を `dogdb-v3:normalize=trim+collapse-whitespace+lowercase` へ更新する
- [x] 1.2 `src/dogdb/core/decision.py`: `legacy_unit_interval` / `legacy_id` を削除する
- [x] 1.3 `src/dogdb/core/faults.py` `_fires`: 障害名分岐を削除し、全障害を `unit_interval(key, "fire:<FAULT>")` に統一する
- [x] 1.4 `src/dogdb/core/faults.py` `_event`: event ID分岐を削除し、全障害を `deterministic_id` に統一する
- [x] 1.5 `src/dogdb/core/faults.py` `_stash`: 行位置をdigest直接使用から `derive(key, "rows:STASH")` へ、event ID / treasure IDを `deterministic_id` へ変更する
- [x] 1.6 `src/dogdb/core/faults.py` `_shuffle`: swap導出を `unit_interval(key, "perm:SHUFFLE:<index>")` へ変更する
- [x] 1.7 `src/dogdb/proxy/connection.py` `_log_return`: phaseによるevent ID分岐を削除し `deterministic_id` に統一する

## 2. テストの追随とゴールデン再生成

- [x] 2.1 `tests/test_mood.py` の `legacy_unit_interval` 参照を正規形（`unit_interval` + `fire:` タグ）へ更新する
- [x] 2.2 値非依存の性質テスト群が全通過することを確認する（`.venv/bin/pytest tests/ --ignore=tests/test_mvp_compatibility.py`）
- [x] 2.3 `legacy_` への参照がsrc/testsからゼロであることを確認する（`grep -rn "legacy_unit_interval\|legacy_id" src tests` が空）
- [x] 2.4 ゴールデンフィクスチャをv3実装の出力から1回だけ再生成し、`tests/fixtures/policy_v3_golden.json` として保存する（`schema_version` は2のまま記録し、v1書き戻しハックを廃止する）
- [x] 2.5 `tests/test_mvp_compatibility.py` を `tests/test_policy_regression.py` へ改名し、新フィクスチャを参照するv3基準線の回帰テストへ付け替える
- [x] 2.6 全テストを実行する（`.venv/bin/pytest`）

## 3. 契約文書の更新

- [x] 3.1 `docs/contract-v2.md`: POLICY_VERSION据え置き記述をv3へ更新し、「MVP 導出互換性」節を削除する（用途タグ表は変更しない）
- [x] 3.2 `docs/contract-v1.md`: 冒頭に「歴史的文書・policy v3で失効」のマークを追記する（削除しない）

## 4. 検証とGitHub連携

- [x] 4.1 `openspec validate policy-v3-derivation-cleanup` が通ることを確認する
- [ ] 4.2 issue #7 へ完了コメントを投稿しクローズする（PRマージ後）
- [ ] 4.3 統括issue #11 のW3-aチェックボックスを更新する（PRマージ後）
