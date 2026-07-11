# dog-house — 自動返却の追加

## ADDED Requirements

### Requirement: RETURN_TREASURE自動返却
自動返却が設定で有効化された場合、STASH発火時に決定キーから宝物の保持期間（論理操作数）を導出しなければならない（SHALL）。保持期間が経過した宝物は、経過後最初の `execute` / `executemany` 呼び出しの冒頭（当該操作の障害決定より前）で自動的に返却され、`treasure_returned` イベント（phase="auto_return"）として記録されなければならない（MUST）。自動返却は既定で無効であり（MUST）、手動の `return_all()` / `return_treasure()` は自動返却の予定に関わらず即時に機能しなければならない（SHALL）。

#### Scenario: ドリーが気まぐれに返しに来る
- **WHEN** 自動返却を有効にしてSTASHが発火し、その後クエリを重ねて保持期間が経過する
- **THEN** 経過後最初の操作の前に該当行が結果へ復帰し、`phase: "auto_return"` の `treasure_returned` イベントが当該操作のイベントより小さい `seq` で記録される

#### Scenario: 保持期間の起点はSTASH操作の直後
- **WHEN** 論理時計上の操作番号3でSTASHが発火し、保持期間1が導出される
- **THEN** STASH操作自体は経過数に含まれず、操作番号4の冒頭で自動返却される（保持期間Nの宝物はSTASH操作のN操作後の冒頭で返る）

#### Scenario: 返却タイミングも再現する
- **WHEN** 同一seed・同一クエリ列で2回のrunを実行する
- **THEN** 自動返却が起こる操作位置と返却される宝物は両runで一致する
