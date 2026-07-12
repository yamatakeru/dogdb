# backend-faithful-surfaces — バックエンド忠実アーキテクチャとSQLite忠実化

## Why

テスト専用障害注入ツールへの立ち位置移行により、「本番と同じコード経路に障害を流せること」が中核価値となり、宣言した対応表面内でのバックエンド忠実性が必須要件に昇格した。現行の統一表面（`execute()` が自身を返す単一結果スロット）はDuckDBには忠実だが、sqlite3の表面（`execute()` はカーソルを返し、結果状態はカーソルごとに独立、`with` はトランザクション管理）とは乖離しており、SQLite利用者のテストは本番と異なるコード経路を通ってしまう。統一表面という前提が失効したのであり、共通介入コアを共有したままバックエンドごとに表面を分岐する。

## What Changes

- **アーキテクチャ分岐**: 統一表面 `DBAPIProxy` を、共通介入コア（Decision/Fault/Event/House/Stats — 変更なし）＋バックエンド別プロキシ表面（SQLiteProxy / DuckDBProxy）の構造へ再編する。
- **BREAKING — conformance契約の再定義**: 「両バックエンドで表面挙動が一致」を廃し、「介入コア（decision・イベント列・論理結果への障害適用）が一致」へ縮小する。表面はバックエンドごとに分岐してよい。
- **BREAKING — SQLite表面の忠実化**:
  - `execute(sql)` ≡ `cursor().execute(sql)`（sqlite3のショートカット意味論と同型）。`execute()` は自身ではなく毎回新規の CursorProxy を返し、結果状態はカーソルごとに独立する。
  - CursorProxy は `execute`（介入コア経由・自身を返す）／`fetchall`・`fetchone`・`fetchmany`／`__iter__`／`description`／`rowcount` を備える。
  - 接続の `__exit__` を「無条件 close」から sqlite3 ネイティブと同型の「例外なしなら commit・例外時 rollback（close しない）」へ変更する。
- **DuckDB表面**: 現行表面は既にほぼ忠実であり維持する。`cursor()` は W4-a（duckdb-cursor-clone-wrap）まで暫定 fail-closed のまま（W1-a の機構を継続）。
- **ネイティブ並走テスト**: 同一操作列を素の sqlite3 と SQLiteProxy（全障害確率0）に流し、表面挙動（execute 返り値の独立性・with 意味論・イテレーション）の一致を機械検証するテストを追加する。

### Non-Goals

- **row_factory 対応**: 行は tuple に正規化したまま。決定性＞忠実性の優先順位を適用した明示的不忠実として ADR に記録する（機能追加はしない）。
- **description の変更**: sqlite3 ネイティブも `(name, None×6)` であることを実測確認済み。既に忠実であり変更しない。
- **DuckDB `cursor()` のラップ**: W4-a の別changeで扱う。
- **streaming 介入**: 決定性のため MVP design で却下済み（再提案しない）。

## Capabilities

### New Capabilities

（なし）

### Modified Capabilities

- `dbapi-proxy`: 公開表面の契約をバックエンド分岐へ再定義する。SQLite表面（execute がカーソルプロキシを返す・カーソル独立結果状態・with＝トランザクション管理）と DuckDB表面（現行維持）を別々の要件として規定し、「接続自身が単一結果スロットを持つ」統一表面要件を置き換える。
- `backend-adapters`: 共通適合テストスイートの要件を「表面挙動の一致」から「介入コアの一致（同一seed・同一SQL列での障害イベント列・論理結果への適用結果の一致）」へ再定義する。SQLite表面のネイティブ並走一致要件を追加する。

## Impact

- **影響コード**: `src/dogdb/proxy/connection.py`（表面分岐の中心。SQLiteProxy / CursorProxy 新設、DuckDBProxy への改名・整理）、`src/dogdb/__init__.py`（`wrap()` のプロキシ選択）、`src/dogdb/adapters/`（必要に応じた入口整理）、共通コア（`src/dogdb/core/`）は無変更が目標。
- **影響テスト**: conformance系テストの書き換え、ネイティブ並走テストの新設、既存テストの表面依存箇所（`execute(...).fetchall()` 連鎖は sqlite でも動作するが返り値の同一性に依存する箇所）の更新。
- **影響ドキュメント**: `docs/contract-v2.md`・README の表面契約記述、ADR節（design.md）。
- **破壊的変更**: `execute()` の返り値型（自身→CursorProxy、SQLite表面）と `__exit__` の意味論（close→commit/rollback）。最初のタグ付きリリース前であり、破壊的変更ポリシーの範囲内。移行方法は design.md の ADR 節に記す。
- **GitHub連携**: issue #6（本change）、統括 issue #11 のチェックボックス更新。
