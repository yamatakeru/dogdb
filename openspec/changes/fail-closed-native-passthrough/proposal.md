# fail-closed-native-passthrough — Proposal

GitHub issue: [#3](https://github.com/yamatakeru/dogdb/issues/3)（統括: [#11](https://github.com/yamatakeru/dogdb/issues/11)）

## Why

`DBAPIProxy.__getattr__` は未定義属性を生接続へ無条件転送するため、`conn.cursor()` や DuckDB の `conn.sql()` を経由する操作は障害注入・stats・イベント・論理時計を**沈黙のままバイパス**する。利用者は「注入が効いていないのにカオステストが通った」ことを検出する手段を持たず、テスト専用ツールとしての中核価値（偽陰性を出さないこと）を毀損している。転送に依存する正当なコードはリポジトリ内に現存せず（実測インベントリ：ゼロ件）、「閉じて始めて後で開く」変更は非破壊で行える非対称性があるため、タグ付きリリース前の今が唯一の低コストな実施機会である。

## What Changes

- **BREAKING**: `__getattr__` による生接続への無条件転送を廃止し、全面 fail-closed 化する。未知属性へのアクセスは誘導メッセージ付き `AttributeError` になる。
- `wrap()` に opt-out `allow_native_passthrough=True` を追加する。指定時は従来どおり全転送し、代わりに転送実績を `dolly.stats()` に記録する。
- バックエンドアダプタが「SQL実行能力のある入口」の閉じた集合を宣言する（core にハードコードしない）。宣言された名前（例: `cursor`, `sql`）へのアクセスには専用の誘導メッセージを返し、opt-out 時の stats 分類（`escape_hatches.<name>`）に使う。
- stats のカウントは属性**取得**ではなく**呼び出し時**に行う（`hasattr` 等による汚染を防ぐ）。
- dbapi-proxy spec の「対応範囲外操作の素通し」契約を改訂し、属性レベルの扱い（既定拒否・opt-out 転送）を明文化する。

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

- `dbapi-proxy`: 「対応範囲外操作の素通し」Requirement を改訂。未定義属性の静かな転送を廃止し、既定 fail-closed（誘導付き `AttributeError`）と opt-out `allow_native_passthrough` の二態を規定する。`conn.dolly.stats()` の Requirement を拡張し、opt-out 時の転送記録（escape hatch 呼び出しカウント）を追加する。
- `backend-adapters`: アダプタ契約に「SQL実行能力のある入口名の閉じた集合の宣言」を追加する。

## Impact

- **影響コード**: `src/dogdb/proxy/connection.py`（`__getattr__`、`wrap()` シグネチャ）、`src/dogdb/adapters/base.py`・`duckdb.py`・`sqlite.py`（能力集合の宣言）、`src/dogdb/core/stats.py`（転送カウンタ）。
- **影響 API**: `wrap()` に引数追加（加算的）。プロキシの属性アクセス挙動が変わる（破壊的）。既存の `execute`/`fetch*`/`commit`/`rollback`/`close`/`dolly` 等の明示表面は不変。
- **影響契約**: `openspec/specs/dbapi-proxy/spec.md`、`openspec/specs/backend-adapters/spec.md`。
- **後続 change との関係**: W2（backend-faithful-surfaces）で SQLite の `cursor()` が正式対応になった際、SQLite 側の能力集合から `cursor` を外す（fail-closed 対象が縮む）。W4-a まで DuckDB の `cursor()` は本 change の遮断対象。
- **non-goals**: cursor のプロキシ実装（W2/W4-a の担当）、生 SQL・生パラメータの記録（機密原則により名前バケットのみ）、`executemany`・名前付きパラメータ・分類不能文の既存素通し契約の変更。

## 破壊的変更の宣言

本 change は破壊的変更を含むため、design.md に ADR 節（何が壊れるか／なぜ設計的に妥当か／移行方法）を必須とする（openspec/config.yaml の破壊的変更ポリシー準拠）。
