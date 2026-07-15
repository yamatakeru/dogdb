## 1. 公開kwargの一本化

- [ ] 1.1 `src/dogdb/proxy/connection.py` `wrap()`: シグネチャから `fault_probabilities: Mapping[str, float] | None = None`（611行）を削除する
- [ ] 1.2 `src/dogdb/proxy/connection.py` `wrap()`: 637-639行の二重kwargs受け付け（`supplied = fault_probabilities if fault_probabilities is not None else faults`）を `faults` 単独参照へ簡略化する
- [ ] 1.3 `grep -rn fault_probabilities src tests examples` が `README.md` 以外の箇所を返さないことを確認する（現時点で `tests/` `examples/` の使用は0件、変更不要をあわせて確認する）

## 2. README・契約文書の更新

- [ ] 2.1 `README.md:32` 付近: `fault_probabilities` の言及を削除し、「発火確率」を正式名として導入する文言へ差し替える（`faults` のみを案内する）
- [ ] 2.2 `README.md` 「障害モデル」節の末尾（`### opt-in状態機能` を含む節全体の末尾、`## 使用例` の直前）に意味論の小段落を追加する:
  1. 発火判定はfaultごとに独立（`fire:<FAULT>` のdomain separation）
  2. 適用は固定優先順位の先勝ちで最大1件——後順位の観測発生率は概算 `p_i × Π(1−p_j)` に遮蔽される
  3. mood有効時はさらに実効倍率が乗る
  4. これが「1障害ずつ小さな確率で足す」推奨の理由である
- [ ] 2.3 `README.md` 「限界と安全上の前提」節へ1行追加する（設定した発火確率は観測発生率ではない旨）
- [ ] 2.4 `docs/contract-v2.md` のfault合成規則節（46行付近、「未指定の障害の base weight は0である」の後）へ非規範の注記1文を追加する（base weight＝mood倍率適用前の発火確率、観測発生率との乖離）
- [ ] 2.5 README・contract-v2内で「発火確率（firing probability）」「base weight」「観測発生率（observed rate）」の対応関係が一貫した言葉遣いで示されていることを相互参照して確認する

## 3. テストの確認

- [ ] 3.1 `tests/` 配下に `fault_probabilities` を使用する箇所がないことを再確認する（1.3で完了済みなら本タスクは検証のみ）
- [ ] 3.2 `wrap()` に `fault_probabilities=` を渡すと `TypeError` になることを検証するテストを追加する（`specs/dbapi-proxy` の新規Requirement「障害設定引数の一意性」に対応）
- [ ] 3.3 全テストを実行する（`.venv/bin/pytest`）

## 4. 検証とGitHub連携

- [ ] 4.1 `openspec validate --change firing-probability-semantics`（または `openspec validate firing-probability-semantics`）が通ることを確認する
- [ ] 4.2 design.mdのADR節（「何が壊れるか」「なぜ設計的に妥当か」「移行方法」）が破壊的変更ポリシーの要件を満たしていることを確認する
- [ ] 4.3 issue #23 へ完了コメントを投稿しクローズする（PRマージ後）
- [ ] 4.4 統括issue #19 のW6-4（#23）チェックボックスを更新する（PRマージ後）
