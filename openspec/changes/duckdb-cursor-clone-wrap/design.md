# design — duckdb-cursor-clone-wrap

## Context

duckdb の `cursor()` は sqlite3 と異なり、新しい DuckDBPyConnection（クローン）を返す。クローンは同一DBを共有しつつ独自のトランザクション文脈を持つ（実測確認済み: 親の未コミットINSERTがカーソルから見えない）。W2（backend-faithful-surfaces）では `cursor` を `sql_capable_attrs` 経由の誘導付き fail-closed とし、archived proposal に「W4-a まで暫定 fail-closed のまま」と予告している。

現行実装の制約:

- `_InterventionEngine`（proxy/connection.py）が介入コア（DecisionEngine・EventLog・HouseLedger・FaultEngine・StatsTracker・論理時計 `_logical_tick`）と**実行先（`_connection`/`_adapter`）の両方**を所有する。`_EngineBackedSurface.__init__` は常に新規 engine を生成するため、現状のままでは「介入コアだけ共有し実行先だけ差し替える」生成経路がない。
- `Adapter.materialize()`（adapters/base.py）は `description` の第0スロット（列名）のみを抽出し、型情報（第2スロット）を破棄する。`LogicalResult` は列名・行・rowcount しか運ばない。duckdb はネイティブで第2スロットに型を返すため、`DuckDBProxy.description` の `(name, None×6)` 再構成は不忠実。sqlite3 はネイティブでも `(name, None×6)` であり、SQLite側は現状が忠実。

## Goals / Non-Goals

**Goals**

- `DuckDBProxy.cursor()` がネイティブのクローン接続を新しい `DuckDBProxy` で包んで返し、親と介入コアを共有する。
- セッション＝「全カーソル横断の execute 呼び出しの全順序」。occurrence・論理時計・イベント連番はセッション共有、`POLICY_VERSION` 据え置き。
- duckdb `description` の型情報（第2スロット）をアダプタ→`LogicalResult`→表面と透過する。
- 既存挙動の byte-for-byte 維持（イベント・decision・既存テストの期待値は不変。fail-closed 反転による既存テスト1件の置換のみ）。

**Non-Goals**

- relation API（`sql`/`query`/`table`）の注入対応（遅延評価 relation は呼び出し回数≠実行回数のため fail-closed 維持）。
- SQLite 側 `description` の変更。
- クローン間のトランザクション整合の管理・検出（バックエンドの性質として不関知、文書化のみ）。
- マルチスレッド並行実行での決定性保証（従来どおり単一スレッド前提）。
- `description` 第3〜7スロットの透過（ネイティブ duckdb も現状 None を返す。忠実性の範囲は第2スロットまで）。

## Decisions

### D1: 介入コアの共有単位は engine 本体、実行先アダプタは表面ごとに保持する

クローンプロキシは親の `_InterventionEngine` インスタンスをそのまま共有し、SQL の実行先（クローン接続を包むアダプタ）は各表面（プロキシ）が保持して execute 経路で engine に渡す形へ整理する。

- 代替案A（クローンごとに新 engine を生成し、DecisionEngine 等のコアオブジェクトを注入して共有）: `_logical_tick`（論理時計）や今後 engine に置かれる状態が engine ごとに分裂し、「介入コアの共有」（dbapi-proxy spec「接続のラップ」の MUST）が構造的に壊れやすい。却下。
- 代替案B（既存の `_adapter` setter で共有 engine のアダプタを差し替える）: 親子を交互に使う操作列（決定性テストの中心ケース）で実行先が競合する。却下。
- 採用案: engine は介入コアの所有に純化し、実行先は操作ごとに呼び出し表面から受け取る（表面が自身のアダプタを保持）。SQLiteProxy/CursorProxy は従来どおり親のアダプタを渡すだけで挙動不変。

### D2: `cursor()` の返り値は `DuckDBProxy` そのもの（新クラスを作らない）

