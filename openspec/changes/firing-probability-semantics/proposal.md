## Why

外部レビュー指摘3（障害確率が独立でなく、固定優先順位の先勝ちで後順位が遮蔽されるため、設定確率≠観測発生率）の妥当性判定（統括issue #19）の結論は、選択モデル自体（固定優先順位・先勝ち・最大1 fault）は正確であり変更不要というものだった。一方で、`wrap()` の二重kwargs（`fault_probabilities` / `faults`、`connection.py:611-612`）と、「probabilities」という命名自体が「設定値＝観測発生率」という誤読の当事者であることが判明した。未リリースで破壊的変更のコストが最小のうちに、選択モデルは一切変更せず、用語・API・文書の整合だけを是正する。

## What Changes

- **BREAKING**: `wrap()` の `fault_probabilities` kwargを削除し、`faults` へ一本化する（`connection.py:611-612`の二重kwargs受け付けと637-639行のマージロジックを解消する）。未リリースにつき破壊自由。
- 設定値の正式名を**「発火確率（firing probability）」**と定める。
- contract-v2の既存語「base weight」は変更せず、「base weight＝mood倍率適用前の発火確率」という対応を1行明示する。
- 対義語として**「観測発生率（observed rate）」**を導入し、「設定値（発火確率）≠観測発生率」を明文化する。
- README「障害モデル」節の末尾に意味論の小段落を追加する:
  1. 発火判定はfaultごとに独立（`fire:<FAULT>`のdomain separation）
  2. 適用は固定優先順位の先勝ちで最大1件——後順位の観測発生率は概算 `p_i × Π(1−p_j)` に遮蔽される（`j` は `i` より先順位で同一操作の候補となったfaultに限る。`p` はmood倍率適用後の実効発火確率で、mood無効時は設定した発火確率に等しい）
  3. mood有効時はさらに実効倍率が乗る
  4. これが「1障害ずつ小さな確率で足す」推奨の理由である
- README「限界と安全上の前提」節へ1行（設定した発火確率は観測発生率ではない旨）を追加する。
- `docs/contract-v2.md` の fault 合成規則節へ、非規範の注記1文（base weightと観測発生率の関係）を追加する。
- 内部 `FaultPolicy(probabilities=...)` は改名しない（Bernoulli発火閾値としては正確な名前であり、改名の価値がコストを下回るため——issueの決定）。

### Non-goals

- 選択モデル自体（固定優先順位・先勝ちによる排他適用・最大1 fault）の変更は行わない。契約どおりの決定値を維持する。
- `POLICY_VERSION` の更新は行わない。本changeは指摘3対応5件中、唯一POLICY_VERSIONを壊さない対応である。
- 内部 `FaultPolicy(probabilities=...)` の改名は行わない。
- fault taxonomy・語彙自体の見直しは対象外（別waveの射程）。

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

- `dbapi-proxy`: `wrap()` の障害設定引数を `faults` 一本に限定する要件を追加する（同義エイリアス `fault_probabilities` の提供禁止。既存の「イベントログ出力先の一意性」要件と同型のkwarg一意性制約）。
- `fault-injection`: 「障害確率の設定」要件の用語を、発火確率（firing probability）／base weight／観測発生率（observed rate）の対応関係で明確化する。「1操作1 faultと優先順位」要件に、固定優先順位の先勝ちによる後順位faultの観測発生率遮蔽（近似式 `p_i × Π(1−p_j)`）を明記する。選択モデルの決定値自体は変更しない。

## Impact

- **コード**: `src/dogdb/proxy/connection.py`（`wrap()` のkwargシグネチャからの `fault_probabilities` 削除、604-642行の二重kwargs受け付け・マージロジックの解消）。
- **文書**: `README.md`（クイックスタート32行付近の `fault_probabilities` 言及、「障害モデル」節末尾、「限界と安全上の前提」節）、`docs/contract-v2.md`（fault 合成規則節への非規範注記）。
- **テスト**: 全数grep済み（`grep -rn fault_probabilities`）。使用箇所は `README.md:32` と `src/dogdb/proxy/connection.py` のみで、`tests/` および `examples/` は既に `faults` のみを使用しており更新不要。
- **利用者影響**: `fault_probabilities` を使用していた外部呼び出しは `TypeError`（未知の引数）になる（**BREAKING**）。外部利用者はゼロ・リリース前のため破壊的変更ガバナンス（openspec/config.yaml）の通常選択肢として実施する。ADR節を design.md に必須で設ける。
- **依存関係**: 統括issue #19が定める並列実装可能な5本のうちの1本。`connection.py` を触る他waveとのコンフリクト解消はwave集約時に親が行う。
