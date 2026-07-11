# max-rows-and-session-limits — Design

## Context

`max_rows` は adapter が全行を materialize した**後**に `FaultEngine.on_result`（faults.py:302-304）で検査され、超過時は fault 適用をスキップして `limit_exceeded`（outcome: `fault_skipped`）を記録し、結果を無改変で返す。実測により、100万行のSELECTは100万行をメモリに載せてから「上限超過」と判定されることを確認済み——つまり**メモリ保護ではない**。しかし「max_rows」という名前は取得上限・安全弁と誤読させる（Fusionパネル3ワーカーが独立に同じ誤解リスクを指摘）。

また `wrap()` には `log_path`／`event_log` の同義重複引数（connection.py:296-297）、occurrence／stats 辞書のセッション内単調増加という未文書の資源特性がある。

grilling で確定した方針: 名前が意味論を語れば但し書きは不要（宣言表面の正直さ原則）。既定挙動は不変。切り詰めは全パネリスト一致で棄却（正常結果を「別のsilent fault」のように破壊し、TAIL_CHASE との区別を失うため）。

## Goals / Non-Goals

**Goals:**
- 引数名と実態の一致（`max_intervention_rows`）。
- 巨大結果でテストを**明示的に**失敗させたい利用者への opt-in（`on_max_rows="error"`）。
- セッション資源の成長特性と不退避原則の契約化。

**Non-Goals:**
- メモリ保護の実装（fetchall 後の検査では原理的に不可能。真の安全弁は streaming architecture を要し、決定性のため MVP design で却下済み）。
- 既定挙動の変更（既定は従来どおり `"skip"`）。
- occurrence／stats の上限・LRU 退避（決定性破壊のため禁止。determinism delta で明文化）。
- `log_path` の機能変更（削除するのは `event_log` エイリアスのみ）。

## Decisions

### D1: 改名先は `max_intervention_rows`
**代替案**: `max_fault_rows`（短いが「fault の行数」と誤読しうる）、犬語彙（`house_limit` と揃える案）— 上限は fault ではなく「介入判定の対象となる結果サイズ」なので、介入（intervention）が最も正確。stats の既存語彙（interventions）とも揃う。

### D2: `on_max_rows="error"` は「記録してから送出」
イベント記録 → 例外送出の順を契約で固定する。**理由**: 例外を先にすると `dolly.log()` から超過の痕跡が消え、「テストが落ちた原因」の観測性が失われる。例外は `DogDBError` 派生（`event_id`／`fault=None` 相当の構造化属性を持つ）とし、実DBエラーとの機械的判別（`isinstance`）を維持する。例外型名は実装時に確定（候補: `DollyLimitError`）。バックエンド実行完了**後**の例外である点は NO_DROP と同じ意味論であり、契約文書に明記する（grok-4.5 の指摘を採用）。

### D3: `event_log` エイリアスは即時削除（deprecation 期間なし）
リリース前・外部利用者ゼロのため、警告付き移行期間はコストだけが残る。未知引数として `TypeError` になる標準挙動に任せる。

### D4: 不退避原則は determinism 契約に置く
資源ガイダンス（README）だけでなく Requirement として固定する。**理由**: 「メモリが増えるので上限を付けよう」という将来の善意のリファクタリングが occurrence 再利用＝決定キー変化を引き起こす事故を、契約違反として機械的に検出可能にする（Fusion パネルで deepseek が LRU 退避を提案し、他 2 ワーカーが決定性破壊として棄却した対立の恒久的決着）。

### ADR: 破壊的変更の宣言

- **何が壊れるか**: `wrap()`／`connect()` の `max_rows` 引数名（→ `max_intervention_rows`）と `event_log` エイリアス引数（削除）。`limit_exceeded.details.limit` の識別子文字列も新名に追従する。既定の実行時挙動は一切変わらない。
- **なぜ設計的に妥当か**: 名前が「取得上限・メモリ保護」を暗示するのに実態は「fault 適用上限」であるという乖離は、契約文書の但し書きでは根治しない。テスト専用ツールの利用者が最初に読むのは引数名であり、名前自体が正しい期待を設定するべき（宣言表面の正直さ原則）。同義エイリアスは「どちらが正か」という問いを永続的に生む負債であり、受益者が現存しない。
- **移行方法**: 機械的な一括置換（`max_rows=` → `max_intervention_rows=`、`event_log=` → `log_path=`）。リポジトリ内の全参照は本 change のタスクで更新する。

## Risks / Trade-offs

- [`details.limit` の識別子変更が記録済みイベントの読み手を混乱させる] → 読み手は現状リポジトリ内のみ。contract-v2 の表を同時更新し、旧識別子は「policy v3 以前の記録にのみ出現」と注記。
- [`on_max_rows="error"` が「メモリ保護になった」と誤読される] → 契約・README・例外メッセージの3箇所で「バックエンド実行済み・全行 materialize 済みの後の判定」であることを明記。
- [W1-a と同一ファイル（connection.py の `wrap()`）を触る] → Wave 1 内の実装順を W1-a → W1-b → W1-c とし、逐次リベースする（統括 #11 の実施順どおり）。

## Migration Plan

1. `errors.py` に上限例外型を追加（非破壊）。
2. `on_max_rows` を追加し、`FaultEngine` の超過分岐に error モードを実装（非破壊・opt-in）。
3. 引数改名とエイリアス削除、全参照の一括更新（破壊点）。
4. determinism delta（不退避）は挙動変更を伴わない契約化のみ。
5. ロールバックは改名の逆置換で完結する。

## Open Questions

- 上限例外の `retryable` は `False` が自然（リトライしても同じ結果サイズ）だが、テストハーネス側で「上限を上げて再実行」を促す語彙が必要か。**暫定判断**: `retryable=False` とし、メッセージで `max_intervention_rows` の調整を案内（実装時に確定）。
