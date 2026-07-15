## Context

`_InterventionEngine.execute()`（`connection.py:131-151`）は、次の4条件のいずれかで decision・event を生成せずバックエンドへ素通しする: `params` がMapping（名前付きパラメータ）、SQL分類器（`sql.py`）が `SQLKind.UNKNOWN` と判定、`classification.is_transaction`（BEGIN/COMMIT/ROLLBACK）、パラメータfingerprintの入力域外（`unsupported_params`）。理由別記録は `unsupported_params` の1系統のみ（143-144行）で、他3系統は素通しの事実自体がstatsに残らない。`executemany()`（242-246行）はさらに分類記録すら持たない。

README 132行目は「理由別の匿名素通し件数」を契約として謳っており、この実装とのギャップが外部レビュー指摘の派生として issue #22 で確定した。決定済み仕様はグリルセッション（issue #22 本文）で固定済みであり、本 design.md は実装方針の確認と、issueが明示していない実装レベルの疑問の切り出しに専念する。

`on_max_rows`（`faults.py` の `FaultPolicy.on_max_rows`、既定 `"skip"`）が「命名対称の根拠」として issue に明記されている。`on_max_rows="error"` は `limit_exceeded` イベントを記録した**後**に `DollyLimitError`（`DogDBError` 派生、実event_idを保持）を送出する（`faults.py:366-369`）。この「記録してから送出」順序は `max-rows-and-session-limits` change の design.md（D2）で確定した既存パターンであり、本changeの `on_passthrough="error"` にも構造として踏襲できる可能性が高いが、素通し操作は既存契約で「decision・イベントを生成してはならない（MUST NOT）」と規定されており、`limit_exceeded` のような実イベントが存在しない点が `on_max_rows` との非対称点になる（Decisions / Open Questions参照）。

## Goals / Non-Goals

**Goals:**
- 正規語彙5種すべての素通し理由を `conn.dolly.stats()` から観測可能にする（`on_passthrough` の設定値に関わらず常時記録）。
- 「注入したつもりが素通り」の罠を、利用者が opt-in で warn/error に格上げできるようにする。
- `stats()` のsnapshot形状を破壊しない（キー追加のみ）。
- README記述と実装を一致させる。

**Non-Goals:**
- SQL分類器（`sql.py`）自体の変更・sqlglot導入（W6-1/issue #20の射程）。
- 素通し対象範囲（5理由の分類ロジック）自体の拡大・縮小。
- `POLICY_VERSION` の変更（決定キー・イベント系列導出は本changeで一切変えない — 素通し操作は現行もdecision・eventを生成しないため、record-then-raiseの経路を新設しても導出系列に影響しない前提。この前提はDecisionsで確認する）。
- `transaction_statement`／`executemany` を発火対象に追加するオプション（issueで対象外と確定済み）。

## Decisions

### D1: 理由別記録は `on_passthrough` の設定値と独立に、常時行う

5理由の記録（stats加算）と、`on_passthrough` によるwarn/error発火は直交する関心事として実装する。issue受け入れ基準は「5理由すべての記録テスト」と「`on_passthrough` 3モードのテスト」を別項目として列挙しており、記録は allow/warn/error のいずれでも変わらず行われる（warn/errorは記録に加えて追加の通知・拒否を行うだけ）。

### D2: `on_passthrough="error"` は記録してから送出する

`on_max_rows="error"`（`DollyLimitError`、`limit_exceeded` イベントを記録した後に送出）の既存パターンに倣い、`on_passthrough="error"` も stats記録を先に行ってから `DollyPassthroughError` を送出する。これにより、ブロックされた操作もobservability上は消えない（stats加算は残る）。issueの「素通し実行後に怒るのは矛盾」という要請は「バックエンド実行」の前後についてのものであり、「stats記録」の前後については触れていない。stats記録はイベントログへの書き込みとは別の集計であり、素通し操作へのdecision・イベント禁止（既存dbapi-proxy契約）には抵触しない。

### D3: `DollyPassthroughWarning` はPython標準の `Warning` 系統に属し、`DogDBError` とは無関係の階層とする

`warnings.warn(msg, DollyPassthroughWarning)` はPythonの警告機構であり、例外階層（`DogDBError`）とは独立している。命名のみ既存Dolly*語彙に整合させ、継承関係は `Warning`（または `UserWarning`）を起点とする。

### D4: 発火対象3種・除外2種の理由

