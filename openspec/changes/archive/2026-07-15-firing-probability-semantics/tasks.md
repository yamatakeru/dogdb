## 1. 公開kwargの一本化

- [x] 1.1 `src/dogdb/proxy/connection.py` `wrap()`: シグネチャから `fault_probabilities: Mapping[str, float] | None = None`（611行）を削除する
- [x] 1.2 `src/dogdb/proxy/connection.py` `wrap()`: 637-639行の二重kwargs受け付け（`supplied = fault_probabilities if fault_probabilities is not None else faults`）を `faults` 単独参照へ簡略化する
- [x] 1.3 リポジトリ全体で `grep -rn fault_probabilities .`（`.git` 除外）を実行し、実装・テスト・examples・READMEの残存が0件であることを確認する。意図的な残存（OpenSpecアーカイブや本change自身のartifact等の歴史的記録）は、その分類を確認結果に明記する

## 2. README・契約文書の更新

- [x] 2.1 `README.md:32` 付近: `fault_probabilities` の言及を削除し、「発火確率」を正式名として導入する文言へ差し替える（`faults` のみを案内する）
- [x] 2.2 `README.md` 「障害モデル」節の末尾（`### opt-in状態機能` を含む節全体の末尾、`## 使用例` の直前）に意味論の小段落を追加する:
  1. 発火判定はfaultごとに独立（`fire:<FAULT>` のdomain separation）
  2. 適用は固定優先順位の先勝ちで最大1件——後順位の観測発生率は概算 `p_i × Π(1−p_j)` に遮蔽される（`j` は `i` より先順位で同一操作の候補となったfaultに限る。`p` はmood倍率適用後の実効発火確率で、mood無効時は設定した発火確率に等しい）
  3. mood有効時はさらに実効倍率が乗る
  4. これが「1障害ずつ小さな確率で足す」推奨の理由である
- [x] 2.3 `README.md` 「限界と安全上の前提」節へ1行追加する（設定した発火確率は観測発生率ではない旨）
- [x] 2.4 `docs/contract-v2.md` のfault合成規則節（46行付近、「未指定の障害の base weight は0である」の後）へ非規範の注記1文を追加する（base weight＝mood倍率適用前の発火確率、観測発生率との乖離）
- [x] 2.5 README・contract-v2に加え、本changeのproposal.md・design.md・specs delta（dbapi-proxy／fault-injection）内で、「発火確率（firing probability）」「base weight」「観測発生率（observed rate）」の対応関係と、近似式の `p` の意味（mood倍率適用後の実効発火確率）が一貫した言葉遣いで示されていることを相互参照して確認する

## 3. テストの確認

- [x] 3.1 `tests/` 配下に `fault_probabilities` を使用する箇所がないことを再確認する（1.3で完了済みなら本タスクは検証のみ）
- [x] 3.2 `wrap()` に `fault_probabilities=` を渡すと `TypeError` になり、かつ `faults=` が正常に受理されることの両面を検証するテストを追加する（`specs/dbapi-proxy` の新規Requirement「障害設定引数の一意性」の2 Scenarioに対応）
- [x] 3.3 全テストを実行する（`.venv/bin/pytest`）

## 4. 検証とGitHub連携

- [x] 4.1 `openspec validate --change firing-probability-semantics`（または `openspec validate firing-probability-semantics`）が通ることを確認する
- [x] 4.2 design.mdのADR節（「何が壊れるか」「なぜ設計的に妥当か」「移行方法」）が破壊的変更ポリシーの要件を満たしていることを確認する
- [x] 4.3 issue #23 へ完了コメントを投稿しクローズする（PRマージ後）
- [x] 4.4 統括issue #19 のW6-4（#23）チェックボックスを更新する（PRマージ後）
