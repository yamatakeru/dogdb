## MODIFIED Requirements

### Requirement: 乱数導出のdomain separation
決定キーから導出する値（発火判定、行位置、順列、遅延量、保持期間、stale参照先など）は、`SHA-256(decision_key ‖ ":" ‖ 用途タグ)` の形で用途ごとに分離されたハッシュから導出しなければならない（MUST）。用途タグの一覧は契約文書に列挙しなければならない（SHALL）。同一の導出値を複数の用途に流用してはならない（MUST NOT）。この規則は全障害に例外なく適用され、特定の障害のための代替導出経路を実装してはならない（MUST NOT）。

#### Scenario: 障害ごとに別の導出値で判定される
- **WHEN** 2つの障害に同じ重みを設定して同一操作を評価する
- **THEN** 各障害の発火判定は互いに異なる用途タグ（`fire:<FAULT>`）から導出された別の値を使い、同一の導出値が複数の障害の判定に再利用されることはない

#### Scenario: MVP由来の3障害も正規形から導出される
- **WHEN** STASH・SHUFFLE・IGNOREのいずれかを評価・適用する
- **THEN** 発火判定は `fire:<FAULT>`、STASHの行位置は `rows:STASH`、SHUFFLEの各交換は `perm:SHUFFLE:<index>` の用途タグから導出され、event ID / treasure IDも他の障害と同一の導出形を使う