issue決定を転記する（発明ではなく確認）: 発火対象は `unknown_sql`・`named_parameters`・`unsupported_parameter_type` — いずれも「バインドしたつもりの値がfingerprint化・注入対象化されず、利用者が誤ってテストの意図を達成できていると錯覚しうる」操作である。除外対象は `transaction_statement`（BEGIN/COMMIT/ROLLBACKは構造的に障害注入の対象になり得ない正常運転であり、警告する意味がない）と `executemany`（README限界節で既に対象外と宣言済みの表面であり、対象に含めるとORMのbulk insert等の定型操作が警告まみれになり、シグナル対ノイズ比が崩れる）。この2種は `on_passthrough` の値に関わらず常に無警告・無エラーで素通しする。

## Risks / Trade-offs

- [`on_passthrough="warn"` が定型操作（例: マイグレーションツールのPRAGMA発行）で警告過多になる] → 発火対象を3種に絞ることで軽減済み（issue決定）。それでも問題化する場合はテーブルスコープ（`only_tables`/`exclude_tables`）との組み合わせで利用者側が絞り込む。
- [`on_passthrough="error"` が既存の「素通しは操作を失敗させない」契約（対応範囲外操作の素通しRequirement）と字面上衝突する] → 「既定 `allow` では失敗させない」契約は維持し、`error` はopt-in時のみの例外であることをspec/契約文書で明示する。
- [理由別記録の分類優先順位が未定義のまま複数理由に該当する操作が発生した場合、記録・発火判定が実装依存になる] → Open Questions参照。低頻度の境界ケースであり、5理由それぞれの独立シナリオでの記録・発火は本changeのスコープで固定するが、複数理由の同時該当時の優先順位はspec本文で断定しない。

## Open Questions

1. **`DollyPassthroughError` は `DogDBError` を継承すべきか。** 継承する場合、`DogDBError.__init__` は `event_id` を必須引数として要求するが、素通し操作は既存契約で「decision・イベントを生成してはならない（MUST NOT）」ため、`DollyLimitError`（`limit_exceeded` という実イベントのevent_idを持つ）のような裏付けが存在しない。issueは「非retryableの `DollyPassthroughError`」とのみ記載し、`DogDBError` 継承や `event_id`・`category`・`severity` の要否には触れていない。選択肢: (a) `DogDBError` を継承しない独立例外にする（`retryable` 属性など最小限のみ持たせる）、(b) `DogDBError` を継承し、event_idには実イベントを伴わない識別子（例: 記録目的のみで `conn.dolly.log()` には現れない合成ID）を持たせる、(c) `on_passthrough="error"` の発火時に限り、素通し操作の「decision・イベントを生成してはならない」契約の適用範囲を「実行に至った素通し」に限定し直し、新規イベント種別（例 `passthrough_blocked`）を導入して `limit_exceeded` と同型にする。(c)は既存Requirementの文言変更を伴うため影響が最も大きい。→ **確定（統括レビュー、2026-07-15）**: (a)を採用する。`DogDBError` を継承しない独立例外とし、契約上の必須属性は読み取り専用の `retryable`（`False` 固定）のみとする。根拠: 素通しはイベント生成禁止で `event_id` の裏付けが構造的に存在せず、(b)の合成IDは `dolly.log()` と相関できない罠になる。(c)は既存契約の適用範囲変更で影響が過大。また本例外は注入faultではなく設定ポリシー違反であり、fault処理として `DogDBError` を捕捉する利用者コードに握りつぶされるべきでない。
2. **`params` がMappingかつSQL分類がUNKNOWN／トランザクション文であるなど、複数の素通し理由に同時該当する操作の分類優先順位。** 現行コードの早期return条件（`is_mapping or classification.kind is UNKNOWN or classification.is_transaction or unsupported_params`、`connection.py:145-150`）は理由を区別せず一括で素通しするため、優先順位は未定義。issueは5理由を独立した表で列挙するのみで、重複時の優先順位を指定していない。最小スコープとして、既存条件式の評価順（`named_parameters` → `unknown_sql` → `transaction_statement` → `unsupported_parameter_type`）をそのまま理由決定の優先順位に採用する案が実装コストが最小である。→ **確定（統括レビュー、2026-07-15）**: この案を採用する。評価順を理由決定の優先順位として実装コメントとテストで固定し、spec本文では重複時の挙動を断定しない。
