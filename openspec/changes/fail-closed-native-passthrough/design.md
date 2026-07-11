# fail-closed-native-passthrough — Design

## Context

`DBAPIProxy.__getattr__`（connection.py:263-264）は未定義属性を生接続へ無条件転送する。このため `conn.cursor()`（両バックエンド）や DuckDB の `conn.sql()` は、障害注入・SQL分類・stats・イベントログ・論理時計のすべてを沈黙のままバイパスする。2回の Fusion パネル（`.fusion-runs/` 記録）と実測で以下が確定している：

- 転送に依存する正当なコードは tests/examples に**現存しない**（属性使用インベントリで実証。ヒットは `conn._mood` 等のプロキシ実属性のみ）。
- 現行の「静かな素通し」契約（dbapi-proxy spec）が列挙するのは `executemany`・名前付きパラメータ・分類不能文というSQLレベルの操作のみで、属性レベルの転送は**未文書**。
- `dolly.stats()` の `interventions: 0` からは「障害が起きなかった」のか「全部バイパスされた」のか区別できない（観測不能）。
- DuckDB の `sql()` は遅延評価の relation を返すため「呼び出し回数≠SQL実行回数」であり、注入対象化は本 change の範囲外。

本 change は統括 issue #11 の Wave 1 先頭であり、W2（backend-faithful-surfaces）で SQLite の `cursor()` が正式対応した後は SQLite 側の遮断対象から `cursor` が外れる。

## Goals / Non-Goals

**Goals:**
- 沈黙バイパスを構造的に不可能にする（既定 fail-closed）。
- 意図的な生アクセスの逃げ道を1つだけ残し（`allow_native_passthrough=True`）、その利用を観測可能にする。
- SQL実行能力のある入口の知識をアダプタに置き、core をバックエンド非依存に保つ。

**Non-Goals:**
- cursor のプロキシ実装（W2 / W4-a）。
- `executemany`・名前付きパラメータ・分類不能文の既存素通し契約の変更（W1-b が別途扱う）。
- 生SQL・生パラメータ・呼び出し引数の記録（機密原則）。
- `__setattr__` 側の統制（`conn.row_factory = ...` 等の代入はプロキシ実属性の設定として現状維持。row_factory の扱いは W2 の非目標として文書化される）。

## Decisions

### D1: 全面 fail-closed（SQL入口限定の遮断ではなく）
**採用**: 公開表面と `_` 内部属性以外のすべての属性アクセスを `AttributeError` にする。
**代替案**: (a) SQL実行能力のある入口だけ遮断し他は転送 — DuckDB の SQL 入口（`sql`/`table`/`query`/`read_csv`/relation API…）は広く進化し続けるため、ブロックリスト追跡は構造的に負け戦。(b) 現状維持＋stats記録のみ — 事後検出であり予防にならない（パネルで対立し、実測インベントリと非対称性論証で全面遮断に決着）。
**根拠**: ①転送依存の現存利用者ゼロ（実測）。②「閉→開」（許可リスト追加）は非破壊、「開→閉」は破壊的という非対称性。タグ前の今だけ閉じる側を無料で選べる。

### D2: 誘導メッセージの二段構え
アダプタ宣言集合に含まれる名前（`cursor`、`sql` 等）には「DogDBはこの入口に注入できません。`execute()` を使うか `allow_native_passthrough=True` を指定してください」という専用メッセージ。それ以外の未知属性には汎用メッセージ（公開表面の列挙と opt-out への言及）。**理由**: 利用者が最も踏みやすい入口で最も具体的な誘導を返す。

### D3: 能力集合はアダプタが宣言（core にハードコードしない）
`DuckDBAdapter` / `SQLiteAdapter` にクラス属性（例: `sql_capable_attrs: frozenset[str]`）を追加。DuckDB: `{"cursor", "sql", "table", "query", "execute", "executemany", ...}` のうち生接続直呼びで SQL を発行しうる名前、SQLite: `{"cursor", "executescript"}` を最低限とする。**理由**: バックエンド追加時の拡張点を1箇所に閉じ、core のバックエンド非依存契約（backend-adapters spec）を守る。

### D4: 計数は「呼び出し時」のみ
opt-out 転送時、宣言集合内の callable は薄いラッパで包んで返し、**呼び出された時**に `StatsTracker` の escape hatch カウンタを増やす。宣言外の転送は名前を集約カウンタ（`other`）で数える。属性取得だけでは計数しない。**理由**: `hasattr`/introspection による汚染防止（パネル一致）。**トレードオフ**: ラップにより object identity が変わるが、opt-out は明示的な逃げ道でありテスト用途では許容（契約文書に明記）。

### D5: stats の構造
`stats()` 返り値に `escape_hatches: dict[str, int]` を追加（例: `{"cursor": 2, "sql": 1, "other": 0}`）。名前は「取得数」ではなく「呼び出し数」を意味する。fault イベントには記録しない（replay 系列と論理時計に診断情報を侵入させない——パネル一致）。

### ADR: 破壊的変更の宣言

- **何が壊れるか**: 未定義属性の生接続への暗黙転送。`conn.cursor()`・`conn.sql()`・その他バックエンド固有属性へのプロキシ経由アクセスが既定で `AttributeError` になる。なお、spec に明記された公開表面（execute/fetch*/commit/rollback/close/dolly 等）は一切変わらない——壊れるのは**未文書の暗黙挙動**のみである。
- **なぜ設計的に妥当か**: テスト専用障害注入ツールの中核価値は偽陰性を出さないことであり、沈黙バイパスはそれを毀損する。旧挙動は互換性のための便宜だったが、その受益者が現存しないことを実測で確認した。前提（暗黙転送に頼る利用がある、という想定）が失効した。
- **移行方法**: 生接続の機能が必要なコードは (1) `allow_native_passthrough=True` を指定する、(2) ラップ前の生接続を直接保持して使う、のいずれか。エラーメッセージ自体が移行先を案内する。

## Risks / Trade-offs

- [将来の実利用者が無害な属性（`interrupt`、`total_changes` 等）で摩擦を受ける] → 許可リストへの追加は非破壊。issue 1本で解決できる運用をREADMEに明記。
- [ダンダーメソッドは `__getattr__` を経由しないため、fail-closed 化しても `with conn:` や `for row in conn` の挙動には影響しない（=本 change では改善もされない）] → イテレーションは W2 の担当であることを契約に注記。
- [opt-out 時の callable ラップで introspection が変わる] → ラップは宣言集合内の名前に限定し、宣言外は素のオブジェクトを返して集約計数のみ行う。
- [テストが `conn._connection` 等の内部属性に直接触れている（test_conformance.py:306-308 ほか）] → `_` 始まりの属性はプロキシ実属性であり `__getattr__` を経由しない。fail-closed の対象は非公開表面の**転送**のみで、既存テストへの影響はないことを実装時に確認する。

## Migration Plan

1. アダプタに能力集合を追加（非破壊）。
2. `wrap()` に `allow_native_passthrough` を追加（非破壊）。
3. `__getattr__` を fail-closed 実装に差し替え（破壊点）。
4. spec delta を検証し、README の限界節に「対応入口の一覧と遮断の理由」を追記。
5. ロールバックは `__getattr__` の旧実装復帰のみで完結する（他の手順は加算的）。

## Open Questions

- 専用例外型を新設するか（`DollyGateError(DogDBError)` 等）、素の `AttributeError` に留めるか。**暫定判断**: `AttributeError` のサブクラスでない独自型は `getattr`/`hasattr` の意味論を壊すため、`AttributeError` を維持しメッセージで誘導する（実装時に確定）。
