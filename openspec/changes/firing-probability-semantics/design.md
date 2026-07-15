## Context

外部レビュー指摘3の妥当性判定（統括issue #19）は、fault適用の排他（固定優先順位の先勝ち・最大1 fault）自体は `faults.py:240-256` と `contract-v2.md:46` に明文化された正しい設計判断であると確定した。一方で、発火判定自体は `fire:<FAULT>` タグによるdomain separation（`faults.py:216-226`）でfaultごとに独立しており、「疑似乱数の共有」ではなく「適用の排他による遮蔽」が観測発生率が設定値と乖離する正確な機構である。

この乖離が起きる余地は、`wrap()` の公開kwargが `fault_probabilities` と `faults` の二重（`connection.py:604-642`、611-612行で宣言、637-639行でマージ）であることと、「probabilities」という名前が「設定値＝観測発生率」という誤読を誘発することの2点に集約される。グリルセッション（issue #23）で、選択モデルは変更せず、用語・API・文書の整合のみで対応する方針が確定済みである。

## Goals / Non-Goals

**Goals:**

- `wrap()` の障害設定引数を `faults` 一本に統一し、`fault_probabilities` を削除する。
- 設定値の正式名を「発火確率（firing probability）」として定義し、contract-v2の既存語「base weight」との対応、および対義語「観測発生率（observed rate）」を明文化する。
- README「障害モデル」節・「限界と安全上の前提」節・`docs/contract-v2.md` に、issue #23で確定した意味論（発火判定の独立性、先勝ち適用による観測発生率の遮蔽、mood倍率、推奨運用）を反映する。

**Non-Goals:**

- 選択モデル自体（固定優先順位・先勝ちによる排他適用・最大1 fault）の変更。決定値・golden fixtureへの影響はゼロに保つ。
- `POLICY_VERSION` の更新。本changeは決定キー導出に一切触れない。
- 内部 `FaultPolicy(probabilities=...)` および `FaultPolicy.probability()` の改名。
- fault taxonomy・優先順位表・語彙自体の見直し。

## Decisions

### D1: `fault_probabilities` は非推奨期間を置かず即時削除する

代替案として、非推奨警告付きで1リリース分残す案を検討したが却下した。未リリースにつき外部利用者はゼロで、互換シムの受益者が存在しない。加えて、二重kwargsそのものが指摘3の一部（「probabilities」という名前が誤読を誘発する）であるため、残存期間を設けることは問題を先送りするだけである。`connect()` は `wrap()` へ `**options` を委譲するのみで独自にkwargを宣言しないため（`connection.py:709-726`）、変更点は `wrap()` の1箇所に閉じる。

### D2: 用語の配置は「定義1箇所＋参照複数箇所」とする

「発火確率」の正式定義とREADME:32付近のquickstart文言に置き、`docs/contract-v2.md` には「base weight＝mood倍率適用前の発火確率」という対応を1行（非規範）で示すのみに留める（contract-v2の既存語「base weight」自体は変更しない、issueの決定）。「観測発生率」はREADME障害モデル節末尾の4点セマンティクス段落で導入し、限界節の1行、contract-v2の非規範注記でも同じ語を再利用する。同じ概念に複数の言い方を作らない。

### D3: spec deltaは`dbapi-proxy`と`fault-injection`の2ファイルに分ける

`wrap()` のkwarg一意性（「同義エイリアスを提供してはならない」という制約）は、既存の `dbapi-proxy` spec「イベントログ出力先の一意性」要件（`log_path` 単一化、同義エイリアス `event_log` を拒否する既存の型）と同じ性質の制約であり、同spec内にADDED Requirementとして追加する（`### Requirement: 障害設定引数の一意性`）。一方、発火確率／base weight／観測発生率の用語対応と、先勝ちによる観測発生率遮蔽の近似式は、値の意味論そのものであり `fault-injection` spec「障害確率の設定」要件（MODIFIED）と「1操作1 faultと優先順位」要件（MODIFIED）に属する。既存要件の見出しは変更しない（本文のみ更新）。

## ADR: 公開kwarg `fault_probabilities` の削除

**何が壊れるか**: `wrap(..., fault_probabilities={...})` を呼んでいた既存コードは `TypeError`（未知のキーワード引数）になる。`faults={...}` に書き換えれば、キーと値の意味（障害名→0〜1の発火確率）は完全に不変であり、機械的な引数名置換で移行できる。決定キー・導出値・イベント列・`POLICY_VERSION` への影響はない。