duckdb ネイティブの `cursor()` は接続と同型の DuckDBPyConnection を返す。忠実性から、クローンプロキシも接続プロキシと同一クラス・同一表面とする。クローンの `cursor()` も再帰的に同じ包み直しを行う（クローンのクローンも同一の介入コアを共有）。

### D3: `LogicalResult` に省略可能な列型情報フィールドを追加する

`column_types`（バックエンドが `description` 第2スロットで返した値の列。返さないバックエンドでは None）を追加する。列名と分離する理由: 既存の障害変換（TANGLED_LEASH の列名入替、FALSE_EMPTY の列名保持）は `columns` を直接操作しており、型は値（位置）に従う別軸のため。core は型情報を不透明な値として扱い、内容に依存しない（backend-adapters spec の core 中立を維持）。

### D4: 型は値の位置に従い、TANGLED_LEASH では移動しない

TANGLED_LEASH は「列名だけが嘘をつく」障害（行値は不変）。型は値を記述するものなので位置に留まり、名前とともに入れ替えない。値と型の対応は真実を保ち、ラベルのみが偽られる — 既存の障害意味論（値変異: ラベル入替、値不変）と整合する。

### D5: 型情報は正規化せずネイティブ値を素通しする

duckdb が第2スロットに返す値（バージョンにより文字列または型オブジェクト）をそのまま保存・露出する。正規化はバージョン依存の写像を DogDB が所有することになり、忠実性にも反する。検証はネイティブ接続との並走比較（同一クエリの `description` 一致）で行い、値の表現形式に依存しないテストにする。

### D6: `DuckDBProxy.description` は `(name, type, None×5)` を返す

`columns`（障害変換後の列名）と `column_types`（位置固定）から再構成する。第3〜7スロットはネイティブ duckdb も None のため None 固定（並走一致で検証可能）。OLD_BONE が過去の `LogicalResult` を返す場合も、型情報は当該結果のものが自然に露出する。

### D7: トランザクション分離は不関知・文書化のみ

クローンの独立トランザクション文脈はバックエンドの性質であり、DogDB は変更・管理・検出しない。contract-v2.md に「クローンのトランザクション分離はネイティブ同型（DogDB 不関知）」を明記する。検証は「素の duckdb と ラップ版で同じ操作列の観察結果が一致する」並走形式で行う。

### D8: クローンの close 意味論はネイティブ同型

クローンプロキシの `close()`／`__exit__` はクローン接続のみを閉じる（DuckDB 表面の既存意味論のまま）。親 close 後のクローン利用の挙動は duckdb ネイティブに委ねる。共有介入コアはクローンの close で影響を受けない（イベントログ・house はセッションの寿命）。

## Risks / Trade-offs

- [engine 純化リファクタが SQLite 経路の挙動を変える] → 全既存テスト（204件）を無変更で通すことを合格条件とし、イベント・decision の byte-for-byte 維持で担保する。
- [duckdb のバージョンで型表現が変わる] → D5 の素通し＋並走比較テストで吸収。DogDB は型表現に関知しない。
- [クローンの操作が親の stats・house・ログに合算される] → 意図どおり（セッション＝全カーソル横断）。契約文書に明記して意図であることを固定する。
- [`cursor()` の fail-closed に依存した利用者コードの挙動変化] → エラーだった入口が機能する方向の加算的変化であり、W2 の proposal で「W4-a まで暫定」と予告済み。既存テスト `test_fail_closed_duckdb_cursor_does_not_reach_native_connection` は共有決定性テストへ置換する。

## Migration Plan

加算的・非破壊（BREAKING なし、ADR 節不要）。デプロイ手順は通常の PR フロー。ロールバックは revert のみで、イベントスキーマ・decision key・`POLICY_VERSION` に変更がないため保存済みログとの互換に影響しない。

## Open Questions

（なし — 実装中に D1 の分離境界で迷った場合は「SQLite 経路のイベント・decision が不変であること」を優先制約とする）
