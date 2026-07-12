# backend-faithful-surfaces — 設計

## Context

現行の `DBAPIProxy`（`src/dogdb/proxy/connection.py`）は単一クラスに2つの責務が同居している:

1. **介入オーケストレーション**: SQL分類 → decision → アダプタ実行 → 障害適用 → イベント・統計記録（Decision/Fault/Event/House/Stats を束ねる実行パイプライン）
2. **公開表面**: `execute()` が自身を返し、接続自身が単一の結果スロット（`_result`）を持ち、`fetch*`／`description`／`rowcount` を接続レベルで提供し、`__exit__` は無条件に `close()` する

この表面はDuckDBのネイティブ表面（`execute()` が接続自身を返し、接続レベルで fetch する）には忠実だが、sqlite3の表面（`execute()` は新規カーソルを返し、結果状態はカーソルごとに独立、`with` はトランザクション管理であり close しない）とは乖離している。テスト専用障害注入ツールにとって「本番と同じコード経路に障害を流せること」は中核価値であり、SQLite利用者の本番コード（`conn.execute(sql).fetchone()`、カーソル併用、`with conn:` によるトランザクション）がプロキシ上で同型に動かないことは要件不達である。

実測確認済みの前提（統括issue #11・issue #6）:

- sqlite3 ネイティブの `with` はトランザクション管理（commit/rollback）であり close しない
- sqlite3 ネイティブの `description` も `(name, None×6)` 形式 — 現行実装は既に忠実
- duckdb の `cursor()` は接続クローン（独立トランザクション）を返す — ラップは W4-a の別change

## Goals / Non-Goals

**Goals:**

- 共通介入コアを1実装のまま保ち、公開表面のみ SQLiteProxy / DuckDBProxy に分岐する
- SQLite表面を sqlite3 ネイティブと同型にする（execute→新規カーソル、カーソル独立結果状態、with＝トランザクション）
- conformance 契約を「介入コアの一致」へ再定義し、ネイティブ並走テストで表面忠実性を機械検証する

**Non-Goals:**

- row_factory 対応（行は tuple 正規化のまま。ADR-001 に明示的不忠実として記録）
- DuckDB `cursor()` のラップ（W4-a）と DuckDB 表面の追加整理（現行維持）
- `executescript` 等、SQL実行能力集合に宣言済みの未対応入口の開通（fail-closed のまま）
- streaming 介入（MVP design で却下済み・再提案しない）

## Decisions

### D1: 介入エンジンの抽出＋表面クラスの分岐（継承ではなく合成）

現行 `DBAPIProxy` から介入パイプライン（分類・decision・アダプタ実行・障害適用・イベント/統計/house/論理時計）を内部エンジンとして抽出し、`SQLiteProxy` / `DuckDBProxy` はエンジンを合成して表面だけを定義する。`wrap()` は既存の `_adapter_for()` の判別結果でプロキシクラスを選択する。`dolly` 名前空間はエンジンを参照するため両表面で同一実装を共有する。

公開表面を持たないprivate委譲・配管の共有基底はこの決定と両立する（却下したのは表面メソッドの継承である）。

- 代替案A（基底クラス継承で表面を上書き）: 却下。基底の表面メソッドが派生に漏れ、「SQLite表面に存在しないはずの `fetchall`」が残存する。忠実性は表面の**不在**も含む。
- 代替案B（単一クラス＋バックエンド分岐フラグ）: 却下。全メソッドが条件分岐だらけになり、fail-closed 表面の列挙も不明瞭になる。

### D2: SQLiteProxy の表面は sqlite3.Connection と同型、結果状態は接続から排除

`execute()`／`executemany()` は毎回新規の `CursorProxy` を返す（sqlite3 のショートカット意味論 `execute(sql)` ≡ `cursor().execute(sql)` と同型）。`cursor()` は未実行の `CursorProxy` を返す（SQLite表面では fail-closed を解除 — 注入はカーソル経由でエンジンを通るため、W1-a が塞いだ「注入不能なバイパス」ではなくなる）。接続レベルの `fetchall`／`fetchone`／`fetchmany`／`description`／`rowcount` は**提供しない**（sqlite3.Connection に存在しないため。アクセスは fail-closed の誘導付き AttributeError になる）。

- 代替案（互換のため接続レベル fetch* を残す）: 却下。接続が結果スロットを持ち続けることになり、「単一結果スロットの廃止」（懸念Bの根治）と矛盾する。移行は `conn.execute(sql).fetchall()` 連鎖で旧新どちらでも動くため、残す動機が弱い。

### D3: CursorProxy は1クラス、materialize 済み結果＋消費位置を保持

`CursorProxy` は `execute`（エンジン経由で介入・自身を返す）／`fetchall`・`fetchone`・`fetchmany`／`__iter__`／`description`／`rowcount` を備える。結果は従来どおり全行 materialize（決定性＞ストリーミング忠実性）し、カーソルごとに消費位置を持つ。`__iter__` と `fetch*` は同一の消費位置を共有する（sqlite3 と同型）。決定キー・論理時計はエンジン側で操作単位に前進するため、どのカーソルから実行しても決定性は不変。

### D4: `__exit__` の意味論はバックエンド別（SQLite: commit/rollback、DuckDB: close 維持）