**なぜ設計的に妥当か**: `fault_probabilities` は未リリースの公開APIであり、外部利用者ゼロ（`grep -rn fault_probabilities` で確認した使用箇所は `README.md:32` と `connection.py` 自身のみで、`tests/`・`examples/` は既に `faults` のみを使用）。互換維持のコスト（二重kwargsの受け付けとマージロジック、ドキュメント上の二重表記）を正当化する受益者が存在しない。さらに、「probabilities」という名前自体が指摘3の誤読（設定値＝観測発生率という誤解）の当事者であり、削除は単なる整理ではなく誤読源の除去そのものである。名前を変えず両方残す選択肢は、誤読源を温存したまま複雑さだけ増やすため却下した。

**移行方法**: 呼び出し側は `fault_probabilities=` を `faults=` に置換するのみ。値の形式・意味論は無変更。リポジトリ内に旧kwargへの依存は存在しない（grep済み）。ロールバックは単一PRのrevertで完結する（データ移行・golden再生成は不要、`POLICY_VERSION` 不変）。

## Risks / Trade-offs

- [近似式 `p_i × Π(1−p_j)` が「発火確率を上げれば必ずその割合で観測される」という新しい誤解を生むリスク] → 4点セマンティクス段落と非規範注記で明示的に「概算（≈）」と表記し、「1障害ずつ小さな確率で足す」推奨の理由として提示することで、複数fault同時設定が乖離を広げる実践的な回避策とセットで説明する。
- [「発火確率」「base weight」「観測発生率」の3用語が並立し、読者がどれが正式名か迷うリスク] → 正式名は「発火確率」のみとし、「base weight」はcontract-v2内の既存語として1行で対応を示すだけに限定、「観測発生率」は対義語として常にペアで導入する。3用語を独立に定義しない。
- [`only_tables` / `exclude_tables` によるスコープ限定時、対象外操作では候補集合自体が変わるため近似式の前提が崩れるリスク] → 「同一操作で前提条件・スコープを満たす候補に限る」旨を明示する（Open Questionsで詳述）。

## Migration Plan

1. `src/dogdb/proxy/connection.py`: `wrap()` シグネチャから `fault_probabilities` を削除し、604-642行の二重kwargs受け付け（611-612行）とマージロジック（637-639行）を `faults` 単独参照へ簡略化する。
2. `README.md`: quickstart（32行付近）の `fault_probabilities` 言及を除去、「障害モデル」節末尾に4点セマンティクス段落を追加、「限界と安全上の前提」節に1行追加する。
3. `docs/contract-v2.md`: fault合成規則節（46行付近）へ非規範の注記1文を追加する。
4. spec delta適用: `dbapi-proxy`（ADDED「障害設定引数の一意性」）、`fault-injection`（MODIFIED「障害確率の設定」「1操作1 faultと優先順位」）。
5. `grep -rn fault_probabilities tests examples` が空であることを再確認する（既に空を確認済みのため、実装時の変更は不要）。
6. 全テスト実行、`openspec validate` 通過を確認する。ロールバックは単一PRのrevertで完結する（データ移行なし、`POLICY_VERSION`不変）。

## Open Questions

- **近似式 `p_i × Π(1−p_j)` の `j` の範囲**: issue #23の原文は「後順位の観測発生率は概算 `p_i × Π(1−p_j)` に遮蔽される」とのみ述べ、`j` が「固定全順序表の全ての先順位fault」を指すのか、「同一操作で前提条件・スコープ（`only_tables`/`exclude_tables`、SQL分類、rowcount等）を満たし実際に候補となった先順位faultに限る」のかを明示していない。コード上は `select_candidate` が事前にフィルタ済みの `candidates` 集合のみを評価するため、後者（候補集合内の先順位のみ）が実装と整合する。本changeでは最小スコープとしてこの限定を明示する文言（「同一操作で候補となる先順位のfaultについて」）を採用した。→ **確定（統括レビュー、2026-07-15）**: この解釈（候補集合内の先順位に限る）で確定する。`select_candidate` の実装意味論と一致し、READMEに載せる近似式の説明としても観測発生率に最も近い。
