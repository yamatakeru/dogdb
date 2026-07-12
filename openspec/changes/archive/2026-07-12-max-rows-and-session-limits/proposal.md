# max-rows-and-session-limits — Proposal

GitHub issue: [#5](https://github.com/yamatakeru/dogdb/issues/5)（統括: [#11](https://github.com/yamatakeru/dogdb/issues/11)）

## Why

`max_rows`（既定10,000）は全行 materialize の**後**に検査され、切り詰めもメモリ保護もしない「fault 適用上限」である。「上限」という名前が安全弁と誤読させ、契約文書の但し書きで名前の嘘を補い続けるのは「宣言表面の正直さ」原則に反する。また `wrap()` には `log_path`／`event_log` という同義の重複引数があり、occurrence／stats 辞書がセッション中単調増加する前提（テスト単位でセッションを作り直す）も未文書である。タグ付きリリース前の今なら、名前と実態の一致を引数改名で達成できる。

## What Changes

- **BREAKING**: `wrap()`／`connect()` の引数 `max_rows` を `max_intervention_rows` に改名する（意味論は不変: fault 適用の上限であり、超過時は結果を無改変で返し `limit_exceeded` を記録する）。
- **BREAKING**: `wrap()` の `event_log` エイリアス引数を削除し、`log_path` に一本化する。
- opt-in `on_max_rows`（既定 `"skip"`、`"error"` 指定可）を追加する。`"error"` はバックエンド実行済みの後に DogDB 例外を送出する（NO_DROP と同様の「実行済みなのに例外」意味論を文書化）。既定の切り詰めは行わない。
- セッション資源の成長特性を契約化する: occurrence／stats は単調増加であり退避（eviction）を行わないこと、セッションはテストケース単位で作り直す前提であることを明文化する。
- `limit_exceeded` イベントの `details.limit` 識別子を新名に追従させる。

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

- `dbapi-proxy`: 介入上限（`max_intervention_rows`）の意味論と `on_max_rows` の二態を Requirement として追加し、設定引数の一意性（イベントログ出力先は単一引数 `log_path`）を規定する。
- `determinism`: セッション状態（occurrence／stats）の不退避を Requirement として追加する（退避は occurrence 再利用により決定キーを変え、「同一入力列は同一イベント列」を破るため）。
- `event-log`: 「上限超過の警告イベント」Requirement を改訂し、`on_max_rows="error"` 時の outcome 語彙とイベント記録順序（記録後に例外送出）を追加する。

## Impact

- **影響コード**: `src/dogdb/proxy/connection.py`（引数改名・削除・`on_max_rows` 伝搬）、`src/dogdb/core/faults.py`（超過時のエラー分岐）、`src/dogdb/core/errors.py`（上限例外型）、全テスト・examples の引数参照。
- **影響契約**: `openspec/specs/dbapi-proxy/spec.md`、`openspec/specs/determinism/spec.md`、`openspec/specs/event-log/spec.md`、`docs/contract-v2.md`（`details.limit` 識別子、outcome 語彙表）。
- **non-goals**: 既定挙動の変更（切り詰め・既定エラー化はしない）、メモリ保護の実装（fetchall 後の検査では原理的に不可能。真の安全弁は streaming を要し非目標）、occurrence 辞書の上限・退避機構。

## 破壊的変更の宣言

引数改名・エイリアス削除を含むため、design.md に ADR 節を必須とする（openspec/config.yaml 準拠）。