`SQLiteProxy.__exit__` は sqlite3 ネイティブと同型に「例外なしなら `commit()`、例外時は `rollback()`、close しない」。`DuckDBProxy.__exit__` は現行の close を維持する（duckdb ネイティブの `with` は接続 close であり、現行が既に忠実）。

### D5: conformance 契約は「介入コアの一致」に縮小、表面は各バックエンドのネイティブとの並走一致で検証

両バックエンド間で一致を要求するのは介入コア（同一seed・同一SQL列に対する障害イベント列・decision・論理結果への適用結果）のみとする。表面挙動の検証対象は「もう一方のバックエンド」ではなく「同一バックエンドのネイティブ接続」に変わる: 同一操作列を素の sqlite3 と SQLiteProxy（全障害確率0）に流し、execute 返り値の独立性・with 意味論・イテレーションの一致を機械検証する。

## ADR-001: 統一表面の廃止とバックエンド忠実アーキテクチャへの移行

### どの前提が失効したか

旧表面（`execute()` が自身を返す単一結果スロット）は、ジョークツールとして「両バックエンドで同じ見た目」を優先し、かつDuckDBには忠実な、決定性駆動の正当な設計だった。テスト専用障害注入ツールへの立ち位置移行により「本番と同じコード経路に障害を流せること」が中核価値となり、**宣言した対応表面内でのバックエンド忠実性**が必須要件に昇格した。旧設計が杜撰だったのではなく、統一表面という前提が失効した。不変条件の優先順位は **決定性 ＞ 宣言表面の忠実性 ＞ 利便性**。

### 何が壊れるか

1. **SQLite表面の `execute()` 返り値**: プロキシ自身 → 毎回新規の `CursorProxy`。返り値を接続として使い回すコード（`c = conn.execute(...); c.commit()` 等）は壊れる。
2. **SQLite表面の接続レベル結果取得**: `conn.fetchall()` 等は `AttributeError`（誘導付き）になる。
3. **SQLite表面の `with` 意味論**: ブロック終了時の無条件 close → commit/rollback（close しない）。close に依存していたコードはリークではなく「開いたまま」になる。
4. **conformance 契約**: 「両バックエンドで表面挙動が一致」という保証は撤回される。

DuckDB表面は無変更（`execute()` が自身を返す・接続レベル fetch・`__exit__`=close は duckdb ネイティブに忠実なため維持）。

### なぜ設計的に妥当か

- 表面の乖離はSQLite利用者のテストを本番と別経路に通し、ツールの存在意義（本番コード経路への障害注入）を損なう。
- カーソル独立の結果状態は、単一結果スロットに起因する既知の懸念（複数 execute の結果踏み潰し）の根治でもある。
- 介入コアは無変更のため、決定性契約（同一seed・同一SQL列→同一イベント列）は両バックエンドで維持される。

### 移行方法

- 最初のタグ付きリリース前であり、破壊的変更ポリシー（openspec/config.yaml）の通常手続き内。外部利用者ゼロ。
- `conn.execute(sql).fetchall()` の連鎖形は旧（self を返す）・新（cursor を返す）どちらでも同じ結果になるため、推奨移行形とする。
- `conn.fetchall()` 形は `conn.execute(sql).fetchall()` へ、close 依存の `with` は明示 `close()`（または `contextlib.closing`）へ書き換える。README・docs/contract-v2.md に新表面契約を記載する。

### 明示的不忠実の記録（row_factory）

sqlite3 ネイティブは `row_factory` により行型をカスタマイズできるが、DogDB は行を tuple に正規化したままとする。障害適用（行の隠蔽・並び替え・値変異）の決定性を行表現に依存させないためであり、優先順位「決定性＞宣言表面の忠実性」の適用例である。対応表面の宣言（ドキュメント）に不忠実点として明記する。

## Risks / Trade-offs

- [SQLite表面の変更で既存テスト・examplesが広範に壊れる] → 既存コードの大半は `execute(...).fetchall()` 連鎖形で新旧互換。接続レベル fetch と `with` 依存箇所のみ書き換え、ネイティブ並走テストで回帰を封じる。
- [`with` の意味論変更により、旧挙動を期待するユーザコードが接続を開いたままにする] → タグ前・外部利用者ゼロ。契約文書に太字で記載。
- [カーソル独立化で結果保持量が増える（複数カーソル同時保持）] → 全行 materialize は従来からの設計で、`max_intervention_rows` の意味論（メモリ上限ではない）も不変。増分はカーソル数に比例するのみで、テスト用途では許容。
- [エンジン抽出のリファクタで介入コアの挙動が変わる回帰リスク] → 既存の determinism・conformance テスト（イベント列一致）を無改変のまま通すことを検証タスクに含める。

## Migration Plan

単一changeで実施（段階導入なし）。実装 → 既存テスト更新 → ネイティブ並走テスト追加 → conformance spec 書き換え → ドキュメント更新の順。ロールバックは change ブランチの破棄で足りる（コア無変更のため他changeへの波及なし）。

## Open Questions

- なし（スコープ・意味論は issue #6 の grilling で確定済み。エンジンクラスの命名・配置は実装者の裁量）。
