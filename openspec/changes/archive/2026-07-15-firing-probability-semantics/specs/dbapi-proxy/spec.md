## ADDED Requirements

### Requirement: 障害設定引数の一意性
`wrap()` の障害ごとの発火確率を渡す引数は `faults` の一つでなければならない（SHALL）。同義のエイリアス引数（`fault_probabilities` を含む）を提供してはならない（MUST NOT）。

#### Scenario: 旧エイリアスは受け付けない
- **WHEN** `wrap(raw, seed=1, fault_probabilities={"STASH": 0.1})` を呼ぶ
- **THEN** `TypeError`（未知の引数）が送出され、接続はラップされない

#### Scenario: 正規の引数名は動作する
- **WHEN** `wrap(raw, seed=1, faults={"STASH": 0.1})` を呼ぶ
- **THEN** 接続は正常にラップされ、STASHの発火確率は0.1として設定される
