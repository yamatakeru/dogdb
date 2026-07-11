# determinism — delta: max-rows-and-session-limits

## ADDED Requirements

### Requirement: セッション状態の不退避
occurrence カウンタおよび fingerprint 単位の統計は、セッション存続中に退避（eviction）や再初期化を行ってはならない（MUST NOT）。これらはセッション内で単調増加であり、退避による occurrence の再利用は同一入力列に対する決定キーを変化させるため禁止される。セッションの想定寿命はテストケースまたは小規模テストスイート単位であり、長時間稼働プロセスへの常設を想定しないことを契約文書に明記しなければならない（SHALL）。

#### Scenario: 大量テンプレートでも退避されない
- **WHEN** セッション内で相異なるSQLテンプレートを大量（例: 10,000種）に実行した後、最初のテンプレートを再実行する
- **THEN** 再実行の `occurrence` は 2 であり、決定キーはテンプレート数の影響を受けない
