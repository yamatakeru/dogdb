# unsupported-param-passthrough — Proposal

GitHub issue: [#4](https://github.com/yamatakeru/dogdb/issues/4)（統括: [#11](https://github.com/yamatakeru/dogdb/issues/11)）

## Why

`parameter_fingerprint` はホワイトリスト外のパラメータ型に実行前 `TypeError` を送出する（determinism 契約の明示的 MUST）。しかし sqlite3 の `__conform__` 型など**生ドライバが受理する型でも、全障害確率0のラッパーが実行を拒否してクラッシュ**する（実測済み）。名前付きパラメータが「静かな素通し」でクエリ実行されるのと非対称であり、テスト用ラッパーが被テストアプリより先に落ちるのは非介入性の毀損である。

## What Changes

- **BREAKING（契約改訂）**: determinism 契約の「ホワイトリスト外は実行前に `TypeError` で拒否（MUST）」を削除する。
- ホワイトリスト外の位置パラメータを含む操作を、名前付きパラメータ・分類不能文と同じ「対応範囲外操作の素通し」族へ合流させる: fingerprint・decision・イベントを生成せず、バックエンドへ無介入で委譲する。
- 素通し操作でも論理時計（mood／自動返却）は進む——現行の named/UNKNOWN 素通しの挙動に揃え、契約に明文化する。
- 素通し操作は occurrence を消費しない（後続クエリの決定キーが不変であることを契約で保証する）。
- `dolly.stats()` に `unsupported_parameter_type` の素通しカウンタを追加する（生パラメータ・型名の値は記録しない）。
- フォールバック fingerprint（repr／pickle／型名）は**採用しない**（決定性保証を静かに損なうため。Fusion パネル全員一致）。

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

- `determinism`: 「パラメータfingerprintの入力域」Requirement を改訂。許可リストは fingerprint 計算の入力域として維持しつつ、入力域外の値を含む操作は拒否ではなく素通しとし、fingerprint・decision・イベントを生成しないことを規定する（「全イベントに parameter_fingerprint 必須」とは、イベント自体を生成しないことで整合）。
- `dbapi-proxy`: 「対応範囲外操作の素通し」Requirement を改訂。素通し対象の列挙に入力域外パラメータ操作を追加し、素通し時の論理時計前進・occurrence 不消費・素通し統計を明文化する。

## Impact

- **影響コード**: `src/dogdb/proxy/connection.py`（execute の素通し分岐）、`src/dogdb/core/decision.py`／`fingerprints.py`（入力域判定の位置）、`src/dogdb/core/stats.py`（素通しカウンタ）。
- **影響契約**: `openspec/specs/determinism/spec.md`、`openspec/specs/dbapi-proxy/spec.md`。
- **後続 change との関係**: W3-b（zero-weight-fast-path）は「unsupported param に対していつ fingerprint が必要か」の本 change の確定を前提とする。
- **non-goals**: フォールバック fingerprint、`include_params=True` 時の特別扱い（入力域外なら同様に素通し）、名前付きパラメータ・executemany の既存素通し挙動の変更。

## 破壊的変更の宣言

determinism 契約の MUST 削除を含むため、design.md に ADR 節を必須とする（openspec/config.yaml 準拠）。
