## MODIFIED Requirements

### Requirement: 障害確率の設定
`wrap()` は障害ごとの発火重み（base重み）設定を受け付けなければならない（SHALL）。設定されない障害の重みは0でなければならず（MUST）、重み0はその障害を無効化しなければならない（MUST）。mood有効時の実効重みは base重み × mood係数 で計算される（SHALL）。スコーピング設定 `only_tables` / `exclude_tables` が与えられた場合、分類器が抽出したテーブル名に基づいて障害適用の対象を制限しなければならない（SHALL）。テーブル名を抽出できない文は、`only_tables` 指定時は対象外、`exclude_tables` 指定時は対象としなければならない（MUST）。`only_tables` と `exclude_tables` の同時指定は意味が曖昧なため、設定エラーとして拒否しなければならない（MUST）。

#### Scenario: 全確率0で無風
- **WHEN** 全障害の確率を0にして任意のクエリ列を実行する
- **THEN** fault イベントは一件も記録されず、結果は素の接続と完全に一致する

#### Scenario: 対象テーブルを絞る
- **WHEN** `only_tables=["orders"]` を指定し、`orders` と `users` へのSELECTを実行する
- **THEN** 障害は `orders` への文にのみ発火し得て、テーブル名を抽出できない複文には発火しない
