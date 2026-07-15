## MODIFIED Requirements

### Requirement: 障害確率の設定
`wrap()` は障害ごとの発火確率（firing probability）設定を受け付けなければならない（SHALL）。設定されない障害の発火確率は0でなければならず（MUST）、発火確率0はその障害を無効化しなければならない（MUST）。契約文書の既存語「base weight」は、本要件が定義する発火確率と同じ値を指す呼称であり、mood倍率適用前の値を表す（SHALL）。mood有効時の実効発火確率は base weight（発火確率） × mood係数 で計算される（SHALL）。発火確率はfaultごとに独立した判定に用いられ（`fire:<FAULT>` によるdomain separation）、同一操作で複数のfaultの発火判定に同一の導出値を流用してはならない（MUST NOT）。発火確率は、実際に適用される頻度（観測発生率／observed rate）と同義ではなく（SHALL）、両者の関係は「1操作1 faultと優先順位」要件が定める。スコーピング設定 `only_tables` / `exclude_tables` が与えられた場合、分類器が抽出したテーブル名に基づいて障害適用の対象を制限しなければならない（SHALL）。テーブル名を抽出できない文は、`only_tables` 指定時は対象外、`exclude_tables` 指定時は対象としなければならない（MUST）。`only_tables` と `exclude_tables` の同時指定は意味が曖昧なため、設定エラーとして拒否しなければならない（MUST）。

#### Scenario: 全確率0で無風
- **WHEN** 全障害の確率を0にして任意のクエリ列を実行する
- **THEN** fault イベントは一件も記録されず、結果は素の接続と完全に一致する

#### Scenario: 対象テーブルを絞る
- **WHEN** `only_tables=["orders"]` を指定し、`orders` と `users` へのSELECTを実行する
- **THEN** 障害は `orders` への文にのみ発火し得て、テーブル名を抽出できないCTE文には発火しない

### Requirement: 1操作1 fault と優先順位
1回の操作で適用される障害は最大1つでなければならない（MUST）。評価はphase順に行い、`before_execute` で failure injection（BARK、GUARD_BOWL、IGNORE）が発火した場合、文を実行してはならない（MUST NOT）。SLOTHは `before_execute` で発火しても遅延後に実行を継続し、その操作のfault枠を消費する（SHALL）。`on_result` の候補は、契約文書に記載された固定の全順序 — failure injection（NO_DROP、STASHエラーモード）、形状変異（STASH行欠落、FALSE_EMPTY、TAIL_CHASE、PAGE_HOLE、ECHO、SHUFFLE）、値変異（TANGLED_LEASH、CHEW、WRONG_COUNT）、状態系（OLD_BONE）の順 — で評価し、最初に発火した1つだけを適用しなければならない（SHALL）。前提条件を満たさない障害は発火候補になってはならない（MUST NOT）。

この先勝ちによる排他適用の帰結として、後順位のfaultが実際に適用される頻度（観測発生率）は、設定した発火確率 `p_i` そのものとは一致しない（SHALL）。同一操作で候補となる（前提条件・スコープを満たす）先順位のfaultをそれぞれ `j` としたとき、後順位fault `i` の観測発生率は概算 `p_i × Π(1−p_j)` に遮蔽される（SHALL）。この `p_i`・`p_j` はmood倍率適用後の実効発火確率であり、mood無効時は設定した発火確率に等しい（SHALL）。この近似式は契約文書とREADMEに明記しなければならない（SHALL）。

#### Scenario: 候補が競合しても1つだけ
- **WHEN** 同一操作でIGNOREとSHUFFLEの両方が発火候補になる
- **THEN** IGNOREのみが適用され、イベントログに記録される fault は1件である

#### Scenario: 優先順位は固定表に従う
- **WHEN** 同一操作でECHOとCHEWの両方が発火候補になる
- **THEN** 形状変異であるECHOだけが適用され、同一入力列の再実行でも常に同じ選択になる

#### Scenario: 先勝ちにより後順位の観測発生率は遮蔽される
- **WHEN** 先順位のfault（例: STASHエラーモード、order 6）の発火確率を1.0に設定し、後順位のfault（例: FALSE_EMPTY、order 8）にも同時に非0の発火確率を設定して同一操作を評価する
- **THEN** 後順位のfaultが適用されることはなく、適用されるfaultは常に先順位のfaultであり、後順位の観測発生率は0（近似式 `p_i × Π(1−p_j)` の `p_j=1` の極限）に一致する
